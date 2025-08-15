"""
Конфигурация Smart Calendar API
"""
from pydantic import Field
from typing import Dict, Tuple, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения"""

    app_name: str = "Smart Calendar API"
    app_version: str = "1.0.0"
    api_prefix: str = "/api/v1"
    debug: bool = False

    default_timezone: str = "Europe/Moscow"

    horizon_days: int = 30
    days_limit: Optional[int] = 14

    expand_recurring: bool = True

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout: int = 60
    use_llm: bool = True

    database_url: str = (
        "postgresql+psycopg2://calendar:calendar123@localhost:5432/smart_calendar"
    )

    analysis_weeks_default: int = 2
    min_events_for_pattern: int = 3

    recommendation_days_ahead: int = 7
    max_slot_alternatives: int = 3

    work_day_start: int = 7
    work_day_end: int = 23

    @property
    def default_time_windows(self) -> Dict[str, Tuple[str, str]]:
        return {
            "работа": ("09:00", "18:00"),
            "учёба_и_саморазвитие": ("19:00", "21:00"),
            "здоровье_и_активность": ("07:00", "09:00"),
            "быт_и_личная_администрация": ("10:00", "12:00"),
            "семья_и_отношения": ("18:00", "22:00"),
            "творчество_и_проекты": ("20:00", "22:00"),
            "путешествия_и_дорога": ("08:00", "20:00"),
            "отдых_и_досуг": ("19:00", "23:00"),
            "личные_рутины_и_уход": ("07:00", "08:00"),
            "прочее": ("09:00", "21:00")
        }

    event_buffer_before: int = 10
    event_buffer_after: int = 10

    scoring_weights: Dict[str, float] = {
        "time_preference_match": 0.3,
        "no_conflicts": 0.3,
        "within_working_hours": 0.2,
        "proximity": 0.2
    }

    cors_origins: list = ["*"]
    cors_allow_methods: list = ["*"]
    cors_allow_headers: list = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()

EVENT_KEYWORDS = {
    "работа": [
        "встреча", "митинг", "совещание", "презентация", "отчет",
        "проект", "задача", "дедлайн", "созвон", "планерка",
        "meeting", "call", "standup", "review", "sync"
    ],
    "учёба_и_саморазвитие": [
        "курс", "лекция", "вебинар", "обучение", "тренинг",
        "книга", "чтение", "изучение", "практика", "урок",
        "study", "learning", "course", "lesson", "tutorial"
    ],
    "здоровье_и_активность": [
        "врач", "доктор", "поликлиника", "анализы", "обследование",
        "тренировка", "спорт", "фитнес", "бег", "йога",
        "gym", "workout", "running", "fitness", "doctor"
    ],
    "быт_и_личная_администрация": [
        "банк", "документы", "оплата", "покупки", "магазин",
        "уборка", "ремонт", "стирка", "готовка", "продукты",
        "shopping", "cleaning", "payment", "bills", "grocery"
    ],
    "семья_и_отношения": [
        "семья", "родители", "дети", "жена", "муж",
        "друзья", "встреча", "день рождения", "праздник", "гости",
        "family", "friends", "birthday", "party", "dinner"
    ],
    "творчество_и_проекты": [
        "хобби", "творчество", "рисование", "музыка", "писать",
        "проект", "идея", "создание", "разработка", "дизайн",
        "hobby", "creative", "design", "writing", "art"
    ],
    "путешествия_и_дорога": [
        "поездка", "путешествие", "аэропорт", "вокзал", "поезд",
        "самолет", "дорога", "трансфер", "такси", "командировка",
        "travel", "flight", "trip", "airport", "train"
    ],
    "отдых_и_досуг": [
        "отдых", "кино", "театр", "концерт", "ресторан",
        "кафе", "бар", "клуб", "игра", "развлечение",
        "relax", "movie", "restaurant", "game", "entertainment"
    ],
    "личные_рутины_и_уход": [
        "утренняя рутина", "вечерняя рутина", "медитация", "душ",
        "завтрак", "обед", "ужин", "сон", "уход за собой",
        "morning routine", "evening routine", "meditation", "breakfast"
    ]
}

PRIORITY_KEYWORDS = {
    "high": [
        "срочно", "важно", "критично", "дедлайн", "обязательно",
        "urgent", "important", "critical", "deadline", "must",
        "asap", "emergency", "priority"
    ]
}
