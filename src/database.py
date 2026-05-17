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
-- ════════════════════════════════════════════════════════════
-- Users — proposal Table 3.2
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL,
    matric_no        TEXT    NOT NULL UNIQUE,
    user_level       INTEGER NOT NULL,
    registered_date  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════
-- Face Embeddings — DNN (SFace) per-pose vectors
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    pose_name     TEXT    NOT NULL,            -- 'FRONTAL'/'LEFT'/...
    vector        TEXT    NOT NULL,            -- JSON list of 128 floats
    created_date  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_embeddings_user ON embeddings(user_id);

-- ════════════════════════════════════════════════════════════
-- Lecture Halls — one row per physical device location
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS lecture_halls (
    hall_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    hall_name    TEXT    NOT NULL UNIQUE,        -- 'Electrical Hall 1'
    building     TEXT,                            -- 'EEE Block'
    capacity     INTEGER,                         -- optional, e.g. 120
    created_date DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════
-- Lecturers
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS lecturers (
    lecturer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    staff_id      TEXT UNIQUE,                    -- e.g. 'OOU/STAFF/001'
    department    TEXT,                           -- 'Electrical & Electronics'
    email         TEXT,
    phone         TEXT,
    created_date  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════
-- Courses
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS courses (
    course_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code  TEXT    NOT NULL UNIQUE,         -- 'EES501'
    course_name  TEXT    NOT NULL,
    course_level INTEGER NOT NULL,                -- 100/200/300/400/500
    created_date DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════
-- Sessions — the recurring weekly timetable
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sessions (
    session_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id       INTEGER NOT NULL,
    lecturer_id     INTEGER NOT NULL,
    hall_id         INTEGER NOT NULL,
    day_of_week     TEXT    NOT NULL,    -- 'MON' / 'TUE' / 'WED' / 'THU' / 'FRI'
    start_time      TEXT    NOT NULL,    -- 'HH:MM'  e.g. '08:00'
    end_time        TEXT    NOT NULL,    -- 'HH:MM'  e.g. '10:00'
    grace_minutes   INTEGER DEFAULT 60,  -- on-time window
    active          INTEGER DEFAULT 1,   -- 0 = retired session
    created_date    DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id)   REFERENCES courses(course_id),
    FOREIGN KEY (lecturer_id) REFERENCES lecturers(lecturer_id),
    FOREIGN KEY (hall_id)     REFERENCES lecture_halls(hall_id),
    UNIQUE (hall_id, day_of_week, start_time)   -- can't double-book one slot
);

-- ════════════════════════════════════════════════════════════
-- Session Cancellations — per specific date
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS session_cancellations (
    cancellation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER NOT NULL,
    cancellation_date DATE    NOT NULL,           -- 'YYYY-MM-DD'
    reason_category   TEXT    NOT NULL,           -- 'INSTITUTIONAL'/'LEAVE'/'HEALTH'/'HOLIDAY'/'OTHER'
    reason_note       TEXT,                       -- free-text detail
    cancelled_by      TEXT,                       -- lecturer name or 'ADMIN'
    cancelled_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    synced            INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    UNIQUE (session_id, cancellation_date)        -- one cancellation per date per session
);

-- ════════════════════════════════════════════════════════════
-- Attendance — extended with session linkage
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS attendance (
    record_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    session_id    INTEGER,                        -- which recurring session
    session_date  DATE,                           -- which specific date
    course_id     INTEGER,                        -- denormalized for convenience
    hall_id       INTEGER,                        -- denormalized for convenience
    timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
    confidence    REAL    NOT NULL,
    status        TEXT    DEFAULT 'PRESENT',      -- 'PRESENT' / 'LATE'
    synced        INTEGER DEFAULT 0,
    FOREIGN KEY (user_id)    REFERENCES users(user_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (course_id)  REFERENCES courses(course_id),
    FOREIGN KEY (hall_id)    REFERENCES lecture_halls(hall_id)
);

-- ════════════════════════════════════════════════════════════
-- Intruders — extended with session linkage
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS intruders (
    intruder_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER,                        -- which session was active
    session_date  DATE,
    hall_id       INTEGER,
    timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
    image_path    TEXT    NOT NULL,
    image_url     TEXT,                            -- populated after ImgBB upload
    confidence    REAL    NOT NULL,
    synced        INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (hall_id)    REFERENCES lecture_halls(hall_id)
);

-- ════════════════════════════════════════════════════════════
-- Indexes
-- ════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_attendance_user      ON attendance(user_id);
CREATE INDEX IF NOT EXISTS idx_attendance_session   ON attendance(session_id);
CREATE INDEX IF NOT EXISTS idx_attendance_date      ON attendance(session_date);
CREATE INDEX IF NOT EXISTS idx_attendance_synced    ON attendance(synced);
CREATE INDEX IF NOT EXISTS idx_intruders_synced     ON intruders(synced);
CREATE INDEX IF NOT EXISTS idx_sessions_hall_day    ON sessions(hall_id, day_of_week);
CREATE INDEX IF NOT EXISTS idx_cancel_session_date  ON session_cancellations(session_id, cancellation_date);
"""


def init_db():
    """Create all tables and indexes if they don't already exist."""
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)
    print(f"[INFO] Database initialised at: {DATABASE_PATH}")


# ── Basic CRUD operations ─

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

# ── Courses ────────────────────────────────────────────────────

def add_course(course_code, course_name, course_level):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO courses (course_code, course_name, course_level) "
            "VALUES (?, ?, ?)",
            (course_code.upper(), course_name, course_level))
        return cur.lastrowid


def get_course_by_code(course_code):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM courses WHERE course_code = ?",
            (course_code.upper(),)).fetchone()
        return dict(row) if row else None


def get_all_courses():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM courses ORDER BY course_code").fetchall()]

# ── Face Embeddings (DNN) ──────────────────────────────────────
import json as _json

def add_embedding(user_id, pose_name, vector_list):
    """Store one pose embedding (a list of 128 floats) for a user."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO embeddings (user_id, pose_name, vector) "
            "VALUES (?, ?, ?)",
            (user_id, pose_name, _json.dumps(vector_list))
        )
        return cur.lastrowid


def get_all_embeddings():
    """
    Return every stored embedding as a list of dicts:
       {user_id, pose_name, vector(list[float])}
    Used by the DNN recognizer to build its in-memory match set.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, pose_name, vector FROM embeddings"
        ).fetchall()
        result = []
        for r in rows:
            result.append({
                "user_id":   r["user_id"],
                "pose_name": r["pose_name"],
                "vector":    _json.loads(r["vector"]),
            })
        return result


def delete_embeddings_for_user(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM embeddings WHERE user_id = ?", (user_id,))


def count_embeddings_for_user(user_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM embeddings WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        return row["n"]


# ── Lecture Halls ──────────────────────────────────────────────

def add_hall(hall_name, building=None, capacity=None):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO lecture_halls (hall_name, building, capacity) "
            "VALUES (?, ?, ?)", (hall_name, building, capacity))
        return cur.lastrowid

def get_hall_by_name(hall_name):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM lecture_halls WHERE hall_name = ?",
            (hall_name,)).fetchone()
        return dict(row) if row else None

def get_all_halls():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM lecture_halls ORDER BY hall_name").fetchall()]


# ── Lecturers ──────────────────────────────────────────────────

def add_lecturer(full_name, staff_id=None, department=None,
                 email=None, phone=None):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO lecturers (full_name, staff_id, department, email, phone) "
            "VALUES (?, ?, ?, ?, ?)",
            (full_name, staff_id, department, email, phone))
        return cur.lastrowid

def get_lecturer_by_id(lecturer_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM lecturers WHERE lecturer_id = ?",
            (lecturer_id,)).fetchone()
        return dict(row) if row else None

def get_all_lecturers():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM lecturers ORDER BY full_name").fetchall()]


# ── Sessions ───────────────────────────────────────────────────

def add_session(course_id, lecturer_id, hall_id, day_of_week,
                start_time, end_time, grace_minutes=60):
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO sessions
              (course_id, lecturer_id, hall_id, day_of_week,
               start_time, end_time, grace_minutes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (course_id, lecturer_id, hall_id, day_of_week.upper(),
              start_time, end_time, grace_minutes))
        return cur.lastrowid

def get_sessions_for_hall_day(hall_id, day_of_week):
    """Return all active sessions for a given hall and day."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.*, c.course_code, c.course_name, c.course_level,
                   l.full_name AS lecturer_name
            FROM sessions s
            JOIN courses   c ON s.course_id   = c.course_id
            JOIN lecturers l ON s.lecturer_id = l.lecturer_id
            WHERE s.hall_id = ? AND s.day_of_week = ? AND s.active = 1
            ORDER BY s.start_time
        """, (hall_id, day_of_week.upper())).fetchall()
        return [dict(r) for r in rows]


# ── Session Cancellations ──────────────────────────────────────

def cancel_session(session_id, cancellation_date, reason_category,
                   reason_note=None, cancelled_by=None):
    """Mark one specific date's instance of a session as cancelled."""
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO session_cancellations
              (session_id, cancellation_date, reason_category,
               reason_note, cancelled_by)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, cancellation_date, reason_category.upper(),
              reason_note, cancelled_by))
        return cur.lastrowid

def is_session_cancelled(session_id, cancellation_date):
    with get_conn() as conn:
        row = conn.execute("""
            SELECT 1 FROM session_cancellations
            WHERE session_id = ? AND cancellation_date = ?
        """, (session_id, cancellation_date)).fetchone()
        return row is not None

def get_cancellations_for_date(date_str):
    """All cancellations for a given date (across all sessions)."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT sc.*, s.course_id, c.course_code, c.course_name,
                   l.full_name AS lecturer_name
            FROM session_cancellations sc
            JOIN sessions  s ON sc.session_id = s.session_id
            JOIN courses   c ON s.course_id   = c.course_id
            JOIN lecturers l ON s.lecturer_id = l.lecturer_id
            WHERE sc.cancellation_date = ?
            ORDER BY s.start_time
        """, (date_str,)).fetchall()
        return [dict(r) for r in rows]


# ── Attendance (Phase 3B) ──────────────────────────────────────

def log_attendance(user_id, confidence, session_id=None, session_date=None,
                   course_id=None, hall_id=None, status="PRESENT"):
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO attendance
              (user_id, session_id, session_date, course_id, hall_id,
               confidence, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, session_id, session_date, course_id, hall_id,
              confidence, status))
        return cur.lastrowid

def has_attended_session(user_id, session_id, session_date):
    """Has this user already been logged for this session on this date?"""
    with get_conn() as conn:
        row = conn.execute("""
            SELECT 1 FROM attendance
            WHERE user_id = ? AND session_id = ? AND session_date = ?
            LIMIT 1
        """, (user_id, session_id, session_date)).fetchone()
        return row is not None

def get_todays_attendance(hall_id=None, session_id=None):
    """
    Return all attendance records from today, joined with user, course,
    lecturer, and hall info. Optionally filter by hall and/or session.
    """
    sql = """
        SELECT a.record_id, a.timestamp, a.confidence, a.status,
               a.session_date,
               u.user_id, u.name, u.matric_no, u.user_level,
               c.course_code, c.course_name, c.course_level,
               l.full_name AS lecturer_name,
               h.hall_name
        FROM attendance a
        JOIN users     u ON a.user_id    = u.user_id
        LEFT JOIN courses    c ON a.course_id   = c.course_id
        LEFT JOIN sessions   s ON a.session_id  = s.session_id
        LEFT JOIN lecturers  l ON s.lecturer_id = l.lecturer_id
        LEFT JOIN lecture_halls h ON a.hall_id  = h.hall_id
        WHERE DATE(a.timestamp) = DATE('now', 'localtime')
    """
    params = []
    if hall_id is not None:
        sql += " AND a.hall_id = ?"
        params.append(hall_id)
    if session_id is not None:
        sql += " AND a.session_id = ?"
        params.append(session_id)
    sql += " ORDER BY a.timestamp"

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def get_todays_intruders(hall_id=None):
    """All intruder snapshots from today (used by view_attendance.py)."""
    sql = """
        SELECT i.*, h.hall_name, c.course_code
        FROM intruders i
        LEFT JOIN lecture_halls h ON i.hall_id = h.hall_id
        LEFT JOIN sessions  s ON i.session_id = s.session_id
        LEFT JOIN courses   c ON s.course_id  = c.course_id
        WHERE DATE(i.timestamp) = DATE('now', 'localtime')
    """
    params = []
    if hall_id is not None:
        sql += " AND i.hall_id = ?"
        params.append(hall_id)
    sql += " ORDER BY i.timestamp"

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

# ── Intruders (Phase 3B) ───────────────────────────────────────

def log_intruder(image_path, confidence, session_id=None,
                 session_date=None, hall_id=None):
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO intruders
              (image_path, confidence, session_id, session_date, hall_id)
            VALUES (?, ?, ?, ?, ?)
        """, (image_path, confidence, session_id, session_date, hall_id))
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