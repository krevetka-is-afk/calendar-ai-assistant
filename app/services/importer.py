"""
Сервис импорта и нормализации событий
"""
import hashlib
from datetime import datetime, timedelta, date
from typing import List, Optional, Set
from zoneinfo import ZoneInfo

from dateutil import rrule, parser
from icalendar import Calendar

from app.core.config import settings
from app.core.schemas import (
    ImportRequest, ImportResponse, Event, RawEvent
)
from app.core.db import log_layer_result
from app.services.cache import cache_service, PipelineStage


class ImporterService:
    """Сервис для импорта и нормализации событий"""

    def __init__(self):
        self.default_tz = ZoneInfo(settings.default_timezone)

    async def import_events(self, request: ImportRequest, use_cache: bool = True) -> ImportResponse:
        """Импортирует события из ICS или сырого списка с поддержкой кеширования"""
        
        cache_input = {
            "ics_content": request.ics_content,
            "events": [event.model_dump() if hasattr(event, 'model_dump') else event.dict() for event in request.events] if request.events else None,
            "timezone": request.timezone,
            "expand_recurring": request.expand_recurring,
            "horizon_days": request.horizon_days,
            "days_limit": request.days_limit
        }

        async def _compute_import():
            """Внутренняя функция для выполнения импорта"""
            events = []

            tz = ZoneInfo(request.timezone)
            now = datetime.now(tz)
            week_start_date = now.date() - timedelta(days=now.weekday())
            week_start = datetime.combine(week_start_date, datetime.min.time(), tz)

            if request.days_limit is None:
                window_start = datetime.min.replace(tzinfo=tz)
                window_end = datetime.max.replace(tzinfo=tz)
            else:
                window_start = week_start - timedelta(days=request.days_limit)
                window_end = week_start + timedelta(days=7 + request.days_limit)

            if request.ics_content:
                events.extend(self._parse_ics(
                    request.ics_content,
                    request.timezone,
                    request.expand_recurring,
                    window_start,
                    window_end
                ))

            # Импорт из сырых событий
            if request.events:
                for raw_event in request.events:
                    normalized = self._normalize_event(raw_event, request.timezone)
                    if not normalized:
                        continue
                    if raw_event.rrule and request.expand_recurring:
                        recurring_events = self._expand_rrule(
                            raw_event.rrule,
                            normalized.start,
                            normalized.end,
                            window_start,
                            window_end,
                            normalized.summary,
                            normalized.description,
                            normalized.calendar,
                            normalized.attendees,
                            raw_event.all_day or False,
                        )
                        events.extend(recurring_events)
                    else:
                        if window_start <= normalized.start <= window_end:
                            events.append(normalized)

            # Фильтрация по оконному диапазону
            events = [e for e in events if window_start <= e.start <= window_end]

            # Дедупликация
            events = self._deduplicate_events(events)

            # Сортировка по времени начала
            events.sort(key=lambda e: e.start)

            # Статистика
            stats = {
                "total_imported": len(events),
                "recurring_expanded": sum(1 for e in events if hasattr(e, '_from_recurring')),
                "all_day_events": sum(1 for e in events if hasattr(e, '_all_day')),
                "unique_calendars": len(set(e.calendar for e in events))
            }

            response_data = {
                "tz": request.timezone,
                "generated_at": datetime.now(self.default_tz),
                "events": [event.model_dump() if hasattr(event, 'model_dump') else event.dict() for event in events],
                "stats": stats
            }
            
            await log_layer_result("import", response_data)
            return response_data

        if use_cache:
            result_data = await cache_service.get_or_cache(
                PipelineStage.IMPORT,
                cache_input,
                _compute_import,
                max_age_hours=24,  # Кеш на 24 часа
                expires_hours=48   # Время жизни 48 часов
            )
        else:
            result_data = await _compute_import()

        # Преобразуем обратно в объекты
        events = [Event.model_validate(event_data) for event_data in result_data["events"]]
        
        return ImportResponse(
            tz=result_data["tz"],
            generated_at=result_data["generated_at"],
            events=events,
            stats=result_data["stats"]
        )

    def _parse_ics(
            self,
            ics_content: str,
            timezone: str,
            expand_recurring: bool,
            window_start: datetime,
            window_end: datetime
    ) -> List[Event]:
        """Парсит ICS контент"""

        events = []
        tz = ZoneInfo(timezone)

        try:
            cal = Calendar.from_ical(ics_content)
            calendar_name = str(cal.get('X-WR-CALNAME', 'Calendar'))

            for component in cal.walk():
                if component.name == "VEVENT":
                    # Базовая информация
                    summary = str(component.get('SUMMARY', ''))
                    description = str(component.get('DESCRIPTION', ''))

                    # Участники
                    attendees = []
                    for attendee in component.get('ATTENDEE', []):
                        if hasattr(attendee, 'params'):
                            email = attendee.params.get('CN', str(attendee))
                            attendees.append(email.replace('mailto:', ''))

                    dtstart = component.get('DTSTART')
                    dtend = component.get('DTEND')

                    if not dtstart:
                        continue

                    # Проверка all-day события
                    is_all_day = not hasattr(dtstart.dt, 'hour')

                    if is_all_day:
                        # All-day событие
                        if isinstance(dtstart.dt, date):
                            start_dt = datetime.combine(dtstart.dt, datetime.min.time(), tzinfo=tz)
                            if dtend and isinstance(dtend.dt, date):
                                end_dt = datetime.combine(dtend.dt, datetime.min.time(), tzinfo=tz)
                            else:
                                end_dt = start_dt + timedelta(days=1)
                        else:
                            continue
                    else:
                        # Обычное событие с временем
                        start_dt = self._normalize_datetime(dtstart.dt, tz)
                        if dtend:
                            end_dt = self._normalize_datetime(dtend.dt, tz)
                        else:
                            # Если нет конца, считаем событие часовым
                            end_dt = start_dt + timedelta(hours=1)

                    rrule_data = component.get('RRULE')

                    # Фильтрация одиночных событий и мастеров повторений
                    if not rrule_data or not expand_recurring:
                        if not self._intersects(start_dt, end_dt, window_start, window_end):
                            continue

                    if rrule_data and expand_recurring:
                        # Разворачиваем RRULE
                        recurring_events = self._expand_rrule(
                            rrule_data,
                            start_dt,
                            end_dt,
                            window_start,
                            window_end,
                            summary,
                            description,
                            calendar_name,
                            attendees,
                            is_all_day
                        )
                        events.extend(recurring_events)
                    else:
                        # Обычное событие
                        event = Event(
                            calendar=calendar_name,
                            start=start_dt,
                            end=end_dt,
                            summary=summary,
                            description=description,
                            attendees=attendees,
                        )
                        if is_all_day:
                            event._all_day = True
                        if window_start <= event.start <= window_end:
                            events.append(event)

        except Exception as e:
            print(f"Ошибка парсинга ICS: {e}")

        return events

    def _expand_rrule(
            self,
            rrule_data,
            start_dt: datetime,
            end_dt: datetime,
            window_start: datetime,
            window_end: datetime,
            summary: str,
            description: str,
            calendar: str,
            attendees: List[str],
            is_all_day: bool = False
    ) -> List[Event]:
        """Разворачивает повторяющееся событие"""

        events = []
        duration = end_dt - start_dt

        try:
            rule = (
                rrule.rrulestr(rrule_data, dtstart=start_dt)
                if isinstance(rrule_data, str)
                else rrule.rrulestr(rrule_data.to_ical().decode(), dtstart=start_dt)
            )

            occurrences = rule.between(window_start, window_end, inc=False)
            for occurrence in occurrences:
                event = Event(
                    calendar=calendar,
                    start=occurrence,
                    end=occurrence + duration,
                    summary=summary,
                    description=description,
                    attendees=attendees
                )
                event._from_recurring = True
                if is_all_day:
                    event._all_day = True
                events.append(event)

        except Exception as e:
            print(f"Ошибка разворачивания RRULE: {e}")
            # Возвращаем исходное событие только если оно пересекает окно
            if self._intersects(start_dt, end_dt, window_start, window_end):
                event = Event(
                    calendar=calendar,
                    start=start_dt,
                    end=end_dt,
                    summary=summary,
                    description=description,
                    attendees=attendees
                )
                if is_all_day:
                    event._all_day = True
                events.append(event)

        return events

    def _normalize_event(self, raw_event: RawEvent, timezone: str) -> Optional[Event]:
        """Нормализует сырое событие"""

        tz = ZoneInfo(timezone)

        try:
            # Парсим даты
            start_dt = self._parse_datetime_string(raw_event.start, tz)
            end_dt = self._parse_datetime_string(raw_event.end, tz)

            if not start_dt or not end_dt:
                return None

            # Проверка корректности
            if end_dt <= start_dt:
                end_dt = start_dt + timedelta(hours=1)

            event = Event(
                calendar=raw_event.calendar,
                start=start_dt,
                end=end_dt,
                summary=raw_event.summary,
                description=raw_event.description or "",
                attendees=raw_event.attendees
            )
            if raw_event.all_day:
                event._all_day = True
            return event

        except Exception as e:
            print(f"Ошибка нормализации события: {e}")
            return None

    def _parse_datetime_string(self, dt_str: str, default_tz: ZoneInfo) -> Optional[datetime]:
        """Парсит строку даты/времени"""

        if not dt_str:
            return None

        try:
            # Пробуем распарсить с dateutil
            dt = parser.parse(dt_str)

            # Если нет таймзоны, добавляем дефолтную
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=default_tz)

            return dt

        except Exception as e:
            print(f"Ошибка парсинга даты {dt_str}: {e}")
            return None

    def _normalize_datetime(self, dt, default_tz: ZoneInfo) -> datetime:
        """Нормализует datetime объект"""

        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                return dt.replace(tzinfo=default_tz)
            return dt

        # Если это date, конвертируем в datetime
        if isinstance(dt, date):
            return datetime.combine(dt, datetime.min.time(), tzinfo=default_tz)

        return datetime.now(default_tz)

    def _intersects(self, start_dt: datetime, end_dt: datetime,
                    window_start: datetime, window_end: datetime) -> bool:
        """Проверяет пересечение интервалов (конец исключителен)"""
        return end_dt > window_start and start_dt < window_end

    def _deduplicate_events(self, events: List[Event]) -> List[Event]:
        """Удаляет дубликаты событий"""

        seen: Set[str] = set()
        unique_events = []

        for event in events:
            event_hash = self._get_event_hash(event)

            if event_hash not in seen:
                seen.add(event_hash)
                unique_events.append(event)

        return unique_events

    def _get_event_hash(self, event: Event) -> str:
        """Создает хеш события для дедупликации"""

        # Используем ключевые поля для создания уникального идентификатора
        key = f"{event.calendar}|{event.start.isoformat()}|{event.end.isoformat()}|{event.summary}"
        return hashlib.md5(key.encode()).hexdigest()


importer_service = ImporterService()