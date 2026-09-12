from __future__ import annotations

import pytest

from scripts.common.video_resolution_policy import (
    ResolutionApprovalRequiredError,
    resolve_video_resolution,
)


def test_local_wan_defaults_to_480p() -> None:
    assert resolve_video_resolution("wan21_local") == "480p"


def test_local_wan_720p_requires_ceo_approval() -> None:
    with pytest.raises(ResolutionApprovalRequiredError):
        resolve_video_resolution("wan21_local", "720p")


def test_local_wan_720p_accepts_explicit_ceo_approval() -> None:
    assert (
        resolve_video_resolution("wan21_local", "720p", ceo_approved_720p=True)
        == "720p"
    )


def test_seedance_defaults_to_480p() -> None:
    assert resolve_video_resolution("seedance") == "480p"


def test_seedance_720p_requires_ceo_approval() -> None:
    with pytest.raises(ResolutionApprovalRequiredError):
        resolve_video_resolution("seedance", "720p")


def test_seedance_720p_accepts_explicit_ceo_approval() -> None:
    assert (
        resolve_video_resolution("seedance", "720p", ceo_approved_720p=True)
        == "720p"
    )