"""
Student Enrollment Module  (v3 — guided multi-pose capture)
============================================================
Captures face samples across MULTIPLE GUIDED HEAD POSES instead of
just frontal frames. This dramatically improves LBPH recognition
robustness when a student's head is turned or tilted.

Also supports RE-ENROLLING an existing user — replaces their face
images while keeping their database record (name/matric/level).

Usage:
    python -m src.enroll_user
"""

import cv2
import sqlite3
import sys
import time
import shutil

from src import config, database
from src.face_utils import preprocess_face


def ask(prompt, allow_empty=False):
    while True:
        v = input(prompt).strip()
        if v or allow_empty:
            return v
        print("   (required)")


# ────────────────────────────────────────────────────────────
#  Mode selection
# ────────────────────────────────────────────────────────────
def choose_mode():
    print("\n" + "=" * 52)
    print("  STUDENT ENROLLMENT")
    print("=" * 52)
    print("  1. Enroll a NEW student")
    print("  2. RE-ENROLL an existing student (replace face images)")
    print("  0. Cancel")
    while True:
        c = input("Choose: ").strip()
        if c in ("0", "1", "2"):
            return c
        print("   Enter 0, 1 or 2.")


def get_new_user():
    print("\n── New Student Details ──────────────────────────")
    name = ask("Full name           : ")
    matric_no = ask("Matric number       : ").upper()
    while True:
        try:
            level = int(ask("Level (100/200/...) : "))
            if level in (100, 200, 300, 400, 500, 600):
                break
            print("   Enter a valid level.")
        except ValueError:
            print("   Numbers only.")
    try:
        uid = database.add_user(name, matric_no, level)
        print(f"[OK] Registered '{name}' as user_id={uid}")
        return uid, name
    except sqlite3.IntegrityError:
        print(f"[ERROR] Matric '{matric_no}' already exists.")
        print("        Use option 2 (re-enroll) instead.")
        sys.exit(1)


def pick_existing_user():
    users = database.get_all_users()
    if not users:
        print("[ERROR] No users enrolled yet. Use option 1 first.")
        sys.exit(1)
    print("\n── Existing Students ────────────────────────────")
    for u in users:
        print(f"   {u['user_id']}. {u['name']}  "
              f"({u['matric_no']}, L{u['user_level']})")
    while True:
        raw = input("Enter user_id to re-enroll: ").strip()
        try:
            uid = int(raw)
            user = database.get_user_by_id(uid)
            if user:
                folder = config.DATASET_DIR / str(uid)
                old_count = len(list(folder.glob("*.jpg"))) if folder.exists() else 0
                print(f"\n  This will DELETE {old_count} existing face image(s)")
                print(f"  for '{user['name']}' and capture fresh ones.")
                print(f"  The database record (name/matric/level) is kept.")
                if input("  Type 'YES' to confirm: ").strip() == "YES":
                    if folder.exists():
                        shutil.rmtree(folder)
                    return uid, user["name"]
                print("  Cancelled.")
                sys.exit(0)
            print("   No user with that id.")
        except ValueError:
            print("   Numbers only.")


# ────────────────────────────────────────────────────────────
#  Guided multi-pose capture
# ────────────────────────────────────────────────────────────
def capture_pose(cap, face_cascade, user_dir, user_id, name,
                 pose_name, pose_instruction, pose_index, total_poses):
    """Capture IMAGES_PER_POSE samples for a single guided pose.
       Returns number captured, or -1 if the user aborted."""

    # ── Phase 1: 3-second GET READY countdown ──
    countdown_end = time.time() + 3
    while time.time() < countdown_end:
        ret, frame = cap.read()
        if not ret:
            continue
        remaining = int(countdown_end - time.time()) + 1
        _draw_banner(frame, name, pose_name, pose_instruction,
                     pose_index, total_poses)
        cv2.putText(frame, f"Get ready... {remaining}",
                    (frame.shape[1] // 2 - 130, frame.shape[0] // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 0), 3)
        cv2.imshow("Enrollment", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            return -1

    # ── Phase 2: capture loop ──
    captured = 0
    last_t = 0
    INTERVAL = 0.3
    existing = len(list(user_dir.glob("*.jpg")))   # continue numbering

    while captured < config.IMAGES_PER_POSE:
        ret, frame = cap.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=config.HAAR_SCALE_FACTOR,
            minNeighbors=config.HAAR_MIN_NEIGHBORS,
            minSize=config.HAAR_MIN_SIZE,
        )

        if len(faces) == 1 and (time.time() - last_t) > INTERVAL:
            (x, y, w, h) = faces[0]
            processed = preprocess_face(gray, (x, y, w, h))
            idx = existing + captured + 1
            fname = user_dir / f"{user_id}_{pose_name}_{idx:03d}.jpg"
            cv2.imwrite(str(fname), processed)
            captured += 1
            last_t = time.time()
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        else:
            for (x, y, w, h) in faces:
                col = (0, 255, 255) if len(faces) == 1 else (0, 0, 255)
                cv2.rectangle(frame, (x, y), (x + w, y + h), col, 2)
            msg = ("No face detected" if len(faces) == 0
                   else "Hold the pose..." if len(faces) == 1
                   else f"{len(faces)} faces - need exactly 1")
            cv2.putText(frame, msg, (15, 135),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        _draw_banner(frame, name, pose_name, pose_instruction,
                     pose_index, total_poses)
        cv2.putText(frame, f"{captured}/{config.IMAGES_PER_POSE}",
                    (frame.shape[1] - 120, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        cv2.imshow("Enrollment", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            return -1

    return captured


def _draw_banner(frame, name, pose_name, instruction, idx, total):
    """Shared top-banner overlay."""
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 100), (0, 0, 0), -1)
    cv2.putText(frame, f"ENROLLING: {name.upper()}", (15, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.putText(frame, f"POSE {idx}/{total}:  {pose_name}", (15, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, instruction, (15, 86),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.putText(frame, "'q' to abort", (10, frame.shape[0] - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)


def main():
    database.init_db()
    mode = choose_mode()
    if mode == "0":
        print("Cancelled.")
        return
    user_id, name = get_new_user() if mode == "1" else pick_existing_user()

    user_dir = config.DATASET_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        sys.exit(1)

    poses = config.ENROLLMENT_POSES
    total = len(poses)
    total_target = total * config.IMAGES_PER_POSE

    print(f"\n[INFO] Guided enrollment for: {name}")
    print(f"[INFO] {total} poses x {config.IMAGES_PER_POSE} images "
          f"= {total_target} samples total.")
    print("[INFO] Follow the on-screen instruction for each pose.\n")

    grand_total = 0
    for i, (pose_name, instruction) in enumerate(poses, 1):
        print(f"   Pose {i}/{total}: {pose_name} — {instruction}")
        result = capture_pose(cap, face_cascade, user_dir, user_id, name,
                              pose_name, instruction, i, total)
        if result == -1:
            print(f"\n[ABORTED] during pose '{pose_name}'. "
                  f"Captured {grand_total} sample(s).")
            cap.release()
            cv2.destroyAllWindows()
            print(f"[TIP] Re-run, choose option 2, to re-enroll {name} cleanly.")
            return
        grand_total += result

    cap.release()
    cv2.destroyAllWindows()

    print("\n" + "=" * 52)
    print(f"  ENROLLMENT COMPLETE — {name} (id={user_id})")
    print(f"  {grand_total} samples across {total} poses saved to:")
    print(f"  {user_dir}")
    print(f"\n  Next: python -m src.train_model")
    print("=" * 52 + "\n")


if __name__ == "__main__":
    main()