"""
DNN Face Recognizer (SFace embeddings)
=======================================
Open-set face recognition using cosine similarity between SFace
embeddings. Unlike LBPH (closed-set, forced to pick a known user),
this returns "unknown" natively when a face is far from everyone.

Per-pose multi-embedding matching: each user has ~5 stored
embeddings (one per enrollment pose). A live face is compared to
ALL of them; the user with the single best-matching pose wins.
This directly attacks the head-pose weakness that plagued LBPH.
"""

import numpy as np
from collections import defaultdict

from src import config, database
from src import dnn_models


class DNNRecognizer:
    def __init__(self):
        # { user_id: [emb1, emb2, ...] }  (one list per user, ~5 poses)
        self._user_embeddings = defaultdict(list)
        self._loaded = False

    def load(self):
        """Load all stored embeddings from the database into memory."""
        self._user_embeddings.clear()
        rows = database.get_all_embeddings()
        for r in rows:
            vec = np.asarray(r["vector"], dtype=np.float32)
            self._user_embeddings[r["user_id"]].append(vec)
        self._loaded = True

        total = sum(len(v) for v in self._user_embeddings.values())
        print(f"[DNN] Loaded {total} embeddings "
              f"for {len(self._user_embeddings)} user(s).")
        for uid, embs in sorted(self._user_embeddings.items()):
            print(f"      • user_id={uid}: {len(embs)} pose embeddings")
        return self

    def identify(self, frame, face_row):
        """
        Given a frame and a YuNet face row, return:
            (user_id, similarity)  if recognized
            (None,    best_sim)    if unknown

        similarity is cosine similarity in ~[-1, 1]; higher = closer.
        """
        if not self._loaded:
            raise RuntimeError("Call .load() before .identify()")

        live = dnn_models.get_embedding(frame, face_row)

        best_user = None
        best_sim  = -1.0

        # Compare against every stored embedding of every user.
        for uid, embs in self._user_embeddings.items():
            for stored in embs:
                sim = dnn_models.cosine_similarity(live, stored)
                if sim > best_sim:
                    best_sim  = sim
                    best_user = uid

        # Open-set decision: only accept if the BEST match clears
        # the similarity threshold. Otherwise it's genuinely unknown.
        if best_sim >= config.SFACE_COSINE_THRESHOLD:
            return best_user, best_sim
        return None, best_sim


# Module-level singleton (loaded once, reused everywhere)
_recognizer = None

def get_dnn_recognizer():
    global _recognizer
    if _recognizer is None:
        _recognizer = DNNRecognizer().load()
    return _recognizer