"""
Shared DNN model loader.
=========================
Loads YuNet (detector) and SFace (recognizer) once and provides
helper functions used by both enrollment and recognition so the
exact same preprocessing path is used everywhere.
"""

import cv2
import numpy as np
from src import config


_detector = None
_recognizer = None


def get_detector(frame_w=320, frame_h=320):
    global _detector
    if _detector is None:
        if not config.YUNET_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"YuNet model missing: {config.YUNET_MODEL_PATH}\n"
                f"Run: python -m src.download_models")
        _detector = cv2.FaceDetectorYN.create(
            str(config.YUNET_MODEL_PATH), "",
            (frame_w, frame_h),
            config.YUNET_SCORE_THRESHOLD,
            config.YUNET_NMS_THRESHOLD,
        )
    return _detector


def get_recognizer():
    global _recognizer
    if _recognizer is None:
        if not config.SFACE_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"SFace model missing: {config.SFACE_MODEL_PATH}\n"
                f"Run: python -m src.download_models")
        _recognizer = cv2.FaceRecognizerSF.create(
            str(config.SFACE_MODEL_PATH), "")
    return _recognizer


def detect_faces(frame):
    """
    Run YuNet on a BGR frame. Returns a list of face rows
    (each is YuNet's 15-element array: bbox + landmarks + score).
    """
    h, w = frame.shape[:2]
    det = get_detector()
    det.setInputSize((w, h))
    num, faces = det.detect(frame)
    return [] if faces is None else list(faces)


def get_embedding(frame, face_row):
    """
    Given a frame and one YuNet face row, align+crop and return
    the 128-float SFace embedding as a flat numpy array.
    """
    rec = get_recognizer()
    aligned = rec.alignCrop(frame, face_row)
    feat = rec.feature(aligned)
    return feat.flatten().astype(np.float32)


def cosine_similarity(a, b):
    """
    SFace uses cosine similarity. Returns value in ~[-1, 1];
    higher = more similar (same person).
    """
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return -1.0
    return float(np.dot(a, b) / denom)


def face_box(face_row):
    """Extract (x, y, w, h) ints from a YuNet face row."""
    x, y, w, h = face_row[:4]
    return int(x), int(y), int(w), int(h)