# CLIPTRACE-E1 scientific report

**Overall verdict: CORE NO-GO.**

This is a finite-corpus derivation experiment, not a production implementation or ownership determination. No evaluation repair/tuning was performed after the frozen profile.

## Independent verdicts

- visual: **VISUAL-NO-GO**
- audio: **AUDIO-NO-GO**
- alignment: **CAUTION**
- reproducibility: **REPRODUCIBILITY-GO**

## Preserved Q0 evidence

Authorized baseline `aeefc29f066a558322ab08dd477a5ad0ec04b56e`; smoke `765509294925929cc7144af9d4ba036d3652c2b9`. Q0 pHash TPR 0.90 / FPR 0.75 remains a failed sole-MVP control. The collapsed basic audio adapter remains an ineligible final C4 control. Q0 IoU ~0.55, start error ~0.89 s, end error ~3.2 s, false-continuous 0 are not E1 success evidence.

## Design and sealing

16 source identities / 24 negative identities; development 4/6, calibration 4/6, evaluation 8/12. Common-content components remain inside a partition. Each partition has its own registry. The 1,512-row fractional manifest specifies the sampled interactions and all seven requested lengths. All generation and scoring states are retained.

Frozen profile SHA-256: `8bc5c78b4b02eaf44c4367b55628f82a6fee748416f33b43a5e836252addd25e`.
Partition SHA-256: `672a5980789f9933ff3dea8ab66ac0e8e5ce1599e47b0f5dad4947a9e8cbacdd`.
Code and principal data hashes are checked before evaluation and report generation. Stage 2 sees only Stage-1 retrieved parents, with no true-parent injection. With only 4 or 8 registered sources, recall@10 cannot demonstrate retrieval scalability.

A pre-evaluation identity audit found an accidentally shared generated intro between development and evaluation. The evaluation-only artwork was independently replaced in S07/N18/N21 and all 98 affected variants regenerated. Preliminary development/calibration passes were archived and rerun. No evaluation fingerprints or scores had been opened. Revision plans, old manifests and replacement outcomes are retained under `revisions/` and `corpus-revision-*.json`.

## Calibration-selected operating points

| Candidate | Threshold | Minimum duration | Role |
|---|---:|---:|---|
| V-A | NO OPERATING POINT | — | control only |
| V-B | NO OPERATING POINT | — | candidate |
| V-C | 0.163 | 5 s | candidate |
| A-baseline | NO OPERATING POINT | — | control only |
| A-chromaprint | 0.503 | 5 s | candidate |

Best calibration correct-parent TPR attainable at the required FPR bound for the original >=5 s subset (including candidates that failed the TPR gate):

| Candidate | Correct parent / positives | FP / negatives | Threshold |
|---|---:|---:|---:|
| V-A | 0/178 | 0/24 | 1.000 |
| V-B | 112/178 | 0/24 | 0.420 |
| V-C | 140/178 | 0/24 | 0.163 |
| A-baseline | 0/176 | 0/40 | 1.000 |
| A-chromaprint | 146/176 | 0/40 | 0.503 |

Thresholds use calibration only: correct-parent TPR >=70% at <=2% FPR for visual, >=75% at <=1.5% FPR for audio. Harsh positives are reported separately and excluded only from operating-point qualification. Duration selection tests 5, 10, 15 and 30 s; 1/2/3 s remain diagnostic. Complete threshold curves are retained. A null operating point abstains; its zeros are not proof of successful specificity.

## Sealed evaluation: qualification subsets

| Candidate | Correct parent / positive | Wrong parent / positive | FP / available negatives | Ambiguous / positive |
|---|---:|---:|---:|---:|
| V-A | 0/351 (0.000) | 0/351 (0.000) | 0/48 (0.000) | 0/351 (0.000) |
| V-B | 0/351 (0.000) | 0/351 (0.000) | 0/48 (0.000) | 0/351 (0.000) |
| V-C | 291/351 (0.829) | 0/351 (0.000) | 12/48 (0.250) | 0/351 (0.000) |
| A-baseline | 0/352 (0.000) | 0/352 (0.000) | 0/80 (0.000) | 0/352 (0.000) |
| A-chromaprint | 222/352 (0.631) | 0/352 (0.000) | 3/80 (0.037) | 0/352 (0.000) |

Exact numerators, denominators, binomial intervals, identity-level any-FP rates, processing availability and retrieval@1/5/10 are in `metrics.json`. Candidate-level intervals are descriptive because transformed observations are correlated. Twelve evaluation negative identities cannot establish a population FPR of 1.5–2% precisely. Breakdowns by transform, duration, category and severity are included; pooled means do not substitute for them.

## Duration-specific decisions

All transforms are included here, including harsh and unsupported cases. Null operating points abstain at every duration; this is not evidence that their raw scores separate positives and negatives.

### V-A

| Seconds | Correct parent / expected positives | FP / scored negatives | Ambiguous positives | Unavailable positives |
|---:|---:|---:|---:|---:|
| 1 | 0/96 | 0/12 | 0 | 0 |
| 2 | 0/96 | 0/12 | 0 | 2 |
| 3 | 0/96 | 0/12 | 0 | 4 |
| 5 | 0/96 | 0/12 | 0 | 4 |
| 10 | 0/96 | 0/12 | 0 | 6 |
| 15 | 0/96 | 0/12 | 0 | 1 |
| 30 | 0/96 | 0/12 | 0 | 0 |

### V-B

| Seconds | Correct parent / expected positives | FP / scored negatives | Ambiguous positives | Unavailable positives |
|---:|---:|---:|---:|---:|
| 1 | 0/96 | 0/12 | 0 | 0 |
| 2 | 0/96 | 0/12 | 0 | 2 |
| 3 | 0/96 | 0/12 | 0 | 4 |
| 5 | 0/96 | 0/12 | 0 | 4 |
| 10 | 0/96 | 0/12 | 0 | 6 |
| 15 | 0/96 | 0/12 | 0 | 1 |
| 30 | 0/96 | 0/12 | 0 | 0 |

### V-C

| Seconds | Correct parent / expected positives | FP / scored negatives | Ambiguous positives | Unavailable positives |
|---:|---:|---:|---:|---:|
| 1 | 0/96 | 0/12 | 0 | 0 |
| 2 | 0/96 | 0/12 | 0 | 2 |
| 3 | 0/96 | 0/12 | 0 | 4 |
| 5 | 74/96 | 3/12 | 0 | 4 |
| 10 | 74/96 | 3/12 | 0 | 6 |
| 15 | 80/96 | 3/12 | 0 | 1 |
| 30 | 75/96 | 3/12 | 0 | 0 |

### A-baseline

| Seconds | Correct parent / expected positives | FP / scored negatives | Ambiguous positives | Unavailable positives |
|---:|---:|---:|---:|---:|
| 1 | 0/87 | 0/21 | 0 | 0 |
| 2 | 0/88 | 0/20 | 0 | 2 |
| 3 | 0/88 | 0/20 | 0 | 4 |
| 5 | 0/88 | 0/20 | 0 | 4 |
| 10 | 0/88 | 0/20 | 0 | 6 |
| 15 | 0/88 | 0/20 | 0 | 1 |
| 30 | 0/88 | 0/20 | 0 | 0 |

### A-chromaprint

| Seconds | Correct parent / expected positives | FP / scored negatives | Ambiguous positives | Unavailable positives |
|---:|---:|---:|---:|---:|
| 1 | 0/87 | 0/0 | 0 | 87 |
| 2 | 0/88 | 0/0 | 0 | 88 |
| 3 | 0/88 | 0/20 | 0 | 6 |
| 5 | 58/88 | 2/20 | 0 | 4 |
| 10 | 54/88 | 1/20 | 0 | 6 |
| 15 | 53/88 | 0/20 | 0 | 1 |
| 30 | 57/88 | 0/20 | 0 | 0 |

## Temporal evidence

| Method | IoU (missing = 0) | Start error s | End error s | Correct-parent alignment coverage | False continuous / multifragment |
|---|---:|---:|---:|---:|---:|
| V-A | 0.532 | 0.766 | 1.442 | 479/672 | 15/21 |
| V-B | 0.453 | 0.485 | 1.405 | 388/672 | 7/21 |
| V-C | 0.640 | 0.482 | 0.870 | 544/672 | 6/21 |

Boundary errors are conditional on correct-parent alignment; missing and wrong-parent alignments score zero IoU. Fragmentation, padding, supported-only results and transform-specific metrics are retained in `temporal-metrics.json`. Source/candidate interval pairs preserve reordered mapping. Physical screen-capture strata are unsupported, not successful zeros.

## Modality separation and ambiguity

Selected visual: `V-C`. Selected audio: `A-chromaprint`. Every evaluation candidate has separate C3/C4 decisions, C5 not evaluated, disagreement states, visual-only/audio-only/OR/AND routes in `modality-decisions.jsonl`. Audio replacement can retain C3 while losing C4. Conflicting supported parents cause AMBIGUOUS. Calibrated fusion status: `evaluated`; the profile records its identity-held-out qualification or reason for abstention.

Shared B-roll is deliberately inserted into two independently assembled evaluation works; the donor is an attribution negative. Shared slide/meme templates and same-script different-voice controls also test ordinary resemblance. Common-content ambiguity is an empirical policy under test; failures remain visible rather than relabeled using truth.

## Reproducibility and resources

- V-A: TOLERANCE_REPRODUCIBLE (tested runtimes, representative subset).
- V-B: TOLERANCE_REPRODUCIBLE (tested runtimes, representative subset).
- V-C: TOLERANCE_REPRODUCIBLE (tested runtimes, representative subset).
- A-baseline: TOLERANCE_REPRODUCIBLE (tested runtimes, representative subset).
- A-chromaprint: TOLERANCE_REPRODUCIBLE (tested runtimes, representative subset).

Repeated 12 complete candidate comparisons with freshly extracted registry features, plus focused extraction. Second-runtime status: `evaluated`. Artifact hashes, score deltas, alignment deltas and decode timestamps are in `reproducibility.json`. Independent second-machine reproduction is not established.

Pre-run estimate: 13.92 CPU-hours (extrapolated from Q0 wall time, not measured Q0 CPU). Actual summed generation worker wall time: 5610.7 s; candidate matching worker wall time: 3302.5 s; peak sampled Python RSS: 159.6 MB; artifacts: 184.0 MB. Process-tree CPU/RAM accounting is limited; see resource metrics.

## Denominator reconciliation

```json
{
  "manifest": 1512,
  "generation": {
    "evaluated": 1470,
    "unsupported": 40,
    "failed": 2
  },
  "evaluation_expected": 756,
  "evaluation_results": 756,
  "evaluation_states": {
    "evaluated": 739,
    "unsupported": 16,
    "failed": 1
  }
}
```

## Scope limits

- Only 8 evaluation registered sources and 12 independent negative identities; sparse category strata.
- Negative duration excerpts are correlated; confidence intervals do not create additional independent examples.
- No physical capture, trained embedding or validated calibrated fusion; AI-light operations are conventional open-source filters, not generative reconstruction.
- Same-script new-speaker and independently drawn semantic reconstruction controls do not exhaust modern AI reconstruction.
- No ownership, authorization, infringement or product-readiness claims.
- V-D embedding is budget-deferred, not shown to be infeasible on this hardware. Semantic-bleed performance of an embedding was not evaluated.
- Reaction/PIP uses a generated graphic host panel; portrait footage is a crop of real interview footage. Corpus license and provenance details accompany every asset.
- Lanczos upscaling, optical-flow interpolation and denoising are conventional transformations. No claim of a neural-upscaler or generative-model benchmark is made.
- Registered references are normalized to 720p. The 720p transform is a resolution control; 480p and 360p are genuine reductions. Native 1080p-to-720p robustness was not established.

## Stop condition

E1 ends here. No production matcher, dashboard, crawling or enforcement was implemented. The scientific result requires review before further engineering authorization.
