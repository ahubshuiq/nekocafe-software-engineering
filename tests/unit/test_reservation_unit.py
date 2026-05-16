"""
单元测试 - 预约服务
所有测试数据动态生成，每次运行可重复通过。
"""
import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta

from services.reservation.src.main import app
from tests.conftest import unique_member_id, unique_date, unique_time

client = TestClient(app)


# ── 辅助函数 ────────────────────────────────────────────────

_counter = 0


def _next_hour() -> str:
    """Return a unique time slot string to avoid conflicts."""
    global _counter
    _counter += 1
    return unique_time(_counter)


def _create_reservation(member_id=None, table_id=1, days_ahead=1,
                        start_time=None, guest_count=2):
    """Helper to create a reservation and return the response."""
    if member_id is None:
        member_id = unique_member_id()
    if start_time is None:
        start_time = _next_hour()
    payload = {
        "member_id": member_id,
        "store_id": 1,
        "table_id": table_id,
        "reservation_date": str(unique_date(days_ahead)),
        "start_time": start_time,
        "guest_count": guest_count,
    }
    return client.post("/api/reservations", json=payload), payload


# ── 测试用例 ────────────────────────────────────────────────

class TestCreateReservation:
    """预约创建相关测试"""

    def test_create_reservation_valid(self):
        """正常创建预约应返回 201"""
        resp, _ = _create_reservation()
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "CONFIRMED"
        assert data["id"] > 0

    def test_create_returns_correct_fields(self):
        """验证响应包含所有必需字段"""
        resp, payload = _create_reservation()
        assert resp.status_code == 201
        data = resp.json()
        for field in ("id", "member_id", "store_id", "table_id",
                      "reservation_date", "start_time", "end_time",
                      "guest_count", "status", "created_at"):
            assert field in data, f"Missing field: {field}"
        assert data["member_id"] == payload["member_id"]
        assert data["table_id"] == payload["table_id"]


class TestGuestCountBoundary:
    """就餐人数边界测试"""

    def test_guest_count_min(self):
        """最少 1 人应成功"""
        resp, _ = _create_reservation(guest_count=1)
        assert resp.status_code == 201

    def test_guest_count_max(self):
        """最多 8 人应成功"""
        resp, _ = _create_reservation(guest_count=8)
        assert resp.status_code == 201

    def test_guest_count_exceed_max(self):
        """超过 8 人应返回 400/422"""
        resp, _ = _create_reservation(guest_count=9)
        assert resp.status_code in (400, 422)

    def test_guest_count_zero(self):
        """0 人应返回 400/422"""
        resp, _ = _create_reservation(guest_count=0)
        assert resp.status_code in (400, 422)


class TestDateValidation:
    """预约日期验证测试"""

    def test_reservation_date_too_far(self):
        """超过 7 天应返回 400/422"""
        resp, _ = _create_reservation(days_ahead=30)
        assert resp.status_code in (400, 422)

    def test_reservation_date_past(self):
        """过去日期应返回 400/422"""
        payload = {
            "member_id": unique_member_id(),
            "store_id": 1,
            "table_id": 1,
            "reservation_date": str(date.today() - timedelta(days=1)),
            "start_time": "18:00",
            "guest_count": 2,
        }
        resp = client.post("/api/reservations", json=payload)
        assert resp.status_code in (400, 422)

    def test_reservation_date_today(self):
        """今天应成功"""
        resp, _ = _create_reservation(days_ahead=0)
        assert resp.status_code == 201

    def test_reservation_date_max_advance(self):
        """正好 7 天应成功"""
        resp, _ = _create_reservation(days_ahead=7)
        assert resp.status_code == 201


class TestCancelReservation:
    """取消预约测试"""

    def test_cancel_reservation(self):
        """创建后取消应返回 204"""
        resp, _ = _create_reservation(days_ahead=2, table_id=2, start_time="19:00")
        assert resp.status_code == 201
        rid = resp.json()["id"]
        cancel = client.delete(f"/api/reservations/{rid}")
        assert cancel.status_code == 204

    def test_cancel_nonexistent(self):
        """取消不存在的预约应返回 404"""
        resp = client.delete("/api/reservations/999999")
        assert resp.status_code == 404

    def test_double_cancel(self):
        """重复取消应返回 400"""
        resp, _ = _create_reservation(days_ahead=3)
        assert resp.status_code == 201
        rid = resp.json()["id"]
        client.delete(f"/api/reservations/{rid}")
        second = client.delete(f"/api/reservations/{rid}")
        assert second.status_code == 400


class TestGetReservation:
    """查询预约测试"""

    def test_get_reservation(self):
        """查询已创建的预约"""
        resp, _ = _create_reservation()
        assert resp.status_code == 201
        rid = resp.json()["id"]
        get_resp = client.get(f"/api/reservations/{rid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == rid

    def test_get_nonexistent_reservation(self):
        """查询不存在的预约应返回 404"""
        resp = client.get("/api/reservations/999999")
        assert resp.status_code == 404


class TestSlotConflict:
    """时段冲突测试"""

    def test_same_slot_conflict(self):
        """同一桌位同一时段的第二次预约应返回 409"""
        date_str = str(unique_date(4))
        p1 = {
            "member_id": unique_member_id(),
            "store_id": 1, "table_id": 1,
            "reservation_date": date_str,
            "start_time": "14:00", "guest_count": 2,
        }
        r1 = client.post("/api/reservations", json=p1)
        assert r1.status_code == 201

        p2 = {**p1, "member_id": unique_member_id()}
        r2 = client.post("/api/reservations", json=p2)
        assert r2.status_code == 409

    def test_different_table_same_time_ok(self):
        """不同桌位同一时段应都成功"""
        date_str = str(unique_date(5))
        p1 = {
            "member_id": unique_member_id(),
            "store_id": 1, "table_id": 1,
            "reservation_date": date_str,
            "start_time": "15:00", "guest_count": 2,
        }
        p2 = {**p1, "member_id": unique_member_id(), "table_id": 2}
        r1 = client.post("/api/reservations", json=p1)
        r2 = client.post("/api/reservations", json=p2)
        assert r1.status_code == 201
        assert r2.status_code == 201


# ── 变异体杀灭测试 ──────────────────────────────────────────

class TestIsGuestCountValid:
    """直接测试 is_guest_count_valid 纯函数，杀灭 L435 变异体"""

    def test_min_boundary(self):
        """1 人是合法下界"""
        from services.reservation.src.main import is_guest_count_valid
        assert is_guest_count_valid(1) is True

    def test_below_min(self):
        """0 人不合法"""
        from services.reservation.src.main import is_guest_count_valid
        assert is_guest_count_valid(0) is False

    def test_max_boundary(self):
        """8 人是合法上界"""
        from services.reservation.src.main import is_guest_count_valid
        assert is_guest_count_valid(8) is True

    def test_above_max(self):
        """9 人不合法"""
        from services.reservation.src.main import is_guest_count_valid
        assert is_guest_count_valid(9) is False


class TestCheckSlotAvailableCache:
    """测试 check_slot_available 的 Redis 缓存路径，杀灭 L197/L208 变异体"""

    def test_cache_miss_queries_db(self):
        """缓存未命中时应查询数据库并设置缓存"""
        from services.reservation.src.main import check_slot_available, redis_client
        from datetime import time as t
        db = SessionLocal()
        try:
            # 清除缓存
            keys = redis_client.keys("slot:*")
            if keys:
                redis_client.delete(*keys)

            date_val = unique_date(6)
            result = check_slot_available(db, 1, date_val, t(14, 0), t(15, 30))
            assert result is True

            # 验证缓存被设置（杀灭 L208 的 300→299/301 变异体）
            cache_key = f"slot:1:{date_val}:14:00:00"
            cached = redis_client.get(cache_key)
            assert cached == "1"
        finally:
            db.close()

    def test_cache_hit_returns_correctly(self):
        """缓存命中时应直接返回缓存值，杀灭 L197 的 == → != 变异体"""
        from services.reservation.src.main import check_slot_available, redis_client
        from datetime import time as t
        db = SessionLocal()
        try:
            date_val = unique_date(7)
            cache_key = f"slot:1:{date_val}:16:00:00"

            # 设置缓存为 "1"（可用）
            redis_client.setex(cache_key, 300, "1")
            assert check_slot_available(db, 1, date_val, t(16, 0), t(17, 30)) is True

            # 设置缓存为 "0"（不可用）
            redis_client.setex(cache_key, 300, "0")
            assert check_slot_available(db, 1, date_val, t(16, 0), t(17, 30)) is False
        finally:
            db.close()


class TestAvailableSlotsTimeRange:
    """测试 get_available_slots 的时段范围，杀灭 L312-314 变异体"""

    def test_slots_start_at_10(self):
        """最早时段应从 10:00 开始"""
        resp = client.get("/api/reservations/available", params={
            "store_id": 1, "reservation_date": str(unique_date(8)), "guest_count": 2,
        })
        assert resp.status_code == 200
        slots = resp.json()
        if slots:
            start_times = [s["start_time"] for s in slots]
            assert "10:00:00" in start_times

    def test_slots_end_before_22(self):
        """最晚时段的 end_time 不应超过 22:00"""
        resp = client.get("/api/reservations/available", params={
            "store_id": 1, "reservation_date": str(unique_date(9)), "guest_count": 2,
        })
        assert resp.status_code == 200
        slots = resp.json()
        if slots:
            end_times = [s["end_time"] for s in slots]
            assert all(et <= "22:00:00" for et in end_times)

    def test_slot_duration_90_minutes(self):
        """每个时段应为 90 分钟"""
        from datetime import time as t, datetime, timedelta
        resp = client.get("/api/reservations/available", params={
            "store_id": 1, "reservation_date": str(unique_date(10)), "guest_count": 2,
        })
        assert resp.status_code == 200
        slots = resp.json()
        if slots:
            for s in slots[:3]:
                start = datetime.strptime(s["start_time"], "%H:%M:%S")
                end = datetime.strptime(s["end_time"], "%H:%M:%S")
                assert (end - start) == timedelta(minutes=90)
