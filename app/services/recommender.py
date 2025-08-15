"""
Сервис рекомендации оптимальных временных слотов
"""
from datetime import datetime, timedelta
from typing import List, Tuple
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.schemas import (
    RecommendRequest, RecommendResponse, SlotRecommendation,
    TimeSlot, EnrichedEvent, PriorityType
)
from app.core.db import log_layer_result


class RecommenderService:
    """Сервис для рекомендации временных слотов"""

    def __init__(self):
        self.scoring_weights = settings.scoring_weights
        self.work_day_start = settings.work_day_start
        self.work_day_end = settings.work_day_end
        self.buffer_before = timedelta(minutes=settings.event_buffer_before)
        self.buffer_after = timedelta(minutes=settings.event_buffer_after)

    async def recommend_slot(self, request: RecommendRequest) -> RecommendResponse:
        """Рекомендует оптимальный слот для нового события"""

        tz = ZoneInfo(settings.default_timezone)
        now = datetime.now(tz)

        free_slots = self._generate_free_slots(
            request.enriched_events,
            now,
            request.search_days,
            request.user_query.duration_min
        )

        if not free_slots:
            response = RecommendResponse(
                recommendation=SlotRecommendation(
                    slot=TimeSlot(start=now, end=now),
                    score=0.0,
                    rationale=["Не найдено свободных слотов"]
                ),
                alternatives=[],
                conflicts_found=["Календарь полностью занят"],
                search_stats={"slots_found": 0}
            )
            await log_layer_result("recommend", response.model_dump())
            return response

        scored_slots = []
        for slot in free_slots:
            score, rationale = self._score_slot(
                slot,
                request.user_query,
                request.history_habits,
                request.enriched_events
            )

            scored_slots.append((slot, score, rationale))

        scored_slots.sort(key=lambda x: x[1], reverse=True)

        best_slot, best_score, best_rationale = scored_slots[0]
        recommendation = SlotRecommendation(
            slot=best_slot,
            score=best_score,
            rationale=best_rationale
        )

        alternatives = []
        for slot, score, rationale in scored_slots[1:request.max_alternatives + 1]:
            alternatives.append(SlotRecommendation(
                slot=slot,
                score=score,
                rationale=rationale
            ))

        conflicts = self._check_conflicts(best_slot, request.enriched_events)

        search_stats = {
            "slots_found": len(free_slots),
            "slots_evaluated": len(scored_slots),
            "search_days": request.search_days,
            "duration_requested": request.user_query.duration_min
        }

        response = RecommendResponse(
            recommendation=recommendation,
            alternatives=alternatives,
            conflicts_found=conflicts,
            search_stats=search_stats
        )
        await log_layer_result("recommend", response.model_dump())
        return response

    def _generate_free_slots(
            self,
            events: List[EnrichedEvent],
            start_from: datetime,
            days_ahead: int,
            duration_min: int
    ) -> List[TimeSlot]:
        """Генерирует список свободных слотов"""

        free_slots = []
        duration_td = timedelta(minutes=duration_min)

        busy_intervals = []
        for event in events:
            if event.start >= start_from:
                busy_start = event.start - self.buffer_before
                busy_end = event.end + self.buffer_after
                busy_intervals.append((busy_start, busy_end))

        # Сортируем и объединяем пересекающиеся интервалы
        busy_intervals.sort(key=lambda x: x[0])
        merged_busy = []
        for start, end in busy_intervals:
            if merged_busy and start <= merged_busy[-1][1]:
                merged_busy[-1] = (merged_busy[-1][0], max(merged_busy[-1][1], end))
            else:
                merged_busy.append((start, end))

        for day in range(days_ahead):
            current_date = start_from.date() + timedelta(days=day)

            if day == 0:
                day_start = max(
                    start_from + timedelta(minutes=30),
                    datetime.combine(
                        current_date,
                        datetime.min.time().replace(hour=self.work_day_start),
                        tzinfo=start_from.tzinfo
                    )
                )
            else:
                day_start = datetime.combine(
                    current_date,
                    datetime.min.time().replace(hour=self.work_day_start),
                    tzinfo=start_from.tzinfo
                )

            day_end = datetime.combine(
                current_date,
                datetime.min.time().replace(hour=self.work_day_end),
                tzinfo=start_from.tzinfo
            )

            current_time = day_start

            for busy_start, busy_end in merged_busy:
                if busy_start.date() <= current_date <= busy_end.date():
                    if current_time < busy_start:
                        free_duration = busy_start - current_time
                        if free_duration >= duration_td:
                            slot_end = min(current_time + duration_td, busy_start)
                            free_slots.append(TimeSlot(
                                start=current_time,
                                end=slot_end
                            ))

                    current_time = max(current_time, busy_end)

            if current_time < day_end:
                remaining = day_end - current_time
                if remaining >= duration_td:
                    free_slots.append(TimeSlot(
                        start=current_time,
                        end=current_time + duration_td
                    ))

        return free_slots

    def _score_slot(
            self,
            slot: TimeSlot,
            query,
            history_habits,
            existing_events: List[EnrichedEvent]
    ) -> Tuple[float, List[str]]:
        """Оценивает слот и возвращает score и обоснование"""

        score = 0.0
        rationale = []

        # 1. Соответствие временным предпочтениям
        time_pref_score = 0.0

        if history_habits and query.event_type:
            # Есть данные о привычках
            window = history_habits.default_windows.get(query.event_type)
            if window:
                slot_hour = slot.start.hour + slot.start.minute / 60

                # Парсим временное окно
                window_start_hour = int(window.start.split(':')[0])
                window_start_min = int(window.start.split(':')[1])
                window_end_hour = int(window.end.split(':')[0])
                window_end_min = int(window.end.split(':')[1])

                window_start = window_start_hour + window_start_min / 60
                window_end = window_end_hour + window_end_min / 60

                # Проверяем попадание в окно
                if window_start <= slot_hour <= window_end:
                    time_pref_score = 1.0
                    rationale.append(f"Попадает в предпочитаемое окно {window.start}-{window.end}")
                else:
                    # Чем дальше от окна, тем хуже
                    if slot_hour < window_start:
                        distance = window_start - slot_hour
                    else:
                        distance = slot_hour - window_end

                    time_pref_score = max(0, 1 - distance / 12)  # Нормализуем на 12 часов
                    if time_pref_score < 0.5:
                        rationale.append(f"Вне предпочитаемого окна {window.start}-{window.end}")
        else:
            # Используем общие предпочтения по времени суток
            hour = slot.start.hour
            if query.preferred_time == "morning" and 6 <= hour < 12:
                time_pref_score = 1.0
                rationale.append("Утреннее время как запрошено")
            elif query.preferred_time == "afternoon" and 12 <= hour < 17:
                time_pref_score = 1.0
                rationale.append("Дневное время как запрошено")
            elif query.preferred_time == "evening" and 17 <= hour < 22:
                time_pref_score = 1.0
                rationale.append("Вечернее время как запрошено")
            else:
                time_pref_score = 0.5  # Нейтральный score

        score += time_pref_score * self.scoring_weights["time_preference_match"]

        # 2. Отсутствие конфликтов (уже гарантировано при генерации слотов)
        no_conflicts_score = 1.0
        score += no_conflicts_score * self.scoring_weights["no_conflicts"]
        rationale.append("Нет конфликтов с существующими событиями")

        # 3. В пределах рабочих часов
        working_hours_score = 0.0
        hour = slot.start.hour

        if self.work_day_start <= hour < self.work_day_end:
            working_hours_score = 1.0
            if slot.start.weekday() < 5:  # Будний день
                rationale.append("В рабочие часы буднего дня")
            else:
                rationale.append("В дневное время выходного")
        else:
            working_hours_score = 0.3  # Штраф за нерабочее время
            rationale.append("Вне стандартных рабочих часов")

        score += working_hours_score * self.scoring_weights["within_working_hours"]

        # 4. Близость по времени
        proximity_score = 0.0
        now = datetime.now(slot.start.tzinfo)
        hours_until = (slot.start - now).total_seconds() / 3600

        if query.priority_type == PriorityType.HIGH:
            # Для высокого приоритета - чем раньше, тем лучше
            if hours_until <= 4:
                proximity_score = 1.0
                rationale.append("Ближайшее доступное время (высокий приоритет)")
            elif hours_until <= 24:
                proximity_score = 0.8
                rationale.append("В течение суток")
            elif hours_until <= 48:
                proximity_score = 0.6
                rationale.append("В течение двух дней")
            else:
                proximity_score = max(0, 1 - hours_until / 168)  # Неделя = 168 часов
        else:
            # Для обычного приоритета - оптимальное расстояние 24-72 часа
            if 24 <= hours_until <= 72:
                proximity_score = 1.0
                rationale.append("Оптимальное время планирования")
            elif hours_until < 24:
                proximity_score = 0.7
                rationale.append("Довольно скоро")
            else:
                proximity_score = max(0.3, 1 - (hours_until - 72) / 168)

        score += proximity_score * self.scoring_weights["proximity"]

        # Дополнительные факторы

        # Бонус за утро понедельника для планирования
        if slot.start.weekday() == 0 and slot.start.hour < 10:
            score += 0.05
            rationale.append("Начало недели - хорошо для планирования")

        # Штраф за пятницу вечер
        if slot.start.weekday() == 4 and slot.start.hour >= 16:
            score -= 0.1
            rationale.append("Пятница вечер - не лучшее время")

        # Нормализуем score в диапазон [0, 1]
        score = max(0.0, min(1.0, score))

        return score, rationale

    def _check_conflicts(
            self,
            slot: TimeSlot,
            events: List[EnrichedEvent]
    ) -> List[str]:
        """Проверяет потенциальные конфликты"""

        conflicts = []

        # Проверяем близкие события (в пределах часа)
        for event in events:
            time_before = (slot.start - event.end).total_seconds() / 60
            time_after = (event.start - slot.end).total_seconds() / 60

            if 0 < time_before < 30:
                conflicts.append(
                    f"Всего {int(time_before)} минут после '{event.summary}'"
                )
            elif 0 < time_after < 30:
                conflicts.append(
                    f"Всего {int(time_after)} минут до '{event.summary}'"
                )

        # Проверяем загруженность дня
        slot_date = slot.start.date()
        day_events = [e for e in events if e.start.date() == slot_date]

        if len(day_events) >= 5:
            conflicts.append(f"День уже загружен ({len(day_events)} событий)")

        return conflicts


recommender_service = RecommenderService()