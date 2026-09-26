"""Classification metrics: TPR, FPR, precision, recall, F1."""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple


def binary_counts(
    y_true: Iterable[bool],
    y_pred: Iterable[bool],
) -> Tuple[int, int, int, int]:
    tp = fp = tn = fn = 0
    for t, p in zip(y_true, y_pred):
        if t and p:
            tp += 1
        elif not t and p:
            fp += 1
        elif not t and not p:
            tn += 1
        else:
            fn += 1
    return tp, fp, tn, fn


def rates(tp: int, fp: int, tn: int, fn: int) -> dict:
    tpr = tp / (tp + fn) if (tp + fn) else None
    fpr = fp / (fp + tn) if (fp + tn) else None
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tpr
    f1 = None
    if prec is not None and rec is not None and (prec + rec) > 0:
        f1 = 2 * prec * rec / (prec + rec)
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "tpr": tpr,
        "fpr": fpr,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "support_positive": tp + fn,
        "support_negative": fp + tn,
    }
