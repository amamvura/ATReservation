from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException

from .db import pool

TZ = ZoneInfo("America/Chicago")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    yield
    pool.close()


app = FastAPI(title="ATReservation", lifespan=lifespan)


@app.get("/rooms")
def list_rooms():
    with pool.connection() as conn:
        return conn.execute(
            "SELECT id, name, capacity, open_time, close_time, slot_minutes "
            "FROM rooms ORDER BY id"
        ).fetchall()


@app.get("/rooms/{room_id}/slots")
def get_slots(room_id: int, day: date):
    with pool.connection() as conn:
        room = conn.execute(
            "SELECT * FROM rooms WHERE id = %s", (room_id,)
        ).fetchone()
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")

        day_start = datetime.combine(day, room["open_time"], tzinfo=TZ)
        day_end = datetime.combine(day, room["close_time"], tzinfo=TZ)

        booked = conn.execute(
            """
            SELECT lower(during) AS start_at, upper(during) AS end_at
            FROM reservations
            WHERE room_id = %s
              AND status = 'confirmed'
              AND during && tstzrange(%s, %s)
            """,
            (room_id, day_start, day_end),
        ).fetchall()

    step = timedelta(minutes=room["slot_minutes"])
    slots = []
    cursor = day_start
    while cursor + step <= day_end:
        slot_end = cursor + step
        taken = any(b["start_at"] < slot_end and b["end_at"] > cursor for b in booked)
        slots.append({"start": cursor, "end": slot_end, "available": not taken})
        cursor = slot_end

    return {"room_id": room_id, "date": day, "slots": slots}