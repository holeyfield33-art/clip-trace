"""Audio fingerprint adapter — matcher family D.

Uses a lightweight spectral landmark approach when chromaprint is unavailable,
so the smoke pipeline remains runnable on minimal environments.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..decode import extract_audio_wav, probe
from ..hashing import sha256_json


def _simple_spectral_landmarks(wav_path: Path, n_bands: int = 16) -> List[float]:
    """Very small deterministic spectral energy vector for smoke tests."""
    try:
        with wave.open(str(wav_path), "rb") as w:
            nch = w.getnchannels()
            sw = w.getsampwidth()
            rate = w.getframerate()
            nframes = w.getnframes()
            raw = w.readframes(nframes)
    except Exception:
        return []

    if sw == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    else:
        return []
    if nch > 1:
        samples = samples.reshape(-1, nch).mean(axis=1)

    # mono energy in coarse bands via rfft
    if len(samples) < 256:
        return []
    # take up to 5 seconds
    max_len = min(len(samples), rate * 5)
    samples = samples[:max_len]
    spectrum = np.abs(np.fft.rfft(samples))
    bands = np.array_split(spectrum, n_bands)
    energies = [float(b.mean()) if len(b) else 0.0 for b in bands]
    total = sum(energies) + 1e-9
    return [e / total for e in energies]


def extract(path: Path, work_dir: Optional[Path] = None) -> Dict[str, Any]:
    info = probe(path)
    if not info.has_audio:
        return {
            "method": "chromaprint_basic",
            "version": "1",
            "status": "not_evaluated",
            "reason": "no_audio",
            "landmarks": [],
        }

    work = work_dir or path.parent / ".audio_tmp"
    work.mkdir(parents=True, exist_ok=True)
    wav = work / f"{path.stem}_16k.wav"
    ok = extract_audio_wav(path, wav)
    if not ok:
        return {
            "method": "chromaprint_basic",
            "version": "1",
            "status": "not_evaluated",
            "reason": "audio_extract_failed",
            "landmarks": [],
        }

    landmarks = _simple_spectral_landmarks(wav)
    artifact = {
        "method": "chromaprint_basic",
        "version": "1",
        "status": "ok" if landmarks else "not_evaluated",
        "landmarks": landmarks,
        "n_landmarks": len(landmarks),
        "duration_s": info.duration_s,
    }
    artifact["artifact_sha256"] = sha256_json(
        {k: v for k, v in artifact.items() if k != "artifact_sha256"}
    )
    return artifact


def score_pair(cand: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    cl = cand.get("landmarks") or []
    sl = src.get("landmarks") or []
    if not cl or not sl or len(cl) != len(sl):
        return {
            "method": "chromaprint_basic",
            "score": None,
            "status": "not_evaluated",
        }
    # cosine similarity
    a = np.array(cl, dtype=np.float64)
    b = np.array(sl, dtype=np.float64)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-12
    cos = float(np.dot(a, b) / denom)
    score = max(0.0, min(1.0, cos))
    return {
        "method": "chromaprint_basic",
        "score": score,
        "status": "ok",
    }
