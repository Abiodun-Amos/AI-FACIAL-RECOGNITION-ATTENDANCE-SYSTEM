"""
One-time cleanup: removes ALL test/debris sessions and courses
that accumulated during debugging, leaving only real timetable data.

Shows you everything BEFORE deleting and asks for confirmation.

Usage:
    python -m tests.purge_test_data
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import database

# Course codes considered "test debris" — anything starting with these
TEST_PREFIXES = ("TEST", "TESTING")


def main():
    database.init_db()

    print("\n" + "=" * 60)
    print("  TEST DATA PURGE")
    print("=" * 60)

    # ── Show ALL current sessions ─────────────────────────────
    with database.get_conn() as conn:
        sessions = [dict(r) for r in conn.execute("""
            SELECT s.session_id, s.day_of_week, s.start_time, s.end_time,
                   c.course_code, c.course_id
            FROM sessions s
            JOIN courses c ON s.course_id = c.course_id
            ORDER BY s.session_id
        """).fetchall()]

    if not sessions:
        print("  No sessions in database. Nothing to do.\n")
        return

    print("\n  ALL sessions currently in database:\n")
    test_session_ids = []
    test_course_ids = set()
    for s in sessions:
        is_test = any(s["course_code"].upper().startswith(p)
                      for p in TEST_PREFIXES)
        tag = "  <-- TEST (will delete)" if is_test else "  (real - keep)"
        print(f"   id={s['session_id']:<3} {s['day_of_week']}  "
              f"{s['start_time']}-{s['end_time']}  "
              f"{s['course_code']:<11}{tag}")
        if is_test:
            test_session_ids.append(s["session_id"])
            test_course_ids.add(s["course_id"])

    if not test_session_ids:
        print("\n  No test sessions found. Database is clean.\n")
        return

    print(f"\n  Will delete {len(test_session_ids)} test session(s) "
          f"and {len(test_course_ids)} test course(s),")
    print("  plus any attendance/intruder/cancellation rows tied to them.")
    print("  Real timetable sessions will be KEPT.")

    confirm = input("\n  Type 'PURGE' to confirm: ").strip()
    if confirm != "PURGE":
        print("  Cancelled. Nothing deleted.\n")
        return

    with database.get_conn() as conn:
        for sid in test_session_ids:
            conn.execute("DELETE FROM attendance WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM intruders WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM session_cancellations WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
        for cid in test_course_ids:
            conn.execute("DELETE FROM courses WHERE course_id = ?", (cid,))

    print(f"\n  [OK] Purged {len(test_session_ids)} test session(s) "
          f"and {len(test_course_ids)} test course(s).")
    print("  [OK] Real timetable preserved.\n")


if __name__ == "__main__":
    main()