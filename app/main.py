from datetime import datetime, timedelta
import logging
from typing import Optional
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BackgroundTaskCreate,
    BackgroundTaskResponse,
    BackgroundTaskStatus,
    EnrichRequest,
    EnrichResponse,
    ErrorResponse,
    Event,
    EnrichedEvent,
    EventType,
    HealthResponse,
    ImportRequest,
    ImportResponse,
    PriorityType,
    RecommendRequest,
    RecommendResponse,
    TaskListResponse,
    TaskResults,
    TaskStatusType,
    UserQuery,
)
from app.services.analyzer import analyzer_service
from app.services.background import background_service
from app.services.cache import cache_service
from app.services.enricher import enricher_service
from app.services.fs_cache import (
    USE_CONTENT_CACHE,
    cache_paths,
    compute_cache_key,
    get_latest_ready_cache_key,
    set_latest_ready_for_session,
    _now_iso,
)
from app.services.importer import importer_service
from app.services.recommender import recommender_service
from app.utils.jsonio import load_json, save_json, to_json_safe

# Logger
logger = logging.getLogger(__name__)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered calendar management API with habit analysis and smart scheduling",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


# @app.on_event("startup")
# async def startup_event() -> None:
#     """Initialize database on application startup."""
#     init_db()

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/favicon.ico")



@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        version=settings.app_version
    )


@app.get("/")
async def serve_frontend():
    return FileResponse("app/static/index.html")



@app.post(
    f"{settings.api_prefix}/import",
    response_model=ImportResponse,
    summary="Import and normalize events",
    description="Import events from ICS file or raw JSON and normalize them"
)
async def import_events(request: ImportRequest, use_cache: bool = True):
    """
    Импортирует события из ICS или сырого JSON.

    - Нормализует даты в ISO-8601 с таймзонами
    - Разворачивает RRULE (повторяющиеся события)
    - Дедуплицирует события
    - Обрабатывает all-day события
    - Поддерживает кеширование результатов
    """
    try:
        response = await importer_service.import_events(request, use_cache=use_cache)
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    f"{settings.api_prefix}/import/file",
    response_model=ImportResponse,
    summary="Import events from ICS file upload",
    description="Upload an ICS file directly"
)
async def import_events_file(
        file: UploadFile = File(...),
        timezone: str = Form(settings.default_timezone),
        expand_recurring: bool = Form(True),
        horizon_days: int = Form(settings.horizon_days),
        days_limit: Optional[int] = Form(settings.days_limit),
        use_cache: bool = Form(True),
):
    """
    Импортирует события из загруженного ICS файла.
    """
    try:
        contents = await file.read()
        ics_content = contents.decode("utf-8", errors="ignore")

        request = ImportRequest(
            ics_content=ics_content,
            timezone=timezone,
            expand_recurring=expand_recurring,
            horizon_days=horizon_days,
            days_limit=days_limit,
        )

        response = await importer_service.import_events(request, use_cache=use_cache)
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.post(
    f"{settings.api_prefix}/enrich",
    response_model=EnrichResponse,
    summary="Enrich events with attributes",
    description="Classify events and add metadata"
)
async def enrich_events(request: EnrichRequest, use_cache: bool = True):
    """
    Обогащает события дополнительными атрибутами.

    - Классифицирует по типам (работа, учеба, здоровье и т.д.)
    - Определяет приоритет (regular/high)
    - Добавляет метаданные (длительность, день недели, теги)
    - Опционально использует LLM для улучшенной классификации
    - Поддерживает кеширование результатов
    """
    try:
        response = await enricher_service.enrich_events(request, use_cache=use_cache)
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.post(
    f"{settings.api_prefix}/analyze",
    response_model=AnalyzeResponse,
    summary="Analyze user habits",
    description="Build user habit profile and statistics for dashboard metrics"
)
async def analyze_habits(request: AnalyzeRequest, use_cache: bool = True):
    """
    Анализирует привычки пользователя.

    - Определяет временные окна для каждого типа событий
    - Вычисляет метрики для дашборда
    - Находит паттерны и повторяющиеся события
    - Анализирует загруженность и продуктивность
    - Поддерживает кеширование результатов
    """
    try:
        response = await analyzer_service.analyze_habits(request, use_cache=use_cache)
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.post(
    f"{settings.api_prefix}/recommend",
    response_model=RecommendResponse,
    summary="Recommend optimal time slot",
    description="Find the best time slot for a new event"
)
async def recommend_slot(request: RecommendRequest):
    """
    Рекомендует оптимальный временной слот.

    - Генерирует свободные слоты с учетом занятости
    - Оценивает слоты по множеству критериев
    - Учитывает привычки и предпочтения пользователя
    - Предлагает альтернативные варианты
    """
    try:
        response = await recommender_service.recommend_slot(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



# @app.get(
#     f"{settings.api_prefix}/cache/stats",
#     summary="Get cache statistics",
#     description="Get current cache usage statistics"
# )
# async def get_cache_stats():
#     """
#     Получает статистику использования кеша.
#
#     - Общее количество записей в кеше
#     - Статистика по этапам пайплайна
#     - Статистика по возрасту записей
#     """
#     try:
#         stats = await cache_service.get_cache_stats()
#         return stats
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @app.delete(
#     f"{settings.api_prefix}/cache/clear",
#     summary="Clear cache",
#     description="Clear pipeline cache entries"
# )
# async def clear_cache(
#         stage: Optional[str] = None,
#         session_id: Optional[str] = None
# ):
#     """
#     Очищает кеш пайплайна.
#
#     - stage: Очистить конкретный этап ("import", "enrich", "analyze") или все
#     - session_id: Очистить кеш конкретной сессии пользователя
#     """
#     try:
#         from app.services.cache import PipelineStage
#
#         pipeline_stage = None
#         if stage:
#             try:
#                 pipeline_stage = PipelineStage(stage)
#             except ValueError:
#                 raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")
#
#         deleted_count = await cache_service.invalidate_cache(
#             stage=pipeline_stage,
#             session_id=session_id
#         )
#
#         return {
#             "message": "Cache cleared successfully",
#             "deleted_entries": deleted_count
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
#
#
# @app.delete(
#     f"{settings.api_prefix}/cache/cleanup",
#     summary="Cleanup expired cache",
#     description="Remove expired and old cache entries"
# )
# async def cleanup_cache():
#     """
#     Удаляет устаревшие записи кеша.
#
#     - Записи с истекшим expires_at
#     - Записи старше 7 дней
#     """
#     try:
#         deleted_count = await cache_service.cleanup_expired_cache()
#         return {
#             "message": "Expired cache cleaned up successfully",
#             "deleted_entries": deleted_count
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@app.post(
    f"{settings.api_prefix}/flow/import+enrich+analyze",
    response_model=TaskResults,
    summary="Import enrichment and analyze tasks",
    description="Import enrichment and analyze tasks"
)
async def import_enrichment_and_analyze_tasks(
    file: UploadFile = File(...),
    timezone: str = Form(f"{settings.default_timezone}"),
    expand_recurring: bool = Form(settings.expand_recurring),
    horizon_days: int = Form(settings.horizon_days),
    days_limit: Optional[int] = Form(settings.days_limit),
    user_session: Optional[str] = Form(None),
):
    """
    Полный цикл: импорт → обогащение → анализ.
    Результаты в кеш: /data/cache/<cache_key>/{import,enrich,analyze}.json
    """
    try:
        contents = await file.read()
        ics_content = contents.decode("utf-8", errors="ignore")
    except Exception as e:
        _stage_fail("read_file", e)

    params = {
        "timezone": timezone,
        "expand_recurring": expand_recurring,
        "horizon_days": horizon_days,
        "days_limit": days_limit,
        "use_llm": settings.use_llm,
    }

    try:
        cache_key = compute_cache_key(ics_content, params)
        p = cache_paths(cache_key)
        if USE_CONTENT_CACHE:
            save_json(p["meta"], {
                "created_at": _now_iso(),
                "status": "running",
                "params": params,
                "steps": {}
            })
    except Exception as e:
        _stage_fail("compute_cache_key", e)

    try:
        if USE_CONTENT_CACHE and p["analyze"].exists():
            analyze_payload = load_json(p["analyze"])
            set_latest_ready_for_session(user_session, cache_key)
            return TaskResults(
                ready=True,
                cache_key=cache_key,
                session_id=user_session,
                counts={
                    "imported": (len(load_json(p["import"]).get("events", []))
                                 if p["import"].exists() else 0),
                    "enriched": (len(load_json(p["enrich"]).get("events", []))
                                 if p["enrich"].exists() else 0),
                },
                params=params,
                message="Hit from cache",
                analysis=AnalyzeResponse(**analyze_payload),
            )
    except Exception as e:
        _stage_fail("read_cache", e, cache_key)

    try:
        import_response = await importer_service.import_events(ImportRequest(
            ics_content=ics_content,
            timezone=timezone,
            expand_recurring=expand_recurring,
            horizon_days=horizon_days,
            days_limit=days_limit,
        ))
        if USE_CONTENT_CACHE:
            save_json(p["import"], import_response)
            meta = load_json(p["meta"]); meta["steps"]["import"] = {
                "ok": True, "done_at": _now_iso(),
                "count": len(import_response.events)
            }
            save_json(p["meta"], meta)
    except Exception as e:
        try:
            if USE_CONTENT_CACHE:
                meta = load_json(p["meta"])
                meta["steps"]["import"] = {"ok": False, "failed_at": _now_iso(), "error": str(e)}
                meta["status"] = "error"; meta["error_stage"] = "import"; meta["error"] = str(e)
                save_json(p["meta"], meta)
        except Exception:
            pass
        _stage_fail("import", e, cache_key)

    try:
        enrich_response = await enricher_service.enrich_events(EnrichRequest(
            tz=timezone,
            events=import_response.events,
            use_llm=settings.use_llm,
        ))
        if USE_CONTENT_CACHE:
            save_json(p["enrich"], enrich_response)
            meta = load_json(p["meta"])
            meta["steps"]["enrich"] = {
                "ok": True, "done_at": _now_iso(),
                "count": len(enrich_response.events)
            }
            save_json(p["meta"], meta)
    except Exception as e:
        try:
            if USE_CONTENT_CACHE:
                meta = load_json(p["meta"])
                meta["steps"]["enrich"] = {"ok": False, "failed_at": _now_iso(), "error": str(e)}
                meta["status"] = "error"; meta["error_stage"] = "enrich"; meta["error"] = str(e)
                save_json(p["meta"], meta)
        except Exception:
            pass
        _stage_fail("enrich", e, cache_key)

    try:
        analyze_response = await analyzer_service.analyze_habits(AnalyzeRequest(
            tz=timezone,
            events=enrich_response.events,
        ))
        if USE_CONTENT_CACHE:
            save_json(p["analyze"], analyze_response)
            meta = load_json(p["meta"])
            meta["steps"]["analyze"] = {"ok": True, "done_at": _now_iso()}
            meta["status"] = "ready"; meta["ready_at"] = _now_iso()
            meta["counts"] = {
                "imported": len(import_response.events),
                "enriched": len(enrich_response.events),
            }
            save_json(p["meta"], meta)
            set_latest_ready_for_session(user_session, cache_key)
    except Exception as e:
        try:
            if USE_CONTENT_CACHE:
                meta = load_json(p["meta"])
                meta["steps"]["analyze"] = {"ok": False, "failed_at": _now_iso(), "error": str(e)}
                meta["status"] = "error"; meta["error_stage"] = "analyze"; meta["error"] = str(e)
                save_json(p["meta"], meta)
        except Exception:
            pass
        _stage_fail("analyze", e, cache_key)

    return TaskResults(
        ready=True,
        cache_key=cache_key,
        session_id=user_session,
        counts={
            "imported": len(import_response.events),
            "enriched": len(enrich_response.events),
        },
        params=params,
        message="Pipeline computed and cached" if USE_CONTENT_CACHE else "Pipeline computed",
        analysis=analyze_response,
    )



@app.post(
    f"{settings.api_prefix}/flow/user_query+recommendation",
    response_model=RecommendResponse,
    summary="Short query + recommendation",
    description="Finish of pipeline query + recommendation"
)
async def user_query_recommendation(
    summary: str = Form(...),
    duration_min: int = Form(60),
    priority_type: PriorityType = Form(PriorityType.REGULAR),
    cache_key: Optional[str] = Form(None),
    user_session: Optional[str] = Form(None),
):
    try:
        use_key = cache_key or get_latest_ready_cache_key(user_session)
        if not use_key:
            raise ValueError("No cache_key provided and no ready flow for this session. Run /flow/import+enrich+analyze first.")
        p = cache_paths(use_key)
        if not p["enrich"].exists() or not p["analyze"].exists():
            raise FileNotFoundError(f"Cache incomplete for key={use_key}. Re-run pipeline.")
    except Exception as e:
        _stage_fail("resolve_cache_key", e, cache_key)

    try:
        tzinfo = ZoneInfo(settings.default_timezone)
        now = datetime.now(tzinfo)
        mock_event = Event(
            calendar="__user_query__",
            start=now,
            end=now + timedelta(minutes=duration_min),
            summary=summary,
            description="",
            attendees=[]
        )
        if settings.use_llm:
            event_type, _conf = await enricher_service._classify_with_llm(mock_event)
        else:
            event_type, _conf = enricher_service._classify_with_rules(mock_event)
        if not event_type:
            event_type = EventType.OTHER
        user_query = UserQuery(
            summary=summary,
            duration_min=duration_min,
            event_type=event_type,
            priority_type=priority_type
        )
    except Exception as e:
        _stage_fail("classify_user_query", e, use_key)

    try:
        enrich_payload = load_json(p["enrich"])
        analyze_payload = load_json(p["analyze"])
        enriched_events = [EnrichedEvent(**e) for e in enrich_payload.get("events", [])]
        try:
            history_habits = AnalyzeResponse(**analyze_payload)
        except Exception:
            history_habits = analyze_payload
    except Exception as e:
        _stage_fail("read_cache_payloads", e, use_key)

    try:
        recommend_response = await recommender_service.recommend_slot(RecommendRequest(
            user_query=user_query,
            enriched_events=enriched_events,
            history_habits=history_habits
        ))
        if USE_CONTENT_CACHE:
            save_json(p["recommend"], recommend_response)
            try:
                meta = load_json(p["meta"])
                meta_steps = meta.setdefault("steps", {})
                meta_steps["recommend"] = {"ok": True, "done_at": _now_iso()}
                save_json(p["meta"], meta)
            except Exception:
                pass
        return recommend_response
    except Exception as e:
        if USE_CONTENT_CACHE:
            try:
                meta = load_json(p["meta"])
                meta_steps = meta.setdefault("steps", {})
                meta_steps["recommend"] = {
                    "ok": False,
                    "failed_at": _now_iso(),
                    "error": str(e)
                }
                save_json(p["meta"], meta)
            except Exception:
                pass
        _stage_fail("recommend", e, use_key)



@app.get(
    f"{settings.api_prefix}/flow/analytics",
    response_model=AnalyzeResponse,
    summary="Get cached analytics",
    description="Return analytics results for a processed calendar",
)
async def get_cached_analytics(
    cache_key: Optional[str] = None,
    user_session: Optional[str] = None,
):
    """Возвращает результаты анализа, сохранённые в кеше."""
    try:
        use_key = cache_key or get_latest_ready_cache_key(user_session)
        if not use_key:
            raise ValueError(
                "No cache_key provided and no ready flow for this session. Run /flow/import+enrich+analyze first."
            )
        p = cache_paths(use_key)
        if not p["analyze"].exists():
            raise FileNotFoundError(f"Analyze results not found for key={use_key}")
        analyze_payload = load_json(p["analyze"])
        return AnalyzeResponse.model_validate(analyze_payload)
    except Exception as e:
        _stage_fail("get_flow_analytics", e, cache_key)

# @app.post(
#     f"{settings.api_prefix}/tasks/upload",
#     response_model=BackgroundTaskResponse,
#     summary="Upload ICS file for background processing",
#     description="Upload an ICS file and start background processing through import → enrich → analyze pipeline"
# )
# async def upload_ics_background(
#         file: UploadFile = File(...),
#         timezone: str = Form("Europe/Moscow"),
#         expand_recurring: bool = Form(True),
#         horizon_days: int = Form(30),
#         days_limit: Optional[int] = Form(14),
#         use_cache: bool = Form(True),
#         use_llm: bool = Form(True),
#         user_session: Optional[str] = Form(None)
# ):
#     """
#     Загружает ICS файл и запускает фоновую обработку.
#
#     Возвращает task_id для отслеживания прогресса.
#     Обработка включает: импорт → обогащение → анализ привычек.
#     """
#     try:
#         # Проверяем тип файла
#         if not file.filename.lower().endswith('.ics'):
#             raise HTTPException(status_code=400, detail="Only ICS files are supported")
#
#         # Читаем содержимое файла
#         contents = await file.read()
#         ics_content = contents.decode("utf-8", errors="ignore")
#
#         if not ics_content.strip():
#             raise HTTPException(status_code=400, detail="ICS file is empty")
#
#         # Создаем фоновую задачу
#         task_id = await background_service.create_ics_processing_task(
#             ics_content=ics_content,
#             timezone=timezone,
#             expand_recurring=expand_recurring,
#             horizon_days=horizon_days,
#             days_limit=days_limit,
#             use_cache=use_cache,
#             use_llm=use_llm,
#             user_session=user_session
#         )
#
#         return BackgroundTaskResponse(
#             task_id=task_id,
#             status=TaskStatusType.PENDING,
#             message="ICS file uploaded successfully. Processing started in background."
#         )
#
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")
#
#
# @app.get(
#     f"{settings.api_prefix}/tasks/{{task_id}}",
#     response_model=BackgroundTaskStatus,
#     summary="Get task status",
#     description="Get the current status and results of a background task"
# )
# async def get_task_status(task_id: str):
#     """
#     Получает статус фоновой задачи по ID.
#
#     Включает прогресс, текущий этап, результаты и ошибки (если есть).
#     """
#     try:
#         task_status = await background_service.get_task_status(task_id)
#
#         if not task_status:
#             raise HTTPException(status_code=404, detail="Task not found")
#
#         # Преобразуем в Pydantic модель
#         return BackgroundTaskStatus(
#             task_id=task_status["task_id"],
#             status=TaskStatusType(task_status["status"]),
#             progress=task_status["progress"],
#             current_stage=task_status["current_stage"],
#             error_message=task_status["error_message"],
#             created_at=task_status["created_at"],
#             started_at=task_status["started_at"],
#             completed_at=task_status["completed_at"],
#             results={
#                 "import_result": task_status["results"]["import"],
#                 "enrich_result": task_status["results"]["enrich"],
#                 "analyze_result": task_status["results"]["analyze"]
#             }
#         )
#
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
#
#
# @app.get(
#     f"{settings.api_prefix}/tasks",
#     response_model=TaskListResponse,
#     summary="List background tasks",
#     description="Get a list of background tasks with optional filtering"
# )
# async def list_tasks(
#         user_session: Optional[str] = None,
#         status: Optional[TaskStatusType] = None,
#         limit: int = 50
# ):
#     """
#     Получает список фоновых задач с фильтрацией.
#
#     Параметры:
#     - user_session: Фильтр по пользовательской сессии
#     - status: Фильтр по статусу задачи
#     - limit: Максимальное количество задач (по умолчанию 50)
#     """
#     try:
#         from app.core.db import TaskStatus
#
#         # Преобразуем TaskStatusType в TaskStatus если нужно
#         db_status = None
#         if status:
#             db_status = TaskStatus(status.value)
#
#         tasks_data = await background_service.list_tasks(
#             user_session=user_session,
#             status=db_status,
#             limit=limit
#         )
#
#         # Преобразуем в Pydantic модели
#         tasks = []
#         for task_data in tasks_data:
#             tasks.append(BackgroundTaskStatus(
#                 task_id=task_data["task_id"],
#                 status=TaskStatusType(task_data["status"]),
#                 progress=task_data["progress"],
#                 current_stage=task_data["current_stage"],
#                 error_message=task_data["error_message"],
#                 created_at=task_data["created_at"],
#                 started_at=task_data["started_at"],
#                 completed_at=task_data["completed_at"],
#                 results={
#                     "import_result": task_data["results"]["import"],
#                     "enrich_result": task_data["results"]["enrich"],
#                     "analyze_result": task_data["results"]["analyze"]
#                 }
#             ))
#
#         return TaskListResponse(
#             tasks=tasks,
#             total=len(tasks)
#         )
#
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
#
#
# @app.delete(
#     f"{settings.api_prefix}/tasks/{{task_id}}",
#     summary="Cancel task",
#     description="Cancel a running or pending background task"
# )
# async def cancel_task(task_id: str):
#     """
#     Отменяет выполнение фоновой задачи.
#
#     Работает только для задач в статусе PENDING или RUNNING.
#     """
#     try:
#         success = await background_service.cancel_task(task_id)
#
#         if not success:
#             raise HTTPException(status_code=404, detail="Task not found or cannot be cancelled")
#
#         return {"message": "Task cancelled successfully"}
#
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
#
#
# @app.delete(
#     f"{settings.api_prefix}/tasks/cleanup",
#     summary="Cleanup old tasks",
#     description="Remove old completed, failed, or cancelled tasks"
# )
# async def cleanup_old_tasks(days_old: int = 7):
#     """
#     Удаляет старые завершенные задачи.
#
#     По умолчанию удаляет задачи старше 7 дней.
#     """
#     try:
#         deleted_count = await background_service.cleanup_old_tasks(days_old)
#
#         return {
#             "message": f"Old tasks cleaned up successfully",
#             "deleted_tasks": deleted_count,
#             "days_threshold": days_old
#         }
#
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
#


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error="Validation Error",
            detail=str(exc)
        ).dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal Server Error",
            detail=str(exc) if settings.debug else "An error occurred"
        ).dict()
    )

def _stage_fail(stage: str, e: Exception, cache_key: str | None = None):
    logger.exception("Flow stage '%s' failed%s", stage, f" (cache_key={cache_key})" if cache_key else "")
    raise HTTPException(
        status_code=400,
        detail={"stage": stage, "error": str(e), "cache_key": cache_key}
    )


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info"
    )


