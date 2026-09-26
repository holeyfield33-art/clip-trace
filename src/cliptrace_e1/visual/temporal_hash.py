"""Temporal sequence of visual hashes — matcher family B."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .frame_hash import extract as frame_extract, score_pair as frame_score


def extract(path: Path, sample_fps: float = 2.0, max_frames: int = 64) -> Dict[str, Any]:
    art = frame_extract(path, sample_fps=sample_fps, max_frames=max_frames)
    art["method"] = "temporal_phash"
    return art


def score_pair(cand: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    result = frame_score(cand, src)
    result["method"] = "temporal_phash"
    return result
