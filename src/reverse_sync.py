"""
Reverse Sync Watcher — Cloud-to-Device Management Commands
===========================================================
Polls Firestore for management commands written by the web
dashboard and applies them to local SQLite.

This completes the bidirectional IoT architecture:
  Device → Cloud : attendance, intruders, reference data
  Cloud → Device : management commands (timetable, users)

Supported commands:
  ADD_COURSE        Add a new course to the local DB
  ADD_LECTURER      Add a new lecturer
  ADD_SESSION       Add a new recurring session (timetable slot)
  UPDATE_SESSION    Toggle a session active/inactive
  DELETE_SESSION    Deactivate a session
  PRE_REGISTER_USER Pre-register a student (face capture still at device)
  CANCEL_SESSION    Cancel a specific session date

Usage:
    python -m src.reverse_sync --once    (process pending, exit)
    python -m src.reverse_sync --loop    (run continuously)
"""

import sys
import time
import sqlite3
import traceback
from datetime import datetime

from src import config, database
from src import cloud_firebase as cf


def _log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [REVERSE/{level}] {msg}")


# ── Command handlers ───────────────────────────────────────────

def _handle_add_course(payload):
    try:
        cid = database.add_course(
            payload["course_code"],
            payload["course_name"],
            int(payload["course_level"])
        )
        _log(f"ADD_COURSE: created {payload['course_code']} "
             f"(id={cid})")
        return True, None
    except sqlite3.IntegrityError:
        # Course code already exists — idempotent
        _log(f"ADD_COURSE: {payload['course_code']} already exists "
             f"(skipped)", "WARN")
        return True, None
    except Exception as e:
        return False, str(e)


def _handle_add_lecturer(payload):
    try:
        lid = database.add_lecturer(
            payload["full_name"],
            payload.get("staff_id"),
            payload.get("department"),
            payload.get("email"),
            payload.get("phone"),
        )
        _log(f"ADD_LECTURER: created {payload['full_name']} (id={lid})")
        return True, None
    except sqlite3.IntegrityError:
        _log(f"ADD_LECTURER: {payload.get('staff_id')} already exists "
             f"(skipped)", "WARN")
        return True, None
    except Exception as e:
        return False, str(e)


def _handle_add_session(payload):
    try:
        # Resolve course_id and lecturer_id from codes if IDs not provided
        course_id = payload.get("course_id")
        if not course_id:
            c = database.get_course_by_code(payload["course_code"])
            if not c:
                return False, f"Course {payload['course_code']} not found"
            course_id = c["course_id"]

        lecturer_id = payload.get("lecturer_id")
        if not lecturer_id:
            return False, "lecturer_id required"

        hall = database.get_hall_by_name(config.CURRENT_HALL_NAME)
        hall_id = payload.get("hall_id", hall["hall_id"] if hall else None)
        if not hall_id:
            return False, "hall_id required and default hall not found"

        sid = database.add_session(
            course_id, lecturer_id, hall_id,
            payload["day_of_week"],
            payload["start_time"],
            payload["end_time"],
            int(payload.get("grace_minutes", 60))
        )
        _log(f"ADD_SESSION: created {payload.get('course_code', '')} "
             f"{payload['day_of_week']} {payload['start_time']}"
             f"–{payload['end_time']} (id={sid})")
        return True, None
    except sqlite3.IntegrityError:
        _log(f"ADD_SESSION: slot already exists (skipped)", "WARN")
        return True, None
    except Exception as e:
        return False, str(e)


def _handle_pre_register_user(payload):
    """Pre-register student details. Face capture still happens at device."""
    try:
        uid = database.add_user(
            payload["name"],
            payload["matric_no"],
            int(payload["user_level"])
        )
        _log(f"PRE_REGISTER: {payload['name']} "
             f"({payload['matric_no']}) id={uid} — "
             f"face capture needed at device")
        return True, None
    except sqlite3.IntegrityError:
        _log(f"PRE_REGISTER: {payload['matric_no']} already exists "
             f"(skipped)", "WARN")
        return True, None
    except Exception as e:
        return False, str(e)


def _handle_cancel_session(payload):
    try:
        database.cancel_session(
            int(payload["session_id"]),
            payload["cancellation_date"],
            payload.get("reason_category", "OTHER"),
            payload.get("reason_note"),
            payload.get("cancelled_by", "web_admin"),
        )
        _log(f"CANCEL_SESSION: session {payload['session_id']} "
             f"on {payload['cancellation_date']}")
        return True, None
    except sqlite3.IntegrityError:
        _log(f"CANCEL_SESSION: already cancelled (skipped)", "WARN")
        return True, None
    except Exception as e:
        return False, str(e)


def _handle_delete_session(payload):
    try:
        with database.get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET active = 0 WHERE session_id = ?",
                (int(payload["session_id"]),))
        _log(f"DELETE_SESSION: deactivated session "
             f"{payload['session_id']}")
        return True, None
    except Exception as e:
        return False, str(e)


HANDLERS = {
    "ADD_COURSE":        _handle_add_course,
    "ADD_LECTURER":      _handle_add_lecturer,
    "ADD_SESSION":       _handle_add_session,
    "PRE_REGISTER_USER": _handle_pre_register_user,
    "CANCEL_SESSION":    _handle_cancel_session,
    "DELETE_SESSION":    _handle_delete_session,
}


# ── Process one batch of pending commands ──────────────────────

def process_pending():
    commands = cf.get_pending_commands()
    if not commands:
        return 0

    _log(f"Found {len(commands)} pending command(s).")
    processed = 0

    for cmd in commands:
        cmd_id  = cmd["cmd_id"]
        cmd_type = cmd["type"]
        payload  = cmd.get("payload", {})

        handler = HANDLERS.get(cmd_type)
        if handler is None:
            _log(f"Unknown command type '{cmd_type}' — marking failed.",
                 "WARN")
            cf.mark_command_processed(cmd_id, success=False,
                                      error=f"Unknown type: {cmd_type}")
            continue

        try:
            success, error = handler(payload)
            cf.mark_command_processed(cmd_id, success=success, error=error)
            if success:
                processed += 1
            else:
                _log(f"Command {cmd_id} ({cmd_type}) failed: {error}",
                     "ERROR")
        except Exception:
            err = traceback.format_exc()
            _log(f"Unexpected error on {cmd_id}: {err}", "ERROR")
            cf.mark_command_processed(cmd_id, success=False, error=err)

    # After applying changes, re-sync reference data to cloud
    # so the dashboard sees the updated timetable/users immediately.
    if processed > 0:
        try:
            cf.push_reference_data()
            _log("Reference data re-synced after command processing.")
        except Exception as e:
            _log(f"Reference re-sync failed: {e}", "WARN")

    return processed


# ── Entry points ───────────────────────────────────────────────

def run_once():
    _log("Reverse sync starting (once mode)...")
    database.init_db()
    try:
        n = process_pending()
        _log(f"Done — processed {n} command(s).")
    except Exception as e:
        _log(f"Error: {e}", "ERROR")


def run_loop():
    _log(f"Reverse sync starting (loop mode, "
         f"interval={config.SYNC_CHECK_INTERVAL}s)...")
    database.init_db()
    while True:
        try:
            process_pending()
        except KeyboardInterrupt:
            _log("Stopped by user.")
            break
        except Exception:
            _log(f"Unexpected error:\n{traceback.format_exc()}", "ERROR")
        time.sleep(config.SYNC_CHECK_INTERVAL)


if __name__ == "__main__":
    if "--loop" in sys.argv:
        run_loop()
    elif "--once" in sys.argv:
        run_once()
    else:
        print("Usage:")
        print("  python -m src.reverse_sync --once")
        print("  python -m src.reverse_sync --loop")
        sys.exit(1)