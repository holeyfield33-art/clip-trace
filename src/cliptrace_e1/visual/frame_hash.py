"""Deterministic perceptual frame hashing (pHash family) — matcher family A.

Pure-numpy implementation so the smoke pipeline runs without imagehash/cv2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from ..decode import extract_frames_gray, probe
from ..hashing import sha256_json


def _dct_2d(block: np.ndarray) -> np.ndarray:
    """Separable DCT-II via numpy (sufficient for 32x32 pHash)."""
    n = block.shape[0]
    x = np.arange(n)
    k = x.reshape(-1, 1)
    basis = np.cos(np.pi * (2 * x + 1) * k / (2 * n))
    basis[0] *= 1.0 / np.sqrt(2)
    basis *= np.sqrt(2 / n)
    return basis @ block @ basis.T


def _phash_from_gray_bytes(data: bytes, size: int = 64, hash_size: int = 8) -> str:
    """
    Compute a 64-bit pHash (hex string) from grayscale bytes of shape (size, size).
    """
    arr = np.frombuffer(data, dtype=np.uint8).reshape((size, size)).astype(np.float64)
    img = Image.fromarray(arr.astype(np.uint8), mode="L").resize((32, 32), Image.BILINEAR)
    pixels = np.asarray(img, dtype=np.float64)
    dct = _dct_2d(pixels)
    low = dct[:hash_size, :hash_size].copy()
    low[0, 0] = 0
    med = np.median(low)
    bits = (low > med).flatten()
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return f"{value:016x}"


def extract(path: Path, sample_fps: float = 2.0, max_frames: int = 64) -> Dict[str, Any]:
    """Extract a sequence of pHash values at regular intervals."""
    info = probe(path)
    if info.duration_s <= 0 or info.width == 0:
        return {"method": "frame_phash", "frames": [], "error": "probe_failed", "frame_hashes": [], "n_frames": 0}

    step = 1.0 / sample_fps if sample_fps > 0 else 0.5
    timestamps = []
    t = 0.0
    while t < info.duration_s and len(timestamps) < max_frames:
        timestamps.append(t)
        t += step

    raw_frames = extract_frames_gray(path, timestamps, size=(64, 64))
    hashes: List[str] = []
    for data in raw_frames:
        try:
            hashes.append(_phash_from_gray_bytes(data))
        except Exception:
            continue

    artifact = {
        "method": "frame_phash",
        "version": "1",
        "sample_fps": sample_fps,
        "duration_s": info.duration_s,
        "frame_hashes": hashes,
        "n_frames": len(hashes),
    }
    artifact["artifact_sha256"] = sha256_json(
        {k: v for k, v in artifact.items() if k != "artifact_sha256"}
    )
    return artifact


def hamming(a: str, b: str) -> int:
    """Hamming distance between two hex hash strings of equal length."""
    try:
        x = int(a, 16) ^ int(b, 16)
        return bin(x).count("1")
    except Exception:
        return 64


def score_pair(cand: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """Compare candidate frame-hash sequence to source via sliding window."""
    ch = cand.get("frame_hashes") or []
    sh = src.get("frame_hashes") or []
    if not ch or not sh:
        return {
            "method": "frame_phash",
            "score": None,
            "min_avg_distance": None,
            "status": "not_evaluated",
        }

    best = 64.0
    best_off = 0
    window = len(ch)
    for off in range(max(1, len(sh) - window + 1)):
        dists = [hamming(ch[i], sh[off + i]) for i in range(window)]
        avg = sum(dists) / len(dists)
        if avg < best:
            best = avg
            best_off = off

    score = max(0.0, 1.0 - (best / 32.0))
    return {
        "method": "frame_phash",
        "score": score,
        "min_avg_distance": best,
        "best_offset_frames": best_off,
        "status": "ok",
    }
