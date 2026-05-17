"""
Pluggable Recognition Backend
==============================
Unifies LBPH and DNN behind ONE interface so the attendance engine
is algorithm-agnostic. Switch via config.RECOGNITION_BACKEND.

  identify(frame_bgr, gray, face) -> (user_id|None, score, kind)

  • kind = "LBPH_DISTANCE"  → lower is better; recognized if < threshold
  • kind = "DNN_SIMILARITY" → higher is better; recognized if >= threshold

This adapter is the keystone of the comparative study: the entire
Phase 3B pipeline (sessions, cancellations, levels, intruders) runs
unchanged on whichever backend is selected.
"""

import cv2
import numpy as np
from src import config, database


# ════════════════════════════════════════════════════════════
#  LBPH backend
# ════════════════════════════════════════════════════════════
class LBPHBackend:
    kind = "LBPH_DISTANCE"
    name = "LBPH"

    def __init__(self):
        self.recognizer = None
        self.threshold = config.CONFIDENCE_THRESHOLD

    def load(self):
        if not config.TRAINER_PATH.exists():
            raise FileNotFoundError(
                f"LBPH model missing: {config.TRAINER_PATH}\n"
                f"Run: python -m src.train_model")
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.recognizer.read(str(config.TRAINER_PATH))
        print(f"[BACKEND] LBPH loaded (threshold {self.threshold}, "
              f"lower = better match).")
        return self

    def detect(self, frame_bgr, gray):
        """LBPH path uses Haar for detection. Returns list of (x,y,w,h)."""
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=config.HAAR_SCALE_FACTOR,
            minNeighbors=config.HAAR_MIN_NEIGHBORS,
            minSize=config.HAAR_MIN_SIZE,
        )
        return [tuple(f) for f in faces]

    def identify(self, frame_bgr, gray, face):
        from src.face_utils import preprocess_face
        x, y, w, h = face
        crop = preprocess_face(gray, (x, y, w, h))
        user_id, distance = self.recognizer.predict(crop)
        if distance < self.threshold:
            return user_id, distance, self.kind
        return None, distance, self.kind


# ════════════════════════════════════════════════════════════
#  DNN backend
# ════════════════════════════════════════════════════════════
class DNNBackend:
    kind = "DNN_SIMILARITY"
    name = "DNN"

    def __init__(self):
        self.rec = None
        self.threshold = config.SFACE_COSINE_THRESHOLD

    def load(self):
        from src.dnn_recognizer import get_dnn_recognizer
        self.rec = get_dnn_recognizer()
        print(f"[BACKEND] DNN loaded (threshold {self.threshold}, "
              f"higher = better match).")
        return self

    def detect(self, frame_bgr, gray):
        """DNN path uses YuNet. Returns list of YuNet face rows."""
        from src import dnn_models
        return dnn_models.detect_faces(frame_bgr)

    def identify(self, frame_bgr, gray, face):
        # face is a YuNet row here
        uid, sim = self.rec.identify(frame_bgr, face)
        return uid, sim, self.kind

    @staticmethod
    def face_to_bbox(face):
        from src import dnn_models
        return dnn_models.face_box(face)


# ════════════════════════════════════════════════════════════
#  Factory
# ════════════════════════════════════════════════════════════
def get_backend():
    """Instantiate and load the backend named in config."""
    choice = config.RECOGNITION_BACKEND.upper()
    if choice == "LBPH":
        return LBPHBackend().load()
    elif choice == "DNN":
        return DNNBackend().load()
    else:
        raise ValueError(
            f"Unknown RECOGNITION_BACKEND '{config.RECOGNITION_BACKEND}'. "
            f"Use 'LBPH' or 'DNN'.")


def bbox_of(backend, face):
    """Normalize a 'face' (Haar tuple OR YuNet row) to (x,y,w,h) ints."""
    if backend.name == "DNN":
        return DNNBackend.face_to_bbox(face)
    x, y, w, h = face
    return int(x), int(y), int(w), int(h)