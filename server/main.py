from contextlib import asynccontextmanager
from psycopg.errors import ExclusionViolation, ForeignKeyViolation
from pydantic import BaseModel

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

class ReservationIn(BaseModel):
    room_id: int
    user_id: int  # temporary: we replace this with real login later
    start: datetime


@app.post("/reservations", status_code=201)
def create_reservation(body: ReservationIn):
    start = body.start if body.start.tzinfo else body.start.replace(tzinfo=TZ)

    with pool.connection() as conn:
        room = conn.execute(
            "SELECT * FROM rooms WHERE id = %s", (body.room_id,)
        ).fetchone()
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")

        step = timedelta(minutes=room["slot_minutes"])
        end = start + step

        # Must be a real slot: inside opening hours and aligned to the slot grid
        local = start.astimezone(TZ)
        open_dt = datetime.combine(local.date(), room["open_time"], tzinfo=TZ)
        close_dt = datetime.combine(local.date(), room["close_time"], tzinfo=TZ)
        on_grid = (local - open_dt) % step == timedelta(0)
        if not (open_dt <= local and local + step <= close_dt and on_grid):
            raise HTTPException(status_code=400, detail="Not a valid slot for this room")

        if start <= datetime.now(TZ):
            raise HTTPException(status_code=400, detail="Cannot book a slot in the past")

        try:
            row = conn.execute(
                """
                INSERT INTO reservations (user_id, room_id, during)
                VALUES (%s, %s, tstzrange(%s, %s))
                RETURNING id, user_id, room_id, status
                """,
                (body.user_id, body.room_id, start, end),
            ).fetchone()
        except ExclusionViolation:
            # The database itself refused the overlap: this is the guarantee
            raise HTTPException(status_code=409, detail="That slot was just taken")
        except ForeignKeyViolation:
            raise HTTPException(status_code=404, detail="User not found")

    return {**row, "start": start, "end": end}