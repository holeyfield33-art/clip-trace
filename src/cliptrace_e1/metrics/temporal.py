"""Temporal metric helpers (re-exports + aggregation)."""

from __future__ import annotations

from typing import Any, Dict, List

from ..alignment.temporal import start_end_error, temporal_iou


def summarize_temporal(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    ious = [r["iou"] for r in rows if r.get("iou") is not None]
    start_errs = [r["start_error_s"] for r in rows if r.get("start_error_s") is not None]
    end_errs = [r["end_error_s"] for r in rows if r.get("end_error_s") is not None]
    false_continuous = sum(1 for r in rows if r.get("false_continuous"))

    def avg(xs: List[float]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    return {
        "n": len(rows),
        "mean_iou": avg(ious),
        "mean_start_error_s": avg(start_errs),
        "mean_end_error_s": avg(end_errs),
        "false_continuous_count": false_continuous,
        "false_continuous_rate": false_continuous / len(rows) if rows else None,
    }
