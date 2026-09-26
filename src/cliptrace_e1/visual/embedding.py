"""Lightweight visual embedding placeholder — matcher family C.

Heavy models are intentionally not required for the smoke pipeline.
This module exposes the same interface and returns not_evaluated until
an optional backend is configured.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def extract(path: Path, **kwargs) -> Dict[str, Any]:
    return {
        "method": "visual_embedding",
        "version": "1",
        "status": "not_evaluated",
        "reason": "no_embedding_backend_configured",
        "vector": None,
    }


def score_pair(cand: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "method": "visual_embedding",
        "score": None,
        "status": "not_evaluated",
        "reason": "no_embedding_backend_configured",
    }
