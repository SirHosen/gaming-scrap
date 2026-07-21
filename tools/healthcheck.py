#!/usr/bin/env python3
"""Convenience wrapper so you can run the health-check without installing.

    python tools/healthcheck.py [samples_dir]

Equivalent to `python -m nestfetch.healthcheck` once the package is installed.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from nestfetch.healthcheck import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
