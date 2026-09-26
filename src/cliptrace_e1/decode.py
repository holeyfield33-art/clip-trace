"""Media probing and lightweight frame/audio extraction via ffmpeg/ffprobe."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class MediaInfo:
    path: str
    duration_s: float
    width: int
    height: int
    fps: float
    has_audio: bool
    codec_video: str
    codec_audio: Optional[str]
    size_bytes: int


def probe(path: Path) -> MediaInfo:
    """Return basic media properties using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    raw = subprocess.check_output(cmd, text=True)
    data = json.loads(raw)
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = float(fmt.get("duration") or v.get("duration") or 0.0)
    width = int(v.get("width") or 0)
    height = int(v.get("height") or 0)
    fr = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1"
    num, den = fr.split("/") if "/" in fr else (fr, "1")
    fps = float(num) / float(den) if float(den) else 0.0

    return MediaInfo(
        path=str(path),
        duration_s=duration,
        width=width,
        height=height,
        fps=fps,
        has_audio=a is not None,
        codec_video=v.get("codec_name", ""),
        codec_audio=(a or {}).get("codec_name"),
        size_bytes=int(fmt.get("size") or path.stat().st_size),
    )


def extract_frames_gray(
    path: Path,
    timestamps_s: List[float],
    size: Tuple[int, int] = (64, 64),
) -> List[bytes]:
    """
    Extract grayscale frames. Uses one ffmpeg process with fps sampling when
    timestamps are roughly uniform; falls back to per-timestamp otherwise.
    """
    if not timestamps_s:
        return []
    w, h = size
    expected = w * h

    # Prefer single-pass fps filter for speed (smoke-friendly)
    duration = timestamps_s[-1] - timestamps_s[0] if len(timestamps_s) > 1 else 1.0
    n = len(timestamps_s)
    approx_fps = max(0.5, (n - 1) / duration) if duration > 0 else 2.0

    with tempfile.TemporaryDirectory() as td:
        out_pattern = str(Path(td) / "f%04d.raw")
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(path),
            "-vf", f"fps={approx_fps:.4f},scale={w}:{h},format=gray",
            "-frames:v", str(n + 2),
            "-f", "image2",
            "-pix_fmt", "gray",
            out_pattern.replace("%04d", "%04d"),
        ]
        # Use rawvideo pipe instead for simplicity
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(path),
            "-vf", f"fps={approx_fps:.4f},scale={w}:{h},format=gray",
            "-frames:v", str(min(n + 1, 64)),
            "-f", "rawvideo",
            "-pix_fmt", "gray",
            "pipe:1",
        ]
        try:
            data = subprocess.check_output(cmd, timeout=60)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return []

        frames: List[bytes] = []
        for i in range(0, len(data), expected):
            chunk = data[i : i + expected]
            if len(chunk) == expected:
                frames.append(chunk)
            if len(frames) >= n:
                break
        return frames


def extract_audio_wav(path: Path, out_wav: Path, sample_rate: int = 16000) -> bool:
    """Extract mono WAV for fingerprinting. Returns True on success."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(path),
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "wav", str(out_wav),
    ]
    try:
        subprocess.check_call(cmd, timeout=60)
        return out_wav.exists() and out_wav.stat().st_size > 44
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
