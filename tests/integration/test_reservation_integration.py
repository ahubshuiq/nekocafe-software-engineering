"""
集成测试 — 使用 Testcontainers 启动真实 PostgreSQL + Redis
运行前: pip install testcontainers[postgres,redis] psycopg2-binary httpx
运行:   pytest tests/integration/test_reservation_integration.py -v
"""
import os
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import uuid
import time as _time
from datetime import date, timedelta

import pytest
import httpx

# ── Testcontainers：在测试进程内启动真实容器 ──────────────────

from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container():
    """启动 PostgreSQL 容器，整个测试会话共享。"""
    with PostgresContainer("postgres:16-alpine", username="test", password="test", dbname="testdb") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    """启动 Redis 容器，整个测试会话共享。"""
    with RedisContainer("redis:7-alpine") as rc:
        yield rc


@pytest.fixture(scope="session")
def app_url(postgres_container, redis_container):
    """
    用 Testcontainers 容器的真实连接串启动 FastAPI 应用，
    返回服务的基础 URL。
    """
    # 设置环境变量让 main.py 读取测试容器的连接串
    pg_url = postgres_container.get_connection_url()
    # testcontainers 返回的 URL 可能包含 +psycopg2，需要去掉
    if "+psycopg2" in pg_url:
        pg_url = pg_url.replace("+psycopg2", "")

    redis_port = redis_container.get_exposed_port(6379)
    redis_host = redis_container.get_container_host_ip()
    redis_url = f"redis://{redis_host}:{redis_port}/0"

    os.environ["DATABASE_URL"] = pg_url
    os.environ["REDIS_URL"] = redis_url

    # 延迟导入 main，确保环境变量已设置
    from services.reservation.src.main import Base, engine
    Base.metadata.create_all(bind=engine)

    # 用 uvicorn 子线程启动应用
    import threading
    import uvicorn

    from services.reservation.src.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)

    # 找一个可用端口
    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config.port = port
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # 等待服务启动
    import time
    base = f"http://127.0.0.1:{port}"
    for _ in range(30):
        try:
            r = httpx.get(f"{base}/health", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)

    yield base
    server.should_exit = True


@pytest.fixture()
def client(app_url):
    """每个测试用例独立的 HTTP 客户端。"""
    return httpx.Client(base_url=app_url, timeout=10)


@pytest.fixture(autouse=True)
def _clean_db(app_url):
    """每个测试前清空预约表 + Redis 缓存。"""
    from services.reservation.src.main import SessionLocal, Reservation, redis_client
    db = SessionLocal()
    try:
        db.query(Reservation).delete()
        db.commit()
    finally:
        db.close()
    try:
        keys = redis_client.keys("slot:*")
        if keys:
            redis_client.delete(*keys)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _seed_tables(app_url):
    """确保测试用的桌位数据存在。"""
    from services.reservation.src.main import SessionLocal, DiningTable, TableStatus
    db = SessionLocal()
    try:
        if db.query(DiningTable).filter(DiningTable.store_id == 1).count() == 0:
            db.add_all([
                DiningTable(store_id=1, table_number="A1", capacity=4, zone="撸猫区",
                            status=TableStatus.IDLE.value),
                DiningTable(store_id=1, table_number="A2", capacity=2, zone="撸猫区",
                            status=TableStatus.IDLE.value),
                DiningTable(store_id=1, table_number="B1", capacity=6, zone="主题包间",
                            status=TableStatus.IDLE.value),
                DiningTable(store_id=1, table_number="B2", capacity=8, zone="主题包间",
                            status=TableStatus.IDLE.value),
                DiningTable(store_id=1, table_number="C1", capacity=4, zone="窗边区",
                            status=TableStatus.IDLE.value),
            ])
        db.commit()
    finally:
        db.close()


# ── 辅助函数 ────────────────────────────────────────────────

def _uid():
    return int(_time.time() * 1000000) % 2_000_000_000 + int(uuid.uuid4().int % 10000)


def _date(days=1):
    return str(date.today() + timedelta(days=days))


# ── 10 个集成测试 ───────────────────────────────────────────

class TestCreateAndGet:
    """IT-01 创建→查询的完整链路"""

    def test_create_and_get(self, client):
        payload = {
            "member_id": _uid(), "store_id": 1, "table_id": 1,
            "reservation_date": _date(1), "start_time": "18:00", "guest_count": 2,
        }
        resp = client.post("/api/reservations", json=payload)
        assert resp.status_code == 201
        rid = resp.json()["id"]

        get_resp = client.get(f"/api/reservations/{rid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["member_id"] == payload["member_id"]
        assert get_resp.json()["status"] == "CONFIRMED"

    def test_create_response_matches_db(self, client, app_url):
        """IT-02 API 响应与数据库记录一致。"""
        payload = {
            "member_id": _uid(), "store_id": 1, "table_id": 2,
            "reservation_date": _date(2), "start_time": "19:00", "guest_count": 3,
        }
        resp = client.post("/api/reservations", json=payload)
        assert resp.status_code == 201
        rid = resp.json()["id"]

        from services.reservation.src.main import SessionLocal, Reservation
        db = SessionLocal()
        try:
            db_r = db.query(Reservation).filter(Reservation.id == rid).first()
            assert db_r is not None
            assert db_r.member_id == payload["member_id"]
            assert db_r.guest_count == 3
            assert db_r.status == "CONFIRMED"
        finally:
            db.close()


class TestCancel:
    """IT-03 / IT-04 取消相关"""

    def test_cancel(self, client, app_url):
        """IT-03 创建→取消，验证 DB 状态。"""
        payload = {
            "member_id": _uid(), "store_id": 1, "table_id": 2,
            "reservation_date": _date(3), "start_time": "19:00", "guest_count": 2,
        }
        create = client.post("/api/reservations", json=payload)
        assert create.status_code == 201
        rid = create.json()["id"]

        cancel = client.delete(f"/api/reservations/{rid}")
        assert cancel.status_code == 204

        from services.reservation.src.main import SessionLocal, Reservation
        db = SessionLocal()
        try:
            db_r = db.query(Reservation).filter(Reservation.id == rid).first()
            assert db_r.status == "CANCELLED"
            assert db_r.cancel_reason is not None
        finally:
            db.close()

    def test_cancel_then_get_shows_cancelled(self, client):
        """IT-04 取消后查询应显示 CANCELLED。"""
        payload = {
            "member_id": _uid(), "store_id": 1, "table_id": 3,
            "reservation_date": _date(4), "start_time": "12:00", "guest_count": 4,
        }
        create = client.post("/api/reservations", json=payload)
        rid = create.json()["id"]
        client.delete(f"/api/reservations/{rid}")

        get_resp = client.get(f"/api/reservations/{rid}")
        assert get_resp.json()["status"] == "CANCELLED"


class TestAvailableSlots:
    """IT-05 / IT-06 可用时段"""

    def test_get_available_slots(self, client):
        """IT-05 查询可用时段应返回非空列表。"""
        resp = client.get("/api/reservations/available", params={
            "store_id": 1, "reservation_date": _date(5), "guest_count": 2,
        })
        assert resp.status_code == 200
        slots = resp.json()
        assert isinstance(slots, list)
        assert len(slots) > 0
        for s in slots:
            assert "table_id" in s
            assert "start_time" in s
            assert "end_time" in s

    def test_available_slots_reduced_after_booking(self, client):
        """IT-06 预约后可用时段应减少。"""
        resv_date = _date(6)
        before = client.get("/api/reservations/available", params={
            "store_id": 1, "reservation_date": resv_date, "guest_count": 2,
        }).json()
        if not before:
            pytest.skip("没有可用时段")
        slot = before[0]
        client.post("/api/reservations", json={
            "member_id": _uid(), "store_id": 1, "table_id": slot["table_id"],
            "reservation_date": resv_date, "start_time": slot["start_time"],
            "guest_count": 2,
        })
        after = client.get("/api/reservations/available", params={
            "store_id": 1, "reservation_date": resv_date, "guest_count": 2,
        }).json()
        assert len(after) < len(before)


class TestConflictScenarios:
    """IT-07 / IT-08 冲突场景"""

    def test_overlapping_reservation_rejected(self, client):
        """IT-07 同一时段重叠预约应返回 409。"""
        resv_date = _date(7)
        base = {
            "member_id": _uid(), "store_id": 1, "table_id": 1,
            "reservation_date": resv_date, "start_time": "16:00", "guest_count": 2,
        }
        r1 = client.post("/api/reservations", json=base)
        assert r1.status_code == 201

        base["member_id"] = _uid()
        r2 = client.post("/api/reservations", json=base)
        assert r2.status_code == 409

    def test_cancel_frees_slot_for_rebooking(self, client):
        """IT-08 取消后该时段可重新预约（DB + Redis 联动）。"""
        resv_date = _date(3)
        payload = {
            "member_id": _uid(), "store_id": 1, "table_id": 1,
            "reservation_date": resv_date, "start_time": "17:00", "guest_count": 2,
        }
        r1 = client.post("/api/reservations", json=payload)
        assert r1.status_code == 201
        rid = r1.json()["id"]

        payload["member_id"] = _uid()
        assert client.post("/api/reservations", json=payload).status_code == 409

        client.delete(f"/api/reservations/{rid}")
        payload["member_id"] = _uid()
        assert client.post("/api/reservations", json=payload).status_code == 201


class TestDoubleCancel:
    """IT-09 重复取消"""

    def test_double_cancel_rejected(self, client):
        """已取消的预约再次取消应返回 400。"""
        create = client.post("/api/reservations", json={
            "member_id": _uid(), "store_id": 1, "table_id": 2,
            "reservation_date": _date(4), "start_time": "13:00", "guest_count": 2,
        })
        rid = create.json()["id"]
        assert client.delete(f"/api/reservations/{rid}").status_code == 204
        assert client.delete(f"/api/reservations/{rid}").status_code == 400


class TestCatPreference:
    """IT-10 含可选字段"""

    def test_reservation_with_cat_preference(self, client, app_url):
        """创建含 cat_preference 的预约，验证 API + DB 持久化。"""
        payload = {
            "member_id": _uid(), "store_id": 1, "table_id": 3,
            "reservation_date": _date(5), "start_time": "11:00",
            "guest_count": 2, "cat_preference": "布偶猫",
        }
        create = client.post("/api/reservations", json=payload)
        assert create.status_code == 201
        rid = create.json()["id"]

        get_resp = client.get(f"/api/reservations/{rid}")
        assert get_resp.json()["cat_preference"] == "布偶猫"

        from services.reservation.src.main import SessionLocal, Reservation
        db = SessionLocal()
        try:
            db_r = db.query(Reservation).filter(Reservation.id == rid).first()
            assert db_r.cat_preference == "布偶猫"
        finally:
            db.close()
