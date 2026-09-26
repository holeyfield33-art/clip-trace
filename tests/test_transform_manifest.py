"""Transformation manifest consistency checks (unit-level)."""

from cliptrace_e1.transforms import TransformSpec


def test_transform_spec_id():
    t = TransformSpec(id="crop_25", params={"crop_pct": 25})
    assert t.id == "crop_25"
    assert t.params["crop_pct"] == 25
