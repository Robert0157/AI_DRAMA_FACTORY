"""Resolution policy gates for local Wan and Seedance generation.

CEO ruling (2026-09-11): 720p is cancelled for mass production. Both engines
default to 480p; 720p requires explicit per-case CEO approval on either engine.
"""
from __future__ import annotations

MASS_PRODUCTION_RESOLUTION = "480p"


class ResolutionApprovalRequiredError(PermissionError):
    """Raised when 720p is requested without explicit CEO approval."""


def resolve_video_resolution(
    engine: str,
    requested: str | None = None,
    *,
    ceo_approved_720p: bool = False,
) -> str:
    """Return an allowed resolution while enforcing the CEO approval gate."""
    normalized_engine = engine.strip().lower()
    if normalized_engine not in {"wan21_local", "seedance"}:
        raise ValueError(f"Unsupported video engine: {engine}")

    resolution = requested or MASS_PRODUCTION_RESOLUTION
    if resolution not in {"480p", "720p"}:
        raise ValueError(f"Unsupported resolution for {engine}: {resolution}")
    if resolution == "720p" and not ceo_approved_720p:
        raise ResolutionApprovalRequiredError(
            f"{engine} 720p requires explicit CEO approval; "
            f"mass production runs at {MASS_PRODUCTION_RESOLUTION}"
        )
    return resolution