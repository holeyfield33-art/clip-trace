"""Transformation engine: generate candidates with recorded ground truth."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .hashing import sha256_file
from .ground_truth import GroundTruthRecord


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
    """Apply a short chain of transforms via ffmpeg."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Special path: discontinuous two-fragment excerpt
    if any(t.get("fragments") == 2 for t in transforms):
        return _discontinuous_two(source_path, out_path, transforms, duration_s or 6.0)

    if any(t.get("reorder_blocks") for t in transforms):
        return _reorder_two(source_path, out_path, transforms, duration_s or 6.0)

    vf_parts: List[str] = []
    af_parts: List[str] = []
    extra_inputs: List[str] = []
    audio_replaced = False

    ss_args: List[str] = []
    if start_s > 0:
        ss_args = ["-ss", f"{start_s:.3f}"]
    t_args: List[str] = []
    if duration_s is not None:
        t_args = ["-t", f"{duration_s:.3f}"]

    for t in transforms:
        if "scale" in t:
            vf_parts.append(f"scale={t['scale']}")
        if "crop_pct" in t:
            pct = float(t["crop_pct"]) / 100.0
            keep = 1.0 - pct
            vf_parts.append(f"crop=iw*{keep}:ih*{keep}")
        if t.get("hflip"):
            vf_parts.append("hflip")
        if "rotate_deg" in t:
            rad = float(t["rotate_deg"]) * 3.14159265 / 180.0
            vf_parts.append(f"rotate={rad}:fillcolor=black")
        if t.get("overlay") == "subtitles":
            vf_parts.append(
                "drawtext=text='Q0 subtitle line':fontsize=18:fontcolor=white:"
                "borderw=2:bordercolor=black:x=20:y=h-40"
            )
        if t.get("audio") == "replace":
            extra_inputs += ["-f", "lavfi", "-i", "sine=frequency=330:duration=60"]
            audio_replaced = True
        if "audio_shift_s" in t:
            shift = float(t["audio_shift_s"])
            af_parts.append(f"adelay={int(shift*1000)}|{int(shift*1000)}")
        if "pitch_semitones" in t:
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


def _discontinuous_two(
    source_path: Path,
    out_path: Path,
    transforms: Sequence[Dict[str, Any]],
    total_duration_s: float,
) -> bool:
    """Two non-contiguous fragments concatenated."""
    half = max(1.0, total_duration_s / 2.0)
    # fragment A from start, fragment B from later region
    tmp_a = out_path.with_suffix(".fragA.mp4")
    tmp_b = out_path.with_suffix(".fragB.mp4")
    # strip discontinuous marker for encoding of each frag
    base = [t for t in transforms if not t.get("fragments")]
    ok_a = apply_transform_chain(source_path, tmp_a, base, start_s=0.5, duration_s=half)
    ok_b = apply_transform_chain(source_path, tmp_b, base, start_s=8.0, duration_s=half)
    if not (ok_a and ok_b):
        return False
    list_file = out_path.with_suffix(".txt")
    list_file.write_text(f"file '{tmp_a.resolve()}'\nfile '{tmp_b.resolve()}'\n", encoding="utf-8")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(out_path),
    ]
    ok = _run_ffmpeg(cmd)
    tmp_a.unlink(missing_ok=True)
    tmp_b.unlink(missing_ok=True)
    list_file.unlink(missing_ok=True)
    return ok and out_path.exists()


def _reorder_two(
    source_path: Path,
    out_path: Path,
    transforms: Sequence[Dict[str, Any]],
    total_duration_s: float,
) -> bool:
    """Two blocks swapped in time order."""
    half = max(1.0, total_duration_s / 2.0)
    tmp_a = out_path.with_suffix(".blkA.mp4")
    tmp_b = out_path.with_suffix(".blkB.mp4")
    base = [t for t in transforms if not t.get("reorder_blocks")]
    ok_a = apply_transform_chain(source_path, tmp_a, base, start_s=1.0, duration_s=half)
    ok_b = apply_transform_chain(source_path, tmp_b, base, start_s=1.0 + half + 1.0, duration_s=half)
    if not (ok_a and ok_b):
        return False
    # concat B then A (reordered)
    list_file = out_path.with_suffix(".txt")
    list_file.write_text(f"file '{tmp_b.resolve()}'\nfile '{tmp_a.resolve()}'\n", encoding="utf-8")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(out_path),
    ]
    ok = _run_ffmpeg(cmd)
    tmp_a.unlink(missing_ok=True)
    tmp_b.unlink(missing_ok=True)
    list_file.unlink(missing_ok=True)
    return ok and out_path.exists()


def generate_candidates_for_source(
    source: Dict[str, Any],
    out_dir: Path,
    chains: List[List[Dict[str, Any]]],
    clip_lengths_s: List[float],
    id_start: int = 1,
) -> List[GroundTruthRecord]:
    """Generate candidates for one source across chains and lengths."""
    records: List[GroundTruthRecord] = []
    src_path = Path(source["path"])
    src_dur = float(source["duration_s"])
    out_dir.mkdir(parents=True, exist_ok=True)
    idx = id_start

    for length in clip_lengths_s:
        if length > src_dur - 0.5:
            continue
        start = max(0.0, min(1.0, (src_dur - length) / 4.0))
        for chain in chains:
            chain_ids = [t.get("id", "unknown") for t in chain]
            is_disc = any(t.get("fragments") == 2 for t in chain)
            is_reord = any(t.get("reorder_blocks") for t in chain)

            # length policy: discontinuous/reorder need enough material
            if (is_disc or is_reord) and length < 5:
                continue

            cid = f"C{idx:04d}"
            idx += 1
            out_name = f"{cid}_{source['asset_id']}_{'_'.join(chain_ids)}_{length:.0f}s.mp4"
            out_path = out_dir / out_name
            ok = apply_transform_chain(src_path, out_path, chain, start_s=start, duration_s=length)
            if not ok or not out_path.exists():
                # record failure explicitly
                records.append(
                    GroundTruthRecord(
                        candidate_id=cid,
                        source_id=source["asset_id"],
                        is_derivative=True,
                        source_intervals_ms=[],
                        candidate_intervals_ms=[],
                        visual_ancestry=True,
                        audio_ancestry=not any(t.get("audio") == "replace" for t in chain),
                        transcript_ancestry=False,
                        transformations=chain_ids + ["FAILED"],
                        candidate_sha256="",
                        candidate_path=str(out_path),
                        clip_length_s=length,
                        extra={"status": "failed"},
                    )
                )
                continue

            digest = sha256_file(out_path)
            audio_anc = not any(t.get("audio") == "replace" for t in chain)
            visual_anc = True

            if is_disc:
                half_ms = int((length / 2.0) * 1000)
                # GT: two source intervals (early + later)
                src_intervals = [
                    (int(0.5 * 1000), int((0.5 + length / 2.0) * 1000)),
                    (int(8.0 * 1000), int((8.0 + length / 2.0) * 1000)),
                ]
                cand_intervals = [(0, half_ms), (half_ms, int(length * 1000))]
            elif is_reord:
                half_ms = int((length / 2.0) * 1000)
                # blocks swapped: candidate [0,half] comes from later source region
                src_intervals = [
                    (int((1.0 + length / 2.0 + 1.0) * 1000), int((1.0 + length / 2.0 + 1.0 + length / 2.0) * 1000)),
                    (int(1.0 * 1000), int((1.0 + length / 2.0) * 1000)),
                ]
                cand_intervals = [(0, half_ms), (half_ms, int(length * 1000))]
            else:
                src_start_ms = int(start * 1000)
                src_end_ms = int((start + length) * 1000)
                # speed change compresses/expands candidate duration relative to source
                speed = 1.0
                for t in chain:
                    if "speed" in t:
                        speed = float(t["speed"])
                src_end_ms = int((start + length * speed) * 1000) if speed != 1.0 else src_end_ms
                src_intervals = [(src_start_ms, src_end_ms)]
                cand_intervals = [(0, int(length * 1000))]

            records.append(
                GroundTruthRecord(
                    candidate_id=cid,
                    source_id=source["asset_id"],
                    is_derivative=True,
                    source_intervals_ms=src_intervals,
                    candidate_intervals_ms=cand_intervals,
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


def generate_smoke_candidates(
    source: Dict[str, Any],
    out_dir: Path,
    transform_chains: List[List[Dict[str, Any]]],
    clip_lengths_s: List[float],
) -> List[GroundTruthRecord]:
    return generate_candidates_for_source(source, out_dir, transform_chains, clip_lengths_s, id_start=1)
