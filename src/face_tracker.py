"""
Face Tracker with Temporal Smoothing
=====================================
Associates detections across frames using centroid proximity, and
maintains a sliding window of recent LBPH predictions per tracked
face. This eliminates the per-frame "wrong name flicker" issue that
plagues raw LBPH output.

Used by recognize_live.py and (later) the main attendance loop.
"""

from collections import deque, Counter
from itertools import count


class FaceTrack:
    """A single tracked face with its prediction history."""

    _id_gen = count(1)

    def __init__(self, bbox, history_size=7):
        self.track_id = next(FaceTrack._id_gen)
        self.bbox = bbox                         # (x, y, w, h)
        self.history = deque(maxlen=history_size)  # list of (user_id, confidence)
        self.misses = 0                          # frames since last seen

    @property
    def centroid(self):
        x, y, w, h = self.bbox
        return (x + w // 2, y + h // 2)

    def update(self, bbox, prediction):
        """Called when this track is matched to a new detection."""
        self.bbox = bbox
        self.history.append(prediction)          # (user_id, confidence)
        self.misses = 0

    def smoothed_prediction(self, min_votes=5):
        """
        Return the smoothed (user_id, avg_confidence) for this track.
        Requires at least `min_votes` of the history to agree on the
        same user_id; otherwise returns None ("uncertain").
        """
        if len(self.history) < min_votes:
            return None

        votes = Counter(uid for uid, _ in self.history)
        winner_id, winner_count = votes.most_common(1)[0]

        if winner_count < min_votes:
            return None    # no clear majority — stay silent

        # Average the confidence values that voted for the winner.
        winning_confs = [c for uid, c in self.history if uid == winner_id]
        avg_conf = sum(winning_confs) / len(winning_confs)
        return winner_id, avg_conf


class FaceTracker:
    """Maintains a list of active FaceTracks across video frames."""

    def __init__(self, max_misses=8, match_distance=80):
        self.tracks = []
        self.max_misses = max_misses           # drop track after this many missed frames
        self.match_distance = match_distance   # px — max centroid distance for match

    @staticmethod
    def _centroid_dist(a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def update(self, detections):
        """
        detections: list of (bbox, (user_id, confidence)) tuples.
        Returns the list of active tracks (after matching).
        """
        unmatched_detections = list(range(len(detections)))
        unmatched_tracks     = list(range(len(self.tracks)))

        # ── Greedy nearest-centroid matching ────────────────────
        matches = []
        for ti in list(unmatched_tracks):
            track = self.tracks[ti]
            best_di, best_dist = None, float("inf")
            for di in unmatched_detections:
                bbox, _ = detections[di]
                cx, cy = bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2
                dist = self._centroid_dist(track.centroid, (cx, cy))
                if dist < best_dist and dist <= self.match_distance:
                    best_di, best_dist = di, dist
            if best_di is not None:
                matches.append((ti, best_di))
                unmatched_detections.remove(best_di)
                unmatched_tracks.remove(ti)

        # ── Update matched tracks ───────────────────────────────
        for ti, di in matches:
            bbox, prediction = detections[di]
            self.tracks[ti].update(bbox, prediction)

        # ── Age out unmatched tracks ────────────────────────────
        for ti in unmatched_tracks:
            self.tracks[ti].misses += 1
        self.tracks = [t for t in self.tracks if t.misses <= self.max_misses]

        # ── Spawn new tracks for unmatched detections ───────────
        for di in unmatched_detections:
            bbox, prediction = detections[di]
            new_track = FaceTrack(bbox)
            new_track.history.append(prediction)
            self.tracks.append(new_track)

        return self.tracks