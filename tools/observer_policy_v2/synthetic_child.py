"""Harmless, bounded fixture child. Never imports or invokes product/build code."""
import sys
import time
from observer_v2 import exclusive_json, require_fixture


def main():
    root = require_fixture(sys.argv[1], sys.argv[2])
    mode = sys.argv[3]
    exclusive_json(root / "audit" / "CHILD_STARTED.json", {"run_id": sys.argv[2], "mode": mode})
    if mode == "stop-at-exit":
        exclusive_json(root / "audit" / "STOP.json", {"run_id": sys.argv[2], "classification": "HARD_STOP"})
    elif mode == "wait":
        time.sleep(2)
    elif mode != "success":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
