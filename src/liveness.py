"""
Liveness Detection — Motion Analysis (anti-spoofing)
=====================================================
Rejects static-photo presentation attacks by measuring inter-frame
motion within a tracked face region. A live face exhibits constant
subtle movement (micro-expressions, breathing, head sway); a held
photo or static phone screen does not.

Scope (honest): defeats printed-photo / static-screen attacks.
Does NOT defeat video-replay attacks (out of scope; see report
Future Work). Chosen for minimal compute cost on the Orange Pi.

Toggle via config.LIVENESS_ENABLED.
"""

import cv2
import numpy as np
from collections import deque

from src import config


class LivenessChecker:
    """
    Tracks recent grayscale crops of a face and computes a motion
    score = mean absolute pixel difference between consecutive
    normalized crops. Above LIVENESS_MOTION_THRESHOLD over the
    window → 'live'. Persistently below → 'static / likely spoof'.
    """

    def __init__(self, window=config.LIVENESS_WINDOW):
        self._crops = deque(maxlen=window)

    def _normalize(self, gray_crop):
        # Fixed size + histogram equalization so the motion signal
        # reflects genuine movement, not lighting flicker or scale.
        c = cv2.resize(gray_crop, (100, 100))
        return cv2.equalizeHist(c)

    def update(self, gray_frame, bbox):
        """Add this frame's face crop to the rolling window."""
        x, y, w, h = bbox
        x0, y0 = max(0, x), max(0, y)
        x1 = min(gray_frame.shape[1], x + w)
        y1 = min(gray_frame.shape[0], y + h)
        if x1 <= x0 or y1 <= y0:
            return
        crop = gray_frame[y0:y1, x0:x1]
        self._crops.append(self._normalize(crop))

    def motion_score(self):
        """
        Mean absolute difference across consecutive crops in the
        window. Higher = more movement = more likely live.
        Returns None until the window has enough samples.
        """
        if len(self._crops) < self._crops.maxlen:
            return None
        diffs = []
        crops = list(self._crops)
        for a, b in zip(crops, crops[1:]):
            diffs.append(np.mean(cv2.absdiff(a, b)))
        return float(np.mean(diffs))

    def is_live(self):
        """
        Tri-state:
          True   → confirmed live (motion above threshold)
          False  → confirmed static (likely spoof)
          None   → not enough data yet (still sampling)
        """
        score = self.motion_score()
        if score is None:
            return None, None
        return (score >= config.LIVENESS_MOTION_THRESHOLD), score