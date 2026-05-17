import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.recognizer_backend import get_backend

print(f"\nconfig.RECOGNITION_BACKEND = {config.RECOGNITION_BACKEND}")
backend = get_backend()
print(f"[OK] Active backend: {backend.name} (kind={backend.kind})")
print(f"[OK] Threshold: {backend.threshold}")
print("\nSwitch backends by editing RECOGNITION_BACKEND in src/config.py")
print("then re-running this test.\n")