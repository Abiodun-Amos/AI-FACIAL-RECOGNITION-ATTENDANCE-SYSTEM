"""Quick smoke test — adds a dummy user and reads it back."""

from src import database

database.init_db()

uid = database.add_user("Test Student", "EES/21/22/9999", 400)
print(f"[OK] Inserted user with id={uid}")

users = database.get_all_users()
print(f"[OK] Users currently in DB ({len(users)}):")
for u in users:
    print(f"   • {u['user_id']} | {u['name']} | {u['matric_no']} | L{u['user_level']}")