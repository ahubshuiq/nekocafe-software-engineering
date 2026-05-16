"""
契约测试 — Member Provider 端（会员服务验证）
使用 pact-python Verifier 验证 Consumer 生成的 pact 文件。

运行前：
  1. docker compose up -d
  2. 运行:  pytest tests/contract/test_contract_member_provider.py -v

前置: pip install pact-python==2.2.2
"""
import os
import pytest

PACT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "pacts")
PACT_FILE = os.path.join(PACT_DIR, "memberconsumer-memberservice.json")
PROVIDER_BASE_URL = os.environ.get("MEMBER_PROVIDER_URL", "http://localhost:3000")


@pytest.fixture(scope="module")
def provider_state():
    os.environ.setdefault("DATABASE_URL",
                          "postgresql://nekocafe:nekocafe_dev@localhost:5432/nekocafe_member")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
    yield


def test_member_provider_verification(provider_state):
    """
    Provider 端验证：读取 Consumer 生成的 pact 文件，
    向运行中的会员服务发起请求，验证所有交互。
    """
    if not os.path.exists(PACT_FILE):
        pytest.skip(f"Pact file not found: {PACT_FILE}. Run consumer tests first.")

    try:
        from pact import Verifier
    except Exception:
        pytest.skip("Pact Verifier not available")

    os.environ["PACT_DO_NOT_TRACK"] = "true"
    os.environ["PYTHONIOENCODING"] = "utf-8"

    verifier = Verifier(
        provider="MemberService",
        provider_base_url=PROVIDER_BASE_URL,
    )

    result = verifier.verify_pacts(
        PACT_FILE,
        enable_pending=False,
        provider_states_setup_url=f"{PROVIDER_BASE_URL}/_pact/provider-states",
    )

    return_code = result[0] if isinstance(result, tuple) else result
    assert return_code == 0, f"Provider verification failed with {return_code} mismatches"
