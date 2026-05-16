"""
Shared test fixtures for all Python test suites.
Provides database cleanup, unique data helpers, and table seeding.
"""
import os
os.environ.setdefault("DATABASE_URL",
                      "postgresql://nekocafe:nekocafe_dev@localhost:5432/nekocafe_reservation")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import time as _time
import uuid
import pytest
from datetime import date, time, timedelta


def _get_main():
    """延迟导入 main 模块，确保环境变量已生效后再创建 redis_client。"""
    from services.reservation.src.main import (
        app, engine, Base, SessionLocal,
        Reservation, DiningTable, TableStatus, redis_client,
    )
    return app, SessionLocal, Reservation, DiningTable, TableStatus, redis_client


@pytest.fixture(autouse=True)
def clean_database():
    """Clear reservation table and Redis cache before each test."""
    _, SessionLocal, Reservation, _, _, redis_client = _get_main()
    db = SessionLocal()
    try:
        db.query(Reservation).delete()
        db.commit()
    finally:
        db.close()
    # Clear Redis slot availability cache
    try:
        keys = redis_client.keys("slot:*")
        if keys:
            redis_client.delete(*keys)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def seed_tables():
    """Ensure dining tables exist for store_id=1."""
    _, SessionLocal, _, DiningTable, TableStatus, _ = _get_main()
    db = SessionLocal()
    try:
        existing = db.query(DiningTable).filter(DiningTable.store_id == 1).count()
        if existing == 0:
            tables = [
                DiningTable(store_id=1, table_number="A1", capacity=4, zone="撸猫区", status=TableStatus.IDLE.value),
                DiningTable(store_id=1, table_number="A2", capacity=2, zone="撸猫区", status=TableStatus.IDLE.value),
                DiningTable(store_id=1, table_number="B1", capacity=6, zone="主题包间", status=TableStatus.IDLE.value),
                DiningTable(store_id=1, table_number="B2", capacity=8, zone="主题包间", status=TableStatus.IDLE.value),
                DiningTable(store_id=1, table_number="C1", capacity=4, zone="窗边区", status=TableStatus.IDLE.value),
            ]
            db.add_all(tables)
            db.commit()
    finally:
        db.close()


def unique_member_id() -> int:
    """Generate a unique member ID based on timestamp + random suffix."""
    return int(_time.time() * 1000000) % 2_000_000_000 + int(uuid.uuid4().int % 10000)


def unique_date(days_ahead: int = 1) -> date:
    """Generate a future date for reservations."""
    return date.today() + timedelta(days=days_ahead)


def unique_time(hour_offset: int = 0) -> str:
    """Generate a time string (HH:00) that avoids conflicts.
    hour_offset cycles through 0-10 to produce times from 10:00 to 20:00.
    """
    hour = 10 + (hour_offset % 11)
    return f"{hour:02d}:00"
