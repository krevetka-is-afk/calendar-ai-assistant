"""
Migration: Add background tasks table
Created: 2025-01-XX
"""

from sqlalchemy import create_engine, text
from app.core.config import settings

CREATE_BACKGROUND_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS background_tasks (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(64) UNIQUE NOT NULL,
    user_session VARCHAR(64) NULL,
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    
    input_data JSONB NOT NULL,
    
    import_result JSONB NULL,
    enrich_result JSONB NULL,
    analyze_result JSONB NULL,
    
    progress INTEGER DEFAULT 0,
    current_stage VARCHAR(50) NULL,
    error_message TEXT NULL,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    
    use_cache VARCHAR(10) DEFAULT 'true',
    use_llm VARCHAR(10) DEFAULT 'true'
);

CREATE INDEX IF NOT EXISTS idx_background_tasks_task_id ON background_tasks(task_id);
CREATE INDEX IF NOT EXISTS idx_background_tasks_user_session ON background_tasks(user_session);
CREATE INDEX IF NOT EXISTS idx_background_tasks_task_type ON background_tasks(task_type);
CREATE INDEX IF NOT EXISTS idx_background_tasks_status ON background_tasks(status);
CREATE INDEX IF NOT EXISTS idx_background_tasks_created_at ON background_tasks(created_at);

-- Добавляем constraint для статуса
ALTER TABLE background_tasks ADD CONSTRAINT chk_status 
CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled'));

-- Добавляем constraint для прогресса
ALTER TABLE background_tasks ADD CONSTRAINT chk_progress 
CHECK (progress >= 0 AND progress <= 100);
"""

# SQL для отката миграции
DROP_BACKGROUND_TASKS_TABLE = """
DROP TABLE IF EXISTS background_tasks;
"""


def upgrade():
    """Применить миграцию"""
    engine = create_engine(settings.database_url, future=True)
    
    with engine.connect() as conn:
        conn.execute(text(CREATE_BACKGROUND_TASKS_TABLE))
        
        # Коммитим изменения
        conn.commit()
        
    print("✅ Background tasks table created successfully")


def downgrade():
    """Откатить миграцию"""
    engine = create_engine(settings.database_url, future=True)
    
    with engine.connect() as conn:
        # Удаляем таблицу фоновых задач
        conn.execute(text(DROP_BACKGROUND_TASKS_TABLE))
        
        # Коммитим изменения
        conn.commit()
        
    print("✅ Background tasks table dropped successfully")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        print("🔄 Rolling back background tasks migration...")
        downgrade()
    else:
        print("🚀 Applying background tasks migration...")
        upgrade()