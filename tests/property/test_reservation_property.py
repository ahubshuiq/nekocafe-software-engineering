"""
基于属性的测试（Property-Based Testing）
使用 Hypothesis 生成随机输入，验证预约服务的核心逻辑。
"""
import os
os.environ.setdefault("DATABASE_URL",
                      "postgresql://nekocafe:nekocafe_dev@localhost:5432/nekocafe_reservation")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from hypothesis import given, strategies as st
from datetime import date, time, timedelta

from services.reservation.src.main import (
    is_reservation_date_valid,
    is_guest_count_valid,
    slots_overlap,
    cancel_reservations,
    get_stores_by_ids,
)


@given(d=st.dates())
def test_date_validity(d):
    """日期在 [today, today+7] 内才合法。"""
    today = date.today()
    if d < today or d > today + timedelta(days=7):
        assert is_reservation_date_valid(d) is False
    else:
        assert is_reservation_date_valid(d) is True


@given(guest_count=st.integers(min_value=0, max_value=20))
def test_guest_count_in_range(guest_count):
    """人数在 [1, 8] 内才合法。"""
    if 1 <= guest_count <= 8:
        assert is_guest_count_valid(guest_count) is True
    else:
        assert is_guest_count_valid(guest_count) is False


@given(
    h1=st.integers(min_value=0, max_value=22),
    h2=st.integers(min_value=0, max_value=22),
)
def test_time_slot_overlap_symmetric(h1, h2):
    """重叠判断应满足对称性: overlap(a,b) == overlap(b,a)。"""
    slot_a = (time(h1, 0), time(min(h1 + 2, 23), 0))
    slot_b = (time(h2, 0), time(min(h2 + 2, 23), 0))
    assert slots_overlap(slot_a, slot_b) == slots_overlap(slot_b, slot_a)


@given(
    h=st.integers(min_value=0, max_value=18),
    offset=st.integers(min_value=1, max_value=3),
)
def test_adjacent_slots_no_overlap(h, offset):
    """首尾相接的时段不应重叠。"""
    slot_a = (time(h, 0), time(h + offset, 0))
    slot_b = (time(h + offset, 0), time(min(h + offset + 1, 23), 0))
    assert slots_overlap(slot_a, slot_b) is False


@given(
    h=st.integers(min_value=1, max_value=20),
    duration=st.integers(min_value=1, max_value=3),
)
def test_contained_slot_overlaps(h, duration):
    """被包含的时段一定重叠。"""
    outer = (time(0, 0), time(23, 59))
    inner = (time(h, 0), time(min(h + duration, 23), 0))
    assert slots_overlap(outer, inner) is True


@given(ids=st.lists(st.integers(min_value=1, max_value=100), min_size=1, max_size=10, unique=True))
def test_cancel_reservations_returns_list(ids):
    """cancel_reservations 应返回列表。"""
    result = cancel_reservations(ids)
    assert isinstance(result, list)
    assert len(result) <= len(ids)


@given(store_ids=st.sets(st.integers(min_value=1, max_value=100), min_size=1, max_size=5))
def test_get_stores_by_ids(store_ids):
    """返回的门店数不超过请求数。"""
    stores = get_stores_by_ids(store_ids)
    assert len(stores) <= len(store_ids)
    assert len(stores) == len(store_ids)
    for store in stores:
        assert "id" in store
        assert store["id"] in store_ids
