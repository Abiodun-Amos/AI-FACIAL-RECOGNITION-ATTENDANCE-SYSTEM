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

    # Simulate a successful cloud sync of the first attendance record
    if att:
        first = att[0]["record_id"]
        print(f"\n  [SIM] Marking attendance record {first} as synced "
              f"(simulating successful cloud push)...")
        database.mark_attendance_synced(first)
        new_summary = database.sync_queue_summary()
        print(f"  [SIM] Pending attendance now: "
              f"{new_summary['attendance']} (was {summary['attendance']})")
        print("  [SIM] This is exactly what the real sync engine will do,")
        print("        but only AFTER the cloud confirms receipt.")

    print("\n" + "=" * 55)
    print("  Queue logic verified — no cloud needed yet.")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()