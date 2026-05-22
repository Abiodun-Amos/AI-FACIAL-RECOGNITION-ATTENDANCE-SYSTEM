"""
Retention Manager — Rolling 5-Year Sync-Gated Pruner
======================================================
Runs once daily (cron/systemd on the Orange Pi; manually during
development). Deletes records whose date is exactly RETENTION_YEARS
ago today — BUT ONLY if synced=1. Unsynced records are NEVER
deleted regardless of age.

This safety gate makes data loss structurally impossible:
a record must reach the cloud before it can be pruned locally.

What gets pruned:
  • attendance rows (text — tiny, but bounded)
  • intruder rows (text only — image is already on ImgBB by
    the time synced=1, so the local file is already gone)
  • session_cancellations rows

What is NEVER pruned:
  • users, courses, sessions, lecturers, lecture_halls
    (reference data — small, permanent, always needed)
  • Any row with synced=0 regardless of age

Usage:
    python -m src.retention_manager            (dry run — shows what would be pruned)
    python -m src.retention_manager --prune    (actually prune)
"""

import sys
from datetime import date, timedelta
from src import config, database


RETENTION_YEARS = 5


def _target_date():
    """The specific date we prune today: exactly RETENTION_YEARS ago."""
    today = date.today()
    try:
        target = today.replace(year=today.year - RETENTION_YEARS)
    except ValueError:
        # Handles Feb 29 in a leap year — roll back to Feb 28
        target = today.replace(year=today.year - RETENTION_YEARS,
                               day=today.day - 1)
    return target.isoformat()


def get_prunable_records(target_date):
    """
    Find all synced records dated exactly target_date.
    Returns dict of lists, keyed by table name.
    """
    with database.get_conn() as conn:
        attendance = [dict(r) for r in conn.execute("""
            SELECT a.record_id, a.timestamp, a.status,
                   u.name, c.course_code
            FROM attendance a
            JOIN users u ON a.user_id = u.user_id
            LEFT JOIN courses c ON a.course_id = c.course_id
            WHERE DATE(a.timestamp) = ?
              AND a.synced = 1
        """, (target_date,)).fetchall()]

        intruders = [dict(r) for r in conn.execute("""
            SELECT intruder_id, timestamp, confidence, image_url
            FROM intruders
            WHERE DATE(timestamp) = ?
              AND synced = 1
        """, (target_date,)).fetchall()]

        cancellations = [dict(r) for r in conn.execute("""
            SELECT cancellation_id, cancellation_date,
                   reason_category
            FROM session_cancellations
            WHERE cancellation_date = ?
              AND synced = 1
        """, (target_date,)).fetchall()]

    return {
        "attendance":     attendance,
        "intruders":      intruders,
        "cancellations":  cancellations,
    }


def get_protected_count(target_date):
    """Count unsynced records on target_date — these are KEPT."""
    with database.get_conn() as conn:
        a = conn.execute(
            "SELECT COUNT(*) n FROM attendance "
            "WHERE DATE(timestamp) = ? AND synced = 0",
            (target_date,)).fetchone()["n"]
        i = conn.execute(
            "SELECT COUNT(*) n FROM intruders "
            "WHERE DATE(timestamp) = ? AND synced = 0",
            (target_date,)).fetchone()["n"]
        c = conn.execute(
            "SELECT COUNT(*) n FROM session_cancellations "
            "WHERE cancellation_date = ? AND synced = 0",
            (target_date,)).fetchone()["n"]
    return {"attendance": a, "intruders": i, "cancellations": c}


def prune(target_date, prunable):
    """Delete the prunable records. Called only when --prune passed."""
    ids_a = [r["record_id"]      for r in prunable["attendance"]]
    ids_i = [r["intruder_id"]    for r in prunable["intruders"]]
    ids_c = [r["cancellation_id"] for r in prunable["cancellations"]]

    with database.get_conn() as conn:
        if ids_a:
            conn.execute(
                f"DELETE FROM attendance WHERE record_id IN "
                f"({','.join('?' * len(ids_a))})", ids_a)
        if ids_i:
            conn.execute(
                f"DELETE FROM intruders WHERE intruder_id IN "
                f"({','.join('?' * len(ids_i))})", ids_i)
        if ids_c:
            conn.execute(
                f"DELETE FROM session_cancellations "
                f"WHERE cancellation_id IN "
                f"({','.join('?' * len(ids_c))})", ids_c)

    return len(ids_a) + len(ids_i) + len(ids_c)


def main(do_prune=False):
    database.init_db()
    target = _target_date()

    print("\n" + "=" * 60)
    print(f"  RETENTION MANAGER")
    print(f"  Today      : {date.today().isoformat()}")
    print(f"  Target date: {target} (exactly {RETENTION_YEARS} years ago)")
    print(f"  Mode       : {'PRUNE' if do_prune else 'DRY RUN (read-only)'}")
    print("=" * 60)

    prunable  = get_prunable_records(target)
    protected = get_protected_count(target)

    total_prunable  = sum(len(v) for v in prunable.values())
    total_protected = sum(protected.values())

    print(f"\n  Synced records on {target} (eligible to prune):")
    print(f"    attendance     : {len(prunable['attendance'])}")
    print(f"    intruders      : {len(prunable['intruders'])}")
    print(f"    cancellations  : {len(prunable['cancellations'])}")
    print(f"    TOTAL          : {total_prunable}")

    if total_protected > 0:
        print(f"\n  ⚠  PROTECTED (unsynced — will NOT be pruned):")
        print(f"    attendance     : {protected['attendance']}")
        print(f"    intruders      : {protected['intruders']}")
        print(f"    cancellations  : {protected['cancellations']}")
        print(f"    These will retry sync and become prunable later.")

    if total_prunable == 0:
        print(f"\n  Nothing to prune for {target}. Done.\n")
        return

    # Show a sample of what would be pruned
    if prunable["attendance"]:
        print(f"\n  Sample attendance to prune (first 5):")
        for r in prunable["attendance"][:5]:
            print(f"    {r['timestamp']}  {r['name']}  "
                  f"{r['course_code'] or '-'}  {r['status']}")

    if prunable["intruders"]:
        print(f"\n  Sample intruders to prune (first 3):")
        for r in prunable["intruders"][:3]:
            print(f"    {r['timestamp']}  "
                  f"conf={r['confidence']:.2f}  "
                  f"url={'YES' if r['image_url'] else 'NO'}")

    if not do_prune:
        print(f"\n  DRY RUN COMPLETE — no data deleted.")
        print(f"  To actually prune: "
              f"python -m src.retention_manager --prune\n")
        return

    # Actual prune
    confirm = input(f"\n  Delete {total_prunable} record(s) from "
                    f"{target}? (Type 'PRUNE' to confirm): ").strip()
    if confirm != "PRUNE":
        print("  Cancelled — no data deleted.\n")
        return

    deleted = prune(target, prunable)
    print(f"\n  [OK] Pruned {deleted} record(s) from {target}.")
    print(f"  [OK] {total_protected} unsynced record(s) protected "
          f"and retained.")
    print(f"  [OK] Storage is bounded. Cloud retains the permanent "
          f"archive.\n")


if __name__ == "__main__":
    do_prune = "--prune" in sys.argv
    main(do_prune)

