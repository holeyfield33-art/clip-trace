from pathlib import Path
from cliptrace_e1.ground_truth import GroundTruthRecord, write_ground_truth, load_ground_truth


def test_roundtrip(tmp_path: Path):
    rec = GroundTruthRecord(
        candidate_id="C0001",
        source_id="S01",
        is_derivative=True,
        source_intervals_ms=[(1000, 5000)],
        candidate_intervals_ms=[(0, 4000)],
        visual_ancestry=True,
        audio_ancestry=False,
        transcript_ancestry=False,
        transformations=["crop_25"],
        candidate_sha256="abc",
        candidate_path="/tmp/x.mp4",
        clip_length_s=4.0,
    )
    p = tmp_path / "gt.json"
    write_ground_truth([rec], p)
    loaded = load_ground_truth(p)
    assert len(loaded) == 1
    assert loaded[0].candidate_id == "C0001"
    assert loaded[0].source_intervals_ms == [(1000, 5000)]
    assert loaded[0].audio_ancestry is False
