"""
预约服务冒烟测试 (Smoke Test)
验证服务启动、健康检查、核心 API 端点可达性与基本规则校验
"""

import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta
import time

from src.main import app, CreateReservationRequest

client = TestClient(app)

# 辅助函数：生成唯一 ID 和时间
def _unique_member():
    return int(time.time() * 1000) % 1000000

def _unique_start_time(base_hour=10):
    now = time.localtime()
    minute = now.tm_min + now.tm_sec // 60
    hour = (base_hour + minute // 60) % 24
    return f"{hour:02d}:{minute % 60:02d}"


def test_health_returns_up():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "UP"
    assert data["service"] == "reservation-service"


def test_create_reservation_smoke():
    payload = {
        "member_id": _unique_member(),
        "store_id": 1,
        "table_id": 1,
        "reservation_date": str(date.today() + timedelta(days=1)),
        "start_time": _unique_start_time(10),
        "guest_count": 2,
        "cat_preference": "英短",
    }
    resp = client.post("/api/reservations", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] in ("CONFIRMED", "PENDING")
    # 不需要 return


def test_get_reservation_smoke():
    # 先创建
    member_id = _unique_member()
    start_time = _unique_start_time(14)
    create_payload = {
        "member_id": member_id,
        "store_id": 1,
        "table_id": 2,
        "reservation_date": str(date.today() + timedelta(days=1)),
        "start_time": start_time,
        "guest_count": 2,
    }
    create_resp = client.post("/api/reservations", json=create_payload)
    assert create_resp.status_code == 201
    rid = create_resp.json()["id"]

    get_resp = client.get(f"/api/reservations/{rid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == rid


def test_cancel_reservation_smoke():
    payload = {
        "member_id": _unique_member(),
        "store_id": 1,
        "table_id": 1,
        "reservation_date": str(date.today() + timedelta(days=1)),
        "start_time": _unique_start_time(16),
        "guest_count": 2,
    }
    create_resp = client.post("/api/reservations", json=payload)
    assert create_resp.status_code == 201
    rid = create_resp.json()["id"]

    cancel_resp = client.delete(f"/api/reservations/{rid}")
    assert cancel_resp.status_code == 204

    get_resp = client.get(f"/api/reservations/{rid}")
    assert get_resp.json()["status"] == "CANCELLED"


def test_get_available_slots_smoke():
    resp = client.get(
        "/api/reservations/available",
        params={"store_id": 1, "reservation_date": str(date.today() + timedelta(days=2)), "guest_count": 2},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_reject_too_far_ahead():
    payload = {
        "member_id": _unique_member(),
        "store_id": 1,
        "table_id": 1,
        "reservation_date": str(date.today() + timedelta(days=30)),
        "start_time": "14:00",
        "guest_count": 2,
    }
    resp = client.post("/api/reservations", json=payload)
    assert resp.status_code == 400


def test_reject_too_many_guests():
    payload = {
        "member_id": _unique_member(),
        "store_id": 1,
        "table_id": 1,
        "reservation_date": str(date.today() + timedelta(days=1)),
        "start_time": "14:00",
        "guest_count": 20,
    }
    resp = client.post("/api/reservations", json=payload)
    # Pydantic 模型限制最大 8 人 → 422
    assert resp.status_code == 422


def test_reject_past_date():
    payload = {
        "member_id": _unique_member(),
        "store_id": 1,
        "table_id": 1,
        "reservation_date": str(date.today() - timedelta(days=1)),
        "start_time": "14:00",
        "guest_count": 2,
    }
    resp = client.post("/api/reservations", json=payload)
    assert resp.status_code == 400


def test_not_found_reservation():
    resp = client.get("/api/reservations/99999")
    assert resp.status_code == 404


def test_cancel_not_found():
    resp = client.delete("/api/reservations/99999")
    assert resp.status_code == 404


def test_duplicate_slot_returns_409():
    # 使用唯一的 member 和时间，确保第一次创建成功
    member1 = _unique_member()
    member2 = _unique_member()
    store_id = 1
    table_id = 3
    reservation_date = str(date.today() + timedelta(days=1))
    start_time = _unique_start_time(12)

    payload1 = {
        "member_id": member1,
        "store_id": store_id,
        "table_id": table_id,
        "reservation_date": reservation_date,
        "start_time": start_time,
        "guest_count": 4,
    }
    resp1 = client.post("/api/reservations", json=payload1)
    assert resp1.status_code == 201

    payload2 = {
        "member_id": member2,
        "store_id": store_id,
        "table_id": table_id,
        "reservation_date": reservation_date,
        "start_time": start_time,
        "guest_count": 4,
    }
    resp2 = client.post("/api/reservations", json=payload2)
    assert resp2.status_code == 409