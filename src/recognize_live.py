"""
Live Face Recognition Demo  (with temporal smoothing)
======================================================
Loads the trained LBPH model and uses a FaceTracker to vote across
multiple frames before displaying a label — eliminates per-frame
wrong-name flicker.

Press 'q' to quit.

Usage:
    python -m src.recognize_live
"""

import cv2
import sys
import time

from src import config, database
from src.face_tracker import FaceTracker
from src.face_utils import preprocess_face


def load_recognizer():
    if not config.TRAINER_PATH.exists():
        print(f"[ERROR] No trained model found at {config.TRAINER_PATH}")
        print("        Run: python -m src.train_model")
        sys.exit(1)
    rec = cv2.face.LBPHFaceRecognizer_create()
    rec.read(str(config.TRAINER_PATH))
    print(f"[OK] Loaded LBPH model from: {config.TRAINER_PATH}")
    return rec


def build_user_lookup():
    users = database.get_all_users()
    lookup = {u["user_id"]: u["name"] for u in users}
    print(f"[OK] Loaded {len(lookup)} user(s):")
    for uid, name in lookup.items():
        print(f"      • id={uid} → {name}")
    return lookup


def main():
    recognizer = load_recognizer()
    users = build_user_lookup()
    tracker = FaceTracker()

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)

    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        sys.exit(1)

    print("\n[INFO] Recognition running with temporal smoothing.")
    print("[INFO] Predictions stabilize after ~4 consistent frames.\n")
    prev_t = time.time()

    while True:
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

        # ── Run LBPH on every detected face this frame ─────────────
        detections = []
        for (x, y, w, h) in faces:
            face_crop = preprocess_face(gray, (x, y, w, h))
            user_id, confidence = recognizer.predict(face_crop)
            detections.append(((x, y, w, h), (user_id, confidence)))

        # ── Feed into the tracker for smoothing ───────────────────
        tracks = tracker.update(detections)

        # ── Draw the SMOOTHED result per track ────────────────────
        for track in tracks:
            x, y, w, h = track.bbox
            smoothed = track.smoothed_prediction()

            if smoothed is None:
                # Track too new — show neutral box while it stabilises
                label = f"Analysing... ({len(track.history)}/4)"
                color = (255, 255, 0)            # cyan
                status = ""
            else:
                user_id, avg_conf = smoothed
                if avg_conf < config.CONFIDENCE_THRESHOLD:
                    name = users.get(user_id, f"id={user_id}")
                    label = f"{name}  ({avg_conf:.1f})"
                    color = (0, 255, 0)          # green
                    status = "RECOGNIZED"
                else:
                    label = f"UNKNOWN  ({avg_conf:.1f})"
                    color = (0, 0, 255)          # red
                    status = "INTRUDER"

            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.rectangle(frame, (x, y - 28), (x + w, y), color, -1)
            cv2.putText(frame, label, (x + 4, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)
            if status:
                cv2.putText(frame, status, (x, y + h + 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        # ── HUD ────────────────────────────────────────────────────
        now = time.time()
        fps = 1.0 / (now - prev_t) if now != prev_t else 0
        prev_t = now

        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, f"Threshold: {config.CONFIDENCE_THRESHOLD}",
                    (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, f"Active tracks: {len(tracks)}", (10, 75),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, "Press 'q' to quit", (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow("Live Recognition (Smoothed) - Phase 2.6", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] Shut down cleanly.")


if __name__ == "__main__":
    main()