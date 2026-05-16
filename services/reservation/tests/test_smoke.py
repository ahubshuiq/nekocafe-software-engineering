"""
预约服务冒烟测试 (Smoke Test)
验证服务启动、健康检查、核心 API 端点可达性与基本规则校验
"""

import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta

from src.main import app, validate_reservation, CreateReservationRequest

client = TestClient(app)


# ======================== 冒烟验证 ========================

def test_health_returns_up():
    """冒烟：健康检查返回 200 且 status=UP"""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "UP"
    assert data["service"] == "reservation-service"


def test_create_reservation_smoke():
    """冒烟：创建预约 → 返回 201 且状态为 CONFIRMED"""
    payload = {
        "member_id": 1,
        "store_id": 1,
        "table_id": 1,
        "reservation_date": str(date.today() + timedelta(days=1)),
        "start_time": "10:00",
        "guest_count": 2,
        "cat_preference": "英短",
    }
    resp = client.post("/api/reservations", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "CONFIRMED"
    assert data["guest_count"] == 2
    return data["id"]


def test_get_reservation_smoke():
    """冒烟：创建预约后可查询"""
    payload = {
        "member_id": 2,
        "store_id": 1,
        "table_id": 2,
        "reservation_date": str(date.today() + timedelta(days=1)),
        "start_time": "14:00",
        "guest_count": 2,
    }
    create_resp = client.post("/api/reservations", json=payload)
    assert create_resp.status_code == 201
    rid = create_resp.json()["id"]

    get_resp = client.get(f"/api/reservations/{rid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == rid


def test_cancel_reservation_smoke():
    """冒烟：创建 → 取消 → 状态变为 CANCELLED"""
    payload = {
        "member_id": 3,
        "store_id": 1,
        "table_id": 1,
        "reservation_date": str(date.today() + timedelta(days=1)),
        "start_time": "16:00",
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
    """冒烟：查询可用时段返回列表"""
    resp = client.get(
        "/api/reservations/available",
        params={"store_id": 1, "reservation_date": str(date.today() + timedelta(days=2)), "guest_count": 2},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ======================== 规则校验 ========================

def test_reject_too_far_ahead():
    """规则校验：超出 7 天 → 400"""
    payload = {
        "member_id": 1,
        "store_id": 1,
        "table_id": 1,
        "reservation_date": str(date.today() + timedelta(days=30)),
        "start_time": "14:00",
        "guest_count": 2,
    }
    resp = client.post("/api/reservations", json=payload)
    assert resp.status_code == 400


def test_reject_too_many_guests():
    """规则校验：人数超限 → 400"""
    payload = {
        "member_id": 1,
        "store_id": 1,
        "table_id": 1,
        "reservation_date": str(date.today() + timedelta(days=1)),
        "start_time": "14:00",
        "guest_count": 20,
    }
    resp = client.post("/api/reservations", json=payload)
    assert resp.status_code == 422


def test_reject_past_date():
    """规则校验：过去日期 → 400"""
    payload = {
        "member_id": 1,
        "store_id": 1,
        "table_id": 1,
        "reservation_date": str(date.today() - timedelta(days=1)),
        "start_time": "14:00",
        "guest_count": 2,
    }
    resp = client.post("/api/reservations", json=payload)
    assert resp.status_code == 400


def test_not_found_reservation():
    """查询不存在的预约 → 404"""
    resp = client.get("/api/reservations/99999")
    assert resp.status_code == 404


def test_cancel_not_found():
    """取消不存在的预约 → 404"""
    resp = client.delete("/api/reservations/99999")
    assert resp.status_code == 404


# ======================== 冲突检测 ========================

def test_duplicate_slot_returns_409():
    """时段冲突：同一桌位同一时段预约两次 → 409"""
    base = {
        "member_id": 10,
        "store_id": 1,
        "table_id": 3,
        "reservation_date": str(date.today() + timedelta(days=1)),
        "start_time": "12:00",
        "guest_count": 4,
    }
    resp1 = client.post("/api/reservations", json=base)
    assert resp1.status_code == 201

    base["member_id"] = 11
    resp2 = client.post("/api/reservations", json=base)
    assert resp2.status_code == 409
