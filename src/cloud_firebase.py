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