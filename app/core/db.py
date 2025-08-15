"""Database utilities for storing layer results and caching pipeline stages."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Any, Optional
from enum import Enum as PyEnum

from sqlalchemy import JSON, Column, DateTime, Integer, String, create_engine, Text, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings
from app.utils.jsonio import to_json_safe

Base = declarative_base()
_engine = None
_SessionLocal = None


class LayerResult(Base):
    """Model for storing layer responses for analytics."""

    __tablename__ = "layer_results"

    id = Column(Integer, primary_key=True, index=True)
    layer = Column(String, index=True, nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PipelineCache(Base):
    """Model for caching pipeline stage results."""

    __tablename__ = "pipeline_cache"

    id = Column(Integer, primary_key=True, index=True)
    stage = Column(String, index=True, nullable=False)
    input_hash = Column(String(64), index=True, nullable=False)
    input_data = Column(JSON, nullable=False)
    result_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    
    def __repr__(self):
        return f"<PipelineCache(stage='{self.stage}', hash='{self.input_hash[:8]}...')>"


class UserSession(Base):
    """Model for storing user session data and associated cache keys."""

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), index=True, nullable=False, unique=True)
    import_hash = Column(String(64), nullable=True, index=True)
    enrich_hash = Column(String(64), nullable=True, index=True)
    analyze_hash = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<UserSession(id='{self.session_id}')>"


class TaskStatus(PyEnum):
    """Статусы фоновых задач"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundTask(Base):
    """Модель для фоновых задач обработки файлов"""

    __tablename__ = "background_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(64), index=True, nullable=False, unique=True)
    user_session = Column(String(64), nullable=True, index=True)
    task_type = Column(String(50), nullable=False, index=True)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING, index=True)
    
    input_data = Column(JSON, nullable=False)
    
    import_result = Column(JSON, nullable=True)
    enrich_result = Column(JSON, nullable=True)
    analyze_result = Column(JSON, nullable=True)
    
    progress = Column(Integer, default=0)
    current_stage = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    use_cache = Column(String(10), default="true")
    use_llm = Column(String(10), default="true")
    
    def __repr__(self):
        return f"<BackgroundTask(id='{self.task_id}', status='{self.status.value}', progress={self.progress}%)>"
    
    def to_dict(self):
        """Преобразует задачу в словарь для API ответов"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress": self.progress,
            "current_stage": self.current_stage,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "results": {
                "import": self.import_result,
                "enrich": self.enrich_result,
                "analyze": self.analyze_result
            }
        }


def init_db() -> None:
    """Initialize database connection and create tables."""
    global _engine, _SessionLocal

    if _engine is not None:
        return

    try:
        _engine = create_engine(settings.database_url, future=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=_engine)
    except Exception as exc:  # pragma: no cover - best effort
        _engine = None
        _SessionLocal = None
        print(f"DB init failed: {exc}")


async def log_layer_result(layer: str, data: Any) -> None:
    """Persist layer result to JSON storage."""
    from app.services.json_storage import json_storage
    
    def _log() -> None:
        try:
            json_storage.log_layer_result(layer, data)
        except Exception as exc:  # pragma: no cover - best effort
            print(f"JSON log failed: {exc}")

    await asyncio.to_thread(_log)


def create_hash(data: Any) -> str:
    """Create SHA256 hash from data for caching."""
    json_str = json.dumps(
        to_json_safe(data),
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(json_str.encode('utf-8')).hexdigest()


def get_session() -> Optional[sessionmaker]:
    """Get database session if available."""
    return _SessionLocal


__all__ = ["init_db", "log_layer_result", "LayerResult", "PipelineCache", "UserSession", "BackgroundTask", "TaskStatus", "Base", "create_hash", "get_session"]
