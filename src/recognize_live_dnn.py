"""
Live DNN Face Recognition Test
===============================
The moment of truth. YuNet detects faces, SFace identifies them
against enrolled embeddings, with temporal smoothing.

Watch for: strangers get a RED 'UNKNOWN' box (correctly rejected
because their embedding is far from everyone) while you stay GREEN.
This is the behaviour LBPH could never reliably achieve.

Press 'q' to quit.

Usage:
    python -m src.recognize_live_dnn
"""

import cv2
import sys
import time

from src import config, database
from src.dnn_recognizer import get_dnn_recognizer
from src import dnn_models
from src.face_tracker import FaceTracker


def build_user_lookup():
    return {u["user_id"]: u["name"] for u in database.get_all_users()}


def main():
    database.init_db()

    print("[INFO] Loading DNN models + embeddings...")
    recognizer = get_dnn_recognizer()
    users = build_user_lookup()
    tracker = FaceTracker()

    cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        sys.exit(1)

    print(f"[OK] {len(users)} enrolled user(s).")
    print("[INFO] DNN recognition running. Press 'q' to quit.\n")
    prev_t = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        faces = dnn_models.detect_faces(frame)

        detections = []
        for fr in faces:
            uid, sim = recognizer.identify(frame, fr)
            bbox = dnn_models.face_box(fr)
            # Pack sim as a pseudo-confidence so FaceTracker can smooth it.
            # (FaceTracker votes on user_id; we average sim separately.)
            detections.append((bbox, (uid if uid is not None else -1, sim)))

        tracks = tracker.update(detections)

        for track in tracks:
            x, y, w, h = track.bbox
            smoothed = track.smoothed_prediction()

            if smoothed is None:
                color = (255, 255, 0)
                label = f"Analysing... ({len(track.history)}/5)"
                status = ""
            else:
                voted_id, avg_sim = smoothed
                if voted_id == -1:
                    color = (0, 0, 255)            # red
                    label = f"UNKNOWN  (sim {avg_sim:.3f})"
                    status = "INTRUDER"
                else:
                    name = users.get(voted_id, f"id={voted_id}")
                    color = (0, 255, 0)            # green
                    label = f"{name}  (sim {avg_sim:.3f})"
                    status = "RECOGNIZED"

            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.rectangle(frame, (x, y - 28), (x + w, y), color, -1)
            cv2.putText(frame, label, (x + 4, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)
            if status:
                cv2.putText(frame, status, (x, y + h + 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        now = time.time()
        fps = 1.0 / (now - prev_t) if now != prev_t else 0
        prev_t = now

        cv2.rectangle(frame, (0, 0), (frame.shape[1], 30), (0, 0, 0), -1)
        cv2.putText(frame, f"DNN (SFace)  FPS:{fps:.1f}  "
                    f"Threshold:{config.SFACE_COSINE_THRESHOLD}  "
                    f"Faces:{len(faces)}",
                    (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (0, 255, 255), 2)
        cv2.putText(frame, "Press 'q' to quit", (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow("Live DNN Recognition - SFace", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] Shut down cleanly.")


if __name__ == "__main__":
    main()