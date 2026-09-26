from cliptrace_e1.alignment.temporal import (
    temporal_iou,
    false_continuous,
    fragmentation_error,
    padding_inflation,
)


def test_false_continuous_metric():
    assert false_continuous(1, 2) is True
    assert false_continuous(2, 2) is False
    assert false_continuous(1, 1) is False


def test_fragmentation_error():
    assert fragmentation_error(1, 2) == 1
    assert fragmentation_error(2, 2) == 0


def test_discontinuous_iou_partial():
    # claimed single continuous covering only one of two truth fragments
    claimed = [[0.0, 5.0]]
    truth = [[0.0, 5.0], [10.0, 15.0]]
    iou = temporal_iou(claimed, truth)
    assert 0.2 < iou < 0.6


def test_padding_inflation():
    claimed = [[0.0, 20.0]]
    truth = [[0.0, 10.0]]
    assert abs(padding_inflation(claimed, truth) - 2.0) < 1e-9
