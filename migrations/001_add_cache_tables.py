"""
Migration: Add cache tables for pipeline results
Created: 2025-01-XX
"""

from sqlalchemy import create_engine, text
from app.core.config import settings

CREATE_PIPELINE_CACHE_TABLE = """
CREATE TABLE IF NOT EXISTS pipeline_cache (
    id SERIAL PRIMARY KEY,
    stage VARCHAR NOT NULL,
    input_hash VARCHAR(64) NOT NULL,
    input_data JSONB NOT NULL,
    result_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_pipeline_cache_stage ON pipeline_cache(stage);
CREATE INDEX IF NOT EXISTS idx_pipeline_cache_hash ON pipeline_cache(input_hash);
CREATE INDEX IF NOT EXISTS idx_pipeline_cache_created ON pipeline_cache(created_at);
CREATE INDEX IF NOT EXISTS idx_pipeline_cache_expires ON pipeline_cache(expires_at);
"""

CREATE_USER_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS user_sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) UNIQUE NOT NULL,
    import_hash VARCHAR(64) NULL,
    enrich_hash VARCHAR(64) NULL,
    analyze_hash VARCHAR(64) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_session_id ON user_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_import_hash ON user_sessions(import_hash);
CREATE INDEX IF NOT EXISTS idx_user_sessions_enrich_hash ON user_sessions(enrich_hash);
CREATE INDEX IF NOT EXISTS idx_user_sessions_analyze_hash ON user_sessions(analyze_hash);
CREATE INDEX IF NOT EXISTS idx_user_sessions_last_accessed ON user_sessions(last_accessed);
"""

# SQL для отката миграции
DROP_CACHE_TABLES = """
DROP TABLE IF EXISTS user_sessions;
DROP TABLE IF EXISTS pipeline_cache;
"""


def upgrade():
    """Применить миграцию"""
    engine = create_engine(settings.database_url, future=True)
    
    with engine.connect() as conn:
        conn.execute(text(CREATE_PIPELINE_CACHE_TABLE))
        
        conn.execute(text(CREATE_USER_SESSIONS_TABLE))
        
        # Коммитим изменения
        conn.commit()
        
    print("✅ Cache tables created successfully")


def downgrade():
    """Откатить миграцию"""
    engine = create_engine(settings.database_url, future=True)
    
    with engine.connect() as conn:
        # Удаляем таблицы кеша
        conn.execute(text(DROP_CACHE_TABLES))
        
        # Коммитим изменения
        conn.commit()
        
    print("✅ Cache tables dropped successfully")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        print("🔄 Rolling back migration...")
        downgrade()
    else:
        print("🚀 Applying migration...")
        upgrade()