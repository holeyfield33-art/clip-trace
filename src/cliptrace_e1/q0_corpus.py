"""Q0 corpus generation: 4 diverse sources + 8 confusing negatives (synthetic, redistribution-safe)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Tuple

from .corpus import AssetRecord, scan_directory, write_manifest
from .hashing import sha256_file
from .decode import probe


def _ffmpeg(cmd: str, timeout: int = 90) -> bool:
    try:
        subprocess.check_call(cmd, shell=True, timeout=timeout)
        return True
    except Exception:
        return False


def build_q0_sources(sources_dir: Path) -> List[Path]:
    """
    Create 4 diverse synthetic sources (~20–40 s each).
    Categories: talking-head-like, screen-recording-like, outdoor/motion, low-vis/high-audio.
    """
    sources_dir.mkdir(parents=True, exist_ok=True)
    out: List[Path] = []

    # S01 talking head-like: moving face-ish rectangle + speech-like tone pattern
    p = sources_dir / "S01_talkinghead.mp4"
    if not p.exists():
        _ffmpeg(
            f'ffmpeg -hide_banner -loglevel error -y '
            f'-f lavfi -i "testsrc2=size=640x360:rate=15:duration=24" '
            f'-f lavfi -i "sine=frequency=220:duration=24" '
            f'-f lavfi -i "sine=frequency=330:duration=24" '
            f'-filter_complex "[1:a][2:a]amix=inputs=2:duration=first[a]" '
            f'-map 0:v -map "[a]" -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"'
        )
    out.append(p)

    # S02 screen recording-like: scrolling text + UI-ish bars
    p = sources_dir / "S02_screenrecord.mp4"
    if not p.exists():
        _ffmpeg(
            f'ffmpeg -hide_banner -loglevel error -y '
            f'-f lavfi -i "color=c=0x1a1a2e:s=640x360:d=24:r=15" '
            f'-f lavfi -i "sine=frequency=600:duration=24" '
            f'-vf "drawtext=text=ClipTrace\\ Q0\\ Screen:fontsize=28:fontcolor=white:x=40:y=h/2-20+10*sin(2*PI*t/3),'
            f'drawbox=x=0:y=0:w=iw:h=40:color=0x16213e:t=fill,'
            f'drawbox=x=0:y=ih-30:w=iw:h=30:color=0x0f3460:t=fill" '
            f'-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"'
        )
    out.append(p)

    # S03 outdoor / high-motion: mandelbrot zoom (motion-rich)
    p = sources_dir / "S03_outdoor_motion.mp4"
    if not p.exists():
        _ffmpeg(
            f'ffmpeg -hide_banner -loglevel error -y '
            f'-f lavfi -i "mandelbrot=size=640x360:rate=15:maxiter=100" -t 24 '
            f'-f lavfi -i "sine=frequency=150:duration=24" '
            f'-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"'
        )
    out.append(p)

    # S04 low-info visual + distinctive audio: near-static color + rich tone sequence
    p = sources_dir / "S04_lowvis_highaudio.mp4"
    if not p.exists():
        _ffmpeg(
            f'ffmpeg -hide_banner -loglevel error -y '
            f'-f lavfi -i "color=c=0x2d3436:s=640x360:d=24:r=10" '
            f'-f lavfi -i "sine=frequency=440:duration=6" '
            f'-f lavfi -i "sine=frequency=554:duration=6" '
            f'-f lavfi -i "sine=frequency=659:duration=6" '
            f'-f lavfi -i "sine=frequency=880:duration=6" '
            f'-filter_complex "[1:a][2:a][3:a][4:a]concat=n=4:v=0:a=1[a]" '
            f'-map 0:v -map "[a]" -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"'
        )
    out.append(p)

    return [x for x in out if x.exists()]


def build_q0_negatives(negatives_dir: Path) -> List[Path]:
    """8 category-matched confusing negatives."""
    negatives_dir.mkdir(parents=True, exist_ok=True)
    specs: List[Tuple[str, str]] = [
        # similar talking-head composition, different pattern
        (
            "N01_talkinghead_other.mp4",
            'ffmpeg -hide_banner -loglevel error -y '
            '-f lavfi -i "testsrc=size=640x360:rate=15:duration=20" '
            '-f lavfi -i "sine=frequency=280:duration=20" '
            '-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"',
        ),
        # unrelated software-like UI
        (
            "N02_screen_other.mp4",
            'ffmpeg -hide_banner -loglevel error -y '
            '-f lavfi -i "color=c=0x0d1117:s=640x360:d=20:r=15" '
            '-f lavfi -i "sine=frequency=700:duration=20" '
            '-vf "drawtext=text=Other\\ App:fontsize=26:fontcolor=0x58a6ff:x=50:y=100,'
            'drawbox=x=0:y=0:w=iw:h=36:color=0x21262d:t=fill" '
            '-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"',
        ),
        # similar motion-rich but different generator
        (
            "N03_motion_other.mp4",
            'ffmpeg -hide_banner -loglevel error -y '
            '-f lavfi -i "cellauto=size=640x360:rate=15:rule=30" -t 20 '
            '-f lavfi -i "sine=frequency=180:duration=20" '
            '-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"',
        ),
        # static + different distinctive speech tones
        (
            "N04_static_otherspeech.mp4",
            'ffmpeg -hide_banner -loglevel error -y '
            '-f lavfi -i "color=c=0x636e72:s=640x360:d=20:r=10" '
            '-f lavfi -i "sine=frequency=300:duration=5" '
            '-f lavfi -i "sine=frequency=450:duration=5" '
            '-f lavfi -i "sine=frequency=500:duration=5" '
            '-f lavfi -i "sine=frequency=600:duration=5" '
            '-filter_complex "[1:a][2:a][3:a][4:a]concat=n=4:v=0:a=1[a]" '
            '-map 0:v -map "[a]" -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"',
        ),
        # shared title-card style
        (
            "N05_titlecard.mp4",
            'ffmpeg -hide_banner -loglevel error -y '
            '-f lavfi -i "color=c=black:s=640x360:d=12:r=15" '
            '-f lavfi -i "sine=frequency=100:duration=12" '
            '-vf "drawtext=text=INTRO:fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" '
            '-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"',
        ),
        # room-tone-ish low audio + mild visual noise
        (
            "N06_roomtone.mp4",
            'ffmpeg -hide_banner -loglevel error -y '
            '-f lavfi -i "color=c=0x222222:s=640x360:d=16:r=10" '
            '-f lavfi -i "anoisesrc=color=pink:amplitude=0.02:duration=16" '
            '-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"',
        ),
        # comparable subject without ancestry (testsrc variant)
        (
            "N07_testsrc_variant.mp4",
            'ffmpeg -hide_banner -loglevel error -y '
            '-f lavfi -i "testsrc2=size=640x360:rate=12:duration=18" '
            '-f lavfi -i "sine=frequency=500:duration=18" '
            '-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"',
        ),
        # near-static gray + silence-ish
        (
            "N08_nearstatic_quiet.mp4",
            'ffmpeg -hide_banner -loglevel error -y '
            '-f lavfi -i "color=c=0x444444:s=640x360:d=14:r=8" '
            '-f lavfi -i "sine=frequency=50:duration=14" '
            '-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{p}"',
        ),
    ]

    out: List[Path] = []
    for name, tmpl in specs:
        p = negatives_dir / name
        if not p.exists():
            _ffmpeg(tmpl.format(p=p))
        if p.exists():
            out.append(p)
    return out


def materialize_q0_corpus(corpus_root: Path) -> Tuple[List[AssetRecord], List[AssetRecord]]:
    sources_dir = corpus_root / "sources"
    negatives_dir = corpus_root / "negatives"
    build_q0_sources(sources_dir)
    build_q0_negatives(negatives_dir)

    cat_s = {
        "S01_talkinghead.mp4": "talking_head",
        "S02_screenrecord.mp4": "screen_recording",
        "S03_outdoor_motion.mp4": "outdoor_motion",
        "S04_lowvis_highaudio.mp4": "lowvis_highaudio",
    }
    cat_n = {
        "N01_talkinghead_other.mp4": "talking_head",
        "N02_screen_other.mp4": "screen_recording",
        "N03_motion_other.mp4": "outdoor_motion",
        "N04_static_otherspeech.mp4": "lowvis_highaudio",
        "N05_titlecard.mp4": "title_card",
        "N06_roomtone.mp4": "room_tone",
        "N07_testsrc_variant.mp4": "common_template",
        "N08_nearstatic_quiet.mp4": "near_static",
    }
    sources = scan_directory(sources_dir, role="source", category_map=cat_s)
    negatives = scan_directory(negatives_dir, role="negative", category_map=cat_n)
    # stable IDs S001.. N001..
    for i, r in enumerate(sources, 1):
        r.asset_id = f"S{i:03d}"
    for i, r in enumerate(negatives, 1):
        r.asset_id = f"N{i:03d}"
    write_manifest(sources, corpus_root / "sources_manifest.json")
    write_manifest(negatives, corpus_root / "negatives_manifest.json")
    return sources, negatives
