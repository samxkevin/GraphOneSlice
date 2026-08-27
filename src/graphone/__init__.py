"""Separate, source-backed output pipeline for the GraphOne trial.

This package intentionally does not reuse AI Orbit entity counts as GraphOne
counts. It reads the independently stored research-paper export and produces
separate validated artifacts for the six requested GraphOne sheet tabs.
"""

from __future__ import annotations

from typing import Any


def build_graphone_outputs(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Lazy public entry point; avoids importing the CLI module at package load."""

    from .build import build_graphone_outputs as _build_graphone_outputs

    return _build_graphone_outputs(*args, **kwargs)


__all__ = ["build_graphone_outputs"]
