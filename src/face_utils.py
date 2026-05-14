"""
Shared face preprocessing utilities.
=====================================
Used by enrollment, training, and recognition so that faces are
processed IDENTICALLY everywhere. A mismatch between how training
images and live frames are processed is a classic cause of poor
recognition accuracy — centralising it here prevents that.
"""

import cv2
from src import config


def preprocess_face(gray_image, bbox):
    """
    Given a full grayscale frame and a face bounding box (x, y, w, h),
    return a normalized face crop ready for LBPH:

      1. Crop to the face region
      2. Resize to the standard FACE_IMG_SIZE
      3. Apply histogram equalization to normalize lighting

    MUST be applied identically at enrollment and at recognition.
    """
    x, y, w, h = bbox
    crop = gray_image[y:y + h, x:x + w]
    crop = cv2.resize(crop, config.FACE_IMG_SIZE)
    crop = cv2.equalizeHist(crop)        # lighting normalization
    return crop