"""
Standalone liveness signal test. Shows your live motion score vs.
a held-photo score so we can calibrate LIVENESS_MOTION_THRESHOLD.

Usage:
    python -m tests.liveness_test
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
from src import config
from src import dnn_models
from src.liveness import LivenessChecker


def main():
    cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        return

    checker = LivenessChecker()
    print("\n[INFO] Liveness signal test.")
    print("  1. Sit normally a few seconds — note the LIVE score.")
    print("  2. Hold a phone/printed photo of a face still — note that score.")
    print("  Press 'q' to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = dnn_models.detect_faces(frame)

        if len(faces) == 1:
            bbox = dnn_models.face_box(faces[0])
            checker.update(gray, bbox)
            live, score = checker.is_live()
            x, y, w, h = bbox

            if score is None:
                txt, col = "Sampling...", (255, 255, 0)
            elif live:
                txt, col = f"LIVE  ({score:.2f})", (0, 255, 0)
            else:
                txt, col = f"STATIC?  ({score:.2f})", (0, 0, 255)

            cv2.rectangle(frame, (x, y), (x+w, y+h), col, 2)
            cv2.putText(frame, txt, (x, y-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
            cv2.putText(frame, f"Threshold: {config.LIVENESS_MOTION_THRESHOLD}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 255), 2)

        cv2.putText(frame, "Press 'q' to quit", (10, frame.shape[0]-15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.imshow("Liveness Signal Test", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()