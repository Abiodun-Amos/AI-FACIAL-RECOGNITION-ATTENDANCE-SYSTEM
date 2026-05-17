"""
Test helper: inject a TEMPORARY session active RIGHT NOW (any weekday,
including weekends) so Phase 3B can be tested off-timetable. Also
supports removing the temporary session afterward.

Usage:
    python -m tests.make_test_session add      # create one active now
    python -m tests.make_test_session remove   # delete test sessions
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timedelta
from src import config, database

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
TEST_COURSE_CODE = "TESTING101"


def _ensure_prereqs():
    """Make sure there's a course, lecturer, and the hall to attach to."""
    database.init_db()

    hall = database.get_hall_by_name(config.CURRENT_HALL_NAME)
    if hall is None:
        hid = database.add_hall(config.CURRENT_HALL_NAME, building="EEE Block")
        hall = database.get_hall_by_name(config.CURRENT_HALL_NAME)
    hall_id = hall["hall_id"]

    course = database.get_course_by_code(TEST_COURSE_CODE)
    if course is None:
        # Match the level to one of your enrolled users so PRESENT works
        users = database.get_all_users()
        lvl = users[0]["user_level"] if users else 500
        database.add_course(TEST_COURSE_CODE, "Temporary Test Course", lvl)
        course = database.get_course_by_code(TEST_COURSE_CODE)

    lecturers = database.get_all_lecturers()
    if not lecturers:
        database.add_lecturer("Test Lecturer", "OOU/TEST/001",
                              "Electrical Electronics")
        lecturers = database.get_all_lecturers()

    return hall_id, course["course_id"], lecturers[0]["lecturer_id"]


def add():
    hall_id, course_id, lecturer_id = _ensure_prereqs()

    now = datetime.now()
    day = DAYS[now.weekday()]
    start = (now - timedelta(minutes=5)).strftime("%H:%M")
    end   = (now + timedelta(minutes=45)).strftime("%H:%M")

    try:
        sid = database.add_session(course_id, lecturer_id, hall_id,
                                   day, start, end, grace_minutes=60)
        print(f"[OK] Temporary session created:")
        print(f"     {TEST_COURSE_CODE}  {day}  {start}–{end}  (grace 60 min)")
        print(f"     session_id={sid}")
        print(f"\n  It is ACTIVE NOW. Run: python -m src.attendance_engine")
        print(f"  When done: python -m tests.make_test_session remove")
    except Exception as e:
        print(f"[ERROR] Could not create test session: {e}")
        print("        A test session for this slot may already exist.")
        print("        Run 'remove' first, then 'add' again.")


def remove():
    database.init_db()
    course = database.get_course_by_code(TEST_COURSE_CODE)
    if course is None:
        print("[INFO] No test course found — nothing to remove.")
        return
    with database.get_conn() as conn:
        # Delete sessions for the test course, plus the test course itself,
        # plus any attendance/cancellations tied to those sessions.
        sess_ids = [r["session_id"] for r in conn.execute(
            "SELECT session_id FROM sessions WHERE course_id = ?",
            (course["course_id"],)).fetchall()]
        for sid in sess_ids:
            conn.execute("DELETE FROM attendance WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM session_cancellations WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM intruders WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM sessions WHERE course_id = ?",
                     (course["course_id"],))
        conn.execute("DELETE FROM courses WHERE course_id = ?",
                     (course["course_id"],))
    print(f"[OK] Removed {len(sess_ids)} test session(s), the TEST999 "
          f"course, and any test attendance/intruder rows.")
    print("[OK] Your real timetable is untouched.")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("add", "remove"):
        print("Usage:")
        print("  python -m tests.make_test_session add")
        print("  python -m tests.make_test_session remove")
        sys.exit(1)
    (add if sys.argv[1] == "add" else remove)()