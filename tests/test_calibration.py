from cliptrace_e1.calibration import ScoreSample, select_threshold, score_distributions, build_threshold_profile


def test_select_threshold_max_tpr_fpr_cap():
    # positives high, negatives low
    samples = (
        [ScoreSample(f"p{i}", 0.9, True, "visual") for i in range(10)]
        + [ScoreSample(f"n{i}", 0.1, False, "visual") for i in range(10)]
    )
    thr, curve, rule = select_threshold(samples, rule="max_tpr_at_fpr_le_0.20")
    assert thr is not None
    assert 0.0 <= thr <= 1.0
    assert len(curve) > 5


def test_not_evaluated_not_in_samples():
    # caller must filter; distributions handle empty
    dist = score_distributions([])
    assert dist["positive"]["n"] == 0


def test_profile_immutable_fields():
    samples = {
        "visual": [ScoreSample("a", 0.8, True, "visual"), ScoreSample("b", 0.2, False, "visual")],
        "audio": [ScoreSample("a", 0.7, True, "audio"), ScoreSample("b", 0.3, False, "audio")],
    }
    profile = build_threshold_profile(samples)
    assert "visual" in profile.modalities
    assert profile.modalities["visual"]["threshold"] is not None
