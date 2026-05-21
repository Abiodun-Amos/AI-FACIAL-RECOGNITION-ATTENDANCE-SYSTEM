"""
Connectivity smoke test for both cloud services.
Writes a throwaway 'ping' doc to Firestore and uploads a tiny
test image to ImgBB. Then cleans up the Firestore doc.

If both succeed, the cloud layer is wired up correctly.

Usage:
    python -m tests.cloud_connectivity_test
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datetime as _dt
import cv2
import numpy as np

from src import config
from src import cloud_firebase as cf
from src import cloud_imgbb as ci


def main():
    print("\n" + "=" * 55)
    print("  CLOUD CONNECTIVITY TEST")
    print("=" * 55)

    # ── 1. Firebase ──
    print("\n  [1/2] Firebase Firestore...")
    try:
        cf._init()
        doc_id = f"ping_{_dt.datetime.now():%Y%m%d_%H%M%S}"
        ping_doc = {
            "purpose": "connectivity test",
            "at": _dt.datetime.now().isoformat(),
        }
        cf._db.collection("_diagnostic").document(doc_id).set(ping_doc)
        print(f"        [OK] Wrote test doc to _diagnostic/{doc_id}")
        # Clean up immediately
        cf._db.collection("_diagnostic").document(doc_id).delete()
        print(f"        [OK] Deleted test doc.")
    except Exception as e:
        print(f"        [FAIL] {type(e).__name__}: {e}")
        print("        Check: firebase_key.json valid? Firestore enabled?")
        return

    # ── 2. ImgBB ──
    print("\n  [2/2] ImgBB upload...")
    try:
        # Create a tiny 50x50 test image on the fly
        tmp_path = config.DATA_DIR / "_imgbb_ping.jpg"
        img = (np.random.rand(50, 50, 3) * 255).astype("uint8")
        cv2.imwrite(str(tmp_path), img)

        url = ci.upload(str(tmp_path))
        print(f"        [OK] Upload succeeded.")
        print(f"        URL: {url}")
        tmp_path.unlink(missing_ok=True)
    except Exception as e:
        print(f"        [FAIL] {type(e).__name__}: {e}")
        print("        Check: imgbb_key.txt valid? Internet up?")
        return

    print("\n" + "=" * 55)
    print("  CLOUD CONNECTIVITY OK — both services reachable.")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()