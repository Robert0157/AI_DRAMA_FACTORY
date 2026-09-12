"""Offline checks for the dispatcher step-count policy (CEO 2026-09-12)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pipeline.dispatch_to_mac import enforce_steps_policy  # noqa: E402


def test_default_steps_pass():
    enforce_steps_policy(None, smoke_test=False)  # production default is 20


def test_twenty_steps_pass():
    enforce_steps_policy(20, smoke_test=False)


def test_sub_twenty_steps_rejected():
    try:
        enforce_steps_policy(8, smoke_test=False)
    except SystemExit:
        return
    raise AssertionError("sub-20 steps must be rejected without --smoke-test")


def test_sub_twenty_steps_allowed_for_smoke_tests():
    enforce_steps_policy(8, smoke_test=True)
