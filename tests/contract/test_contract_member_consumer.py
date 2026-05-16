"""
契约测试 — Member Consumer 端（会员服务消费者视角）
使用 pact-python 定义期望，生成 pact JSON 文件。

运行: pytest tests/contract/test_contract_member_consumer.py -v
前置: pip install pact-python==2.2.2 requests
"""
import os
import pytest
from datetime import date

PACT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "pacts")
os.makedirs(PACT_DIR, exist_ok=True)


def _can_start_pact_mock():
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
    if not _pact_available:
        pytest.skip("Pact mock service 不可用 (Windows 需安装 Ruby + pact-mock_service)")

    from pact import Consumer, Provider
    pact = Consumer("MemberConsumer").has_pact_with(
        Provider("MemberService"),
        pact_dir=PACT_DIR,
    )
    pact.start_service()
    yield pact
    pact.stop_service()


# ── 契约 1: POST /api/members — 注册会员 ──────────────────

def test_create_member_contract(pact_service):
    """消费者期望：注册会员返回 201，包含 id、name、phone、level 等字段。"""
    from pact import Like, Term

    request_body = {
        "name": "测试用户",
        "phone": "13800001111",
        "email": "test@nekocafe.com",
    }

    expected_body = {
        "id": Like(1),
        "name": "测试用户",
        "phone": Term(r"1[3-9]\d{9}", "13800001111"),
        "email": Like("test@nekocafe.com"),
        "level": Term(r"(NORMAL|SILVER|GOLD|BLACK)", "NORMAL"),
        "points": Like(0),
        "total_spent": Like(0),
        "preferences": None,
        "created_at": Like("2026-05-16T10:00:00"),
    }

    (pact_service
     .given("phone 13800001111 is not registered")
     .upon_receiving("a request to register a member")
     .with_request("POST", "/api/members",
                   headers={"Content-Type": "application/json"},
                   body=request_body)
     .will_respond_with(201, body=expected_body))

    with pact_service:
        import requests
        resp = requests.post(
            f"{pact_service.uri}/api/members",
            json=request_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["name"] == "测试用户"
        assert body["level"] == "NORMAL"


# ── 契约 2: GET /api/members/:id — 查询会员 ────────────────

def test_get_member_contract(pact_service):
    """消费者期望：查询会员返回 200，包含 id 和 phone。"""
    from pact import Like, Term

    expected_body = {
        "id": Like(1),
        "name": Like("测试用户"),
        "phone": Term(r"1[3-9]\d{9}", "13800001111"),
        "email": Like("test@nekocafe.com"),
        "level": "NORMAL",
        "points": Like(0),
        "total_spent": Like(0),
        "preferences": None,
        "created_at": Like("2026-05-16T10:00:00"),
    }

    (pact_service
     .given("member 1 exists")
     .upon_receiving("a request to get a member by id")
     .with_request("GET", "/api/members/1")
     .will_respond_with(200, body=expected_body))

    with pact_service:
        import requests
        resp = requests.get(f"{pact_service.uri}/api/members/1")
        assert resp.status_code == 200
        assert resp.json()["id"] == 1


# ── 契约 3: POST /api/members/:id/points/earn — 积分累加 ───

def test_earn_points_contract(pact_service):
    """消费者期望：积分累加返回 200，包含 earned_points 和 total_points。"""
    from pact import Like, Term

    request_body = {"amount": 100}

    expected_body = {
        "member_id": Like(1),
        "earned_points": Like(100),
        "total_points": Like(100),
        "level": Term(r"(NORMAL|SILVER|GOLD|BLACK)", "NORMAL"),
    }

    (pact_service
     .given("member 1 exists with 0 points")
     .upon_receiving("a request to earn points")
     .with_request("POST", "/api/members/1/points/earn",
                   headers={"Content-Type": "application/json"},
                   body=request_body)
     .will_respond_with(200, body=expected_body))

    with pact_service:
        import requests
        resp = requests.post(
            f"{pact_service.uri}/api/members/1/points/earn",
            json=request_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["earned_points"] == 100
        assert "total_points" in body


# ── 契约 4: POST /api/members/:id/points/redeem — 积分兑换 ──

def test_redeem_points_contract(pact_service):
    """消费者期望：积分兑换返回 200，包含 redeemed_points 和 remaining_points。"""
    from pact import Like

    request_body = {"points": 50}

    expected_body = {
        "member_id": Like(1),
        "redeemed_points": Like(50),
        "remaining_points": Like(50),
    }

    (pact_service
     .given("member 1 exists with 100 points")
     .upon_receiving("a request to redeem points")
     .with_request("POST", "/api/members/1/points/redeem",
                   headers={"Content-Type": "application/json"},
                   body=request_body)
     .will_respond_with(200, body=expected_body))

    with pact_service:
        import requests
        resp = requests.post(
            f"{pact_service.uri}/api/members/1/points/redeem",
            json=request_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["redeemed_points"] == 50
        assert "remaining_points" in body
