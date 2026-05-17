"""
Diagnostic: dump all sessions, the current day/time, and what the
session manager returns right now. Read-only, safe to run anytime.

Usage:
    python -m tests.diagnose_sessions
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from src import config, database
from src.session_manager import get_active_session, describe_session

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def main():
    database.init_db()

    # ── 1. Current day / time ─────────────────────────────────
    now = datetime.now()
    print("\n" + "=" * 55)
    print("  SESSION DIAGNOSTIC")
    print("=" * 55)
    print(f"  Now      : {now.strftime('%A %d %b %Y, %H:%M:%S')}")
    print(f"  Day code : {DAYS[now.weekday()]}")
    print(f"  Time     : {now.strftime('%H:%M')}")

    # ── 2. All sessions in the DB ─────────────────────────────
    print("\n  ── All sessions in database ──")
    with database.get_conn() as conn:
        rows = conn.execute("""
            SELECT s.session_id, s.day_of_week, s.start_time, s.end_time,
                   s.grace_minutes, c.course_code, h.hall_name
            FROM sessions s
            JOIN courses c ON s.course_id = c.course_id
            JOIN lecture_halls h ON s.hall_id = h.hall_id
            ORDER BY s.day_of_week, s.start_time
        """).fetchall()
        rows = [dict(r) for r in rows]

    if not rows:
        print("    (NO SESSIONS AT ALL — the test session was NOT created)")
    else:
        for r in rows:
            print(f"    id={r['session_id']:<3} {r['day_of_week']}  "
                  f"{r['start_time']}–{r['end_time']}  "
                  f"{r['course_code']:<9} @ {r['hall_name']} "
                  f"(grace {r['grace_minutes']})")

    # ── 3. Hall lookup ────────────────────────────────────────
    hall = database.get_hall_by_name(config.CURRENT_HALL_NAME)
    print(f"\n  Hall '{config.CURRENT_HALL_NAME}': "
          f"{'FOUND id=' + str(hall['hall_id']) if hall else 'NOT FOUND'}")

    # ── 4. What does the session manager return NOW? ──────────
    if hall:
        active = get_active_session(hall["hall_id"])
        print(f"\n  Session manager says: {describe_session(active)}")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()