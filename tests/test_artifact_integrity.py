from pathlib import Path
from cliptrace_e1.evidence.artifacts import store_artifact, load_artifact
from cliptrace_e1.hashing import sha256_json


def test_store_and_load(tmp_path: Path):
    obj = {"method": "frame_phash", "frame_hashes": ["abc"], "version": "1"}
    digest = store_artifact(tmp_path, obj)
    assert len(digest) == 64
    loaded = load_artifact(tmp_path, digest)
    assert loaded["method"] == "frame_phash"
    # content address stable
    digest2 = store_artifact(tmp_path, obj)
    assert digest == digest2
