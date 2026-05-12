"""
Phase 2.1 — Face Detection Demo
================================
Validates that OpenCV is correctly installed and that the Haar Cascade
Classifier can detect faces from the laptop webcam in real-time.

This is the same algorithm that will run on the Orange Pi 4 Pro later.
Press 'q' to quit.
"""

import cv2
import time

def main():
    # Load OpenCV's bundled Haar Cascade for frontal face detection.
    # Later, we'll copy this XML into our `models/` folder for portability.
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    if face_cascade.empty():
        print(f"[ERROR] Could not load cascade file: {cascade_path}")
        return

    # Open the default webcam (index 0). If you have multiple cameras,
    # try 1, 2, etc.
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # CAP_DSHOW = faster on Windows

    if not cap.isOpened():
        print("[ERROR] Could not open the webcam.")
        return

    # Lock resolution to 720p — matches the Logitech C270 spec in your
    # proposal and prevents the Orange Pi from overheating later.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print("[INFO] Camera ready. Press 'q' in the video window to quit.")

    prev_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARN] Failed to grab frame.")
            break

        # Haar Cascade only works on grayscale images.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Detection parameters straight from your proposal (Section 3.5.2):
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,    # 10% scale-down per pyramid level
            minNeighbors=5,     # min detections required to confirm a face
            minSize=(30, 30)    # ignore anything smaller than 30x30 px
        )

        # Draw a green rectangle + label on each detected face.
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, "Face", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # FPS overlay.
        now = time.time()
        fps = 1.0 / (now - prev_time) if now != prev_time else 0
        prev_time = now

        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(frame, f"Faces: {len(faces)}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(frame, "Press 'q' to quit", (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow("Face Detection Demo - Phase 2.1", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] Shut down cleanly.")


if __name__ == "__main__":
    main()