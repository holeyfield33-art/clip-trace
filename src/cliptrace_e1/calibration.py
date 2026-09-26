"""Threshold calibration on the calibration partition only.

Evaluation data must never influence the selected threshold profile.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .hashing import sha256_json
from .metrics.classification import binary_counts, rates


@dataclass
class ScoreSample:
    candidate_id: str
    score: float
    is_positive: bool  # true if this pair is a true derivation for this modality
    modality: str


@dataclass
class ThresholdProfile:
    version: str
    selection_rule: str
    modalities: Dict[str, Dict[str, Any]]
    calibration_n_positive: Dict[str, int]
    calibration_n_negative: Dict[str, int]
    curves: Dict[str, List[Dict[str, Any]]]
    notes: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def score_distributions(samples: Sequence[ScoreSample]) -> Dict[str, Any]:
    pos = sorted(s.score for s in samples if s.is_positive)
    neg = sorted(s.score for s in samples if not s.is_positive)

    def stats(xs: List[float]) -> Dict[str, Any]:
        if not xs:
            return {"n": 0, "median": None, "p10": None, "p90": None, "min": None, "max": None, "mean": None}
        n = len(xs)
        def pct(p: float) -> float:
            i = min(n - 1, max(0, int(round(p * (n - 1)))))
            return xs[i]
        return {
            "n": n,
            "median": pct(0.5),
            "p10": pct(0.1),
            "p90": pct(0.9),
            "min": xs[0],
            "max": xs[-1],
            "mean": sum(xs) / n,
        }

    return {
        "positive": stats(pos),
        "negative": stats(neg),
        "overlap_hint": _overlap_hint(pos, neg),
    }


def _overlap_hint(pos: List[float], neg: List[float]) -> str:
    if not pos or not neg:
        return "insufficient_data"
    # crude: if median_pos <= median_neg -> inverted or collapsed
    mp, mn = pos[len(pos) // 2], neg[len(neg) // 2]
    if mp <= mn:
        return "inverted_or_collapsed"
    # fraction of neg above median pos
    above = sum(1 for x in neg if x >= mp) / len(neg)
    if above > 0.4:
        return "high_overlap"
    if above > 0.15:
        return "moderate_overlap"
    return "low_overlap"


def candidate_thresholds(samples: Sequence[ScoreSample], n_points: int = 21) -> List[float]:
    scores = sorted({round(s.score, 4) for s in samples})
    if len(scores) >= 3:
        # mix unique scores with uniform grid
        grid = [i / (n_points - 1) for i in range(n_points)]
        return sorted(set(scores) | set(grid))
    return [i / (n_points - 1) for i in range(n_points)]


def evaluate_threshold(samples: Sequence[ScoreSample], thr: float) -> Dict[str, Any]:
    y_true = [s.is_positive for s in samples]
    y_pred = [s.score >= thr for s in samples]
    return rates(*binary_counts(y_true, y_pred))


def select_threshold(
    samples: Sequence[ScoreSample],
    rule: str = "max_tpr_at_fpr_le_0.20",
) -> Tuple[Optional[float], List[Dict[str, Any]], str]:
    """
    Declared calibration rules:
    - max_tpr_at_fpr_le_0.20: maximize TPR subject to FPR <= 0.20
    - max_f1: maximize F1
    - youden: maximize TPR - FPR

    Returns (selected_threshold | None, full_curve, rule_used).
    """
    if not samples:
        return None, [], rule

    thrs = candidate_thresholds(samples)
    curve: List[Dict[str, Any]] = []
    for thr in thrs:
        r = evaluate_threshold(samples, thr)
        r["threshold"] = thr
        curve.append(r)

    selected: Optional[float] = None
    if rule == "max_tpr_at_fpr_le_0.20":
        feasible = [c for c in curve if c["fpr"] is not None and c["fpr"] <= 0.20]
        if feasible:
            best = max(feasible, key=lambda c: (c["tpr"] or 0.0, -(c["fpr"] or 1.0)))
            selected = best["threshold"]
        else:
            # fall back to min FPR point
            best = min(curve, key=lambda c: (c["fpr"] if c["fpr"] is not None else 1.0))
            selected = best["threshold"]
            rule = rule + "+fallback_min_fpr"
    elif rule == "max_f1":
        best = max(curve, key=lambda c: (c["f1"] if c["f1"] is not None else -1.0))
        selected = best["threshold"]
    elif rule == "youden":
        best = max(
            curve,
            key=lambda c: ((c["tpr"] or 0.0) - (c["fpr"] or 1.0)),
        )
        selected = best["threshold"]
    else:
        raise ValueError(f"Unknown calibration rule: {rule}")

    return selected, curve, rule


def build_threshold_profile(
    samples_by_modality: Dict[str, List[ScoreSample]],
    rule: str = "max_tpr_at_fpr_le_0.20",
) -> ThresholdProfile:
    modalities: Dict[str, Dict[str, Any]] = {}
    curves: Dict[str, List[Dict[str, Any]]] = {}
    n_pos: Dict[str, int] = {}
    n_neg: Dict[str, int] = {}

    for mod, samples in samples_by_modality.items():
        # drop not_evaluated (score is None) — already filtered by caller
        n_pos[mod] = sum(1 for s in samples if s.is_positive)
        n_neg[mod] = sum(1 for s in samples if not s.is_positive)
        thr, curve, used_rule = select_threshold(samples, rule=rule)
        dist = score_distributions(samples)
        modalities[mod] = {
            "threshold": thr,
            "selection_rule": used_rule,
            "distribution": dist,
            "usable": thr is not None and dist["overlap_hint"] not in ("insufficient_data",),
        }
        curves[mod] = curve

    return ThresholdProfile(
        version="1",
        selection_rule=rule,
        modalities=modalities,
        calibration_n_positive=n_pos,
        calibration_n_negative=n_neg,
        curves=curves,
        notes="Thresholds selected on calibration partition only.",
    )


def write_threshold_profile(profile: ThresholdProfile, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(profile)
    digest = sha256_json(data)
    data["profile_sha256"] = digest
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest


def load_threshold_profile(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
