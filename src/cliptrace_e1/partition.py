"""Immutable calibration / evaluation partition management.

Partitions are by source/negative *identity*, never by transformed candidate alone.
A transformed version of an evaluation source must not appear in calibration.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set

from .hashing import sha256_json


@dataclass
class PartitionManifest:
    version: str
    calibration_source_ids: List[str]
    evaluation_source_ids: List[str]
    calibration_negative_ids: List[str]
    evaluation_negative_ids: List[str]
    rule: str
    notes: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def all_calibration_ids(self) -> Set[str]:
        return set(self.calibration_source_ids) | set(self.calibration_negative_ids)

    def all_evaluation_ids(self) -> Set[str]:
        return set(self.evaluation_source_ids) | set(self.evaluation_negative_ids)

    def assert_no_leakage(self) -> None:
        cal = self.all_calibration_ids()
        ev = self.all_evaluation_ids()
        inter = cal & ev
        if inter:
            raise ValueError(f"Partition leakage: IDs in both calibration and evaluation: {inter}")


def build_partition(
    source_ids: List[str],
    negative_ids: List[str],
    calibration_source_frac: float = 0.5,
    calibration_negative_frac: float = 0.5,
) -> PartitionManifest:
    """
    Deterministic split: first floor(n*frac) IDs (sorted) go to calibration.
    """
    src = sorted(source_ids)
    neg = sorted(negative_ids)
    n_cal_s = max(1, int(len(src) * calibration_source_frac)) if src else 0
    n_cal_n = max(1, int(len(neg) * calibration_negative_frac)) if neg else 0
    # ensure at least one evaluation when possible
    if len(src) >= 2 and n_cal_s >= len(src):
        n_cal_s = len(src) - 1
    if len(neg) >= 2 and n_cal_n >= len(neg):
        n_cal_n = len(neg) - 1

    pm = PartitionManifest(
        version="1",
        calibration_source_ids=src[:n_cal_s],
        evaluation_source_ids=src[n_cal_s:],
        calibration_negative_ids=neg[:n_cal_n],
        evaluation_negative_ids=neg[n_cal_n:],
        rule="sorted_identity_frac",
        notes="Partition by parent asset identity. Transformed candidates inherit parent partition.",
    )
    pm.assert_no_leakage()
    return pm


def write_partition(pm: PartitionManifest, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(pm)
    digest = sha256_json(data)
    data["manifest_sha256"] = digest
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest


def load_partition(path: Path) -> PartitionManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("manifest_sha256", None)
    pm = PartitionManifest(**data)
    pm.assert_no_leakage()
    return pm


def candidate_partition(
    record_source_id: str | None,
    is_derivative: bool,
    pm: PartitionManifest,
) -> str:
    """
    Return 'calibration' | 'evaluation' | 'unknown' for a candidate.
    Pure negatives use their own negative asset id as source_id in GT
    (we pass negative asset id via extra or treat is_derivative False with
    source_id pointing to negative when we encode that way).
    """
    if is_derivative and record_source_id:
        if record_source_id in pm.calibration_source_ids:
            return "calibration"
        if record_source_id in pm.evaluation_source_ids:
            return "evaluation"
        return "unknown"
    # pure negative: source_id may be the negative asset id
    if record_source_id:
        if record_source_id in pm.calibration_negative_ids:
            return "calibration"
        if record_source_id in pm.evaluation_negative_ids:
            return "evaluation"
    return "unknown"
