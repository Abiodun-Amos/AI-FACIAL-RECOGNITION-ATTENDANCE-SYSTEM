"""
View today's attendance and intruder records.
Updated for Phase 3B — shows course, status, lecturer, and hall.

Usage:
    python -m src.view_attendance
"""

from datetime import datetime
from src import database


def show_attendance():
    rows = database.get_todays_attendance()
    print("\n" + "═" * 90)
    print(f"  ATTENDANCE — {datetime.now().strftime('%A, %d %B %Y')}")
    print("═" * 90)

    if not rows:
        print("  No attendance recorded today.\n")
        return

    # Group records by course for readability
    by_course = {}
    for r in rows:
        key = r["course_code"] or "(no session)"
        by_course.setdefault(key, []).append(r)

    for course_code, records in by_course.items():
        first = records[0]
        course_name = first["course_name"] or "—"
        lecturer    = first["lecturer_name"] or "—"
        hall        = first["hall_name"] or "—"
        print(f"\n  📘 {course_code}  — {course_name}")
        print(f"     Lecturer: {lecturer}   |   Hall: {hall}")
        print("     " + "-" * 80)
        print(f"     {'TIME':<10} {'STATUS':<9} {'NAME':<25} {'MATRIC':<18} "
              f"{'LVL':<5} {'CONF'}")
        for r in records:
            ts = r["timestamp"].split(" ")[1][:8]
            print(f"     {ts:<10} {r['status']:<9} {r['name']:<25} "
                  f"{r['matric_no']:<18} {r['user_level']:<5} {r['confidence']:.1f}")

    print(f"\n  Total: {len(rows)} attendance record(s) across "
          f"{len(by_course)} course(s).\n")


def show_intruders():
    rows = database.get_todays_intruders()
    print("═" * 90)
    print("  INTRUDER ALERTS — TODAY")
    print("═" * 90)

    if not rows:
        print("  No intruder alerts today.\n")
        return

    print(f"\n  {'TIME':<10} {'CONF':<7} {'HALL':<22} {'COURSE':<10} "
          f"{'SYNCED':<8} IMAGE")
    print("  " + "-" * 86)
    for r in rows:
        ts = r["timestamp"].split(" ")[1][:8]
        synced = "YES" if r["synced"] else "no"
        course = r["course_code"] or "-"
        hall = r["hall_name"] or "-"
        print(f"  {ts:<10} {r['confidence']:<7.1f} {hall:<22} {course:<10} "
              f"{synced:<8} {r['image_path']}")
    print(f"\n  Total: {len(rows)} intruder snapshot(s).\n")


if __name__ == "__main__":
    show_attendance()
    show_intruders()