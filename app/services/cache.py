"""
Сервис кеширования результатов пайплайна
"""
import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List
from enum import Enum

from app.core.db import create_hash
from app.services.json_storage import json_storage


class PipelineStage(str, Enum):
    """Этапы пайплайна для кеширования"""
    IMPORT = "import"
    ENRICH = "enrich"
    ANALYZE = "analyze"


class CacheService:
    """Сервис для кеширования результатов пайплайна"""

    def __init__(self):
        self.storage = json_storage

    async def get_cached_result(
        self, 
        stage: PipelineStage, 
        input_data: Any,
        max_age_hours: int = 24
    ) -> Optional[Dict[str, Any]]:
        """
        Получает закешированный результат для этапа пайплайна.
        
        Args:
            stage: Этап пайплайна
            input_data: Входные данные для хеширования
            max_age_hours: Максимальный возраст кеша в часах
        
        Returns:
            Закешированный результат или None если не найден/устарел
        """
        input_hash = create_hash(input_data)
        
        def _get_cache():
            entry = self.storage.get_cache_entry(stage.value, input_hash)
            if not entry:
                return None
            
            # Проверяем возраст
            created_at = self.storage._parse_datetime(entry.get('created_at'))
            if created_at:
                cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
                if created_at < cutoff_time:
                    return None
            
            return entry.get('result_data')

        return await asyncio.to_thread(_get_cache)

    async def cache_result(
        self, 
        stage: PipelineStage, 
        input_data: Any, 
        result_data: Any,
        expires_hours: Optional[int] = None
    ) -> bool:
        """
        Кеширует результат этапа пайплайна.
        
        Args:
            stage: Этап пайплайна
            input_data: Входные данные
            result_data: Результат для кеширования
            expires_hours: Время жизни кеша в часах (опционально)
        
        Returns:
            True если успешно закеширован, False при ошибке
        """
        input_hash = create_hash(input_data)
        expires_at = None
        if expires_hours:
            expires_at = datetime.utcnow() + timedelta(hours=expires_hours)

        def _cache():
            return self.storage.save_cache_entry(
                stage.value, 
                input_hash, 
                input_data, 
                result_data, 
                expires_at
            )

        return await asyncio.to_thread(_cache)

    async def get_or_cache(
        self, 
        stage: PipelineStage, 
        input_data: Any, 
        compute_func,
        max_age_hours: int = 24,
        expires_hours: Optional[int] = None
    ) -> Any:
        """
        Получает результат из кеша или вычисляет и кеширует его.
        
        Args:
            stage: Этап пайплайна
            input_data: Входные данные
            compute_func: Функция для вычисления результата (async)
            max_age_hours: Максимальный возраст кеша
            expires_hours: Время жизни нового кеша
        
        Returns:
            Результат (из кеша или вычисленный)
        """
        # Пытаемся получить из кеша
        cached_result = await self.get_cached_result(stage, input_data, max_age_hours)
        if cached_result is not None:
            return cached_result

        # Вычисляем результат
        result = await compute_func()
        
        # Кешируем результат
        await self.cache_result(stage, input_data, result, expires_hours)
        
        return result

    async def invalidate_cache(
        self, 
        stage: Optional[PipelineStage] = None, 
        session_id: Optional[str] = None
    ) -> int:
        """
        Инвалидирует кеш.
        
        Args:
            stage: Конкретный этап или None для всех этапов
            session_id: ID сессии пользователя или None
        
        Returns:
            Количество удаленных записей
        """
        def _invalidate():
            return self.storage.invalidate_cache(
                stage.value if stage else None,
                session_id
            )

        return await asyncio.to_thread(_invalidate)

    async def cleanup_expired_cache(self) -> int:
        """
        Удаляет устаревшие записи кеша.
        
        Returns:
            Количество удаленных записей
        """
        def _cleanup():
            return self.storage.cleanup_expired_cache()

        return await asyncio.to_thread(_cleanup)

    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Получает статистику кеша.
        
        Returns:
            Словарь со статистикой кеша
        """
        def _get_stats():
            return self.storage.get_cache_stats()

        return await asyncio.to_thread(_get_stats)


# Глобальный экземпляр сервиса кеширования
cache_service = CacheService()