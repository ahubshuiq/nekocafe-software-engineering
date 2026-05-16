import sys
from pathlib import Path

# 把 services/reservation/ 加入 sys.path，使 `from src.main import ...` 可用
_reservation_dir = str(Path(__file__).resolve().parent.parent)
if _reservation_dir not in sys.path:
    sys.path.insert(0, _reservation_dir)

import pytest


@pytest.fixture(autouse=True)
def _clean_reservation_db():
    """每次测试前清空 reservation 表，避免数据冲突。"""
    from src.main import SessionLocal, Reservation, redis_client
    db = SessionLocal()
    try:
        db.query(Reservation).delete()
        db.commit()
        # 清理 Redis 缓存
        keys = redis_client.keys("slot:*")
        if keys:
            redis_client.delete(*keys)
    except Exception:
        db.rollback()
    finally:
        db.close()
