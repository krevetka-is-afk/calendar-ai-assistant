"""
Сервис обогащения событий атрибутами
"""
import json
import re
from typing import List, Optional
from zoneinfo import ZoneInfo

import requests

from app.core.config import settings, EVENT_KEYWORDS, PRIORITY_KEYWORDS
from app.core.schemas import (
    EnrichRequest, EnrichResponse, Event, EnrichedEvent,
    EnrichAttributes, EventType, PriorityType
)
from app.core.db import log_layer_result
from app.services.cache import cache_service, PipelineStage


class EnricherService:
    """Сервис для обогащения событий атрибутами"""

    def __init__(self):
        self.event_keywords = EVENT_KEYWORDS
        self.priority_keywords = PRIORITY_KEYWORDS
        self.default_tz = ZoneInfo(settings.default_timezone)

    async def enrich_events(self, request: EnrichRequest, use_cache: bool = True) -> EnrichResponse:
        """Обогащает события дополнительными атрибутами с поддержкой кеширования"""
        
        cache_input = {
            "tz": request.tz,
            "events": [event.model_dump() if hasattr(event, 'model_dump') else event.dict() for event in request.events],
            "use_llm": request.use_llm
        }

        async def _compute_enrich():
            """Внутренняя функция для выполнения обогащения"""
            enriched_events = []
            stats = {
                "total_events": len(request.events),
                "classified_by_rules": 0,
                "classified_by_llm": 0,
                "classification_failures": 0,
                "event_types": {}
            }

            tz = ZoneInfo(request.tz)

            for event in request.events:
                if request.use_llm and settings.use_llm:
                    event_type, confidence = await self._classify_with_llm(event)
                    if event_type:
                        stats["classified_by_llm"] += 1
                else:
                    event_type, confidence = self._classify_with_rules(event)
                    if event_type != EventType.OTHER:
                        stats["classified_by_rules"] += 1

                if not event_type:
                    event_type = EventType.OTHER
                    confidence = 0.0
                    stats["classification_failures"] += 1

                # Определяем приоритет
                priority_type = self._determine_priority(event)

                # Вычисляем дополнительные атрибуты
                enrich_attrs = self._calculate_attributes(event, tz, confidence)

                enriched_event = EnrichedEvent(
                    calendar=event.calendar,
                    start=event.start,
                    end=event.end,
                    summary=event.summary,
                    description=event.description,
                    attendees=event.attendees,
                    event_type=event_type,
                    priority_type=priority_type,
                    enrich_attrs=enrich_attrs
                )

                enriched_events.append(enriched_event)

                # Обновляем статистику
                stats["event_types"][event_type] = stats["event_types"].get(event_type, 0) + 1

            response_data = {
                "tz": request.tz,
                "events": [event.model_dump() if hasattr(event, 'model_dump') else event.dict() for event in enriched_events],
                "enrichment_stats": stats
            }
            
            await log_layer_result("enrich", response_data)
            return response_data

        if use_cache:
            result_data = await cache_service.get_or_cache(
                PipelineStage.ENRICH,
                cache_input,
                _compute_enrich,
                max_age_hours=24,  # Кеш на 24 часа
                expires_hours=72   # Время жизни 72 часа (дольше чем импорт, так как классификация редко меняется)
            )
        else:
            result_data = await _compute_enrich()

        # Преобразуем обратно в объекты
        enriched_events = [EnrichedEvent.model_validate(event_data) for event_data in result_data["events"]]
        
        return EnrichResponse(
            tz=result_data["tz"],
            events=enriched_events,
            enrichment_stats=result_data["enrichment_stats"]
        )

    def _classify_with_rules(self, event: Event) -> tuple[EventType, float]:
        """Классификация на основе правил и ключевых слов"""

        # Объединяем текст для анализа
        text = f"{event.summary} {event.description}".lower()

        # Счетчики совпадений для каждого типа
        scores = {}

        for event_type, keywords in self.event_keywords.items():
            score = 0
            matched_keywords = []

            for keyword in keywords:
                if keyword.lower() in text:
                    score += 1
                    matched_keywords.append(keyword)

            if score > 0:
                scores[event_type] = (score, matched_keywords)

        # Дополнительные эвристики

        # Время события для уточнения типа
        hour = event.start.hour

        # Утренние события скорее всего спорт или рутины
        if 6 <= hour < 9:
            if "здоровье_и_активность" in scores:
                scores["здоровье_и_активность"] = (
                scores["здоровье_и_активность"][0] + 1, scores["здоровье_и_активность"][1])
            if "личные_рутины_и_уход" in scores:
                scores["личные_рутины_и_уход"] = (
                scores["личные_рутины_и_уход"][0] + 1, scores["личные_рутины_и_уход"][1])

        # Рабочее время - скорее всего работа
        elif 9 <= hour < 18 and event.start.weekday() < 5:
            if "работа" in scores:
                scores["работа"] = (scores["работа"][0] + 1, scores["работа"][1])

        # Вечернее время - учеба, семья, отдых
        elif 18 <= hour < 22:
            for category in ["учёба_и_саморазвитие", "семья_и_отношения", "отдых_и_досуг"]:
                if category in scores:
                    scores[category] = (scores[category][0] + 0.5, scores[category][1])

        # Проверка участников
        if len(event.attendees) > 2:
            # Много участников - скорее всего встреча/работа
            if "работа" in scores:
                scores["работа"] = (scores["работа"][0] + 1, scores["работа"][1])

        # Выбираем тип с максимальным счетом
        if scores:
            best_type = max(scores.items(), key=lambda x: x[1][0])
            event_type_str = best_type[0]
            score = best_type[1][0]
            max_possible_score = len(self.event_keywords[event_type_str]) + 3  # +3 за эвристики
            confidence = min(score / max_possible_score, 1.0)

            # Конвертируем строку в EventType
            for enum_type in EventType:
                if enum_type.value == event_type_str:
                    return enum_type, confidence

        return EventType.OTHER, 0.0

    async def _classify_with_llm(self, event: Event) -> tuple[Optional[EventType], float]:
        """Классификация с помощью LLM"""

        if not settings.use_llm:
            return None, 0.0

        try:
            # Формируем промпт
            event_types_list = ", ".join([t.value for t in EventType])

            prompt = f"""
            Classify this calendar event into one of these types: {event_types_list}

            Event: "{event.summary}"
            Description: "{event.description}"
            Time: {event.start.strftime('%H:%M')} - {event.end.strftime('%H:%M')}
            Day: {event.start.strftime('%A')}
            Attendees: {len(event.attendees)}

            Return JSON:
            {{"type": "event_type", "confidence": 0.0-1.0}}
            """

            # Вызов Ollama
            response = requests.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=settings.ollama_timeout
            )

            if response.status_code == 200:
                result = response.json().get("response", "{}")

                # Обрезаем думающую часть для qwen
                if "</think>" in result:
                    result = result.split("</think>")[1].strip()

                data = json.loads(result)
                event_type_str = data.get("type")
                val = data.get("confidence")
                confidence = 0.5 if val is None else float(val)
                # confidence = float(data.get("confidence", 0.5))

                # Конвертируем в EventType
                for enum_type in EventType:
                    if enum_type.value == event_type_str:
                        return enum_type, confidence

        except Exception as e:
            print(f"LLM classification error: {e}")

        return None, 0.0

    def _determine_priority(self, event: Event) -> PriorityType:
        """Определяет приоритет события"""

        text = f"{event.summary} {event.description}".lower()

        # Проверяем ключевые слова высокого приоритета
        for keyword in self.priority_keywords["high"]:
            if keyword.lower() in text:
                return PriorityType.HIGH

        # Проверяем другие признаки высокого приоритета

        # Много участников может означать важную встречу
        if len(event.attendees) > 5:
            return PriorityType.HIGH

        # События рано утром или поздно вечером могут быть важными
        hour = event.start.hour
        if hour < 8 or hour > 20:
            # Проверяем, не рутина ли это
            if "рутин" not in text and "routine" not in text:
                return PriorityType.HIGH

        return PriorityType.REGULAR

    def _calculate_attributes(
            self,
            event: Event,
            tz: ZoneInfo,
            confidence: float
    ) -> EnrichAttributes:
        """Вычисляет дополнительные атрибуты события"""

        # Длительность в минутах
        duration = event.end - event.start
        duration_min = int(duration.total_seconds() / 60)

        # День недели (1-7, понедельник = 1)
        day_of_week = event.start.weekday() + 1

        # Час дня
        hour_of_day = event.start.hour

        # Рабочие часы (9-18 в будни)
        is_working_hours = (
                9 <= hour_of_day < 18 and
                day_of_week <= 5
        )

        # Выходной день
        is_weekend = day_of_week > 5

        # Извлекаем теги из текста
        tags = self._extract_tags(event)

        return EnrichAttributes(
            duration_min=duration_min,
            day_of_week=day_of_week,
            hour_of_day=hour_of_day,
            is_working_hours=is_working_hours,
            is_weekend=is_weekend,
            tags=tags,
            category_confidence=confidence
        )

    def _extract_tags(self, event: Event) -> List[str]:
        """Извлекает теги из события"""

        tags = []
        text = f"{event.summary} {event.description}".lower()

        # Извлекаем хештеги
        hashtags = re.findall(r'#(\w+)', text)
        tags.extend(hashtags)

        # Добавляем специальные теги
        if len(event.attendees) > 0:
            tags.append("meeting")

        if "online" in text or "zoom" in text or "teams" in text:
            tags.append("online")

        if "deadline" in text or "дедлайн" in text:
            tags.append("deadline")

        # Ограничиваем количество тегов
        return list(set(tags))[:10]


enricher_service = EnricherService()