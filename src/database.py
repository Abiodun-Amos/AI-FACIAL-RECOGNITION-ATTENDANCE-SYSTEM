"""
SQLite database layer.
Implements the schema described in proposal §3.8 (Tables 3.2 & 3.3),
plus an `intruders` table for the security feature.
"""

import sqlite3
from datetime import datetime
from contextlib import contextmanager
from src.config import DATABASE_PATH


# ── Connection helper ──────────────────────────────────────────
@contextmanager
def get_conn():
    """Context manager that auto-closes the SQLite connection."""
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row   # access columns by name
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── Schema creation ────────────────────────────────────────────
SCHEMA_SQL = """
-- Users (registered students/staff) — Table 3.2 in proposal
CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL,
    matric_no        TEXT    NOT NULL UNIQUE,
    user_level       INTEGER NOT NULL,
    registered_date  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Courses — added in Phase 3 (used fully in 3B)
CREATE TABLE IF NOT EXISTS courses (
    course_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code  TEXT    NOT NULL UNIQUE,        -- e.g. 'EES401'
    course_name  TEXT    NOT NULL,               -- e.g. 'Power Systems Analysis'
    course_level INTEGER NOT NULL,               -- 100/200/300/400/500
    created_date DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Attendance records — extended with course_id and status
CREATE TABLE IF NOT EXISTS attendance (
    record_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    course_id   INTEGER,                          -- NULL for Phase 3A free-mode
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
    confidence  REAL    NOT NULL,
    status      TEXT    DEFAULT 'PRESENT',        -- 'PRESENT' / 'LATE' (used in 3B)
    synced      INTEGER DEFAULT 0,
    FOREIGN KEY (user_id)   REFERENCES users(user_id),
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

-- Intruder snapshots
CREATE TABLE IF NOT EXISTS intruders (
    intruder_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP,
    course_id    INTEGER,                         -- which session was active
    image_path   TEXT    NOT NULL,
    image_url    TEXT,
    confidence   REAL    NOT NULL,
    synced       INTEGER DEFAULT 0,
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

CREATE INDEX IF NOT EXISTS idx_attendance_user      ON attendance(user_id);
CREATE INDEX IF NOT EXISTS idx_attendance_course    ON attendance(course_id);
CREATE INDEX IF NOT EXISTS idx_attendance_timestamp ON attendance(timestamp);
CREATE INDEX IF NOT EXISTS idx_attendance_synced    ON attendance(synced);
CREATE INDEX IF NOT EXISTS idx_intruders_synced     ON intruders(synced);
"""


def init_db():
    """Create all tables and indexes if they don't already exist."""
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)
    print(f"[INFO] Database initialised at: {DATABASE_PATH}")


# ── Basic CRUD operations (we'll add more as we build features) ─

def add_user(name: str, matric_no: str, user_level: int) -> int:
    """Register a new user. Returns the new user_id."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (name, matric_no, user_level) VALUES (?, ?, ?)",
            (name, matric_no, user_level)
        )
        return cur.lastrowid


def get_user_by_id(user_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_users():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY user_id").fetchall()
        return [dict(r) for r in rows]


# def log_attendance(user_id: int, confidence: float) -> int:
#     with get_conn() as conn:
#         cur = conn.execute(
#             "INSERT INTO attendance (user_id, confidence) VALUES (?, ?)",
#             (user_id, confidence)
#         )
#         return cur.lastrowid


# def log_intruder(image_path: str, confidence: float) -> int:
#     with get_conn() as conn:
#         cur = conn.execute(
#             "INSERT INTO intruders (image_path, confidence) VALUES (?, ?)",
#             (image_path, confidence)
#         )
#         return cur.lastrowid


def add_course(course_code: str, course_name: str, course_level: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO courses (course_code, course_name, course_level) "
            "VALUES (?, ?, ?)",
            (course_code.upper(), course_name, course_level)
        )
        return cur.lastrowid


def get_course_by_code(course_code: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM courses WHERE course_code = ?",
            (course_code.upper(),)
        ).fetchone()
        return dict(row) if row else None


def get_all_courses():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM courses ORDER BY course_code"
        ).fetchall()
        return [dict(r) for r in rows]


def log_attendance(user_id: int, confidence: float,
                   course_id: int | None = None,
                   status: str = "PRESENT") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO attendance (user_id, course_id, confidence, status) "
            "VALUES (?, ?, ?, ?)",
            (user_id, course_id, confidence, status)
        )
        return cur.lastrowid


def has_attended_today(user_id: int, course_id: int | None = None) -> bool:
    """
    Returns True if this user already has an attendance record TODAY
    (optionally for a specific course). Used to prevent duplicate logs.
    """
    with get_conn() as conn:
        if course_id is None:
            row = conn.execute(
                "SELECT 1 FROM attendance "
                "WHERE user_id = ? AND DATE(timestamp) = DATE('now', 'localtime') "
                "LIMIT 1",
                (user_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM attendance "
                "WHERE user_id = ? AND course_id = ? "
                "  AND DATE(timestamp) = DATE('now', 'localtime') "
                "LIMIT 1",
                (user_id, course_id)
            ).fetchone()
        return row is not None


def get_todays_attendance(course_id: int | None = None):
    """Return all attendance records from today, joined with user names."""
    with get_conn() as conn:
        if course_id is None:
            rows = conn.execute("""
                SELECT a.record_id, a.timestamp, a.confidence, a.status,
                       u.user_id, u.name, u.matric_no, u.user_level
                FROM attendance a
                JOIN users u ON a.user_id = u.user_id
                WHERE DATE(a.timestamp) = DATE('now', 'localtime')
                ORDER BY a.timestamp
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT a.record_id, a.timestamp, a.confidence, a.status,
                       u.user_id, u.name, u.matric_no, u.user_level
                FROM attendance a
                JOIN users u ON a.user_id = u.user_id
                WHERE DATE(a.timestamp) = DATE('now', 'localtime')
                  AND a.course_id = ?
                ORDER BY a.timestamp
            """, (course_id,)).fetchall()
        return [dict(r) for r in rows]


# ── Extended intruder helpers ────────────────────────────────────

def log_intruder(image_path: str, confidence: float,
                 course_id: int | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO intruders (image_path, confidence, course_id) "
            "VALUES (?, ?, ?)",
            (image_path, confidence, course_id)
        )
        return cur.lastrowid

# ── Convenience: stand-alone init when run directly ───────────
if __name__ == "__main__":
    init_db()
    print("[INFO] Schema ready. Tables:")
    with get_conn() as conn:
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ):
            print(f"   • {r['name']}")