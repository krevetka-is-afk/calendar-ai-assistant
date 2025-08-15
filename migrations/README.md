# Database Migrations

Этот каталог содержит миграции базы данных для системы кеширования пайплайна.

## Структура миграций

- `001_add_cache_tables.py` - Добавляет таблицы для кеширования результатов пайплайна
- `002_add_background_tasks.py` - Добавляет таблицу для фоновых задач обработки файлов

## Как применить миграции

### Применить миграцию
```bash
cd migrations
python 001_add_cache_tables.py
python 002_add_background_tasks.py
```

### Откатить миграции
```bash
cd migrations
python 002_add_background_tasks.py downgrade
python 001_add_cache_tables.py downgrade
```

## Описание таблиц

### pipeline_cache
Хранит закешированные результаты этапов пайплайна (import, enrich, analyze).

**Поля:**
- `id` - Уникальный идентификатор
- `stage` - Этап пайплайна (import/enrich/analyze)
- `input_hash` - SHA256 хеш входных данных
- `input_data` - Оригинальные входные данные (JSON)
- `result_data` - Закешированный результат (JSON)
- `created_at` - Время создания записи
- `expires_at` - Время истечения кеша (опционально)

**Индексы:**
- `stage` - для быстрого поиска по этапу
- `input_hash` - для поиска по хешу входных данных
- `created_at` - для очистки старых записей
- `expires_at` - для очистки истекших записей

### user_sessions
Связывает пользовательские сессии с хешами кеша для быстрого доступа.

**Поля:**
- `id` - Уникальный идентификатор
- `session_id` - ID сессии пользователя
- `import_hash` - Хеш последнего импорта
- `enrich_hash` - Хеш последнего обогащения
- `analyze_hash` - Хеш последнего анализа
- `created_at` - Время создания сессии
- `last_accessed` - Время последнего доступа

### background_tasks
Хранит фоновые задачи обработки ICS файлов с отслеживанием прогресса.

**Поля:**
- `id` - Уникальный идентификатор
- `task_id` - UUID задачи для API
- `user_session` - ID пользовательской сессии
- `task_type` - Тип задачи (ics_processing)
- `status` - Статус (pending/running/completed/failed/cancelled)
- `input_data` - Параметры задачи (JSON)
- `import_result`, `enrich_result`, `analyze_result` - Результаты этапов (JSON)
- `progress` - Прогресс в процентах (0-100)
- `current_stage` - Текущий этап выполнения
- `error_message` - Сообщение об ошибке
- `created_at`, `started_at`, `completed_at` - Временные метки
- `use_cache`, `use_llm` - Настройки выполнения

**Индексы:**
- `task_id` - для быстрого поиска по UUID
- `user_session` - для фильтрации по пользователю
- `status` - для фильтрации по статусу
- `created_at` - для сортировки и очистки

## Автоматическое создание таблиц

Таблицы также создаются автоматически при инициализации приложения через SQLAlchemy. Миграции предоставляют более детальный контроль и возможность отката изменений.