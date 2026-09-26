"""SHA-256 and content-addressing helpers. Deterministic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Union


def sha256_file(path: Union[str, Path], chunk_size: int = 1 << 20) -> str:
    """Return hex SHA-256 of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj: Any) -> str:
    """Canonical JSON (sorted keys, no whitespace) then SHA-256."""
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_bytes(payload.encode("utf-8"))


def content_addressed_path(root: Path, digest: str, suffix: str = "") -> Path:
    """Return path of form root/ab/cd/<digest><suffix> for sharding."""
    return root / digest[:2] / digest[2:4] / f"{digest}{suffix}"
