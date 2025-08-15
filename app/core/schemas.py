"""
Pydantic схемы для Smart Calendar API
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, validator


class EventType(str, Enum):
    """Типы событий"""
    WORK = "работа"
    STUDY = "учёба_и_саморазвитие"
    HEALTH = "здоровье_и_активность"
    HOUSEHOLD = "быт_и_личная_администрация"
    FAMILY = "семья_и_отношения"
    CREATIVE = "творчество_и_проекты"
    TRAVEL = "путешествия_и_дорога"
    LEISURE = "отдых_и_досуг"
    ROUTINE = "личные_рутины_и_уход"
    OTHER = "прочее"


class PriorityType(str, Enum):
    """Типы приоритетов"""
    REGULAR = "regular"
    HIGH = "high"


class TaskStatusType(str, Enum):
    """Статусы фоновых задач"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"



class RawEvent(BaseModel):
    """Сырое событие для импорта"""
    calendar: str
    start: str
    end: str
    summary: str
    description: Optional[str] = ""
    attendees: List[str] = []
    rrule: Optional[str] = None
    all_day: Optional[bool] = False


class ImportRequest(BaseModel):
    """Запрос на импорт"""
    ics_content: Optional[str] = Field(None, description="ICS файл как строка")
    events: Optional[List[RawEvent]] = Field(None, description="Список сырых событий")
    timezone: str = Field("Europe/Moscow", description="Таймзона по умолчанию")
    expand_recurring: bool = Field(True, description="Развернуть повторяющиеся события")
    horizon_days: int = Field(30, description="Горизонт для разворачивания RRULE")
    days_limit: Optional[int] = Field(
        14,
        description="Кол-во дней до и после текущей недели для импорта. None для полного импорта",
    )

    @validator('ics_content', 'events')
    def validate_input(cls, v, values):
        if not v and not values.get('events') and not values.get('ics_content'):
            raise ValueError("Нужен либо ics_content, либо events")
        return v


class Event(BaseModel):
    """Нормализованное событие"""
    calendar: str
    start: datetime
    end: datetime
    summary: str
    description: str = ""
    attendees: List[str] = []
    event_type: Optional[EventType] = None
    priority_type: Optional[PriorityType] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ImportResponse(BaseModel):
    """Ответ импорта"""
    tz: str
    generated_at: datetime
    events: List[Event]
    stats: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }



class EnrichAttributes(BaseModel):
    """Дополнительные атрибуты события"""
    duration_min: int
    day_of_week: int  # 1-7
    hour_of_day: int  # 0-23
    is_working_hours: bool
    is_weekend: bool
    tags: List[str] = []
    category_confidence: float = Field(ge=0.0, le=1.0)


class EnrichedEvent(Event):
    """Обогащенное событие"""
    event_type: EventType
    priority_type: PriorityType = PriorityType.REGULAR
    enrich_attrs: EnrichAttributes


class EnrichRequest(BaseModel):
    """Запрос на обогащение"""
    tz: str = "Europe/Moscow"
    events: List[Event]
    use_llm: bool = Field(True, description="Использовать LLM для классификации")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class EnrichResponse(BaseModel):
    """Ответ обогащения"""
    tz: str
    events: List[EnrichedEvent]
    enrichment_stats: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }



class TimeWindow(BaseModel):
    """Временное окно для типа события"""
    start: str  # "09:00"
    end: str  # "18:00"
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = 0


class DashboardAggregates(BaseModel):
    """Агрегаты для дашборда"""
    total_events: int = 0
    meetings_hours: float = 0
    focus_hours: float = 0
    by_category: Dict[str, float] = Field(default_factory=dict)
    busiest_day: Optional[str] = None
    average_duration_min: float = 0


class AnalyzeRequest(BaseModel):
    """Запрос на анализ"""
    tz: str = "Europe/Moscow"
    events: List[EnrichedEvent]
    analysis_weeks: int = Field(2, description="Недель для анализа")
    min_sample_size: int = Field(4, description="Минимум событий для паттерна")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AnalyzeResponse(BaseModel):
    """Ответ анализа"""
    tz: str
    default_windows: Dict[EventType, TimeWindow]
    dashboard_aggregates: DashboardAggregates
    patterns: Dict[str, Any] = Field(default_factory=dict)



class UserQuery(BaseModel):
    """Запрос пользователя на планирование"""
    summary: str
    duration_min: int = Field(60, ge=15, le=480)
    event_type: Optional[EventType] = None
    priority_type: PriorityType = PriorityType.REGULAR
    preferred_time: Optional[str] = None  # "morning", "afternoon", "evening"
    constraints: Dict[str, Any] = Field(default_factory=dict)


class TimeSlot(BaseModel):
    """Временной слот"""
    start: datetime
    end: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SlotRecommendation(BaseModel):
    """Рекомендация слота"""
    slot: TimeSlot
    score: float = Field(ge=0.0, le=1.0)
    rationale: List[str] = []


class RecommendRequest(BaseModel):
    """Запрос на рекомендацию"""
    user_query: UserQuery
    enriched_events: List[EnrichedEvent]
    history_habits: Optional[AnalyzeResponse] = None
    search_days: int = Field(7, description="Дней вперед для поиска")
    max_alternatives: int = Field(3, description="Максимум альтернатив")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class RecommendResponse(BaseModel):
    """Ответ с рекомендацией"""
    recommendation: SlotRecommendation
    alternatives: List[SlotRecommendation] = []
    conflicts_found: List[str] = []
    search_stats: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }



class HealthResponse(BaseModel):
    """Health check response"""
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.now)
    version: str = "1.0.0"

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ErrorResponse(BaseModel):
    """Стандартный ответ об ошибке"""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }



class BackgroundTaskCreate(BaseModel):
    """Создание фоновой задачи обработки ICS"""
    timezone: str = Field("Europe/Moscow", description="Таймзона")
    expand_recurring: bool = Field(True, description="Развернуть повторяющиеся события")
    horizon_days: int = Field(30, description="Горизонт расширения RRULE в днях")
    days_limit: Optional[int] = Field(14, description="Лимит дней для фильтрации")
    use_cache: bool = Field(True, description="Использовать кеширование")
    use_llm: bool = Field(True, description="Использовать LLM для классификации")
    user_session: Optional[str] = Field(None, description="ID пользовательской сессии")


class BackgroundTaskResponse(BaseModel):
    """Ответ создания фоновой задачи"""
    task_id: str
    status: TaskStatusType
    message: str = "Task created successfully"

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TaskResults(BaseModel):
    ready: bool
    cache_key: str
    session_id: Optional[str] = None
    counts: Optional[Dict[str, int]] = None
    params: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    analysis: Optional[AnalyzeResponse] = None


class BackgroundTaskStatus(BaseModel):
    """Статус фоновой задачи"""
    task_id: str
    status: TaskStatusType
    progress: int = Field(ge=0, le=100, description="Прогресс в процентах")
    current_stage: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    results: TaskResults = Field(default_factory=TaskResults)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TaskListResponse(BaseModel):
    """Список задач"""
    tasks: List[BackgroundTaskStatus]
    total: int

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
