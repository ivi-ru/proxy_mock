"""Verify that the free-threaded Python build has GIL disabled."""

import sys


def main() -> None:
    if not hasattr(sys, "_is_gil_enabled"):
        print("WARNING: sys._is_gil_enabled is not available (not a free-threaded build)")
        sys.exit(0)

    gil_enabled = sys._is_gil_enabled()
    print(f"GIL enabled: {gil_enabled}")

    if gil_enabled:
        print("ERROR: GIL is enabled — a C extension may have re-enabled it")
        sys.exit(1)

    print("OK: free-threaded build confirmed")


if __name__ == "__main__":
    main()
