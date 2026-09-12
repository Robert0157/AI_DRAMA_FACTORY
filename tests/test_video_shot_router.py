from __future__ import annotations

import pytest

from scripts.auxiliary_assets.shot_router import route_storyboard_shot
from scripts.common.video_resolution_policy import ResolutionApprovalRequiredError


def test_explicit_non_character_shot_routes_to_local_wan_480p() -> None:
    route = route_storyboard_shot({"characters": [], "prompt": "misty valley"})
    assert route.engine == "wan21_local"
    assert route.provider == "comfyui_wan21"
    assert route.resolution == "480p"


def test_character_shot_routes_to_seedance_480p() -> None:
    route = route_storyboard_shot({"characters": ["lead"]})
    assert route.engine == "seedance"
    assert route.resolution == "480p"


def test_missing_character_metadata_falls_back_to_seedance() -> None:
    route = route_storyboard_shot({"prompt": "ambiguous shot"})
    assert route.engine == "seedance"
    assert "metadata missing" in route.reason


def test_seedance_720p_route_requires_ceo_approval() -> None:
    with pytest.raises(ResolutionApprovalRequiredError):
        route_storyboard_shot(
            {"characters": ["lead"]}, seedance_resolution="720p"
        )


def test_seedance_720p_route_accepts_ceo_approval() -> None:
    route = route_storyboard_shot(
        {"characters": ["lead"]},
        seedance_resolution="720p",
        ceo_approved_seedance_720p=True,
    )
    assert route.resolution == "720p"