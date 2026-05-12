"""
LBPH Model Trainer
===================
Walks data/dataset/<user_id>/ folders, loads every face image,
trains the LBPH recognizer with (image, user_id) pairs, and saves
the trained model to data/trainer/trainer.yml.

Re-run this script every time a new student is enrolled.

Usage:
    python -m src.train_model
"""

import cv2
import numpy as np
import sys
from pathlib import Path

from src import config, database


def gather_training_data():
    """
    Scan dataset/ for all face images grouped by user_id.
    Returns (face_samples, user_ids) — both required by LBPH.train().
    """
    face_samples = []
    user_ids = []

    if not config.DATASET_DIR.exists():
        print(f"[ERROR] Dataset directory missing: {config.DATASET_DIR}")
        sys.exit(1)

    # Each subfolder is named after the user_id from the database.
    user_folders = [f for f in config.DATASET_DIR.iterdir() if f.is_dir()]

    if not user_folders:
        print("[ERROR] No enrolled users found. Run enroll_user.py first.")
        sys.exit(1)

    print(f"[INFO] Found {len(user_folders)} enrolled user(s).")

    for user_folder in sorted(user_folders, key=lambda p: int(p.name)):
        try:
            user_id = int(user_folder.name)
        except ValueError:
            print(f"[WARN] Skipping non-numeric folder: {user_folder.name}")
            continue

        # Look up the user's name for nicer logging.
        user = database.get_user_by_id(user_id)
        display_name = user["name"] if user else f"(unknown id {user_id})"

        images = list(user_folder.glob("*.jpg"))
        print(f"   • user_id={user_id} ({display_name}): {len(images)} images")

        for img_path in images:
            # Read as grayscale — LBPH operates on single-channel images.
            img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                print(f"      [WARN] Could not read {img_path.name}")
                continue

            # Defensive resize — should already be 200×200 from enrollment,
            # but this guarantees uniformity if the dataset is ever modified.
            img = cv2.resize(img, config.FACE_IMG_SIZE)

            face_samples.append(img)
            user_ids.append(user_id)

    return face_samples, user_ids


def train():
    print("\n" + "=" * 50)
    print("  LBPH MODEL TRAINING")
    print("=" * 50 + "\n")

    samples, ids = gather_training_data()

    if not samples:
        print("[ERROR] No usable face samples found.")
        sys.exit(1)

    print(f"\n[INFO] Total training samples: {len(samples)}")
    print(f"[INFO] Unique users:           {len(set(ids))}")

    # Create LBPH recognizer with parameters from proposal §3.6.2
    recognizer = cv2.face.LBPHFaceRecognizer_create(
        radius=config.LBPH_RADIUS,
        neighbors=config.LBPH_NEIGHBORS,
        grid_x=config.LBPH_GRID_X,
        grid_y=config.LBPH_GRID_Y,
    )

    print("\n[INFO] Training in progress...")
    recognizer.train(samples, np.array(ids))

    config.TRAINER_DIR.mkdir(parents=True, exist_ok=True)
    recognizer.save(str(config.TRAINER_PATH))

    # Report file size — useful for your hardware feasibility discussion
    size_kb = config.TRAINER_PATH.stat().st_size / 1024
    print(f"\n[OK] Model saved to: {config.TRAINER_PATH}")
    print(f"[OK] Model file size: {size_kb:.1f} KB")

    print("\n" + "=" * 50)
    print(f"  TRAINING COMPLETE — {len(set(ids))} user(s) learned.")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    train()