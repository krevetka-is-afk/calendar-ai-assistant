"""
Сервис для работы с JSON файлами вместо базы данных
"""
import json
import os
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import uuid


class JSONStorageService:
    """Сервис для хранения данных в JSON файлах"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
    
    def _get_cache_file(self, stage: str) -> Path:
        """Получить путь к файлу кеша для этапа"""
        return self.data_dir / f"cache_{stage}.json"
    
    def _get_tasks_file(self) -> Path:
        """Получить путь к файлу фоновых задач"""
        return self.data_dir / "background_tasks.json"
    
    def _get_logs_file(self) -> Path:
        """Получить путь к файлу логов"""
        return self.data_dir / "layer_logs.json"
    
    def _load_json(self, file_path: Path) -> Dict[str, Any]:
        """Загружает JSON файл, возвращает пустой dict если файл не существует"""
        if not file_path.exists():
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    
    def _save_json(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """Сохраняет данные в JSON файл"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=self._json_serializer)
            return True
        except (IOError, TypeError) as e:
            print(f"Ошибка сохранения JSON {file_path}: {e}")
            return False
    
    def _json_serializer(self, obj):
        """Сериализатор для datetime объектов"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """Парсит datetime из строки ISO format"""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None
    
    
    def get_cache_entry(self, stage: str, input_hash: str) -> Optional[Dict[str, Any]]:
        """Получить запись из кеша"""
        cache_file = self._get_cache_file(stage)
        cache_data = self._load_json(cache_file)
        
        entry = cache_data.get(input_hash)
        if not entry:
            return None
        
        # Проверяем срок действия
        expires_at = self._parse_datetime(entry.get('expires_at'))
        if expires_at and datetime.utcnow() > expires_at:
            # Удаляем просроченную запись
            del cache_data[input_hash]
            self._save_json(cache_file, cache_data)
            return None
        
        return entry
    
    def save_cache_entry(self, stage: str, input_hash: str, input_data: Dict[str, Any], 
                        result_data: Dict[str, Any], expires_at: Optional[datetime] = None) -> bool:
        """Сохранить запись в кеш"""
        cache_file = self._get_cache_file(stage)
        cache_data = self._load_json(cache_file)
        
        entry = {
            "input_hash": input_hash,
            "input_data": input_data,
            "result_data": result_data,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None
        }
        
        cache_data[input_hash] = entry
        return self._save_json(cache_file, cache_data)
    
    def invalidate_cache(self, stage: Optional[str] = None, session_id: Optional[str] = None) -> int:
        """Очистить кеш"""
        deleted_count = 0
        
        if stage:
            # Очищаем конкретный этап
            cache_file = self._get_cache_file(stage)
            if cache_file.exists():
                cache_data = self._load_json(cache_file)
                deleted_count = len(cache_data)
                self._save_json(cache_file, {})
        else:
            # Очищаем все этапы
            for stage_name in ["import", "enrich", "analyze"]:
                cache_file = self._get_cache_file(stage_name)
                if cache_file.exists():
                    cache_data = self._load_json(cache_file)
                    deleted_count += len(cache_data)
                    self._save_json(cache_file, {})
        
        return deleted_count
    
    def cleanup_expired_cache(self) -> int:
        """Удалить просроченные записи кеша"""
        deleted_count = 0
        now = datetime.utcnow()
        
        for stage in ["import", "enrich", "analyze"]:
            cache_file = self._get_cache_file(stage)
            cache_data = self._load_json(cache_file)
            
            expired_keys = []
            for key, entry in cache_data.items():
                expires_at = self._parse_datetime(entry.get('expires_at'))
                created_at = self._parse_datetime(entry.get('created_at'))
                
                # Удаляем если просрочено или старше 7 дней
                if (expires_at and now > expires_at) or \
                   (created_at and now > created_at + timedelta(days=7)):
                    expired_keys.append(key)
            
            for key in expired_keys:
                del cache_data[key]
                deleted_count += 1
            
            if expired_keys:
                self._save_json(cache_file, cache_data)
        
        return deleted_count
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Получить статистику кеша"""
        stats = {
            "total_entries": 0,
            "stages": {},
            "total_size_bytes": 0
        }
        
        for stage in ["import", "enrich", "analyze"]:
            cache_file = self._get_cache_file(stage)
            cache_data = self._load_json(cache_file)
            
            stage_stats = {
                "entries": len(cache_data),
                "size_bytes": cache_file.stat().st_size if cache_file.exists() else 0
            }
            
            stats["stages"][stage] = stage_stats
            stats["total_entries"] += stage_stats["entries"]
            stats["total_size_bytes"] += stage_stats["size_bytes"]
        
        return stats
    
    
    def create_background_task(self, task_id: str, task_data: Dict[str, Any]) -> bool:
        """Создать фоновую задачу"""
        tasks_file = self._get_tasks_file()
        tasks_data = self._load_json(tasks_file)
        
        task_data["task_id"] = task_id
        task_data["created_at"] = datetime.utcnow().isoformat()
        
        tasks_data[task_id] = task_data
        return self._save_json(tasks_file, tasks_data)
    
    def get_background_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Получить фоновую задачу"""
        tasks_file = self._get_tasks_file()
        tasks_data = self._load_json(tasks_file)
        return tasks_data.get(task_id)
    
    def update_background_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """Обновить фоновую задачу"""
        tasks_file = self._get_tasks_file()
        tasks_data = self._load_json(tasks_file)
        
        if task_id not in tasks_data:
            return False
        
        tasks_data[task_id].update(updates)
        return self._save_json(tasks_file, tasks_data)
    
    def list_background_tasks(self, user_session: Optional[str] = None, 
                            status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить список фоновых задач"""
        tasks_file = self._get_tasks_file()
        tasks_data = self._load_json(tasks_file)
        
        # Фильтрация
        filtered_tasks = []
        for task in tasks_data.values():
            if user_session and task.get("user_session") != user_session:
                continue
            if status and task.get("status") != status:
                continue
            filtered_tasks.append(task)
        
        # Сортировка по дате создания (новые первые)
        filtered_tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return filtered_tasks[:limit]
    
    def cleanup_old_background_tasks(self, days_old: int = 7) -> int:
        """Удалить старые завершенные задачи"""
        tasks_file = self._get_tasks_file()
        tasks_data = self._load_json(tasks_file)
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        deleted_count = 0
        
        tasks_to_delete = []
        for task_id, task in tasks_data.items():
            created_at = self._parse_datetime(task.get("created_at"))
            status = task.get("status")
            
            if created_at and created_at < cutoff_date and \
               status in ["completed", "failed", "cancelled"]:
                tasks_to_delete.append(task_id)
        
        for task_id in tasks_to_delete:
            del tasks_data[task_id]
            deleted_count += 1
        
        if tasks_to_delete:
            self._save_json(tasks_file, tasks_data)
        
        return deleted_count
    
    
    def log_layer_result(self, layer: str, result_data: Dict[str, Any]) -> bool:
        """Логирование результата этапа"""
        logs_file = self._get_logs_file()
        logs_data = self._load_json(logs_file)
        
        log_id = str(uuid.uuid4())
        
        log_entry = {
            "id": log_id,
            "layer": layer,
            "timestamp": datetime.utcnow().isoformat(),
            "result_data": result_data
        }
        
        # Сохраняем в список (новые записи в начало)
        if "logs" not in logs_data:
            logs_data["logs"] = []
        
        logs_data["logs"].insert(0, log_entry)
        
        # Ограничиваем количество логов (оставляем последние 1000)
        logs_data["logs"] = logs_data["logs"][:1000]
        
        return self._save_json(logs_file, logs_data)
    
    def get_layer_logs(self, layer: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Получить логи этапов"""
        logs_file = self._get_logs_file()
        logs_data = self._load_json(logs_file)
        
        logs = logs_data.get("logs", [])
        
        if layer:
            logs = [log for log in logs if log.get("layer") == layer]
        
        return logs[:limit]


# Глобальный экземпляр
json_storage = JSONStorageService()