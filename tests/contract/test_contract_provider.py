"""
契约测试 — Provider 端（预约服务验证）
使用 pact-python Verifier 验证 Consumer 生成的 pact 文件。

运行前：
  1. docker compose up -d
  2. 运行:  pytest tests/contract/test_contract_provider.py -v

前置: pip install pact-python==2.2.2
"""
import os
import sys
import pytest

PACT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "pacts")
PACT_FILE = os.path.join(PACT_DIR, "reservationconsumer-reservationservice.json")
PROVIDER_BASE_URL = os.environ.get("PROVIDER_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def provider_state():
    """
    设置环境变量（数据由 provider-states 端点负责）。
    """
    os.environ.setdefault("DATABASE_URL",
                          "postgresql://nekocafe:nekocafe_dev@localhost:5432/nekocafe_reservation")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("PACT_MODE", "true")
    yield


def test_provider_verification(provider_state):
    """
    Provider 端验证：读取 Consumer 生成的 pact 文件，
    向运行中的预约服务发起请求，验证所有交互。
    """
    if not os.path.exists(PACT_FILE):
        pytest.skip(f"Pact file not found: {PACT_FILE}. Run consumer tests first.")

    try:
        from pact import Verifier
    except Exception:
        pytest.skip("Pact Verifier not available")

    # 修复 Windows 下 Ruby pact verifier 的编码问题
    os.environ["PACT_DO_NOT_TRACK"] = "true"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PACT_MODE"] = "true"

    verifier = Verifier(
        provider="ReservationService",
        provider_base_url=PROVIDER_BASE_URL,
    )

    result = verifier.verify_pacts(
        PACT_FILE,
        enable_pending=False,
        provider_states_setup_url=f"{PROVIDER_BASE_URL}/_pact/provider-states",
    )

    # verify_pacts returns (return_code, logs)
    return_code = result[0] if isinstance(result, tuple) else result
    assert return_code == 0, f"Provider verification failed with {return_code} mismatches"
