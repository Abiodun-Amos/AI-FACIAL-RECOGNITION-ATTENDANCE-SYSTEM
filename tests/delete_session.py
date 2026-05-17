"""
Surgically delete ONE session by its session_id, leaving the
course (and everything else) intact. Shows the session and asks
for confirmation before deleting.

Usage:
    python -m tests.delete_session <session_id>
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import database


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m tests.delete_session <session_id>")
        sys.exit(1)
    try:
        sid = int(sys.argv[1])
    except ValueError:
        print("[ERROR] session_id must be a number.")
        sys.exit(1)

    database.init_db()
    with database.get_conn() as conn:
        row = conn.execute("""
            SELECT s.session_id, s.day_of_week, s.start_time, s.end_time,
                   c.course_code, c.course_name
            FROM sessions s
            JOIN courses c ON s.course_id = c.course_id
            WHERE s.session_id = ?
        """, (sid,)).fetchone()

        if row is None:
            print(f"[INFO] No session with id={sid}. Nothing to do.")
            return
        r = dict(row)

        print("\n  About to delete THIS session (course is kept):")
        print(f"    session_id : {r['session_id']}")
        print(f"    course     : {r['course_code']} — {r['course_name']}")
        print(f"    slot       : {r['day_of_week']} "
              f"{r['start_time']}–{r['end_time']}")
        print("    (the EEG510 course itself will NOT be deleted)")

        if input("\n  Type 'DELETE' to confirm: ").strip() != "DELETE":
            print("  Cancelled.\n")
            return

        conn.execute("DELETE FROM attendance WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM intruders WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM session_cancellations WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))

    print(f"\n  [OK] Session id={sid} deleted. Course preserved.\n")


if __name__ == "__main__":
    main()