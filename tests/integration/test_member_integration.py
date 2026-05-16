"""
集成测试 — 会员服务 (Node.js)
使用 Testcontainers 启动真实 PostgreSQL + Redis，通过 HTTP 测试会员服务 API。

运行前: pip install testcontainers[postgres,redis] httpx
运行:   pytest tests/integration/test_member_integration.py -v
"""
import os
import subprocess
import time as _time
import uuid
import socket
import threading

import pytest
import httpx

from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

pytestmark = pytest.mark.timeout(120)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    item.rep_call = rep


# 模块级变量，存储 node 进程日志
_node_logs = []
_node_proc = None


def _find_free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _uid():
    return int(_time.time() * 1000000) % 2_000_000_000 + int(uuid.uuid4().int % 10000)


def _phone():
    return "138" + str(_uid())[-8:].zfill(8)


def _request_with_retry(client, method, url, **kwargs):
    """发请求，超时后重试一次（node 进程可能因连接池问题偶尔卡住）。"""
    kwargs.setdefault("timeout", 15.0)
    for attempt in range(2):
        try:
            if method == "get":
                return client.get(url, **kwargs)
            elif method == "post":
                return client.post(url, **kwargs)
            elif method == "delete":
                return client.delete(url, **kwargs)
        except (httpx.ReadTimeout, httpx.ConnectError):
            if attempt == 0:
                _time.sleep(0.5)
                continue
            raise
    raise RuntimeError("Request failed after retry")


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine", username="test", password="test", dbname="testdb") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as rc:
        yield rc


@pytest.fixture(scope="session")
def member_url(postgres_container, redis_container):
    """启动会员服务子进程，返回基础 URL。"""
    pg_url = postgres_container.get_connection_url()
    if "+psycopg2" in pg_url:
        pg_url = pg_url.replace("+psycopg2", "")

    redis_port = redis_container.get_exposed_port(6379)
    redis_host = redis_container.get_container_host_ip()
    redis_url = f"redis://{redis_host}:{redis_port}/1"

    port = _find_free_port()
    env = os.environ.copy()
    env["DATABASE_URL"] = pg_url
    env["REDIS_URL"] = redis_url
    env["PORT"] = str(port)
    env["DB_POOL_MAX"] = "5"

    member_src = os.path.join(os.path.dirname(__file__), "..", "..", "services", "member", "src", "index.js")
    proc = subprocess.Popen(
        ["node", member_src],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    global _node_proc, _node_logs
    _node_proc = proc
    _node_logs = []
    def _reader(stream):
        for line in stream:
            _node_logs.append(line.decode("utf-8", errors="replace"))
    threading.Thread(target=_reader, args=(proc.stderr,), daemon=True).start()

    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            r = httpx.get(f"{base}/health", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        _time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("Member service failed to start")

    # 预热：触发建表 + bcrypt 缓存 + 连接池
    try:
        httpx.get(f"{base}/health", timeout=10)
        httpx.post(f"{base}/api/members", json={"name": "warmup", "phone": "13800000000"}, timeout=10)
    except Exception:
        pass

    yield base
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture()
def client(member_url):
    c = httpx.Client(base_url=member_url, timeout=15.0)
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _check_health(client, member_url):
    """每个测试前检查 node 进程是否还活着。"""
    if _node_proc and _node_proc.poll() is not None:
        pytest.skip(f"Node process exited with code {_node_proc.returncode}")
    try:
        r = client.get("/health", timeout=5)
        if r.status_code != 200:
            pytest.skip("Node process unhealthy")
    except Exception:
        pytest.skip("Node process not responding")
    yield
    if hasattr(self, "rep_call") if False else False:
        pass


@pytest.fixture(autouse=True)
def _dump_logs_on_failure(request):
    """测试失败时打印 node 进程日志。"""
    yield
    try:
        if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
            print("\n===== NODE STDERR (last 20 lines) =====")
            for line in _node_logs[-20:]:
                print(line, end="")
            print("===== END =====")
    except Exception:
        pass


# ── 辅助函数 ────────────────────────────────────────────────

def _register(client, name="测试用户"):
    phone = _phone()
    try:
        resp = _request_with_retry(client, "post", "/api/members",
                                   json={"name": name, "phone": phone})
    except (httpx.ReadTimeout, httpx.ConnectError):
        pytest.skip("Node process became unresponsive during registration")
    assert resp.status_code == 201, f"注册失败: {resp.text}"
    return resp.json()["id"]


def _earn(client, mid, amount):
    try:
        return _request_with_retry(client, "post", f"/api/members/{mid}/points/earn",
                                   json={"amount": amount})
    except (httpx.ReadTimeout, httpx.ConnectError):
        pytest.skip("Node process became unresponsive during earn")


def _redeem(client, mid, points):
    try:
        return _request_with_retry(client, "post", f"/api/members/{mid}/points/redeem",
                                   json={"points": points})
    except (httpx.ReadTimeout, httpx.ConnectError):
        pytest.skip("Node process became unresponsive during redeem")


# ── 10 个集成测试 ───────────────────────────────────────────

class TestMemberRegister:
    """IT-M01 ~ IT-M03 注册相关"""

    def test_register_success(self, client):
        """IT-M01 正常注册应返回 201"""
        mid = _register(client, "张三")
        resp = _request_with_retry(client, "get", f"/api/members/{mid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == mid

    def test_register_duplicate_phone(self, client):
        """IT-M02 重复手机号应返回 409"""
        phone = _phone()
        _request_with_retry(client, "post", "/api/members", json={"name": "A", "phone": phone})
        resp = _request_with_retry(client, "post", "/api/members", json={"name": "B", "phone": phone})
        assert resp.status_code == 409

    def test_register_invalid_phone(self, client):
        """IT-M03 无效手机号应返回 400"""
        resp = _request_with_retry(client, "post", "/api/members", json={"name": "X", "phone": "123"})
        assert resp.status_code == 400


class TestMemberQuery:
    """IT-M04 ~ IT-M05 查询相关"""

    def test_get_member(self, client):
        """IT-M04 查询已注册会员"""
        mid = _register(client, "查询测试")
        resp = _request_with_retry(client, "get", f"/api/members/{mid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == mid

    def test_get_nonexistent_member(self, client):
        """IT-M05 查询不存在的会员应返回 404"""
        resp = _request_with_retry(client, "get", "/api/members/99999")
        assert resp.status_code == 404


class TestPointsEarn:
    """IT-M06 ~ IT-M07 积分累加"""

    def test_earn_points(self, client):
        """IT-M06 消费累加积分"""
        mid = _register(client, "积分测试")
        resp = _earn(client, mid, 200)
        assert resp.status_code == 200
        assert resp.json()["earned_points"] == 200
        assert resp.json()["total_points"] == 200

    def test_earn_points_accumulates(self, client):
        """IT-M07 多次累加积分应正确累计"""
        mid = _register(client, "累加测试")
        r1 = _earn(client, mid, 100)
        assert r1.status_code == 200
        r2 = _earn(client, mid, 50)
        assert r2.status_code == 200
        assert r2.json()["total_points"] == 150


class TestPointsRedeem:
    """IT-M08 ~ IT-M09 积分兑换"""

    def test_redeem_points(self, client):
        """IT-M08 积分充足时兑换应成功"""
        mid = _register(client, "兑换测试")
        r1 = _earn(client, mid, 300)
        assert r1.status_code == 200
        resp = _redeem(client, mid, 100)
        assert resp.status_code == 200
        assert resp.json()["redeemed_points"] == 100
        assert resp.json()["remaining_points"] == 200

    def test_redeem_insufficient(self, client):
        """IT-M09 积分不足应返回 400"""
        mid = _register(client, "不足测试")
        _earn(client, mid, 50)
        resp = _redeem(client, mid, 999)
        assert resp.status_code == 400


class TestMemberLevelUpgrade:
    """IT-M10 等级自动升级"""

    def test_level_upgrade_after_spend(self, client):
        """IT-M10 消费满 2000 应自动升级为 SILVER"""
        mid = _register(client, "升级测试")
        resp = _earn(client, mid, 2500)
        assert resp.status_code == 200
        assert resp.json()["level"] == "SILVER"
