"""
Store-and-Forward Sync Engine
==============================
Background watchdog that pushes locally-queued records to the
cloud whenever the network is available.

Design principles:
  • Records are marked synced=1 ONLY after the cloud confirms
    receipt — never before. Data loss is structurally impossible.
  • Per-record error isolation: one bad record never breaks the
    batch. It stays synced=0 and retries next cycle.
  • Intruder images are deleted locally after confirmed upload to
    ImgBB — the URL in Firestore is the permanent reference.
  • Runs offline gracefully: if no connectivity, sleeps and retries.

Two modes:
  --once    Push everything pending right now, then exit.
            (For manual testing and cron-style invocation.)
  --loop    Run continuously, checking every SYNC_CHECK_INTERVAL
            seconds. (Production mode on the Orange Pi.)

Usage:
    python -m src.sync_engine --once
    python -m src.sync_engine --loop
"""

import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from src import config, database
from src import cloud_firebase as cf
from src import cloud_imgbb   as ci


# ── Logging helper ─────────────────────────────────────────────
def _log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


# ── Connectivity ───────────────────────────────────────────────
def is_connected():
    """Check connectivity by attempting a lightweight Firestore
    read. Returns True iff the cloud is reachable right now."""
    try:
        return cf.is_online()
    except Exception:
        return False


# ── Individual sync operations ─────────────────────────────────
def _sync_attendance_record(record):
    """Push one attendance row to Firestore. Returns True on
    success, False on any failure (will retry next cycle)."""
    try:
        cf.push_attendance(record)
        database.mark_attendance_synced(record["record_id"])
        _log(f"ATT synced: record={record['record_id']} "
             f"{record['name']} {record['course_code'] or '-'} "
             f"{record['status']}")
        return True
    except Exception as e:
        _log(f"ATT failed: record={record['record_id']} — "
             f"{type(e).__name__}: {e}", "WARN")
        return False


def _sync_intruder_record(record):
    """Upload intruder image to ImgBB, push metadata to Firestore,
    mark synced=1, then delete the local image file."""
    try:
        img_path = record["image_path"]
        if not Path(img_path).exists():
            # Image file was already deleted (e.g., prior partial
            # sync). Just mark it synced so we stop retrying.
            _log(f"INT skipped (image gone): "
                 f"intruder={record['intruder_id']}", "WARN")
            database.mark_intruder_synced(record["intruder_id"])
            return True

        # Step 1: upload image to ImgBB
        image_url = ci.upload(img_path)

        # Step 2: push metadata + URL to Firestore
        cf.push_intruder(record, image_url)

        # Step 3: mark synced in local DB (with URL stored)
        database.mark_intruder_synced(record["intruder_id"], image_url)

        # Step 4: delete local image (now permanently on ImgBB)
        try:
            Path(img_path).unlink()
            _log(f"INT synced + local deleted: "
                 f"intruder={record['intruder_id']} → {image_url}")
        except OSError as del_err:
            # Sync succeeded even if delete fails — not critical
            _log(f"INT synced but delete failed: {del_err}", "WARN")

        return True

    except Exception as e:
        _log(f"INT failed: intruder={record['intruder_id']} — "
             f"{type(e).__name__}: {e}", "WARN")
        return False


def _sync_cancellation_record(record):
    try:
        cf.push_cancellation(record)
        database.mark_cancellation_synced(record["cancellation_id"])
        _log(f"CAN synced: cancellation={record['cancellation_id']} "
             f"{record['course_code']} {record['cancellation_date']}")
        return True
    except Exception as e:
        _log(f"CAN failed: cancellation={record['cancellation_id']} — "
             f"{type(e).__name__}: {e}", "WARN")
        return False


# ── One complete sync cycle ────────────────────────────────────
def run_sync_cycle():
    """
    Push everything pending. Called by both --once and --loop.
    Returns a dict of counts: pushed, failed, skipped.
    """
    summary = database.sync_queue_summary()
    total_pending = sum(summary.values())

    if total_pending == 0:
        _log("Queue empty — nothing to sync.")
        return {"pushed": 0, "failed": 0}

    _log(f"Queue: {summary['attendance']} attendance, "
         f"{summary['intruders']} intruders, "
         f"{summary['cancellations']} cancellations. "
         f"Pushing...")

    pushed = failed = 0

    # Attendance
    for rec in database.get_unsynced_attendance():
        if _sync_attendance_record(rec):
            pushed += 1
        else:
            failed += 1

    # Intruders
    for rec in database.get_unsynced_intruders():
        if _sync_intruder_record(rec):
            pushed += 1
        else:
            failed += 1

    # Cancellations
    for rec in database.get_unsynced_cancellations():
        if _sync_cancellation_record(rec):
            pushed += 1
        else:
            failed += 1

    _log(f"Cycle done — pushed: {pushed}, failed: {failed}")
    if failed > 0:
        _log(f"{failed} record(s) will retry next cycle.", "WARN")
    return {"pushed": pushed, "failed": failed}


# ── Entry points ───────────────────────────────────────────────
def run_once():
    """Push everything pending right now and exit."""
    _log("Sync engine starting (once mode)...")
    database.init_db()

    if not is_connected():
        _log("Offline — cannot sync right now. "
             "Records remain queued locally.", "WARN")
        _log("Run again when connected.")
        return

    _log("Online — starting sync cycle.")
    run_sync_cycle()
    _log("Sync engine done.")


def run_loop():
    """Run continuously. Checks every SYNC_CHECK_INTERVAL seconds."""
    _log(f"Sync engine starting (loop mode, "
         f"interval={config.SYNC_CHECK_INTERVAL}s)...")
    database.init_db()

    consecutive_failures = 0
    MAX_BACKOFF = 300  # cap sleep at 5 min after repeated failures

    while True:
        try:
            if is_connected():
                consecutive_failures = 0
                run_sync_cycle()
            else:
                _log("Offline — waiting for connectivity...", "WARN")

        except KeyboardInterrupt:
            _log("Sync engine stopped by user.")
            break
        except Exception:
            # Catch-all so one unexpected error never kills the loop
            consecutive_failures += 1
            sleep_t = min(
                config.SYNC_CHECK_INTERVAL * (2 ** consecutive_failures),
                MAX_BACKOFF
            )
            _log(f"Unexpected error (attempt {consecutive_failures}). "
                 f"Retrying in {sleep_t}s:\n{traceback.format_exc()}", "ERROR")
            time.sleep(sleep_t)
            continue

        time.sleep(config.SYNC_CHECK_INTERVAL)


# ── CLI ────────────────────────────────────────────────────────
if __name__ == "__main__":
    if "--loop" in sys.argv:
        run_loop()
    elif "--once" in sys.argv:
        run_once()
    else:
        print("Usage:")
        print("  python -m src.sync_engine --once   (push now, then exit)")
        print("  python -m src.sync_engine --loop   (run continuously)")
        sys.exit(1)