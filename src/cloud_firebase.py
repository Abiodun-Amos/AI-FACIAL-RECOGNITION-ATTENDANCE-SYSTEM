"""
Firebase Firestore client.
===========================
Thin wrapper around firebase-admin. Initialized once with the
service-account key, then offers simple push_* methods that the
sync engine calls.

Methods raise on failure — the caller (sync engine) catches and
keeps the record as synced=0 so it retries later. NEVER mark a
record synced unless the corresponding push_* returned without
raising.
"""

import firebase_admin
from firebase_admin import credentials, firestore

from src import config


_app = None
_db = None


def _init():
    global _app, _db
    if _app is not None:
        return
    if not config.FIREBASE_KEY_PATH.exists():
        raise FileNotFoundError(
            f"Firebase key missing: {config.FIREBASE_KEY_PATH}\n"
            f"Run: python -m tests.check_credentials")
    cred = credentials.Certificate(str(config.FIREBASE_KEY_PATH))
    _app = firebase_admin.initialize_app(cred)
    _db = firestore.client()


def push_attendance(record):
    """Push one attendance row to Firestore. Doc ID = the local
    record_id, so re-runs of an in-flight push are idempotent."""
    _init()
    doc_id = f"att_{record['record_id']}"
    doc = {
        "record_id":   record["record_id"],
        "user_id":     record["user_id"],
        "name":        record["name"],
        "matric_no":   record["matric_no"],
        "user_level":  record["user_level"],
        "session_id":  record["session_id"],
        "session_date": record["session_date"],
        "course_id":   record["course_id"],
        "course_code": record["course_code"],
        "course_name": record["course_name"],
        "hall_id":     record["hall_id"],
        "hall_name":   record["hall_name"],
        "timestamp":   record["timestamp"],
        "confidence":  record["confidence"],
        "status":      record["status"],
    }
    _db.collection(config.FIRESTORE_COLLECTION_ATTENDANCE)\
        .document(doc_id).set(doc)


def push_intruder(record, image_url):
    """Push one intruder row to Firestore (with the ImgBB URL)."""
    _init()
    doc_id = f"int_{record['intruder_id']}"
    doc = {
        "intruder_id":  record["intruder_id"],
        "session_id":   record["session_id"],
        "session_date": record["session_date"],
        "hall_id":      record["hall_id"],
        "hall_name":    record["hall_name"],
        "timestamp":    record["timestamp"],
        "confidence":   record["confidence"],
        "image_url":    image_url,
    }
    _db.collection(config.FIRESTORE_COLLECTION_INTRUDERS)\
        .document(doc_id).set(doc)


def push_cancellation(record):
    _init()
    doc_id = f"can_{record['cancellation_id']}"
    doc = {
        "cancellation_id":  record["cancellation_id"],
        "session_id":       record["session_id"],
        "course_code":      record["course_code"],
        "cancellation_date": record["cancellation_date"],
        "reason_category":  record["reason_category"],
        "reason_note":      record["reason_note"],
        "cancelled_by":     record["cancelled_by"],
        "cancelled_at":     record["cancelled_at"],
    }
    _db.collection(config.FIRESTORE_COLLECTION_CANCELLATIONS)\
        .document(doc_id).set(doc)


def is_online():
    """Lightweight connectivity check via the SDK's project lookup.
    Returns True iff Firestore is reachable right now."""
    try:
        _init()
        # A trivial read — touches Firestore without writing anything.
        next(_db.collection("_ping").limit(1).stream(), None)
        return True
    except Exception:
        return False
    
# ── Reference data sync ────────────────────────────────────────

def push_reference_data():
    """
    Push all device-side reference data to Firestore so the
    dashboard can read it without hitting the local SQLite.
    Uses .set() (upsert) so re-running is safe and idempotent.
    Called by the sync engine after each cycle.
    """
    from src import database as _db_mod
    _init()

    # Users
    users = _db_mod.get_all_users()
    for u in users:
        _db.collection("users").document(
            f"user_{u['user_id']}").set({
            "user_id":         u["user_id"],
            "name":            u["name"],
            "matric_no":       u["matric_no"],
            "user_level":      u["user_level"],
            "registered_date": u["registered_date"],
        })

    # Courses
    courses = _db_mod.get_all_courses()
    for c in courses:
        _db.collection("courses").document(
            f"course_{c['course_id']}").set({
            "course_id":    c["course_id"],
            "course_code":  c["course_code"],
            "course_name":  c["course_name"],
            "course_level": c["course_level"],
        })

    # Lecturers
    lecturers = _db_mod.get_all_lecturers()
    for l in lecturers:
        _db.collection("lecturers").document(
            f"lec_{l['lecturer_id']}").set({
            "lecturer_id":  l["lecturer_id"],
            "full_name":    l["full_name"],
            "staff_id":     l["staff_id"],
            "department":   l["department"],
            "email":        l["email"],
            "phone":        l["phone"],
        })

    # Halls
    halls = _db_mod.get_all_halls()
    for h in halls:
        _db.collection("halls").document(
            f"hall_{h['hall_id']}").set({
            "hall_id":   h["hall_id"],
            "hall_name": h["hall_name"],
            "building":  h["building"],
            "capacity":  h["capacity"],
        })

    # Sessions (denormalised — dashboard doesn't need JOINs)
    sessions = _db_mod.get_all_sessions()
    for s in sessions:
        _db.collection("sessions").document(
            f"session_{s['session_id']}").set({
            "session_id":    s["session_id"],
            "day_of_week":   s["day_of_week"],
            "start_time":    s["start_time"],
            "end_time":      s["end_time"],
            "grace_minutes": s["grace_minutes"],
            "course_id":     s["course_id"],
            "course_code":   s["course_code"],
            "course_name":   s["course_name"],
            "course_level":  s["course_level"],
            "lecturer_id":   s["lecturer_id"],
            "lecturer_name": s["lecturer_name"],
            "hall_id":       s["hall_id"],
            "hall_name":     s["hall_name"],
        })

    return {
        "users": len(users), "courses": len(courses),
        "lecturers": len(lecturers), "halls": len(halls),
        "sessions": len(sessions),
    }


# ── Management commands (dashboard → Orange Pi) ────────────────

import uuid as _uuid
import datetime as _dt

MGMT_COLLECTION = "management_commands"

MGMT_TYPES = {
    "ADD_COURSE",
    "ADD_LECTURER",
    "ADD_SESSION",
    "UPDATE_SESSION",
    "DELETE_SESSION",
    "PRE_REGISTER_USER",
    "CANCEL_SESSION",
}


def write_management_command(cmd_type, payload, created_by="web_admin"):
    """
    Write a management command to Firestore.
    The reverse sync watcher on the Orange Pi polls this collection
    and applies pending commands to local SQLite.

    cmd_type must be one of MGMT_TYPES.
    payload is a dict of command-specific data.

    Returns the command document ID.
    """
    _init()
    if cmd_type not in MGMT_TYPES:
        raise ValueError(f"Unknown command type: {cmd_type}")

    cmd_id = str(_uuid.uuid4())
    doc = {
        "cmd_id":      cmd_id,
        "type":        cmd_type,
        "payload":     payload,
        "status":      "pending",
        "created_at":  _dt.datetime.now().isoformat(),
        "created_by":  created_by,
        "processed_at": None,
        "error":        None,
    }
    _db.collection(MGMT_COLLECTION).document(cmd_id).set(doc)
    return cmd_id


def get_pending_commands():
    """Fetch all pending management commands, oldest first.
    Called by the reverse sync watcher on the Orange Pi.

    Sorting is done in Python rather than Firestore to avoid
    requiring a composite index on (status, created_at) —
    appropriate given the low expected volume of pending commands.
    """
    _init()
    from google.cloud.firestore_v1.base_query import FieldFilter
    docs = (_db.collection(MGMT_COLLECTION)
               .where(filter=FieldFilter("status", "==", "pending"))
               .stream())
    commands = [d.to_dict() for d in docs]
    # Sort oldest-first in Python — no composite index needed
    return sorted(commands, key=lambda x: x.get("created_at", ""))


def mark_command_processed(cmd_id, success=True, error=None):
    """Mark a command as processed (or failed) after the Orange Pi
    has applied it to local SQLite."""
    _init()
    _db.collection(MGMT_COLLECTION).document(cmd_id).update({
        "status":       "processed" if success else "failed",
        "processed_at": _dt.datetime.now().isoformat(),
        "error":        error,
    })