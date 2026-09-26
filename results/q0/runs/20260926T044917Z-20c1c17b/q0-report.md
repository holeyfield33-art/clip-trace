# CLIPTRACE-E1 Q0 Report — 20260926T044917Z-20c1c17b

**Verdict: PASS**

## Reasons
- calibration/evaluation isolation enforced by partition-manifest
- threshold profile frozen before evaluation
- score distributions recorded
- failed candidates retained in results
- AMBIGUOUS disposition represented
- not_evaluated distinct from zero in status fields
- reproducibility BIT_DETERMINISTIC

## Corpus / partition
- Calibration sources: ['S001', 'S002']
- Evaluation sources: ['S003', 'S004']
- Calibration negatives: ['N001', 'N002', 'N003', 'N004']
- Evaluation negatives: ['N005', 'N006', 'N007', 'N008']

## Run meta
```
{
  "run_id": "20260926T044917Z-20c1c17b",
  "tag": "q0a",
  "started_finished": "2026-09-26T04:54:03Z",
  "n_ok": 48,
  "n_failed": 0,
  "index_wall_s": 12.329321587999999,
  "run_wall_s": 272.366263154,
  "max_rss_kb": 44104.0,
  "n_sources_indexed": 4
}
```

## Score distributions (calibration)
```
{
  "audio": {
    "negative": {
      "max": 0.9999991335168651,
      "mean": 0.9997258154442532,
      "median": 0.9999810983713338,
      "min": 0.9993548062633502,
      "n": 8,
      "p10": 0.9993829203264694,
      "p90": 0.9999877034347198
    },
    "overlap_hint": "inverted_or_collapsed",
    "positive": {
      "max": 0.9999877034347198,
      "mean": 0.9991504089560647,
      "median": 0.9993942685930101,
      "min": 0.9962972694845961,
      "n": 16,
      "p10": 0.9976610278752788,
      "p90": 0.9999877034347198
    }
  },
  "n_audio_samples": 24,
  "n_visual_samples": 24,
  "visual": {
    "negative": {
      "max": 0.53125,
      "mean": 0.19921875,
      "median": 0.10546875,
      "min": 0.07421875,
      "n": 4,
      "p10": 0.07421875,
      "p90": 0.53125
    },
    "overlap_hint": "low_overlap",
    "positive": {
      "max": 1.0,
      "mean": 0.5756249999999999,
      "median": 0.625,
      "min": 0.0,
      "n": 20,
      "p10": 0.03749999999999998,
      "p90": 1.0
    }
  }
}
```

## Threshold profile
- Rule: max_tpr_at_fpr_le_0.20
- Visual threshold: 0.55
- Audio threshold: 1.0
- Profile sha256: ae7ee1efc206c0b91a731284bdcc3a8b533713f6db651333897aa603a5dfc571

## Evaluation metrics
```
{
  "evaluation_audio": {
    "f1": null,
    "fn": 16,
    "fp": 0,
    "fpr": 0.0,
    "precision": null,
    "recall": 0.0,
    "support_negative": 8,
    "support_positive": 16,
    "tn": 8,
    "tp": 0,
    "tpr": 0.0
  },
  "evaluation_visual": {
    "f1": 0.8780487804878048,
    "fn": 2,
    "fp": 3,
    "fpr": 0.75,
    "precision": 0.8571428571428571,
    "recall": 0.9,
    "support_negative": 4,
    "support_positive": 20,
    "tn": 1,
    "tp": 18,
    "tpr": 0.9
  },
  "n_ambiguous_all_partitions": 9,
  "n_derivative_eval_approx": 20,
  "n_evaluation_scored_audio": 24,
  "n_evaluation_scored_visual": 24,
  "n_failed": 0,
  "profile_sha256": "ae7ee1efc206c0b91a731284bdcc3a8b533713f6db651333897aa603a5dfc571",
  "retrieval_recall_at_1": 0.9,
  "retrieval_recall_at_5": 1.0,
  "run_id": "20260926T044917Z-20c1c17b",
  "selection_rule": "max_tpr_at_fpr_le_0.20",
  "temporal": {
    "false_continuous_count": 0,
    "false_continuous_rate": 0.0,
    "mean_end_error_s": 3.2222222222222223,
    "mean_iou": 0.5501489251489251,
    "mean_start_error_s": 0.8888888888888888,
    "n": 20
  },
  "thresholds": {
    "audio": 1.0,
    "visual": 0.55
  }
}
```

## Reproducibility
```
{
  "mode": "focused_reextract",
  "n_compared": 8,
  "visual_artifact_hash_matches": 8,
  "audio_artifact_hash_matches": 8,
  "classification": "BIT_DETERMINISTIC",
  "note": "Full dual-run deferred due to 1.2GB RAM / 2CPU limits; focused re-extract of 8 candidates."
}
```

## Note
Q0 PASS does not imply E1 scientific GO. It only qualifies the harness.

