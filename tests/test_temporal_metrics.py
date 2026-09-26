from cliptrace_e1.alignment.temporal import temporal_iou, start_end_error


def test_iou_identical():
    a = [[0.0, 10.0]]
    assert abs(temporal_iou(a, a) - 1.0) < 1e-9


def test_iou_partial():
    claimed = [[0.0, 5.0]]
    truth = [[0.0, 10.0]]
    iou = temporal_iou(claimed, truth)
    assert 0.49 < iou < 0.51


def test_iou_empty():
    assert temporal_iou([], [[0, 1]]) == 0.0
    assert temporal_iou([], []) == 1.0


def test_start_end_error():
    err = start_end_error([[1.0, 5.0]], [[0.0, 6.0]])
    assert abs(err["start_error_s"] - 1.0) < 1e-9
    assert abs(err["end_error_s"] - 1.0) < 1e-9
