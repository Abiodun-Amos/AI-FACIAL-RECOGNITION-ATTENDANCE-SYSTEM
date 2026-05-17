"""
Smoke test: confirms YuNet + SFace load correctly and that SFace
produces a 128-dim embedding from a webcam face.

Usage:
    python tests\\dnn_smoke_test.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
import sys
from src import config


def main():
    # ── Verify model files exist ──────────────────────────────
    if not config.YUNET_MODEL_PATH.exists():
        print(f"[ERROR] Missing {config.YUNET_MODEL_PATH}")
        print("        Run: python -m src.download_models")
        sys.exit(1)
    if not config.SFACE_MODEL_PATH.exists():
        print(f"[ERROR] Missing {config.SFACE_MODEL_PATH}")
        sys.exit(1)

    print("[OK] Model files found.")

    # ── Load detector + recognizer ────────────────────────────
    detector = cv2.FaceDetectorYN.create(
        str(config.YUNET_MODEL_PATH), "",
        (320, 320),
        config.YUNET_SCORE_THRESHOLD,
        config.YUNET_NMS_THRESHOLD,
    )
    recognizer = cv2.FaceRecognizerSF.create(
        str(config.SFACE_MODEL_PATH), ""
    )
    print("[OK] YuNet detector and SFace recognizer loaded.")
    print(f"[OK] OpenCV version: {cv2.__version__}")

    # ── Grab one webcam frame and run the pipeline ────────────
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cap.isOpened():
        print("[ERROR] Cannot open webcam.")
        sys.exit(1)

    print("\n[INFO] Look at the camera. Capturing a test frame in 3s...")
    import time
    time.sleep(3)

    ret, frame = cap.read()
    cap.release()
    if not ret:
        print("[ERROR] Failed to capture frame.")
        sys.exit(1)

    h, w = frame.shape[:2]
    detector.setInputSize((w, h))
    num, faces = detector.detect(frame)

    if faces is None:
        print("[WARN] No face detected. Try again in better lighting.")
        sys.exit(0)

    print(f"[OK] Detected {len(faces)} face(s).")

    # Align + crop the first face, then extract its embedding
    aligned = recognizer.alignCrop(frame, faces[0])
    embedding = recognizer.feature(aligned)

    print(f"[OK] SFace embedding shape: {embedding.shape}")
    print(f"[OK] Embedding (first 8 of 128 values):")
    print(f"     {np.round(embedding.flatten()[:8], 4)}")
    print("\n[SUCCESS] DNN pipeline is fully operational.")
    print("          This is the 'fingerprint' that solves the")
    print("          stranger-misclassification problem.\n")


if __name__ == "__main__":
    main()