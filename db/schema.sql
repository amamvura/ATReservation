CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE users (
  id            SERIAL PRIMARY KEY,
  email         TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rooms (
  id           SERIAL PRIMARY KEY,
  name         TEXT NOT NULL,
  capacity     INT NOT NULL CHECK (capacity > 0),
  open_time    TIME NOT NULL DEFAULT '08:00',
  close_time   TIME NOT NULL DEFAULT '22:00',
  slot_minutes INT NOT NULL DEFAULT 60 CHECK (slot_minutes > 0)
);

CREATE TABLE reservations (
  id         SERIAL PRIMARY KEY,
  user_id    INT NOT NULL REFERENCES users(id),
  room_id    INT NOT NULL REFERENCES rooms(id),
  during     TSTZRANGE NOT NULL,
  status     TEXT NOT NULL DEFAULT 'confirmed'
             CHECK (status IN ('confirmed', 'cancelled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT no_double_booking
    EXCLUDE USING gist (room_id WITH =, during WITH &&)
    WHERE (status = 'confirmed')
);

CREATE INDEX idx_reservations_room_during
  ON reservations USING gist (room_id, during);