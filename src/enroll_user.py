"""
Clean Dual Re-Enrollment  (v4 — LBPH images + DNN embeddings)
==============================================================
Guided multi-pose enrollment that produces BOTH:
  • Face images in data/dataset/<user_id>/   (LBPH baseline)
  • Per-pose SFace embeddings in the DB      (DNN engine)

One capture session → both recognition backends ready.

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
from src import dnn_models


def ask(prompt, allow_empty=False):
    while True:
        v = input(prompt).strip()
        if v or allow_empty:
            return v
        print("   (required)")


def wipe_all_users():
    """Full clean slate: delete ALL users, datasets, embeddings —
    including any orphaned dataset folders not tied to a DB user."""
    users = database.get_all_users()
    print(f"\n[WIPE] Removing {len(users)} DB user(s) + ALL dataset folders...")

    # Nuke the entire dataset directory contents (catches orphans too)
    if config.DATASET_DIR.exists():
        for child in config.DATASET_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    # Clear all DB tables related to identity
    with database.get_conn() as conn:
        conn.execute("DELETE FROM embeddings")
        conn.execute("DELETE FROM attendance")
        conn.execute("DELETE FROM users")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='users'")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='embeddings'")

    print("[WIPE] Clean slate ready (datasets + embeddings + users cleared).\n")


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
    uid = database.add_user(name, matric_no, level)
    print(f"[OK] Registered '{name}' as user_id={uid}")
    return uid, name


def _draw_banner(frame, name, pose_name, instruction, idx, total):
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 100), (0, 0, 0), -1)
    cv2.putText(frame, f"ENROLLING: {name.upper()}", (15, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.putText(frame, f"POSE {idx}/{total}:  {pose_name}", (15, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, instruction, (15, 86),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.putText(frame, "'q' to abort", (10, frame.shape[0] - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)


def capture_pose(cap, user_dir, user_id, name,
                 pose_name, instruction, idx, total):
    """
    Capture IMAGES_PER_POSE samples for one pose.
    Saves LBPH images AND computes one representative SFace
    embedding for this pose (from the sharpest capture).
    Returns (num_images, embedding_or_None) or (-1, None) if aborted.
    """
    # 3-second ready countdown
    countdown_end = time.time() + 3
    while time.time() < countdown_end:
        ret, frame = cap.read()
        if not ret:
            continue
        remaining = int(countdown_end - time.time()) + 1
        _draw_banner(frame, name, pose_name, instruction, idx, total)
        cv2.putText(frame, f"Get ready... {remaining}",
                    (frame.shape[1] // 2 - 130, frame.shape[0] // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 0), 3)
        cv2.imshow("Dual Enrollment", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            return -1, None

    captured = 0
    last_t = 0
    INTERVAL = 0.3
    existing = len(list(user_dir.glob("*.jpg")))
    best_embedding = None
    best_face_area = 0

    while captured < config.IMAGES_PER_POSE:
        ret, frame = cap.read()
        if not ret:
            continue

        # ── DNN detect (used for embedding + as a quality gate) ──
        faces = dnn_models.detect_faces(frame)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if len(faces) == 1 and (time.time() - last_t) > INTERVAL:
            fb = dnn_models.face_box(faces[0])
            x, y, w, h = fb

            # 1) LBPH image (same preprocessing as before)
            #    Clamp box to frame bounds for safety.
            x0, y0 = max(0, x), max(0, y)
            x1 = min(frame.shape[1], x + w)
            y1 = min(frame.shape[0], y + h)
            if x1 > x0 and y1 > y0:
                processed = preprocess_face(gray, (x0, y0, x1 - x0, y1 - y0))
                idxn = existing + captured + 1
                fname = user_dir / f"{user_id}_{pose_name}_{idxn:03d}.jpg"
                cv2.imwrite(str(fname), processed)

                # 2) DNN embedding — keep the one from the largest
                #    (closest / clearest) face in this pose
                area = w * h
                if area > best_face_area:
                    emb = dnn_models.get_embedding(frame, faces[0])
                    best_embedding = emb
                    best_face_area = area

                captured += 1
                last_t = time.time()
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        else:
            for fr in faces:
                bx, by, bw, bh = dnn_models.face_box(fr)
                col = (0, 255, 255) if len(faces) == 1 else (0, 0, 255)
                cv2.rectangle(frame, (bx, by), (bx+bw, by+bh), col, 2)
            msg = ("No face detected" if len(faces) == 0
                   else "Hold the pose..." if len(faces) == 1
                   else f"{len(faces)} faces - need exactly 1")
            cv2.putText(frame, msg, (15, 135),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        _draw_banner(frame, name, pose_name, instruction, idx, total)
        cv2.putText(frame, f"{captured}/{config.IMAGES_PER_POSE}",
                    (frame.shape[1] - 120, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        cv2.imshow("Dual Enrollment", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            return -1, None

    return captured, best_embedding


def main():
    database.init_db()

    print("\n" + "=" * 55)
    print("  CLEAN DUAL RE-ENROLLMENT  (LBPH + DNN)")
    print("=" * 55)
    print("  This wipes ALL existing users for a clean slate,")
    print("  then enrolls fresh — saving BOTH LBPH images and")
    print("  DNN embeddings in one capture session per student.")
    confirm = input("\n  Type 'WIPE' to confirm clean slate: ").strip()
    if confirm != "WIPE":
        print("  Cancelled.")
        return
    wipe_all_users()

    # Warm up the DNN models once before the camera opens
    print("[INFO] Loading DNN models...")
    dnn_models.get_detector()
    dnn_models.get_recognizer()
    print("[OK] DNN models ready.\n")

    face_count_target = len(config.ENROLLMENT_POSES) * config.IMAGES_PER_POSE

    while True:
        user_id, name = get_new_user()
        user_dir = config.DATASET_DIR / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        if not cap.isOpened():
            print("[ERROR] Cannot open camera.")
            sys.exit(1)

        poses = config.ENROLLMENT_POSES
        total = len(poses)
        print(f"\n[INFO] Enrolling {name}: {total} poses x "
              f"{config.IMAGES_PER_POSE} images = {face_count_target} samples")
        print("[INFO] Plus one SFace embedding per pose.\n")

        grand_images = 0
        embeddings_saved = 0
        aborted = False

        for i, (pose_name, instruction) in enumerate(poses, 1):
            print(f"   Pose {i}/{total}: {pose_name} — {instruction}")
            n_img, emb = capture_pose(cap, user_dir, user_id, name,
                                      pose_name, instruction, i, total)
            if n_img == -1:
                print(f"\n[ABORTED] during pose '{pose_name}'.")
                aborted = True
                break
            grand_images += n_img
            if emb is not None:
                database.add_embedding(user_id, pose_name, emb.tolist())
                embeddings_saved += 1
            else:
                print(f"   [WARN] No embedding captured for {pose_name} "
                      f"(face not detected clearly).")

        cap.release()
        cv2.destroyAllWindows()

        if aborted:
            print(f"[TIP] Re-run to redo {name} cleanly.\n")
        else:
            print("\n" + "=" * 55)
            print(f"  {name} (id={user_id}) ENROLLED")
            print(f"  LBPH images : {grand_images}")
            print(f"  DNN embeddings : {embeddings_saved}/{total} poses")
            print("=" * 55)

        again = input("\nEnroll another student? (y/N): ").strip().lower()
        if again != "y":
            break

    print("\n[NEXT] Run: python -m src.train_model   (rebuilds LBPH)")
    print("[INFO] DNN embeddings are already saved — no training needed.\n")


if __name__ == "__main__":
    main()