"""Regression guard: Mac-bound job paths must stay POSIX (no backslashes).

An 8-hour render was once delivered as a silent cut because a Windows-side
dispatcher rewrote "/Volumes/..." into "\\Volumes\\..." (2026-09-12 incident).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pipeline import dispatch_to_mac as dm  # noqa: E402


def test_to_mac_path_uses_forward_slashes():
    result = dm.to_mac_path(
        dm.SMB_ROOT / "assets" / "audio" / "ceo_approved_beats" / "lofi" / "track.mp3"
    )
    assert result == (
        "/Volumes/AI_Workspace/AI_Drama_Factory/assets/audio/ceo_approved_beats/lofi/track.mp3"
    )
    assert "\\" not in result


def test_to_mac_path_rejects_paths_outside_the_share():
    try:
        dm.to_mac_path(Path("F:/AI_DRAMA_FACTORY/assets/audio/track.mp3"))
    except SystemExit:
        return
    raise AssertionError("paths outside the Y: share must raise SystemExit")
