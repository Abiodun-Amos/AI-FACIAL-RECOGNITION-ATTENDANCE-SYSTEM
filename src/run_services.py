"""
Combined Background Services Runner (development convenience)
================================================================
Runs both sync directions concurrently in a single process:
  • sync_engine   (device -> cloud): attendance, intruders, cancellations
  • reverse_sync  (cloud -> device): dashboard management commands

On the Orange Pi, these run as two independent systemd services.
This combined runner is purely a development-time convenience so
only one terminal needs to stay open while testing the dashboard.

Usage:
    python -m src.run_services
    (Ctrl+C to stop both)
"""

import threading
import sys

from src import sync_engine
from src import reverse_sync


def main():
    print("\n" + "=" * 60)
    print("  COMBINED SERVICES RUNNER")
    print("  sync_engine (push) + reverse_sync (pull) running together")
    print("  Press Ctrl+C to stop")
    print("=" * 60 + "\n")

    t1 = threading.Thread(target=sync_engine.run_loop, daemon=True)
    t2 = threading.Thread(target=reverse_sync.run_loop, daemon=True)
    t1.start()
    t2.start()

    try:
        while True:
            t1.join(timeout=1)
            t2.join(timeout=1)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping combined services...")
        sys.exit(0)


if __name__ == "__main__":
    main()