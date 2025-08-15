from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping
from datetime import datetime, date, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo
from uuid import UUID
from decimal import Decimal
from pathlib import Path as _Path
import json

try:
    import orjson
except Exception:
    orjson = None


def _json_default(obj: Any):
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return obj.total_seconds()
    if isinstance(obj, (Enum, ZoneInfo, UUID, _Path)):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", errors="ignore")
    if isinstance(obj, set):
        return list(obj)
    try:
        import numpy as np  # type: ignore
        if isinstance(obj, np.integer):   return int(obj)
        if isinstance(obj, np.floating):  return float(obj)
        if isinstance(obj, np.ndarray):   return obj.tolist()
    except Exception:
        pass
    return str(obj)


def _to_json_safe(obj: Any) -> Any:
    # Глубокое приведение: dict/list/tuple/... → JSON-дружелюбно
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Mapping):
        return {str(k): _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_json_safe(v) for v in obj]
    # pydantic v2 BaseModel?
    try:
        from pydantic import BaseModel  # type: ignore
        if isinstance(obj, BaseModel):
            return _to_json_safe(obj.model_dump(mode="json"))
    except Exception:
        pass
    # fallback
    return _json_default(obj)


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = _to_json_safe(payload)
    if orjson:
        data = orjson.dumps(
            safe,
            option=orjson.OPT_INDENT_2 | orjson.OPT_SERIALIZE_NUMPY
        )
        path.write_bytes(data)
    else:
        with path.open("w", encoding="utf-8") as f:
            json.dump(safe, f, ensure_ascii=False, indent=2, default=_json_default)


def _load_json(path: Path) -> Any:
    if orjson:
        return orjson.loads(path.read_bytes())
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# --- совместимость импортов (публичные алиасы) ---
save_json = _save_json
load_json = _load_json
to_json_safe = _to_json_safe
json_default = _json_default


from typing import Optional, Dict
import os, uuid, hashlib
from datetime import datetime, timezone as _tz

USE_CONTENT_CACHE = True  # при желании можно выключать

DATA_ROOT = Path(os.getenv("DATA_ROOT", "data")).resolve()
CACHE_DIR = DATA_ROOT / "cache"
SESSIONS_DIR = DATA_ROOT / "sessions"
for d in (CACHE_DIR, SESSIONS_DIR):
    d.mkdir(parents=True, exist_ok=True)

PIPELINE_VERSION = "2025-08-14"  # ↑ увеличивай при изменении логики пайплайна


def _now_iso() -> str:
    return datetime.now(_tz.utc).isoformat()


def compute_cache_key(ics_content: str, params: Dict[str, Any]) -> str:
    """Ключ = SHA256(версия + хэш ics + нормализованные параметры)."""
    ics_hash = hashlib.sha256(ics_content.encode("utf-8")).hexdigest()
    payload = {
        "v": PIPELINE_VERSION,
        "ics": ics_hash,
        "params": {
            "timezone": params.get("timezone"),
            "expand_recurring": bool(params.get("expand_recurring")),
            "horizon_days": int(params.get("horizon_days") or 0),
            "days_limit": int(params.get("days_limit") or 0),
            "use_llm": bool(params.get("use_llm", False)),
        }
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def cache_paths(cache_key: str) -> Dict[str, Path]:
    base = CACHE_DIR / cache_key
    return {
        "base": base,
        "import": base / "import.json",
        "enrich": base / "enrich.json",
        "analyze": base / "analyze.json",
        "recommend": base / "recommend.json",
        "meta": base / "meta.json",
    }


def set_latest_ready_for_session(session_id: Optional[str], cache_key: str) -> None:
    if not session_id:
        return
    sess_dir = SESSIONS_DIR / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    _save_json(sess_dir / "latest_ready.json", {"cache_key": cache_key, "ready_at": _now_iso()})


def get_latest_ready_cache_key(session_id: Optional[str]) -> Optional[str]:
    if not session_id:
        return None
    p = SESSIONS_DIR / session_id / "latest_ready.json"
    if p.exists():
        try:
            return _load_json(p).get("cache_key")
        except Exception:
            return None
    return None
