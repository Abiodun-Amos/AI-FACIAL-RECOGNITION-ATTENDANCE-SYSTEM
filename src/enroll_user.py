"""
Student Enrollment Module  (v2 — with confirmation overlay)
============================================================
Captures IMAGES_PER_USER face samples. Adds:
  - A "ready" countdown so only the intended subject is in frame
  - A persistent overlay showing whose face is being captured
  - A strict single-face check (skips frames with 0 or 2+ faces)

Usage:
    python -m src.enroll_user
"""

import cv2
import sqlite3
import sys
import time

from src import config, database


def get_user_input():
    print("\n" + "=" * 50)
    print("  STUDENT ENROLLMENT")
    print("=" * 50)
    name = input("Full name           : ").strip()
    matric_no = input("Matric number       : ").strip().upper()

    while True:
        try:
            level = int(input("Level (100/200/...): ").strip())
            if level in (100, 200, 300, 400, 500, 600):
                break
            print("   Please enter a valid academic level.")
        except ValueError:
            print("   Numbers only, please.")

    if not name or not matric_no:
        print("[ERROR] Name and matric number are required.")
        sys.exit(1)
    return name, matric_no, level


def register_in_db(name, matric_no, level):
    try:
        uid = database.add_user(name, matric_no, level)
        print(f"[OK] Registered '{name}' as user_id={uid}")
        return uid
    except sqlite3.IntegrityError:
        print(f"[ERROR] Matric number '{matric_no}' is already registered.")
        print("        Use 'python -m src.admin_tools delete <user_id>' first.")
        sys.exit(1)


def capture_face_samples(user_id, name):
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

    # ── PHASE 1: 5-second ready countdown ─────────────────────
    print(f"\n[INFO] Enrollment subject: {name.upper()}")
    print("[INFO] Make sure ONLY this person is in front of the camera.")
    print("[INFO] Capture will start in 5 seconds — press 'q' to abort.\n")

    countdown_end = time.time() + 5
    while time.time() < countdown_end:
        ret, frame = cap.read()
        if not ret:
            continue
        remaining = int(countdown_end - time.time()) + 1

        # Big subject banner
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 80), (0, 0, 0), -1)
        cv2.putText(frame, f"ENROLLING: {name.upper()}", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        cv2.putText(frame, "ONLY this person should be in frame", (20, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

        # Countdown
        cv2.putText(frame, f"Starting in {remaining}",
                    (frame.shape[1] // 2 - 130, frame.shape[0] // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
        cv2.putText(frame, "Press 'q' to abort", (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.imshow("Enrollment", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            cap.release()
            cv2.destroyAllWindows()
            print("[ABORTED] No samples captured.")
            return 0

    # ── PHASE 2: Capture loop ─────────────────────────────────
    print(f"[INFO] Capture started. Target: {config.IMAGES_PER_USER} samples.\n")
    count = 0
    last_capture_t = 0
    CAPTURE_INTERVAL = 0.3

    while count < config.IMAGES_PER_USER:
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

        # Strict: capture ONLY when exactly one face is in frame
        if len(faces) == 1 and (time.time() - last_capture_t) > CAPTURE_INTERVAL:
            (x, y, w, h) = faces[0]
            face_crop = gray[y:y + h, x:x + w]
            face_crop = cv2.resize(face_crop, config.FACE_IMG_SIZE)

            filename = user_dir / f"{user_id}_{count + 1:03d}.jpg"
            cv2.imwrite(str(filename), face_crop)
            count += 1
            last_capture_t = time.time()

            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, f"#{count}", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        else:
            for (x, y, w, h) in faces:
                color = (0, 255, 255) if len(faces) == 1 else (0, 0, 255)
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

            if len(faces) == 0:
                status = "No face detected"
            elif len(faces) > 1:
                status = f"{len(faces)} faces detected — only ONE allowed"
            else:
                status = "Hold still..."
            cv2.putText(frame, status, (10, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # Persistent identity banner — leaves no doubt whose face this is
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 80), (0, 0, 0), -1)
        cv2.putText(frame, f"ENROLLING: {name.upper()}", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        cv2.putText(frame, f"Samples: {count}/{config.IMAGES_PER_USER}",
                    (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

        cv2.putText(frame, "Press 'q' to abort", (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.imshow("Enrollment", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print(f"\n[ABORTED] Captured only {count} samples.")
            break

    cap.release()
    cv2.destroyAllWindows()
    if count == config.IMAGES_PER_USER:
        print(f"[OK] Saved {count} samples to: {user_dir}")
    return count


def main():
    database.init_db()
    name, matric_no, level = get_user_input()
    user_id = register_in_db(name, matric_no, level)
    samples = capture_face_samples(user_id, name)

    print("\n" + "=" * 50)
    if samples == config.IMAGES_PER_USER:
        print(f"  ENROLLMENT COMPLETE for {name} (id={user_id})")
        print(f"  Next: python -m src.train_model")
    else:
        print(f"  ENROLLMENT INCOMPLETE — only {samples} samples.")
        print(f"  Delete and retry: python -m src.admin_tools delete {user_id}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()