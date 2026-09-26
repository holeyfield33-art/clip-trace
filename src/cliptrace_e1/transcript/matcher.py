"""Transcript matching — exploratory family F. Offline by default."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def extract(path: Path, **kwargs) -> Dict[str, Any]:
    return {
        "method": "transcript_basic",
        "version": "1",
        "status": "not_evaluated",
        "reason": "transcript_backend_not_configured",
        "text": None,
    }


def score_pair(cand: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "method": "transcript_basic",
        "score": None,
        "status": "not_evaluated",
    }
