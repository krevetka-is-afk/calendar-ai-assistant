from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping
from datetime import datetime, date, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo
from uuid import UUID
from decimal import Decimal
from pathlib import Path as _Path

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

def to_json_safe(obj: Any) -> Any:
    try:
        from pydantic import BaseModel  # type: ignore
        if isinstance(obj, BaseModel):
            return to_json_safe(obj.model_dump(mode="json"))
    except Exception:
        pass

    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Mapping):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_json_safe(v) for v in obj]
    return _json_default(obj)

def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = to_json_safe(payload)
    if orjson:
        data = orjson.dumps(safe, option=orjson.OPT_INDENT_2 | orjson.OPT_SERIALIZE_NUMPY)
        path.write_bytes(data)
    else:
        import json
        with path.open("w", encoding="utf-8") as f:
            json.dump(safe, f, ensure_ascii=False, indent=2, default=_json_default)

def load_json(path: Path) -> Any:
    if orjson:
        return orjson.loads(path.read_bytes())
    import json
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
