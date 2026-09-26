"""Temporal alignment — matcher family E (landmark / simple DTW-style)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..visual.frame_hash import hamming


Interval = Tuple[float, float]  # seconds


def align_frame_hashes(
    cand_hashes: List[str],
    src_hashes: List[str],
    sample_fps: float = 2.0,
    max_avg_distance: float = 16.0,
) -> Dict[str, Any]:
    """
    Find best contiguous alignment of candidate hash sequence inside source.
    Returns claimed source interval in seconds and basic quality metrics.
    """
    if not cand_hashes or not src_hashes or sample_fps <= 0:
        return {
            "method": "landmark_dtw",
            "status": "not_evaluated",
            "source_intervals_s": [],
            "candidate_intervals_s": [],
            "iou_vs_truth": None,
        }

    window = len(cand_hashes)
    best = 64.0
    best_off = 0
    for off in range(max(1, len(src_hashes) - window + 1)):
        dists = [hamming(cand_hashes[i], src_hashes[off + i]) for i in range(window)]
        avg = sum(dists) / len(dists)
        if avg < best:
            best = avg
            best_off = off

    if best > max_avg_distance:
        return {
            "method": "landmark_dtw",
            "status": "insufficient",
            "min_avg_distance": best,
            "source_intervals_s": [],
            "candidate_intervals_s": [],
        }

    src_start = best_off / sample_fps
    src_end = (best_off + window) / sample_fps
    cand_start = 0.0
    cand_end = window / sample_fps

    return {
        "method": "landmark_dtw",
        "status": "ok",
        "min_avg_distance": best,
        "source_intervals_s": [[src_start, src_end]],
        "candidate_intervals_s": [[cand_start, cand_end]],
        "n_fragments_claimed": 1,
    }


def temporal_iou(
    claimed: List[List[float]],
    truth: List[List[float]],
) -> float:
    """IoU of unions of intervals (seconds)."""
    def merge(intervals: List[List[float]]) -> List[Tuple[float, float]]:
        if not intervals:
            return []
        xs = sorted((float(a), float(b)) for a, b in intervals)
        out = [xs[0]]
        for a, b in xs[1:]:
            if a <= out[-1][1]:
                out[-1] = (out[-1][0], max(out[-1][1], b))
            else:
                out.append((a, b))
        return out

    def length(ivs: List[Tuple[float, float]]) -> float:
        return sum(max(0.0, b - a) for a, b in ivs)

    c = merge(claimed)
    t = merge(truth)
    if not c and not t:
        return 1.0
    if not c or not t:
        return 0.0

    # intersection
    inter = 0.0
    i = j = 0
    while i < len(c) and j < len(t):
        a0, a1 = c[i]
        b0, b1 = t[j]
        left = max(a0, b0)
        right = min(a1, b1)
        if left < right:
            inter += right - left
        if a1 < b1:
            i += 1
        else:
            j += 1
    union = length(c) + length(t) - inter
    return inter / union if union > 0 else 0.0


def start_end_error(
    claimed: List[List[float]],
    truth: List[List[float]],
) -> Dict[str, Optional[float]]:
    if not claimed or not truth:
        return {"start_error_s": None, "end_error_s": None}
    # compare first claimed to first truth for simple smoke metric
    cs, ce = claimed[0]
    ts, te = truth[0]
    return {
        "start_error_s": abs(cs - ts),
        "end_error_s": abs(ce - te),
    }
