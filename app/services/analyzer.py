"""
Сервис анализа привычек и паттернов пользователя
"""
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import statistics
from zoneinfo import ZoneInfo

from app.core.schemas import (
    AnalyzeRequest, AnalyzeResponse, EnrichedEvent,
    TimeWindow, DashboardAggregates, EventType
)
from app.core.config import settings
from app.core.db import log_layer_result
from app.services.cache import cache_service, PipelineStage


class AnalyzerService:
    """Сервис для анализа привычек пользователя"""

    def __init__(self):
        self.default_windows = settings.default_time_windows
        self.min_sample_size = settings.min_events_for_pattern

    async def analyze_habits(self, request: AnalyzeRequest, use_cache: bool = True) -> AnalyzeResponse:
        """Анализирует привычки и строит профиль пользователя с поддержкой кеширования"""
        
        cache_input = {
            "tz": request.tz,
            "events": [event.model_dump() if hasattr(event, 'model_dump') else event.dict() for event in request.events],
            "analysis_weeks": request.analysis_weeks,
            "min_sample_size": request.min_sample_size
        }

        async def _compute_analyze():
            """Внутренняя функция для выполнения анализа"""
            tz = ZoneInfo(request.tz)
            now = datetime.now(tz)

            cutoff_date = now - timedelta(weeks=request.analysis_weeks)
            relevant_events = [
                e for e in request.events
                if e.start >= cutoff_date
            ]

            default_windows = await self._analyze_time_windows(
                relevant_events,
                request.min_sample_size
            )

            dashboard = await self._calculate_dashboard_aggregates(
                relevant_events,
                now
            )

            patterns = await self._extract_patterns(relevant_events)

            response_data = {
                "tz": request.tz,
                "default_windows": {k.value if hasattr(k, 'value') else str(k): v.model_dump() if hasattr(v, 'model_dump') else v.dict() for k, v in default_windows.items()},
                "dashboard_aggregates": dashboard.model_dump() if hasattr(dashboard, 'model_dump') else dashboard.dict(),
                "patterns": patterns
            }
            
            await log_layer_result("analyze", response_data)
            return response_data

        if use_cache:
            result_data = await cache_service.get_or_cache(
                PipelineStage.ANALYZE,
                cache_input,
                _compute_analyze,
                max_age_hours=12,
                expires_hours=24
            )
        else:
            result_data = await _compute_analyze()

        default_windows = {}
        for k, v in result_data["default_windows"].items():
            event_type = EventType(k) if isinstance(k, str) else k
            default_windows[event_type] = TimeWindow.model_validate(v)
        
        dashboard = DashboardAggregates.model_validate(result_data["dashboard_aggregates"])
        
        return AnalyzeResponse(
            tz=result_data["tz"],
            default_windows=default_windows,
            dashboard_aggregates=dashboard,
            patterns=result_data["patterns"]
        )

    async def _analyze_time_windows(
        self,
        events: List[EnrichedEvent],
        min_sample_size: int
    ) -> Dict[EventType, TimeWindow]:
        """Анализирует временные окна для каждого типа событий"""

        windows = {}

        # Группируем события по типам
        events_by_type = defaultdict(list)
        for event in events:
            events_by_type[event.event_type].append(event)

        # Анализируем каждый тип
        for event_type in EventType:
            type_events = events_by_type.get(event_type, [])

            if len(type_events) >= min_sample_size:
                # Достаточно данных для анализа
                window = self._calculate_time_window(type_events)
                windows[event_type] = window
            else:
                # Используем дефолтные значения
                default = self.default_windows.get(event_type.value, ("09:00", "17:00"))
                windows[event_type] = TimeWindow(
                    start=default[0],
                    end=default[1],
                    confidence=0.0,  # Низкая уверенность, т.к. мало данных
                    sample_size=len(type_events)
                )

        return windows

    def _calculate_time_window(self, events: List[EnrichedEvent]) -> TimeWindow:
        """Вычисляет оптимальное временное окно для списка событий"""

        if not events:
            return TimeWindow(start="09:00", end="17:00", confidence=0.0, sample_size=0)

        # Собираем времена начала и окончания
        start_hours = []
        end_hours = []

        for event in events:
            start_hour = event.start.hour + event.start.minute / 60
            end_hour = event.end.hour + event.end.minute / 60

            start_hours.append(start_hour)
            end_hours.append(end_hour)

        # Используем квантили для устойчивости к выбросам
        # 25-й квантиль для начала (чтобы захватить ранние события)
        # 75-й квантиль для конца (чтобы захватить поздние события)

        if len(start_hours) >= 3:
            # Сортируем для квантилей
            start_hours.sort()
            end_hours.sort()

            # Вычисляем квантили
            q1_idx = len(start_hours) // 4
            q3_idx = 3 * len(end_hours) // 4

            window_start = start_hours[q1_idx]
            window_end = end_hours[q3_idx]

            # Расширяем окно если оно слишком узкое
            if window_end - window_start < 1:  # Меньше часа
                window_end = window_start + 1

        else:
            # Мало данных, используем медиану
            window_start = statistics.median(start_hours)
            window_end = statistics.median(end_hours)

        # Форматируем время
        start_time = f"{int(window_start):02d}:{int((window_start % 1) * 60):02d}"
        end_time = f"{int(window_end):02d}:{int((window_end % 1) * 60):02d}"

        # Вычисляем уверенность на основе разброса данных
        if len(start_hours) >= 3:
            # Стандартное отклонение как мера разброса
            std_start = statistics.stdev(start_hours)
            std_end = statistics.stdev(end_hours)

            # Чем меньше разброс, тем выше уверенность
            # Нормализуем: если STD < 1 час, уверенность высокая
            confidence = max(0.0, min(1.0, 2.0 - (std_start + std_end) / 2))
        else:
            confidence = 0.3  # Низкая уверенность при малой выборке

        return TimeWindow(
            start=start_time,
            end=end_time,
            confidence=confidence,
            sample_size=len(events)
        )

    async def _calculate_dashboard_aggregates(
        self,
        events: List[EnrichedEvent],
        now: datetime
    ) -> DashboardAggregates:
        """Вычисляет агрегаты для дашборда"""

        # Фильтруем события за последнюю неделю
        week_ago = now - timedelta(days=7)
        week_events = [e for e in events if e.start >= week_ago]

        # Базовые метрики
        total_events = len(week_events)

        # Часы по категориям
        hours_by_category = defaultdict(float)
        total_hours = 0
        durations = []

        for event in week_events:
            duration = (event.end - event.start).total_seconds() / 3600
            hours_by_category[event.event_type.value] += duration
            total_hours += duration
            durations.append(duration * 60)  # В минутах для средней длительности

        # Часы встреч (работа с участниками)
        meetings_hours = sum(
            (e.end - e.start).total_seconds() / 3600
            for e in week_events
            if e.event_type == EventType.WORK and len(e.attendees) > 0
        )

        # Часы фокусной работы (работа без участников)
        focus_hours = sum(
            (e.end - e.start).total_seconds() / 3600
            for e in week_events
            if e.event_type == EventType.WORK and len(e.attendees) == 0
        )

        # Самый загруженный день
        events_by_day = defaultdict(int)
        for event in week_events:
            day_key = event.start.date().isoformat()
            events_by_day[day_key] += 1

        busiest_day = None
        if events_by_day:
            busiest = max(events_by_day.items(), key=lambda x: x[1])
            busiest_day = busiest[0]

        # Средняя длительность
        avg_duration = statistics.mean(durations) if durations else 0

        return DashboardAggregates(
            total_events=total_events,
            meetings_hours=round(meetings_hours, 1),
            focus_hours=round(focus_hours, 1),
            by_category=dict(hours_by_category),
            busiest_day=busiest_day,
            average_duration_min=round(avg_duration, 0)
        )

    async def _extract_patterns(self, events: List[EnrichedEvent]) -> Dict:
        """Извлекает дополнительные паттерны из событий"""

        patterns = {
            "most_productive_hours": [],
            "preferred_meeting_days": [],
            "average_day_load": {},
            "recurring_events": [],
            "time_distribution": {}
        }

        if not events:
            return patterns

        # Анализ продуктивных часов (когда больше всего событий)
        hour_counts = defaultdict(int)
        for event in events:
            hour_counts[event.start.hour] += 1

        if hour_counts:
            # Топ-3 продуктивных часа
            top_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            patterns["most_productive_hours"] = [
                {"hour": h, "count": c} for h, c in top_hours
            ]

        # Предпочитаемые дни для встреч
        meeting_days = defaultdict(int)
        for event in events:
            if len(event.attendees) > 0:
                weekday = event.start.strftime("%A")
                meeting_days[weekday] += 1

        if meeting_days:
            top_days = sorted(meeting_days.items(), key=lambda x: x[1], reverse=True)[:2]
            patterns["preferred_meeting_days"] = [d[0] for d in top_days]

        # Средняя загрузка по дням недели
        day_loads = defaultdict(list)
        for event in events:
            weekday = event.start.weekday()
            duration = (event.end - event.start).total_seconds() / 3600
            day_loads[weekday].append(duration)

        for day, loads in day_loads.items():
            day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][day]
            patterns["average_day_load"][day_name] = round(sum(loads) / len(loads), 1)

        # Поиск повторяющихся событий (одинаковое название в разные дни)
        event_names = defaultdict(list)
        for event in events:
            event_names[event.summary].append(event.start)

        for name, dates in event_names.items():
            if len(dates) >= 3:  # Минимум 3 повторения
                patterns["recurring_events"].append({
                    "name": name,
                    "count": len(dates),
                    "frequency": self._detect_frequency(dates)
                })

        # Распределение времени по категориям
        category_hours = defaultdict(float)
        total_hours = 0
        for event in events:
            duration = (event.end - event.start).total_seconds() / 3600
            category_hours[event.event_type.value] += duration
            total_hours += duration

        if total_hours > 0:
            for category, hours in category_hours.items():
                percentage = (hours / total_hours) * 100
                patterns["time_distribution"][category] = round(percentage, 1)

        return patterns

    def _detect_frequency(self, dates: List[datetime]) -> str:
        """Определяет частоту повторения событий"""

        if len(dates) < 2:
            return "разовое"

        # Сортируем даты
        dates.sort()

        # Вычисляем интервалы между событиями
        deltas = []
        for i in range(1, len(dates)):
            delta = (dates[i] - dates[i-1]).days
            deltas.append(delta)

        if not deltas:
            return "разовое"

        # Медианный интервал
        median_delta = statistics.median(deltas)

        # Определяем частоту
        if median_delta <= 1:
            return "ежедневно"
        elif median_delta <= 3:
            return "несколько раз в неделю"
        elif 6 <= median_delta <= 8:
            return "еженедельно"
        elif 13 <= median_delta <= 15:
            return "раз в две недели"
        elif 27 <= median_delta <= 31:
            return "ежемесячно"
        else:
            return f"примерно раз в {int(median_delta)} дней"


analyzer_service = AnalyzerService()