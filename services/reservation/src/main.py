"""
NekoCafé 桌位预约服务
桌位管理、时段预约、排队候补
"""

import os
import json
import logging
from datetime import datetime, date, time, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Date,
    Time, Numeric, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import timezone
import redis
import enum

# ======================== 配置 ========================

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("reservation-service")


def log_json(level: str, msg: str, **kwargs):
    record = {
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "level": level,
        "service": "reservation-service",
        "message": msg,
        **kwargs,
    }
    logger.log(getattr(logging, level, logging.INFO), json.dumps(record, ensure_ascii=False))


# ======================== 数据库 ========================

engine = create_engine(
    DATABASE_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "30")),
    pool_recycle=3600,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ReservationStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class TableStatus(str, enum.Enum):
    IDLE = "IDLE"
    RESERVED = "RESERVED"
    IN_USE = "IN_USE"
    MAINTENANCE = "MAINTENANCE"


class DiningTable(Base):
    __tablename__ = "dining_table"
    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, nullable=False, index=True)
    table_number = Column(String(10), nullable=False)
    capacity = Column(Integer, nullable=False)
    zone = Column(String(32))
    status = Column(String(20), nullable=False, default=TableStatus.IDLE.value)


class Reservation(Base):
    __tablename__ = "reservation"
    id = Column(Integer, primary_key=True, autoincrement=True)
    member_id = Column(Integer, nullable=False, index=True)
    store_id = Column(Integer, nullable=False, index=True)
    table_id = Column(Integer, nullable=False)
    reservation_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    guest_count = Column(Integer, nullable=False)
    cat_preference = Column(String(128))
    status = Column(String(20), nullable=False, default=ReservationStatus.PENDING.value)
    deposit_amount = Column(Numeric(10, 2))
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    cancel_reason = Column(String(256))


# ======================== Redis ========================

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=3,
    retry_on_timeout=True,
    max_connections=20,
)

# ======================== 请求/响应模型 ========================


class CreateReservationRequest(BaseModel):
    member_id: int
    store_id: int
    table_id: int
    reservation_date: date
    start_time: time = Field(..., description="HH:MM 格式")
    guest_count: int = Field(..., ge=1, le=8)
    cat_preference: Optional[str] = None


class ReservationResponse(BaseModel):
    id: int
    member_id: int
    store_id: int
    table_id: int
    reservation_date: date
    start_time: str
    end_time: str
    guest_count: int
    cat_preference: Optional[str]
    status: str
    deposit_amount: Optional[float]
    created_at: datetime


class AvailableSlotResponse(BaseModel):
    table_id: int
    table_number: str
    capacity: int
    zone: Optional[str]
    start_time: str
    end_time: str


# ======================== 依赖注入 ========================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ======================== 预约策略 ========================

MAX_ADVANCE_DAYS = 7
SLOT_DURATION_MINUTES = 90
MAX_GUESTS_PER_TABLE = 8


def validate_reservation(req: CreateReservationRequest):
    """业务规则校验（格式/范围由 Pydantic 负责）。"""
    days_ahead = (req.reservation_date - date.today()).days
    if days_ahead < 0 or days_ahead > MAX_ADVANCE_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"预约须在 {MAX_ADVANCE_DAYS} 天以内"
        )


def check_slot_available(db: Session, table_id: int, resv_date: date, start: time, end: time) -> bool:
    cache_key = f"slot:{table_id}:{resv_date}:{start}"
    cached = redis_client.get(cache_key)
    if cached is not None:
        return cached == "1"

    conflict = db.query(Reservation).filter(
        Reservation.table_id == table_id,
        Reservation.reservation_date == resv_date,
        Reservation.status.in_(["PENDING", "CONFIRMED"]),
        Reservation.start_time < end,
        Reservation.end_time > start,
    ).first()

    available = conflict is None
    redis_client.setex(cache_key, 300, "1" if available else "0")
    return available


# ======================== FastAPI 应用 ========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    log_json("INFO", "Reservation service starting up")
    Base.metadata.create_all(bind=engine)
    yield
    log_json("INFO", "Reservation service shutting down")


app = FastAPI(
    title="NekoCafé 桌位预约服务",
    version="1.0.0",
    description="桌位管理、时段预约、排队候补",
    lifespan=lifespan,
)

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)


@app.get("/health")
def health_check():
    return {
        "status": "UP",
        "service": "reservation-service",
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
    }


@app.post("/api/reservations", response_model=ReservationResponse, status_code=201)
def create_reservation(req: CreateReservationRequest, db: Session = Depends(get_db)):
    log_json("INFO", "Creating reservation",
             store_id=req.store_id, date=str(req.reservation_date), time=req.start_time.isoformat())

    validate_reservation(req)

    start = req.start_time
    end_dt = datetime.combine(date.today(), start) + timedelta(minutes=SLOT_DURATION_MINUTES)
    end = end_dt.time()

    if not check_slot_available(db, req.table_id, req.reservation_date, start, end):
        raise HTTPException(status_code=409, detail="该时段桌位已被占用")

    reservation = Reservation(
        member_id=req.member_id,
        store_id=req.store_id,
        table_id=req.table_id,
        reservation_date=req.reservation_date,
        start_time=start,
        end_time=end,
        guest_count=req.guest_count,
        cat_preference=req.cat_preference,
        status=ReservationStatus.CONFIRMED.value,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)

    cache_key = f"slot:{req.table_id}:{req.reservation_date}:{start}"
    redis_client.delete(cache_key)

    log_json("INFO", "Reservation created", reservation_id=reservation.id)
    return _to_response(reservation)
@app.get("/api/reservations/available", response_model=list[AvailableSlotResponse])
def get_available_slots(
    store_id: int = Query(...),
    reservation_date: date = Query(...),
    guest_count: int = Query(default=2, ge=1, le=8),
    db: Session = Depends(get_db),
):
    tables = db.query(DiningTable).filter(
        DiningTable.store_id == store_id,
        DiningTable.capacity >= guest_count,
        DiningTable.status == TableStatus.IDLE.value,
    ).all()

    results = []
    for t in tables:
        current = datetime.combine(reservation_date, time(10, 0))
        end_of_day = datetime.combine(reservation_date, time(22, 0))
        while current + timedelta(minutes=SLOT_DURATION_MINUTES) <= end_of_day:
            slot_start = current.time()
            slot_end = (current + timedelta(minutes=SLOT_DURATION_MINUTES)).time()
            if check_slot_available(db, t.id, reservation_date, slot_start, slot_end):
                results.append(AvailableSlotResponse(
                    table_id=t.id,
                    table_number=t.table_number,
                    capacity=t.capacity,
                    zone=t.zone,
                    start_time=slot_start.isoformat(),
                    end_time=slot_end.isoformat(),
                ))
            current += timedelta(minutes=SLOT_DURATION_MINUTES)

    return results

@app.get("/api/reservations/{reservation_id}", response_model=ReservationResponse)
def get_reservation(reservation_id: int, db: Session = Depends(get_db)):
    r = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    return _to_response(r)


@app.delete("/api/reservations/{reservation_id}", status_code=204)
def cancel_reservation(reservation_id: int, reason: str = "用户主动取消", db: Session = Depends(get_db)):
    r = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    if r.status in ["CANCELLED", "EXPIRED"]:
        raise HTTPException(status_code=400, detail="预约已取消或已过期")

    r.status = ReservationStatus.CANCELLED.value
    r.cancel_reason = reason
    db.commit()

    cache_key = f"slot:{r.table_id}:{r.reservation_date}:{r.start_time}"
    redis_client.delete(cache_key)
    log_json("INFO", "Reservation cancelled", reservation_id=reservation_id, reason=reason)


# ======================== Pact Provider States ========================

PACT_MODE = os.getenv("PACT_MODE", "false").lower() == "true"


class ProviderStateRequest(BaseModel):
    state: str
    states: Optional[list] = None
    params: Optional[dict] = None


@app.post("/_pact/provider-states", status_code=200)
def setup_provider_state(req: ProviderStateRequest, db: Session = Depends(get_db)):
    """Pact provider state setup — called by the verifier before each interaction."""
    if not PACT_MODE:
        raise HTTPException(status_code=404, detail="Not found")
    if req.state == "table 1 is available on the requested date":
        # Ensure dining tables exist
        if db.query(DiningTable).filter(DiningTable.store_id == 1).count() == 0:
            db.add_all([
                DiningTable(store_id=1, table_number="A1", capacity=4, zone="撸猫区",
                            status=TableStatus.IDLE.value),
                DiningTable(store_id=1, table_number="A2", capacity=2, zone="撸猫区",
                            status=TableStatus.IDLE.value),
            ])
            db.commit()
        # Clear reservations for a clean slate
        db.query(Reservation).delete()
        db.commit()
        # Clear Redis cache
        try:
            keys = redis_client.keys("slot:*")
            if keys:
                redis_client.delete(*keys)
        except Exception:
            pass

    elif req.state == "reservation 1 exists":
        # Create reservation with id=1 for GET/DELETE tests
        existing = db.query(Reservation).filter(Reservation.id == 1).first()
        if not existing:
            r = Reservation(
                id=1, member_id=1, store_id=1, table_id=1,
                reservation_date=date.today() + timedelta(days=1),
                start_time=time(18, 0), end_time=time(19, 30),
                guest_count=2, status=ReservationStatus.CONFIRMED.value,
            )
            db.add(r)
            db.commit()

    return {"status": "ok"}


@app.post("/_pact/provider-states/teardown", status_code=200)
def teardown_provider_state(req: ProviderStateRequest, db: Session = Depends(get_db)):
    """Pact provider state teardown — called by the verifier after each interaction."""
    if not PACT_MODE:
        raise HTTPException(status_code=404, detail="Not found")
    db.query(Reservation).delete()
    db.commit()
    try:
        keys = redis_client.keys("slot:*")
        if keys:
            redis_client.delete(*keys)
    except Exception:
        pass
    return {"status": "ok"}



# ======================== 纯逻辑工具函数（供属性测试使用） ========================


def is_reservation_date_valid(d: date) -> bool:
    """检查预约日期是否在允许范围内 [今天, 今天+7天]。"""
    today = date.today()
    return today <= d <= today + timedelta(days=MAX_ADVANCE_DAYS)


def is_guest_count_valid(count: int) -> bool:
    """检查就餐人数是否在合法范围 [1, 8]。"""
    return 1 <= count <= MAX_GUESTS_PER_TABLE


def slots_overlap(slot1: tuple, slot2: tuple) -> bool:
    """判断两个时间段是否重叠。每个 slot 为 (start_time, end_time)。"""
    s1_start, s1_end = slot1
    s2_start, s2_end = slot2
    return s1_start < s2_end and s2_start < s1_end


def cancel_reservations(reservation_ids: list) -> list:
    """批量取消预约，返回成功取消的 ID 列表。"""
    cancelled = []
    db = SessionLocal()
    try:
        for rid in reservation_ids:
            r = db.query(Reservation).filter(Reservation.id == rid).first()
            if r and r.status not in ["CANCELLED", "EXPIRED"]:
                r.status = ReservationStatus.CANCELLED.value
                cancelled.append(rid)
        db.commit()
    finally:
        db.close()
    return cancelled


def get_stores_by_ids(store_ids) -> list:
    """根据 ID 集合查询门店。"""
    # TODO: 替换为真实 DB 查询，当前为 stub 实现
    return [{"id": sid} for sid in store_ids]


def _to_response(r: Reservation) -> ReservationResponse:
    return ReservationResponse(
        id=r.id,
        member_id=r.member_id,
        store_id=r.store_id,
        table_id=r.table_id,
        reservation_date=r.reservation_date,
        start_time=r.start_time.isoformat(),
        end_time=r.end_time.isoformat(),
        guest_count=r.guest_count,
        cat_preference=r.cat_preference,
        status=r.status,
        deposit_amount=float(r.deposit_amount) if r.deposit_amount else None,
        created_at=r.created_at,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
