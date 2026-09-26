"""Temporal alignment — matcher family E + metric helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..visual.frame_hash import hamming


def align_frame_hashes(
    cand_hashes: List[str],
    src_hashes: List[str],
    sample_fps: float = 2.0,
    max_avg_distance: float = 16.0,
    allow_multi_fragment: bool = True,
) -> Dict[str, Any]:
    """
    Find best alignment of candidate hash sequence inside source.
    When allow_multi_fragment, also attempts a two-window match for discontinuous material.
    """
    if not cand_hashes or not src_hashes or sample_fps <= 0:
        return {
            "method": "landmark_dtw",
            "status": "not_evaluated",
            "source_intervals_s": [],
            "candidate_intervals_s": [],
            "matched_pairs": [],
            "n_fragments_claimed": 0,
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

    matched = [
        {
            "cand_idx": i,
            "src_idx": best_off + i,
            "cand_t_s": i / sample_fps,
            "src_t_s": (best_off + i) / sample_fps,
            "distance": hamming(cand_hashes[i], src_hashes[best_off + i]),
        }
        for i in range(window)
        if best_off + i < len(src_hashes)
    ]

    if best > max_avg_distance:
        return {
            "method": "landmark_dtw",
            "status": "insufficient",
            "min_avg_distance": best,
            "source_intervals_s": [],
            "candidate_intervals_s": [],
            "matched_pairs": matched,
            "n_fragments_claimed": 0,
        }

    # Multi-fragment heuristic: split candidate in half and align each half independently
    fragments: List[Dict[str, Any]] = []
    if allow_multi_fragment and window >= 4:
        mid = window // 2
        for part_idx, (lo, hi) in enumerate([(0, mid), (mid, window)]):
            sub = cand_hashes[lo:hi]
            b, bo = 64.0, 0
            for off in range(max(1, len(src_hashes) - len(sub) + 1)):
                dists = [hamming(sub[i], src_hashes[off + i]) for i in range(len(sub))]
                avg = sum(dists) / len(dists)
                if avg < b:
                    b, bo = avg, off
            if b <= max_avg_distance:
                fragments.append({
                    "part": part_idx,
                    "src_start_s": bo / sample_fps,
                    "src_end_s": (bo + len(sub)) / sample_fps,
                    "cand_start_s": lo / sample_fps,
                    "cand_end_s": hi / sample_fps,
                    "avg_distance": b,
                })

    # Decide continuous vs multi
    use_multi = False
    if len(fragments) == 2:
        # if the two source regions are far apart relative to candidate length, claim multi
        gap = abs(fragments[1]["src_start_s"] - fragments[0]["src_end_s"])
        span = abs(fragments[1]["src_start_s"] - fragments[0]["src_start_s"])
        cont_len = window / sample_fps
        if span > cont_len * 1.3 or gap > 1.0:
            use_multi = True

    if use_multi:
        src_iv = sorted(
            [[f["src_start_s"], f["src_end_s"]] for f in fragments],
            key=lambda x: x[0],
        )
        cand_iv = [[f["cand_start_s"], f["cand_end_s"]] for f in fragments]
        n_frag = 2
    else:
        src_start = best_off / sample_fps
        src_end = (best_off + window) / sample_fps
        src_iv = [[src_start, src_end]]
        cand_iv = [[0.0, window / sample_fps]]
        n_frag = 1

    return {
        "method": "landmark_dtw",
        "status": "ok",
        "min_avg_distance": best,
        "source_intervals_s": src_iv,
        "candidate_intervals_s": cand_iv,
        "matched_pairs": matched,
        "n_fragments_claimed": n_frag,
        "fragment_details": fragments if use_multi else [],
    }


def temporal_iou(
    claimed: List[List[float]],
    truth: List[List[float]],
) -> float:
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
    # compare earliest starts and latest ends
    cs = min(a for a, _ in claimed)
    ce = max(b for _, b in claimed)
    ts = min(a for a, _ in truth)
    te = max(b for _, b in truth)
    return {"start_error_s": abs(cs - ts), "end_error_s": abs(ce - te)}


def fragmentation_error(claimed_n: int, truth_n: int) -> int:
    return abs(int(claimed_n) - int(truth_n))


def false_continuous(
    claimed_n_fragments: int,
    truth_n_fragments: int,
) -> bool:
    """True when claim is a single continuous interval but truth has multiple fragments."""
    return claimed_n_fragments == 1 and truth_n_fragments > 1


def padding_inflation(
    claimed: List[List[float]],
    truth: List[List[float]],
) -> Optional[float]:
    def dur(ivs: List[List[float]]) -> float:
        return sum(max(0.0, b - a) for a, b in ivs) if ivs else 0.0
    t = dur(truth)
    if t <= 0:
        return None
    return dur(claimed) / t
