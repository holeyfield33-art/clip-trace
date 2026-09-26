"""Multimodal fusion modes for evaluation."""

from __future__ import annotations

from typing import Any, Dict, Optional


def fuse(
    visual_score: Optional[float],
    audio_score: Optional[float],
    mode: str,
    visual_threshold: float = 0.5,
    audio_threshold: float = 0.5,
) -> Dict[str, Any]:
    """
    Return a fused decision without claiming ownership or authorization.
    Modes: visual_only, audio_only, visual_or_audio, visual_and_audio, calibrated.
    """
    v_ok = visual_score is not None and visual_score >= visual_threshold
    a_ok = audio_score is not None and audio_score >= audio_threshold

    if mode == "visual_only":
        supported = v_ok
        score = visual_score
    elif mode == "audio_only":
        supported = a_ok
        score = audio_score
    elif mode == "visual_or_audio":
        supported = v_ok or a_ok
        score = max(x for x in (visual_score, audio_score) if x is not None) if (visual_score is not None or audio_score is not None) else None
    elif mode == "visual_and_audio":
        supported = v_ok and a_ok
        if visual_score is not None and audio_score is not None:
            score = min(visual_score, audio_score)
        else:
            score = None
    elif mode == "calibrated":
        # simple average when both present; else the one that exists
        if visual_score is not None and audio_score is not None:
            score = 0.5 * visual_score + 0.5 * audio_score
            supported = score >= 0.5
        elif visual_score is not None:
            score = visual_score
            supported = v_ok
        elif audio_score is not None:
            score = audio_score
            supported = a_ok
        else:
            score = None
            supported = False
    else:
        return {"mode": mode, "status": "not_evaluated", "supported": False, "score": None}

    return {
        "mode": mode,
        "status": "ok" if score is not None else "not_evaluated",
        "supported": bool(supported),
        "score": score,
    }
