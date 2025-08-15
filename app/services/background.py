"""
Сервис для управления фоновыми задачами обработки файлов
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from app.core.schemas import ImportRequest, EnrichRequest, AnalyzeRequest
from app.services.importer import importer_service
from app.services.enricher import enricher_service
from app.services.analyzer import analyzer_service
from app.services.json_storage import json_storage


class BackgroundTaskService:
    """Сервис для управления фоновыми задачами"""

    def __init__(self):
        self.storage = json_storage
        self._running_tasks = {}  # Словарь активных задач в памяти

    async def create_ics_processing_task(
        self, 
        ics_content: str,
        timezone: str = "Europe/Moscow",
        expand_recurring: bool = True,
        horizon_days: int = 30,
        days_limit: Optional[int] = 14,
        use_cache: bool = True,
        use_llm: bool = True,
        user_session: Optional[str] = None
    ) -> str:
        """
        Создает задачу обработки ICS файла.
        
        Returns:
            task_id: Уникальный идентификатор задачи
        """
        task_id = str(uuid.uuid4())
        
        input_data = {
            "ics_content": ics_content,
            "timezone": timezone,
            "expand_recurring": expand_recurring,
            "horizon_days": horizon_days,
            "days_limit": days_limit,
            "use_cache": use_cache,
            "use_llm": use_llm
        }
        
        task_data = {
            "user_session": user_session,
            "task_type": "ics_processing",
            "status": "pending",
            "input_data": input_data,
            "use_cache": "true" if use_cache else "false",
            "use_llm": "true" if use_llm else "false",
            "progress": 0,
            "current_stage": "pending",
            "results": {
                "import": None,
                "enrich": None,
                "analyze": None
            }
        }
        
        def _create_task():
            return self.storage.create_background_task(task_id, task_data)
        
        await asyncio.to_thread(_create_task)
        
        # Запускаем задачу в фоне
        asyncio.create_task(self._process_ics_task(task_id, input_data))
        
        return task_id

    async def _process_ics_task(self, task_id: str, input_data: Dict[str, Any]):
        """Обрабатывает ICS файл через весь пайплайн"""
        
        try:
            await self._update_task_status(
                task_id, 
                "running", 
                progress=0, 
                current_stage="import",
                started_at=datetime.utcnow()
            )
            
            # Этап 1: Импорт
            import_request = ImportRequest(
                ics_content=input_data["ics_content"],
                timezone=input_data["timezone"],
                expand_recurring=input_data["expand_recurring"],
                horizon_days=input_data["horizon_days"],
                days_limit=input_data["days_limit"]
            )
            
            import_result = await importer_service.import_events(
                import_request, 
                use_cache=input_data["use_cache"]
            )
            
            # Сохраняем результат импорта
            await self._update_task_result(task_id, "import", import_result.model_dump())
            await self._update_task_status(task_id, "running", progress=33, current_stage="enrich")
            
            # Этап 2: Обогащение
            enrich_request = EnrichRequest(
                tz=input_data["timezone"],
                events=import_result.events,
                use_llm=input_data["use_llm"]
            )
            
            enrich_result = await enricher_service.enrich_events(
                enrich_request,
                use_cache=input_data["use_cache"]
            )
            
            # Сохраняем результат обогащения
            await self._update_task_result(task_id, "enrich", enrich_result.model_dump())
            await self._update_task_status(task_id, "running", progress=66, current_stage="analyze")
            
            # Этап 3: Анализ
            analyze_request = AnalyzeRequest(
                tz=input_data["timezone"],
                events=enrich_result.events,
                analysis_weeks=2,
                min_sample_size=3
            )
            
            analyze_result = await analyzer_service.analyze_habits(
                analyze_request,
                use_cache=input_data["use_cache"]
            )
            
            # Сохраняем результат анализа и завершаем
            await self._update_task_result(task_id, "analyze", analyze_result.model_dump())
            await self._update_task_status(
                task_id, 
                "completed", 
                progress=100, 
                current_stage="completed",
                completed_at=datetime.utcnow()
            )
            
        except Exception as e:
            # Обрабатываем ошибку
            await self._update_task_status(
                task_id, 
                "failed", 
                error_message=str(e),
                completed_at=datetime.utcnow()
            )
        
        finally:
            # Удаляем из активных задач
            self._running_tasks.pop(task_id, None)

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Получает статус задачи по ID"""
        
        def _get_task():
            return self.storage.get_background_task(task_id)
        
        return await asyncio.to_thread(_get_task)

    async def list_tasks(
        self, 
        user_session: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Получает список задач с фильтрацией"""
        
        def _list_tasks():
            return self.storage.list_background_tasks(user_session, status, limit)
        
        return await asyncio.to_thread(_list_tasks)

    async def cancel_task(self, task_id: str) -> bool:
        """Отменяет выполнение задачи"""
        
        # Обновляем статус в JSON
        success = await self._update_task_status(
            task_id, 
            "cancelled",
            completed_at=datetime.utcnow()
        )
        
        # Удаляем из активных задач
        self._running_tasks.pop(task_id, None)
        
        return success

    async def cleanup_old_tasks(self, days_old: int = 7) -> int:
        """Удаляет старые завершенные задачи"""
        
        def _cleanup():
            return self.storage.cleanup_old_background_tasks(days_old)
        
        return await asyncio.to_thread(_cleanup)

    async def _update_task_status(
        self, 
        task_id: str, 
        status: str,
        progress: Optional[int] = None,
        current_stage: Optional[str] = None,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None
    ) -> bool:
        """Обновляет статус задачи в JSON"""
        
        def _update():
            updates = {"status": status}
            if progress is not None:
                updates["progress"] = progress
            if current_stage is not None:
                updates["current_stage"] = current_stage
            if error_message is not None:
                updates["error_message"] = error_message
            if started_at is not None:
                updates["started_at"] = started_at.isoformat()
            if completed_at is not None:
                updates["completed_at"] = completed_at.isoformat()
            
            return self.storage.update_background_task(task_id, updates)
        
        return await asyncio.to_thread(_update)

    async def _update_task_result(
        self, 
        task_id: str, 
        stage: str, 
        result_data: Dict[str, Any]
    ) -> bool:
        """Обновляет результат конкретного этапа"""
        
        def _update():
            updates = {f"results.{stage}": result_data}
            
            task = self.storage.get_background_task(task_id)
            if task:
                if "results" not in task:
                    task["results"] = {}
                task["results"][stage] = result_data
                return self.storage.update_background_task(task_id, {"results": task["results"]})
            return False
        
        return await asyncio.to_thread(_update)


# Глобальный экземпляр сервиса фоновых задач
background_service = BackgroundTaskService()