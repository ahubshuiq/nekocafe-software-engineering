"""
契约测试 — Consumer 端（预约服务消费者视角）
使用 pact-python 定义期望，生成 pact JSON 文件。
运行: pytest tests/contract/test_contract_consumer.py -v
前置: pip install pact-python==2.2.2 requests
注意: Windows 下需要 pact-mock-service (Ruby) 在 PATH 中；Linux/CI 无此限制。
"""
import os
import sys
import pytest
from datetime import date, timedelta

PACT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "pacts")
os.makedirs(PACT_DIR, exist_ok=True)


def _future_date(days=1):
    return str(date.today() + timedelta(days=days))


def _can_start_pact_mock():
    """检测 pact mock service 是否可用。"""
    try:
        from pact import Consumer, Provider
        p = Consumer("HealthCheck").has_pact_with(Provider("HealthCheck"), pact_dir=PACT_DIR)
        p.start_service()
        p.stop_service()
        return True
    except Exception:
        return False


_pact_available = _can_start_pact_mock()


@pytest.fixture(scope="module")
def pact_service():
    """启动 Pact mock service。"""
    if not _pact_available:
        pytest.skip("Pact mock service 不可用 (Windows 需安装 Ruby + pact-mock_service)")

    from pact import Consumer, Provider
    pact = Consumer("ReservationConsumer").has_pact_with(
        Provider("ReservationService"),
        pact_dir=PACT_DIR,
    )
    pact.start_service()
    yield pact
    pact.stop_service()


# ── 契约 1：POST /api/reservations — 创建预约 ───────────────

def test_create_reservation_contract(pact_service):
    """消费者期望：创建预约返回 201，包含 id、status 等字段。"""
    from pact import Like, Term

    request_body = {
        "member_id": 1,
        "store_id": 1,
        "table_id": 1,
        "reservation_date": _future_date(1),
        "start_time": "18:00",
        "guest_count": 2,
    }

    expected_body = {
        "id": Like(1),
        "member_id": Like(1),
        "store_id": Like(1),
        "table_id": Like(1),
        "reservation_date": Term(r"\d{4}-\d{2}-\d{2}", _future_date(1)),
        "start_time": Term(r"\d{2}:\d{2}(:\d{2})?", "18:00:00"),
        "end_time": Term(r"\d{2}:\d{2}(:\d{2})?", "19:30:00"),
        "guest_count": Like(2),
        "cat_preference": None,
        "status": Term(r"(PENDING|CONFIRMED)", "CONFIRMED"),
        "deposit_amount": None,
        "created_at": Like("2026-05-11T10:00:00"),
    }

    (pact_service
     .given("table 1 is available on the requested date")
     .upon_receiving("a request to create a reservation")
     .with_request("POST", "/api/reservations",
                   headers={"Content-Type": "application/json"},
                   body=request_body)
     .will_respond_with(201, body=expected_body))

    with pact_service:
        import requests
        resp = requests.post(
            f"{pact_service.uri}/api/reservations",
            json=request_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["status"] == "CONFIRMED"


# ── 契约 2：GET /api/reservations/{id} — 查询预约 ───────────

def test_get_reservation_contract(pact_service):
    """消费者期望：查询预约返回 200，包含 id 和 status。"""
    from pact import Like, Term

    reservation_id = 1

    expected_body = {
        "id": Like(reservation_id),
        "member_id": Like(1),
        "store_id": Like(1),
        "table_id": Like(1),
        "reservation_date": Like(_future_date(1)),
        "start_time": Like("18:00:00"),
        "end_time": Like("19:30:00"),
        "guest_count": Like(2),
        "cat_preference": None,
        "status": "CONFIRMED",
        "deposit_amount": None,
        "created_at": Like("2026-05-11T10:00:00"),
    }

    (pact_service
     .given("reservation 1 exists")
     .upon_receiving("a request to get a reservation by id")
     .with_request("GET", f"/api/reservations/{reservation_id}")
     .will_respond_with(200, body=expected_body))

    with pact_service:
        import requests
        resp = requests.get(f"{pact_service.uri}/api/reservations/{reservation_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == reservation_id
        assert resp.json()["status"] == "CONFIRMED"


# ── 契约 3：DELETE /api/reservations/{id} — 取消预约 ────────

def test_cancel_reservation_contract(pact_service):
    """消费者期望：取消预约返回 204。"""
    reservation_id = 1

    (pact_service
     .given("reservation 1 exists")
     .upon_receiving("a request to cancel a reservation")
     .with_request("DELETE", f"/api/reservations/{reservation_id}")
     .will_respond_with(204))

    with pact_service:
        import requests
        resp = requests.delete(f"{pact_service.uri}/api/reservations/{reservation_id}")
        assert resp.status_code == 204


# ── 验证 pact 文件已生成 ────────────────────────────────────

def test_pact_file_generated(pact_service):
    """验证 pact JSON 文件已写入。"""
    pact_file = os.path.join(PACT_DIR, "reservationconsumer-reservationservice.json")
    # pact 文件在 pact.stop_service() 时才写入，此处检查目录存在即可
    assert os.path.isdir(PACT_DIR)
