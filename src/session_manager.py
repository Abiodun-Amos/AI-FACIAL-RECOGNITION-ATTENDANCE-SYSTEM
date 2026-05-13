"""
Session Manager
================
Determines which (if any) session is active at any given moment for
the current lecture hall. Used by the attendance engine to decide
whether and how to log a recognition.

Status logic:
  • outside any session window  → no session
  • within session, cancelled   → no session (attendance suppressed)
  • within session, ≤ grace_min from start → PRESENT
  • within session, after grace, before end → LATE

This module is intentionally small and side-effect free; it just
answers questions about time.
"""

from datetime import datetime, time as dtime
from src import config, database


DAY_LOOKUP = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def _now():
    """Returns (today_date_str, current_time, day_of_week)."""
    now = datetime.now()
    return (
        now.strftime("%Y-%m-%d"),
        now.time(),
        DAY_LOOKUP[now.weekday()],
    )


def _parse_hhmm(s):
    """'08:00' → time(8, 0)"""
    h, m = s.split(":")
    return dtime(int(h), int(m))


def _minutes_between(t_start, t_now):
    """How many minutes after t_start is t_now? (Same day assumed.)"""
    return (t_now.hour * 60 + t_now.minute) - (t_start.hour * 60 + t_start.minute)


def get_active_session(hall_id):
    """
    Return a dict describing the current active session, or None if
    no session is active right now in this hall.

    Returned dict adds 'status' = 'PRESENT' | 'LATE' and 'session_date'.
    Returns None for: weekends, break periods, after-hours, cancelled sessions.
    """
    today, current_time, day = _now()

    # Weekends are immediate-skip (your timetable is Mon–Fri)
    if day in ("SAT", "SUN"):
        return None

    # Pull every session for this hall on this day
    sessions = database.get_sessions_for_hall_day(hall_id, day)
    if not sessions:
        return None

    for s in sessions:
        start = _parse_hhmm(s["start_time"])
        end   = _parse_hhmm(s["end_time"])

        # Are we inside this session's window?
        if start <= current_time <= end:
            # Cancellation check — most important guard
            if database.is_session_cancelled(s["session_id"], today):
                # Lecturer cancelled this specific date → suppress attendance
                return None

            # Determine PRESENT vs LATE based on grace period
            elapsed_min = _minutes_between(start, current_time)
            if elapsed_min <= s["grace_minutes"]:
                status = "PRESENT"
            else:
                status = "LATE"

            return {
                **s,
                "status": status,
                "session_date": today,
                "elapsed_minutes": elapsed_min,
            }

    return None


def describe_session(session):
    """Human-readable one-liner, used for HUD / logs."""
    if session is None:
        return "No active session"
    return (
        f"{session['course_code']} "
        f"({session['start_time']}–{session['end_time']}) "
        f"[{session['status']}] "
        f"Lecturer: {session['lecturer_name']}"
    )


# ── Quick standalone test ─────────────────────────────────────
if __name__ == "__main__":
    hall = database.get_hall_by_name(config.CURRENT_HALL_NAME)
    if not hall:
        print(f"[ERROR] Hall '{config.CURRENT_HALL_NAME}' not in DB.")
    else:
        s = get_active_session(hall["hall_id"])
        print(f"\nHall   : {config.CURRENT_HALL_NAME}")
        print(f"Time   : {datetime.now().strftime('%A %d %b %Y, %H:%M')}")
        print(f"Status : {describe_session(s)}\n")