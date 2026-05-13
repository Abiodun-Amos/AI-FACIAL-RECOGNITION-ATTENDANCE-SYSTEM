"""
Timetable Management CLI
=========================
Interactive tool to set up the weekly teaching timetable:
  • Add lecturers
  • Add courses
  • Add lecture halls
  • Add sessions (the recurring weekly slots)
  • List / view everything

Usage:
    python -m src.manage_timetable
"""

import sys
from datetime import datetime

from src import config, database


DAYS = ["MON", "TUE", "WED", "THU", "FRI"]


# ════════════════════════════════════════════════════════════
#  Input helpers
# ════════════════════════════════════════════════════════════

def ask(prompt, allow_empty=False):
    while True:
        val = input(prompt).strip()
        if val or allow_empty:
            return val
        print("   (required)")


def ask_int(prompt, valid_options=None):
    while True:
        raw = input(prompt).strip()
        try:
            n = int(raw)
            if valid_options is None or n in valid_options:
                return n
            print(f"   Must be one of: {valid_options}")
        except ValueError:
            print("   Numbers only.")


def ask_time(prompt):
    """Returns 'HH:MM' after validating."""
    while True:
        raw = input(prompt).strip()
        try:
            t = datetime.strptime(raw, "%H:%M")
            return t.strftime("%H:%M")
        except ValueError:
            print("   Format must be HH:MM (24-hour), e.g. 08:00 or 14:30")


def ask_choice(prompt, choices):
    """Generic numeric chooser from a list of (id, label) tuples."""
    if not choices:
        return None
    print(prompt)
    for idx, (_, label) in enumerate(choices, 1):
        print(f"   {idx}. {label}")
    while True:
        raw = input("   > ").strip()
        try:
            n = int(raw)
            if 1 <= n <= len(choices):
                return choices[n - 1][0]
        except ValueError:
            pass
        print(f"   Enter a number between 1 and {len(choices)}")


# ════════════════════════════════════════════════════════════
#  Add operations
# ════════════════════════════════════════════════════════════

def add_lecturer():
    print("\n── Add Lecturer ─────────────────────────────────")
    name        = ask("Full name (e.g. Engr. Frank Onaifo) : ")
    staff_id    = ask("Staff ID (e.g. OOU/EEE/045)        : ", allow_empty=True) or None
    department  = ask("Department [Electrical Electronics]: ", allow_empty=True) \
                  or "Electrical Electronics"
    email       = ask("Email (optional)                   : ", allow_empty=True) or None
    phone       = ask("Phone (optional)                   : ", allow_empty=True) or None

    try:
        lid = database.add_lecturer(name, staff_id, department, email, phone)
        print(f"[OK] Added lecturer (id={lid}): {name}")
    except Exception as e:
        print(f"[ERROR] {e}")


def add_course():
    print("\n── Add Course ───────────────────────────────────")
    code  = ask("Course code (e.g. EES501)                  : ").upper()
    name  = ask("Course name (e.g. Power Systems Analysis)  : ")
    level = ask_int("Level (100/200/300/400/500/600)            : ",
                    valid_options=[100, 200, 300, 400, 500, 600])

    try:
        cid = database.add_course(code, name, level)
        print(f"[OK] Added course (id={cid}): {code} — {name} (L{level})")
    except Exception as e:
        print(f"[ERROR] {e}")


def add_hall():
    print("\n── Add Lecture Hall ─────────────────────────────")
    name     = ask("Hall name (e.g. Electrical Hall 1) : ")
    building = ask("Building (optional)               : ", allow_empty=True) or None
    cap_raw  = ask("Capacity (optional, blank=skip)   : ", allow_empty=True)
    capacity = int(cap_raw) if cap_raw.isdigit() else None

    try:
        hid = database.add_hall(name, building, capacity)
        print(f"[OK] Added hall (id={hid}): {name}")
    except Exception as e:
        print(f"[ERROR] {e}")


def add_session():
    print("\n── Add Session (recurring weekly slot) ──────────")

    courses = [(c["course_id"], f"{c['course_code']} — {c['course_name']} (L{c['course_level']})")
               for c in database.get_all_courses()]
    if not courses:
        print("[ERROR] No courses defined yet. Add a course first.")
        return
    course_id = ask_choice("Select course:", courses)

    lecturers = [(l["lecturer_id"], f"{l['full_name']}" +
                  (f" ({l['staff_id']})" if l["staff_id"] else ""))
                 for l in database.get_all_lecturers()]
    if not lecturers:
        print("[ERROR] No lecturers defined yet. Add a lecturer first.")
        return
    lecturer_id = ask_choice("Select lecturer:", lecturers)

    halls = [(h["hall_id"], h["hall_name"]) for h in database.get_all_halls()]
    if not halls:
        print("[ERROR] No halls defined yet. Add a hall first.")
        return
    hall_id = ask_choice("Select hall:", halls)

    print("\nSelect day:")
    for i, d in enumerate(DAYS, 1):
        print(f"   {i}. {d}")
    day_idx = ask_int("   > ", valid_options=list(range(1, 6)))
    day = DAYS[day_idx - 1]

    start = ask_time("Start time (HH:MM, e.g. 08:00) : ")
    end   = ask_time("End time   (HH:MM, e.g. 10:00) : ")

    grace_raw = ask("Grace period in minutes [60]   : ", allow_empty=True)
    grace = int(grace_raw) if grace_raw.isdigit() else 60

    try:
        sid = database.add_session(course_id, lecturer_id, hall_id,
                                   day, start, end, grace)
        print(f"[OK] Added session (id={sid}) → {day} {start}-{end}, grace {grace} min")
    except Exception as e:
        print(f"[ERROR] {e}")
        print("       (a session may already exist at that hall/day/time)")


# ════════════════════════════════════════════════════════════
#  View operations
# ════════════════════════════════════════════════════════════

def list_lecturers():
    rows = database.get_all_lecturers()
    print("\n── Lecturers ────────────────────────────────────")
    if not rows:
        print("(none)\n"); return
    print(f"{'ID':<4} {'NAME':<30} {'STAFF ID':<18} {'DEPT'}")
    print("-" * 75)
    for r in rows:
        print(f"{r['lecturer_id']:<4} {r['full_name']:<30} "
              f"{(r['staff_id'] or '-'):<18} {r['department'] or '-'}")
    print()


def list_courses():
    rows = database.get_all_courses()
    print("\n── Courses ──────────────────────────────────────")
    if not rows:
        print("(none)\n"); return
    print(f"{'ID':<4} {'CODE':<10} {'NAME':<40} LEVEL")
    print("-" * 65)
    for r in rows:
        print(f"{r['course_id']:<4} {r['course_code']:<10} "
              f"{r['course_name']:<40} {r['course_level']}")
    print()


def list_halls():
    rows = database.get_all_halls()
    print("\n── Lecture Halls ────────────────────────────────")
    if not rows:
        print("(none)\n"); return
    print(f"{'ID':<4} {'NAME':<25} {'BUILDING':<20} CAPACITY")
    print("-" * 65)
    for r in rows:
        print(f"{r['hall_id']:<4} {r['hall_name']:<25} "
              f"{(r['building'] or '-'):<20} {r['capacity'] or '-'}")
    print()


def list_full_timetable():
    """Pretty-print the full weekly timetable, grouped by hall and day."""
    print("\n── Weekly Timetable ─────────────────────────────")
    halls = database.get_all_halls()
    if not halls:
        print("(no halls defined)\n"); return

    for hall in halls:
        print(f"\n🏛  {hall['hall_name']}")
        print("=" * 70)
        for day in DAYS:
            sessions = database.get_sessions_for_hall_day(hall["hall_id"], day)
            print(f"\n  {day}")
            if not sessions:
                print("    (no sessions)")
                continue
            for s in sessions:
                print(f"    {s['start_time']}–{s['end_time']}  "
                      f"{s['course_code']:<8} L{s['course_level']}  "
                      f"({s['course_name']})")
                print(f"               Lecturer: {s['lecturer_name']}  "
                      f"| Grace: {s['grace_minutes']} min")
    print()


# ════════════════════════════════════════════════════════════
#  Main menu
# ════════════════════════════════════════════════════════════

MENU = """
╔══════════════════════════════════════════════════════╗
║           TIMETABLE MANAGEMENT                       ║
╠══════════════════════════════════════════════════════╣
║   ADD                                                ║
║     1. Add lecturer                                  ║
║     2. Add course                                    ║
║     3. Add lecture hall                              ║
║     4. Add session (recurring weekly slot)           ║
║                                                      ║
║   VIEW                                               ║
║     5. List lecturers                                ║
║     6. List courses                                  ║
║     7. List halls                                    ║
║     8. View full weekly timetable                    ║
║                                                      ║
║     0. Exit                                          ║
╚══════════════════════════════════════════════════════╝
"""

ACTIONS = {
    "1": add_lecturer,
    "2": add_course,
    "3": add_hall,
    "4": add_session,
    "5": list_lecturers,
    "6": list_courses,
    "7": list_halls,
    "8": list_full_timetable,
}


def main():
    database.init_db()
    while True:
        print(MENU)
        choice = input("Choose an option: ").strip()
        if choice == "0":
            print("Goodbye.\n"); break
        action = ACTIONS.get(choice)
        if action:
            action()
        else:
            print("Invalid choice.\n")


if __name__ == "__main__":
    main()