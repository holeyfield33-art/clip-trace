"""Lightweight modality-specific matchability signals."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .decode import extract_frames_gray, probe
from .audio.fingerprint import extract as audio_extract
import numpy as np


def visual_matchability(path: Path, n_samples: int = 8) -> Dict[str, Any]:
    info = probe(path)
    if info.duration_s <= 0:
        return {"visual_matchability": 0.0, "reason": "no_duration"}

    ts = np.linspace(0, max(0.0, info.duration_s - 0.1), n_samples).tolist()
    frames = extract_frames_gray(path, ts, size=(32, 32))
    if len(frames) < 2:
        return {"visual_matchability": 0.0, "n_frames": len(frames)}

    arrs = [np.frombuffer(f, dtype=np.uint8).astype(np.float32) for f in frames]
    # temporal change energy
    diffs = [np.mean(np.abs(arrs[i] - arrs[i - 1])) for i in range(1, len(arrs))]
    change = float(np.mean(diffs)) if diffs else 0.0
    # edge-ish energy
    edge = float(np.mean([np.mean(np.abs(a[1:] - a[:-1])) for a in arrs]))
    score = min(1.0, (change / 40.0) * 0.6 + (edge / 40.0) * 0.4)
    return {
        "visual_matchability": score,
        "temporal_change": change,
        "edge_energy": edge,
        "n_frames": len(frames),
    }


def audio_matchability(path: Path) -> Dict[str, Any]:
    art = audio_extract(path)
    landmarks = art.get("landmarks") or []
    if not landmarks:
        return {"audio_matchability": 0.0, "reason": art.get("reason", "no_landmarks")}
    density = float(np.std(landmarks))
    score = min(1.0, density * 5.0)
    return {
        "audio_matchability": score,
        "landmark_std": density,
        "n_landmarks": len(landmarks),
    }
