"""
Downloads the DNN model files (YuNet detector + SFace recognizer)
into the models/ directory. Run once. After this, the system is
fully offline — no network needed for recognition ever again.

Usage:
    python -m src.download_models
"""

import sys
import urllib.request
from src import config

MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
}


def main():
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print("\n" + "=" * 60)
    print("  DOWNLOADING DNN MODELS (one-time, ~37 MB total)")
    print("=" * 60)

    for fname, url in MODELS.items():
        dest = config.MODELS_DIR / fname
        if dest.exists():
            size_mb = dest.stat().st_size / (1024 * 1024)
            print(f"[SKIP] {fname} already exists ({size_mb:.1f} MB)")
            continue
        print(f"[GET ] {fname}")
        print(f"       from {url}")
        try:
            urllib.request.urlretrieve(url, str(dest))
            size_mb = dest.stat().st_size / (1024 * 1024)
            print(f"[OK  ] Saved {fname} ({size_mb:.1f} MB)")
        except Exception as e:
            print(f"[FAIL] Could not download {fname}: {e}")
            print("       Check your internet connection and retry.")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("  MODELS READY. System can now run fully offline.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()