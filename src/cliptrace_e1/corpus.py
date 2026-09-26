"""Corpus management: sources, negatives, manifests."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .hashing import sha256_file
from .decode import probe


@dataclass
class AssetRecord:
    asset_id: str
    filename: str
    path: str
    sha256: str
    duration_s: float
    width: int
    height: int
    fps: float
    has_audio: bool
    category: str
    role: str  # "source" | "negative"
    license_note: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def scan_directory(
    directory: Path,
    role: str,
    category_map: Optional[Dict[str, str]] = None,
) -> List[AssetRecord]:
    """Scan a directory of media files and build AssetRecords."""
    records: List[AssetRecord] = []
    if not directory.exists():
        return records
    for p in sorted(directory.iterdir()):
        if p.suffix.lower() not in {".mp4", ".mkv", ".webm", ".mov", ".avi"}:
            continue
        info = probe(p)
        digest = sha256_file(p)
        asset_id = f"{role[0].upper()}{len(records)+1:03d}"
        cat = (category_map or {}).get(p.name, "unspecified")
        records.append(
            AssetRecord(
                asset_id=asset_id,
                filename=p.name,
                path=str(p.resolve()),
                sha256=digest,
                duration_s=info.duration_s,
                width=info.width,
                height=info.height,
                fps=info.fps,
                has_audio=info.has_audio,
                category=cat,
                role=role,
                license_note="",
            )
        )
    return records


def write_manifest(records: List[AssetRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(r) for r in records]
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manifest(path: Path) -> List[AssetRecord]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [AssetRecord(**row) for row in data]


def ensure_smoke_placeholder_videos(corpus_root: Path) -> None:
    """
    Create two tiny synthetic videos (source + negative) if the corpus is empty.
    Uses ffmpeg color/test sources so the smoke pipeline can run without external media.
    """
    sources = corpus_root / "sources"
    negatives = corpus_root / "negatives"
    sources.mkdir(parents=True, exist_ok=True)
    negatives.mkdir(parents=True, exist_ok=True)

    src = sources / "S01_talkinghead_smoke.mp4"
    neg = negatives / "N01_unrelated_smoke.mp4"

    if not src.exists():
        # 8 s, 320x240, solid color + sine audio (distinctive)
        cmd = (
            'ffmpeg -hide_banner -loglevel error -y '
            '-f lavfi -i "color=c=blue:s=320x240:d=8:r=10" '
            '-f lavfi -i "sine=frequency=440:duration=8" '
            '-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest '
            f'"{src}"'
        )
        import subprocess
        subprocess.check_call(cmd, shell=True)

    if not neg.exists():
        cmd = (
            'ffmpeg -hide_banner -loglevel error -y '
            '-f lavfi -i "color=c=red:s=320x240:d=8:r=10" '
            '-f lavfi -i "sine=frequency=880:duration=8" '
            '-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest '
            f'"{neg}"'
        )
        import subprocess
        subprocess.check_call(cmd, shell=True)
