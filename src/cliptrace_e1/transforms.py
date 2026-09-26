"""Transformation engine: generate candidates from sources with recorded manifests."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .hashing import sha256_file
from .decode import probe
from .ground_truth import GroundTruthRecord, Interval


@dataclass
class TransformSpec:
    id: str
    params: Dict[str, Any] = field(default_factory=dict)


def _run_ffmpeg(cmd: List[str], timeout: int = 180) -> bool:
    try:
        subprocess.check_call(cmd, timeout=timeout)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def apply_transform_chain(
    source_path: Path,
    out_path: Path,
    transforms: Sequence[Dict[str, Any]],
    start_s: float = 0.0,
    duration_s: Optional[float] = None,
) -> bool:
    """
    Apply a short chain of transforms via ffmpeg filter_complex / options.
    Supports the smoke subset: scale, crop, hflip, rotate, re-encode, audio replace/shift.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    vf_parts: List[str] = []
    af_parts: List[str] = []
    extra_inputs: List[str] = []
    video_map = "0:v"
    audio_map = "0:a?"

    # trim first
    ss_args: List[str] = []
    if start_s > 0:
        ss_args = ["-ss", f"{start_s:.3f}"]
    t_args: List[str] = []
    if duration_s is not None:
        t_args = ["-t", f"{duration_s:.3f}"]

    audio_replaced = False
    for t in transforms:
        tid = t.get("id", "")
        if "scale" in t:
            vf_parts.append(f"scale={t['scale']}")
        if "crop_pct" in t:
            pct = float(t["crop_pct"]) / 100.0
            # center crop
            keep = 1.0 - pct
            vf_parts.append(f"crop=iw*{keep}:ih*{keep}")
        if t.get("hflip"):
            vf_parts.append("hflip")
        if "rotate_deg" in t:
            rad = float(t["rotate_deg"]) * 3.14159265 / 180.0
            vf_parts.append(f"rotate={rad}:fillcolor=black")
        if t.get("audio") == "replace":
            # replace with a different sine
            extra_inputs += ["-f", "lavfi", "-i", "sine=frequency=330:duration=30"]
            audio_map = f"{1 + len(extra_inputs)//3}:a"
            audio_replaced = True
        if "audio_shift_s" in t:
            shift = float(t["audio_shift_s"])
            af_parts.append(f"adelay={int(shift*1000)}|{int(shift*1000)}")
        if "pitch_semitones" in t:
            # approximate with asetrate/atempo (limited)
            st = float(t["pitch_semitones"])
            factor = 2 ** (st / 12.0)
            af_parts.append(f"asetrate=44100*{factor},aresample=44100")
        if "speed" in t:
            speed = float(t["speed"])
            vf_parts.append(f"setpts={1.0/speed}*PTS")
            af_parts.append(f"atempo={min(max(speed, 0.5), 2.0)}")

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    cmd += ss_args
    cmd += ["-i", str(source_path)]
    cmd += extra_inputs
    cmd += t_args

    if vf_parts:
        cmd += ["-vf", ",".join(vf_parts)]
    if af_parts and not audio_replaced:
        cmd += ["-af", ",".join(af_parts)]

    # encoding defaults
    crf = 28
    for t in transforms:
        if "crf" in t:
            crf = int(t["crf"])
    cmd += [
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ac", "1", "-ar", "16000",
        "-shortest",
        str(out_path),
    ]
    return _run_ffmpeg(cmd)


def generate_smoke_candidates(
    source: Dict[str, Any],
    out_dir: Path,
    transform_chains: List[List[Dict[str, Any]]],
    clip_lengths_s: List[float],
) -> List[GroundTruthRecord]:
    """Generate a tiny set of candidates for the smoke pipeline."""
    records: List[GroundTruthRecord] = []
    src_path = Path(source["path"])
    src_dur = float(source["duration_s"])
    out_dir.mkdir(parents=True, exist_ok=True)
    idx = 0

    for length in clip_lengths_s:
        if length > src_dur:
            continue
        start = max(0.0, (src_dur - length) / 2.0)
        for chain in transform_chains:
            idx += 1
            cid = f"C{idx:04d}"
            chain_ids = [t.get("id", "unknown") for t in chain]
            out_name = f"{cid}_{'_'.join(chain_ids)}_{length:.0f}s.mp4"
            out_path = out_dir / out_name
            ok = apply_transform_chain(src_path, out_path, chain, start_s=start, duration_s=length)
            if not ok or not out_path.exists():
                continue
            digest = sha256_file(out_path)
            # audio ancestry false if any transform replaced audio
            audio_anc = not any(t.get("audio") == "replace" for t in chain)
            visual_anc = True  # all current smoke transforms keep visual ancestry
            src_start_ms = int(start * 1000)
            src_end_ms = int((start + length) * 1000)
            cand_end_ms = int(length * 1000)
            records.append(
                GroundTruthRecord(
                    candidate_id=cid,
                    source_id=source["asset_id"],
                    is_derivative=True,
                    source_intervals_ms=[(src_start_ms, src_end_ms)],
                    candidate_intervals_ms=[(0, cand_end_ms)],
                    visual_ancestry=visual_anc,
                    audio_ancestry=audio_anc,
                    transcript_ancestry=False,
                    transformations=chain_ids,
                    candidate_sha256=digest,
                    candidate_path=str(out_path.resolve()),
                    clip_length_s=length,
                )
            )
    return records
