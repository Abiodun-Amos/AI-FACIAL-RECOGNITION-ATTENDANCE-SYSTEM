"""
Session Cancellation Tool
==========================
Allows a lecturer/admin to cancel a specific date's instance of a
recurring session, with a reason category. Used by the attendance
engine to suppress attendance for cancelled classes.

Usage:
    python -m src.manage_cancellations
"""

from datetime import datetime, date, timedelta
from src import config, database


REASON_CATEGORIES = [
    ("INSTITUTIONAL", "On institutional assignment"),
    ("LEAVE",         "On leave"),
    ("HEALTH",        "Health reasons"),
    ("HOLIDAY",       "Public/institution holiday"),
    ("OTHER",         "Other (specify in note)"),
]

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def ask(prompt, allow_empty=False):
    while True:
        v = input(prompt).strip()
        if v or allow_empty:
            return v
        print("   (required)")


def pick_session():
    """Browse all sessions in this hall and let the user pick one."""
    hall = database.get_hall_by_name(config.CURRENT_HALL_NAME)
    if not hall:
        print(f"[ERROR] Hall '{config.CURRENT_HALL_NAME}' missing.")
        return None

    all_sessions = []
    for day in DAYS[:5]:    # Mon–Fri
        for s in database.get_sessions_for_hall_day(hall["hall_id"], day):
            all_sessions.append(s)

    if not all_sessions:
        print("[ERROR] No sessions found for this hall.")
        return None

    print("\n── Available Sessions ─────────────────────────────")
    for i, s in enumerate(all_sessions, 1):
        print(f"  {i:2}. {s['day_of_week']}  {s['start_time']}–{s['end_time']}  "
              f"{s['course_code']:<8} ({s['lecturer_name']})")

    while True:
        raw = input("Select session number: ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(all_sessions):
                return all_sessions[idx - 1]
        except ValueError:
            pass
        print(f"   Enter a number between 1 and {len(all_sessions)}")


def pick_date(session):
    """Pick a date — must fall on the session's day_of_week."""
    target_day = session["day_of_week"]
    print(f"\nThis session runs on {target_day}. Pick a date that's a {target_day}.")
    print("Examples:")
    today = date.today()
    suggestions = []
    for offset in range(0, 21):
        d = today + timedelta(days=offset)
        if DAYS[d.weekday()] == target_day:
            suggestions.append(d)
        if len(suggestions) >= 3:
            break
    for d in suggestions:
        print(f"   • {d.isoformat()}  ({d.strftime('%A')})")

    while True:
        raw = ask("\nCancellation date (YYYY-MM-DD): ")
        try:
            d = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("   Format must be YYYY-MM-DD, e.g. 2026-05-18")
            continue
        if DAYS[d.weekday()] != target_day:
            print(f"   That date is a {DAYS[d.weekday()]}, but the session is on {target_day}.")
            continue
        if d < today:
            confirm = input("   That date is in the past. Continue? (y/N): ").strip().lower()
            if confirm != "y":
                continue
        return d.isoformat()


def pick_reason():
    print("\n── Reason ──────────────────────────────────────────")
    for i, (code, label) in enumerate(REASON_CATEGORIES, 1):
        print(f"   {i}. {label}")
    while True:
        raw = input("Choose reason: ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(REASON_CATEGORIES):
                return REASON_CATEGORIES[idx - 1][0]
        except ValueError:
            pass
        print(f"   Enter a number between 1 and {len(REASON_CATEGORIES)}")


def cancel_flow():
    print("\n══ CANCEL A SESSION ════════════════════════════════")

    session = pick_session()
    if session is None:
        return

    cancel_date = pick_date(session)
    if database.is_session_cancelled(session["session_id"], cancel_date):
        print(f"[INFO] This session on {cancel_date} is already cancelled.")
        return

    reason = pick_reason()
    note = ask("Optional note: ", allow_empty=True) or None
    cancelled_by = ask("Cancelled by (lecturer name / 'ADMIN'): ")

    print("\n── Confirm ─────────────────────────────────────────")
    print(f"  Course   : {session['course_code']} ({session['course_name']})")
    print(f"  Slot     : {session['day_of_week']} {session['start_time']}–{session['end_time']}")
    print(f"  Date     : {cancel_date}")
    print(f"  Reason   : {reason}")
    if note: print(f"  Note     : {note}")
    print(f"  By       : {cancelled_by}")

    if input("\nProceed? (y/N): ").strip().lower() != "y":
        print("[CANCELLED]")
        return

    database.cancel_session(session["session_id"], cancel_date,
                            reason, note, cancelled_by)
    print(f"\n[OK] Session cancelled. Attendance will be suppressed on {cancel_date}.\n")


def list_today_cancellations():
    today = date.today().isoformat()
    rows = database.get_cancellations_for_date(today)
    print(f"\n── Cancellations for {today} ────────────────────")
    if not rows:
        print("(none)\n"); return
    for r in rows:
        print(f"  • {r['course_code']} ({r['lecturer_name']}) — {r['reason_category']}")
        if r["reason_note"]:
            print(f"       Note: {r['reason_note']}")
    print()


def list_upcoming_cancellations():
    with database.get_conn() as conn:
        rows = conn.execute("""
            SELECT sc.*, c.course_code, l.full_name AS lecturer_name,
                   s.day_of_week, s.start_time, s.end_time
            FROM session_cancellations sc
            JOIN sessions s  ON sc.session_id = s.session_id
            JOIN courses  c  ON s.course_id   = c.course_id
            JOIN lecturers l ON s.lecturer_id = l.lecturer_id
            WHERE sc.cancellation_date >= DATE('now', 'localtime')
            ORDER BY sc.cancellation_date, s.start_time
        """).fetchall()
        rows = [dict(r) for r in rows]

    print("\n── Upcoming Cancellations ──────────────────────────")
    if not rows:
        print("(none)\n"); return
    for r in rows:
        print(f"  • {r['cancellation_date']}  {r['day_of_week']} "
              f"{r['start_time']}-{r['end_time']}  "
              f"{r['course_code']} ({r['lecturer_name']}) — {r['reason_category']}")
    print()


MENU = """
╔══════════════════════════════════════════════════════╗
║         SESSION CANCELLATION                         ║
╠══════════════════════════════════════════════════════╣
║   1. Cancel a session                                ║
║   2. List today's cancellations                      ║
║   3. List upcoming cancellations                     ║
║   0. Exit                                            ║
╚══════════════════════════════════════════════════════╝
"""


def main():
    database.init_db()
    while True:
        print(MENU)
        choice = input("Choose: ").strip()
        if choice == "0":
            break
        elif choice == "1":
            cancel_flow()
        elif choice == "2":
            list_today_cancellations()
        elif choice == "3":
            list_upcoming_cancellations()
        else:
            print("Invalid choice.\n")


if __name__ == "__main__":
    main()