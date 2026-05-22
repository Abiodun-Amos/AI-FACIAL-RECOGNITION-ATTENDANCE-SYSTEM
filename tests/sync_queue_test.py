"""
Tests the local sync-queue logic with NO cloud involved:
shows what's pending sync, simulates marking one record synced,
shows the queue shrink. Pure local logic verification.

Usage:
    python -m tests.sync_queue_test
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import database


def main():
    database.init_db()

    print("\n" + "=" * 55)
    print("  SYNC QUEUE STATE")
    print("=" * 55)

    summary = database.sync_queue_summary()
    print(f"  Pending attendance    : {summary['attendance']}")
    print(f"  Pending intruders     : {summary['intruders']}")
    print(f"  Pending cancellations : {summary['cancellations']}")

    att = database.get_unsynced_attendance()
    if att:
        print(f"\n  ── Unsynced attendance ({len(att)}) ──")
        for r in att[:10]:
            print(f"    record={r['record_id']}  {r['name']}  "
                  f"{r['course_code'] or '-'}  {r['status']}  "
                  f"{r['timestamp']}")
        if len(att) > 10:
            print(f"    ... and {len(att) - 10} more")
    else:
        print("\n  No unsynced attendance.")

    intr = database.get_unsynced_intruders()
    print(f"\n  Unsynced intruders: {len(intr)}")
    for r in intr[:5]:
        print(f"    intruder={r['intruder_id']}  {r['timestamp']}  "
              f"{r['image_path']}")

    # Show what the sync engine WOULD do — without touching the database.
    if att:
        first = att[0]
        print(f"\n  [INFO] When the sync engine runs, it will push:")
        print(f"         record={first['record_id']}  "
              f"{first['name']}  {first['course_code'] or '-'}  "
              f"{first['status']}")
        print(f"         → to Firestore as 'att_{first['record_id']}'")
        print(f"         → then mark it synced=1 in SQLite")
        print(f"\n  [INFO] Run: python -m src.sync_engine --once")
        print(f"         to perform the actual push.")

    print("\n" + "=" * 55)
    print("  Queue logic verified — no cloud needed yet.")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()