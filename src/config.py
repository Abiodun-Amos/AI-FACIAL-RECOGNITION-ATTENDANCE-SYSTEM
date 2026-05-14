"""
Central configuration for the Face Recognition Attendance System.
All hard-coded values live here so they're easy to tune without
hunting through source files.
"""

import os
from pathlib import Path

# ── Project root (auto-detected from this file's location) ──────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Directories ────────────────────────────────────────────────
DATA_DIR        = PROJECT_ROOT / "data"
DATASET_DIR     = DATA_DIR / "dataset"      # per-student face images
TRAINER_DIR     = DATA_DIR / "trainer"      # trained LBPH model
INTRUDERS_DIR   = DATA_DIR / "intruders"    # snapshots awaiting upload
DATABASE_DIR    = PROJECT_ROOT / "database"
MODELS_DIR      = PROJECT_ROOT / "models"
LOGS_DIR        = PROJECT_ROOT / "logs"

# ── File paths ─────────────────────────────────────────────────
DATABASE_PATH   = DATABASE_DIR / "attendance.db"
TRAINER_PATH    = TRAINER_DIR / "trainer.yml"

# ── Device location ────────────────────────────────────────────
# This Orange Pi is physically deployed in this lecture hall.
# Only sessions assigned to this hall will be considered active.
CURRENT_HALL_NAME = "Electrical Hall 1"

# ── Camera settings ────────────────────────────────────────────
CAMERA_INDEX    = 0
FRAME_WIDTH     = 1280
FRAME_HEIGHT    = 720
FACE_IMG_SIZE   = (200, 200)   # normalized face size for LBPH

# ── Face detection (Haar Cascade) — from proposal §3.5.2 ───────
HAAR_SCALE_FACTOR    = 1.1
HAAR_MIN_NEIGHBORS   = 7
HAAR_MIN_SIZE        = (60, 60)

# ── Face recognition (LBPH) — from proposal §3.6.2 ─────────────
LBPH_RADIUS          = 1
LBPH_NEIGHBORS       = 8
LBPH_GRID_X          = 8
LBPH_GRID_Y          = 8
CONFIDENCE_THRESHOLD = 70   # below = recognized, above = intruder

# ── Enrollment — guided multi-pose capture ─────────────────────
ENROLLMENT_POSES = [
    ("FRONTAL", "Look STRAIGHT at the camera"),
    ("LEFT",    "Slowly turn your head to your LEFT"),
    ("RIGHT",   "Slowly turn your head to your RIGHT"),
    ("UP",      "Tilt your head slightly UP"),
    ("DOWN",    "Tilt your head slightly DOWN"),
]
IMAGES_PER_POSE = 7        # 5 poses x 7 = 35 samples per user

# ── Ensure all directories exist on first run ──────────────────
for d in [DATASET_DIR, TRAINER_DIR, INTRUDERS_DIR,
          DATABASE_DIR, MODELS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)