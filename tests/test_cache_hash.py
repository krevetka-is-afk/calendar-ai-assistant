from datetime import datetime
from app.core.db import create_hash


def test_create_hash_handles_datetime():
    data = {"when": datetime(2024, 1, 1, 12, 0, 0)}
    h = create_hash(data)
    assert isinstance(h, str) and len(h) == 64
