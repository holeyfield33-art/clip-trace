import pytest
from cliptrace_e1.partition import build_partition, candidate_partition, PartitionManifest


def test_no_leakage():
    pm = build_partition(["S001", "S002", "S003", "S004"], ["N001", "N002", "N003", "N004"])
    pm.assert_no_leakage()
    assert not (set(pm.calibration_source_ids) & set(pm.evaluation_source_ids))
    assert not (set(pm.calibration_negative_ids) & set(pm.evaluation_negative_ids))


def test_leakage_raises():
    pm = PartitionManifest(
        version="1",
        calibration_source_ids=["S001"],
        evaluation_source_ids=["S001"],
        calibration_negative_ids=[],
        evaluation_negative_ids=[],
        rule="bad",
    )
    with pytest.raises(ValueError):
        pm.assert_no_leakage()


def test_candidate_inherits_parent_partition():
    pm = build_partition(["S001", "S002"], ["N001", "N002"])
    # derivative of calibration source -> calibration
    assert candidate_partition(pm.calibration_source_ids[0], True, pm) == "calibration"
    assert candidate_partition(pm.evaluation_source_ids[0], True, pm) == "evaluation"
    # pure negative
    assert candidate_partition(pm.calibration_negative_ids[0], False, pm) == "calibration"
