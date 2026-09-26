"""Content-addressed evidence artifact storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..hashing import content_addressed_path, sha256_json


def store_artifact(root: Path, obj: Dict[str, Any], suffix: str = ".json") -> str:
    """
    Write artifact under content-addressed path.
    Returns the SHA-256 digest used as the address.
    """
    digest = obj.get("artifact_sha256") or sha256_json(obj)
    path = content_addressed_path(root, digest, suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest


def load_artifact(root: Path, digest: str, suffix: str = ".json") -> Dict[str, Any]:
    path = content_addressed_path(root, digest, suffix)
    return json.loads(path.read_text(encoding="utf-8"))
