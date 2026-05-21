"""
Verifies both cloud credentials are present and well-formed.
Does NOT connect to anything — just checks the files exist and
look valid. Safe, offline.

Usage:
    python -m tests.check_credentials
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config


def main():
    print("\n" + "=" * 55)
    print("  CREDENTIAL CHECK")
    print("=" * 55)

    # Firebase key
    fb = config.FIREBASE_KEY_PATH
    if not fb.exists():
        print(f"  [MISSING] Firebase key not found at: {fb}")
    else:
        try:
            data = json.loads(fb.read_text(encoding="utf-8"))
            needed = {"type", "project_id", "private_key", "client_email"}
            if needed.issubset(data.keys()):
                print(f"  [OK] Firebase key found and valid.")
                print(f"       project_id : {data['project_id']}")
                print(f"       client_email: {data['client_email']}")
            else:
                missing = needed - set(data.keys())
                print(f"  [BAD] Firebase JSON missing fields: {missing}")
        except json.JSONDecodeError as e:
            print(f"  [BAD] Firebase key is not valid JSON: {e}")

    # ImgBB key
    ib = config.IMGBB_KEY_PATH
    if not ib.exists():
        print(f"  [MISSING] ImgBB key not found at: {ib}")
    else:
        key = ib.read_text(encoding="utf-8").strip()
        if len(key) >= 20 and key != "YOUR_IMGBB_KEY_HERE":
            print(f"  [OK] ImgBB key found ({len(key)} chars, "
                  f"starts '{key[:6]}...').")
        else:
            print(f"  [BAD] ImgBB key looks wrong or is the placeholder: "
                  f"'{key[:20]}'")

    print("=" * 55)
    print("  (This only checks files exist & are well-formed.)")
    print("  (Actual cloud connection is tested in the next step.)")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()