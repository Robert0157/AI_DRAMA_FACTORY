#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto_Drama CLI entry point.

Usage examples:
  python run.py book --source sample_inputs/yuewei_sample.txt --mock
  python run.py book --source chapter.txt --series yuewei --episode-limit 2
  python run.py telegram --help
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the package importable when running from repo root or anywhere.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from auto_drama.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
