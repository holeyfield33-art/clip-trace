"""Immutable ground-truth records generated from the transformation process."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


Interval = Tuple[int, int]  # ms


@dataclass
class GroundTruthRecord:
    candidate_id: str
    source_id: Optional[str]  # None for pure negatives
    is_derivative: bool
    source_intervals_ms: List[Interval]
    candidate_intervals_ms: List[Interval]
    visual_ancestry: bool
    audio_ancestry: bool
    transcript_ancestry: bool
    transformations: List[str]
    candidate_sha256: str
    candidate_path: str
    clip_length_s: float
    extra: Dict[str, Any] = field(default_factory=dict)


def write_ground_truth(records: List[GroundTruthRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(r) for r in records]
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_ground_truth(path: Path) -> List[GroundTruthRecord]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: List[GroundTruthRecord] = []
    for row in data:
        # tuples become lists in JSON
        row["source_intervals_ms"] = [tuple(x) for x in row["source_intervals_ms"]]
        row["candidate_intervals_ms"] = [tuple(x) for x in row["candidate_intervals_ms"]]
        out.append(GroundTruthRecord(**row))
    return out
