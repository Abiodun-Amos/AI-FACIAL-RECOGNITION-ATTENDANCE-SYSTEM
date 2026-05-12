"""
Admin Utilities
================
Tools for managing enrolled users — wipe a user cleanly from both
the database and the filesystem dataset, list all users, etc.

Usage:
    python -m src.admin_tools list
    python -m src.admin_tools delete <user_id>
"""

import sys
import shutil

from src import config, database


def list_users():
    users = database.get_all_users()
    if not users:
        print("[INFO] No users enrolled.")
        return

    print(f"\n{'ID':<5} {'NAME':<25} {'MATRIC':<20} {'LEVEL':<6} IMAGES")
    print("-" * 70)
    for u in users:
        folder = config.DATASET_DIR / str(u["user_id"])
        img_count = len(list(folder.glob("*.jpg"))) if folder.exists() else 0
        print(f"{u['user_id']:<5} {u['name']:<25} {u['matric_no']:<20} "
              f"{u['user_level']:<6} {img_count}")
    print()


def delete_user(user_id: int):
    user = database.get_user_by_id(user_id)
    if not user:
        print(f"[ERROR] No user with id={user_id}")
        return

    print(f"\nAbout to permanently delete:")
    print(f"   user_id    : {user['user_id']}")
    print(f"   name       : {user['name']}")
    print(f"   matric_no  : {user['matric_no']}")
    print(f"   level      : {user['user_level']}")

    folder = config.DATASET_DIR / str(user_id)
    img_count = len(list(folder.glob("*.jpg"))) if folder.exists() else 0
    print(f"   images     : {img_count} (in {folder})")

    confirm = input("\nType 'DELETE' to confirm: ").strip()
    if confirm != "DELETE":
        print("[CANCELLED]")
        return

    # ── Wipe filesystem ─────────────────────────────────────
    if folder.exists():
        shutil.rmtree(folder)
        print(f"[OK] Removed folder: {folder}")

    # ── Wipe database rows ──────────────────────────────────
    with database.get_conn() as conn:
        conn.execute("DELETE FROM attendance WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users      WHERE user_id = ?", (user_id,))
    print(f"[OK] Removed DB rows for user_id={user_id}")

    print(f"\n[DONE] User {user['name']} fully removed.")
    print("       Don't forget to re-run train_model.py after re-enrolling.\n")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m src.admin_tools list")
        print("  python -m src.admin_tools delete <user_id>")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "list":
        list_users()
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("[ERROR] Usage: python -m src.admin_tools delete <user_id>")
            sys.exit(1)
        try:
            delete_user(int(sys.argv[2]))
        except ValueError:
            print("[ERROR] user_id must be a number.")
    else:
        print(f"[ERROR] Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()