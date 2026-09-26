"""Ensure not_evaluated is distinct from zero and AMBIGUOUS is representable."""


def test_not_evaluated_not_equal_zero():
    score = None  # not_evaluated
    status = "not_evaluated"
    assert score is None
    assert status != "ok"
    # classification must skip None rather than treat as 0
    thr = 0.5
    pred = (score is not None) and (score >= thr)
    assert pred is False
    # but a real zero score would also be False — distinction is status field
    real_zero = 0.0
    assert real_zero is not None
    assert (real_zero >= thr) is False


def test_ambiguous_disposition():
    ranked = [("S001", 0.81), ("S002", 0.79), ("S003", 0.40)]
    margin = ranked[0][1] - ranked[1][1]
    disposition = "AMBIGUOUS" if margin < 0.08 else "single"
    assert disposition == "AMBIGUOUS"
