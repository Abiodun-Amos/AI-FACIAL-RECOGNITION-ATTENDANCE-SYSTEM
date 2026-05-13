"""
Schema Migration Helper (Phase 3A → Phase 3B)
==============================================
Backs up the current users table, rebuilds the database with the
new schema, restores users with their original user_ids preserved
(so dataset folders and trainer.yml stay valid), and pre-seeds the
configured lecture hall.

Usage:
    python -m src.migrate_schema
"""

import json
import shutil
import sys
from datetime import datetime

from src import config, database


def main():
    print("\n" + "=" * 60)
    print("  SCHEMA MIGRATION — Phase 3A → Phase 3B")
    print("=" * 60)

    if not config.DATABASE_PATH.exists():
        print("[INFO] No existing database — running fresh init.")
        database.init_db()
        seed_hall()
        return

    # ── 1. Backup existing users ─────────────────────────────
    print("[1/4] Backing up users from current database...")
    try:
        users = database.get_all_users()
    except Exception as e:
        print(f"[ERROR] Could not read users: {e}")
        sys.exit(1)

    print(f"      Found {len(users)} user(s) to preserve.")

    backup_path = config.DATA_DIR / f"users_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, default=str)
    print(f"      Backup written to: {backup_path.name}")

    # ── 2. Backup the DB file itself (extra safety net) ──────
    db_backup = config.DATABASE_PATH.with_suffix(".db.bak")
    shutil.copy2(config.DATABASE_PATH, db_backup)
    print(f"      DB file backed up to: {db_backup.name}")

    # ── 3. Wipe and rebuild ──────────────────────────────────
    print("[2/4] Removing old database...")
    config.DATABASE_PATH.unlink()

    print("[3/4] Creating fresh schema...")
    database.init_db()

    # ── 4. Restore users with original IDs ───────────────────
    print(f"[4/4] Restoring {len(users)} user(s) with original IDs...")
    with database.get_conn() as conn:
        for u in users:
            conn.execute("""
                INSERT INTO users
                  (user_id, name, matric_no, user_level, registered_date)
                VALUES (?, ?, ?, ?, ?)
            """, (u["user_id"], u["name"], u["matric_no"],
                  u["user_level"], u["registered_date"]))

    seed_hall()

    print("\n" + "=" * 60)
    print("  MIGRATION COMPLETE.")
    print("  Your dataset/ folders and trainer.yml are still valid.")
    print("  No re-enrollment or re-training needed.")
    print("=" * 60 + "\n")


def seed_hall():
    """Pre-create the lecture hall configured for this device."""
    hall = database.get_hall_by_name(config.CURRENT_HALL_NAME)
    if hall is None:
        hid = database.add_hall(config.CURRENT_HALL_NAME,
                                building="EEE Block")
        print(f"      Seeded lecture hall: '{config.CURRENT_HALL_NAME}' (id={hid})")
    else:
        print(f"      Lecture hall already exists: '{config.CURRENT_HALL_NAME}'")


if __name__ == "__main__":
    main()