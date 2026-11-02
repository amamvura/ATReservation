from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from server.db import pool
from server.main import app

TZ = ZoneInfo("America/Chicago")
SLOT_START = datetime(2027, 6, 15, 10, 0, tzinfo=TZ)  # far-future slot, no seed data
SLOT_END = SLOT_START + timedelta(hours=1)
N = 50


def clear_slot():
    with pool.connection() as conn:
        conn.execute(
            "DELETE FROM reservations "
            "WHERE room_id = 1 AND during && tstzrange(%s, %s)",
            (SLOT_START, SLOT_END),
        )


@pytest.fixture
def client():
    with TestClient(app) as c:  # runs the app lifespan, which opens the pool
        clear_slot()
        yield c
        clear_slot()


def book(client, user_id):
    response = client.post(
        "/reservations",
        json={"room_id": 1, "user_id": user_id, "start": SLOT_START.isoformat()},
    )
    return response.status_code


def test_exactly_one_of_many_simultaneous_bookings_wins(client):
    with ThreadPoolExecutor(max_workers=N) as pool_of_threads:
        codes = list(pool_of_threads.map(lambda i: book(client, 1 + i % 2), range(N)))

    assert codes.count(201) == 1
    assert codes.count(409) == N - 1

    with pool.connection() as conn:
        count = conn.execute(
            "SELECT count(*) AS n FROM reservations "
            "WHERE room_id = 1 AND status = 'confirmed' AND during && tstzrange(%s, %s)",
            (SLOT_START, SLOT_END),
        ).fetchone()["n"]
    assert count == 1