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

Thresholds use calibration only: correct-parent TPR >=70% at <=2% FPR for visual, >=75% at <=1.5% FPR for audio. Only visual operating-point qualification excludes harsh positives. Audio qualification includes all waveform-preserving transformations, including harsh cases. Duration selection tests 5, 10, 15 and 30 s; 1/2/3 s remain diagnostic. Complete threshold curves are retained. A null operating point abstains; its zeros are not proof of successful specificity.

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
- No physical capture or trained embedding. Fusion qualified on calibration but failed to generalize adequately to evaluation; AI-light operations are conventional open-source filters, not generative reconstruction.
- Same-script new-speaker and independently drawn semantic reconstruction controls do not exhaust modern AI reconstruction.
- No ownership, authorization, infringement or product-readiness claims.
- V-D embedding is budget-deferred, not shown to be infeasible on this hardware. Semantic-bleed performance of an embedding was not evaluated.
- Reaction/PIP uses a generated graphic host panel; portrait footage is a crop of real interview footage. Corpus license and provenance details accompany every asset.
- Lanczos upscaling, optical-flow interpolation and denoising are conventional transformations. No claim of a neural-upscaler or generative-model benchmark is made.
- Registered references are normalized to 720p. The 720p transform is a resolution control; 480p and 360p are genuine reductions. Native 1080p-to-720p robustness was not established.

## Interpretation and reporting review

The frozen visual candidate exceeded the sensitivity target but failed specificity: 291/351 correct parents (82.9%) and 12/48 false positives (25.0%) on its qualification subset. Chromaprint failed both targets: 222/352 correct parents (63.1%) and 3/80 false positives (3.75%). Neither modality meets its original gate. No threshold or algorithm was repaired using these results.

The visual false positives concentrate in deliberately confusing controls:

| Method | Negative identity/category | Claimed parent | False-positive excerpts |
|---|---|---|---:|
| V-C | N18: same_slide_template | S07 | 4 |
| V-C | N21: common_meme_imagery | S07 | 4 |
| V-C | N23: semantic_recreation | S07 | 4 |
| A-chromaprint | N15: same_game | S03 | 2 |
| A-chromaprint | N18: same_slide_template | S07 | 1 |

Shared templates and independently drawn semantic resemblance still caused false source attribution. The fixed runner-up margin did not resolve these cases. This is a failure of the tested common-content/ambiguity policy, not evidence that the negative works derive from the claimed source.

### Multimodal routing, all 756 evaluation candidates

These counts include short clips, harsh transforms and unavailable evidence as abstentions. They are binary routing metrics; their truth denominators differ by modality and are not the qualification subsets above.

| Route | TP / expected positives | FP / expected negatives |
|---|---:|---:|
| visual_only | 303/672 | 12/84 |
| audio_only | 222/615 | 3/141 |
| visual_OR_audio | 324/672 | 14/84 |
| visual_AND_audio | 201/615 | 1/141 |
| calibrated | 324/672 | 15/84 |

Fusion did not rescue specificity. The calibrated rule produced 15/84 false positives across all durations (15/48 among the >=5-second negative excerpts). Its calibration qualification is preserved; it is not a successful evaluation result.

For the 56 audio-replacement candidates, 28 retained C3 support with C4 insufficient; the other 28 had both modalities insufficient. None received C4 support. There were 136 modality-disagreement cases overall. C5 was not evaluated.

### Temporal limits

V-C mean IoU was 0.640 over all 672 visual positives, including missing/wrong-parent alignments as zero. Correct-parent boundary errors averaged 0.482 s at the start and 0.870 s at the end, conditional on 544 available alignments. Among 303 supported positives, IoU was 0.828, start error 0.373 s and end error 0.663 s. However, 1/6 supported multifragment cases was falsely continuous (16.7%, exceeding the 5% gate), and raw diagnostics showed 6/21. Alignment remains CAUTION; the aggregate boundary improvement does not establish reliable fragmented provenance.

| V-C transform | Expected visual positives | Mean IoU, missing = 0 | Start error s | End error s | False continuous / multifragment |
|---|---:|---:|---:|---:|---:|
| audio_offset | 9 | 0.767 | 0.250 | 0.375 | 0/0 |
| audio_replace | 56 | 0.760 | 0.286 | 0.327 | 0/0 |
| central_text | 11 | 0.039 | 5.667 | 10.333 | 0/0 |
| crop10 | 11 | 0.835 | 0.200 | 0.500 | 0/0 |
| crop25 | 56 | 0.615 | 0.571 | 1.490 | 0/0 |
| crop40 | 12 | 0.631 | 2.000 | 1.000 | 0/0 |
| crop60 | 12 | 0.053 | 7.000 | 11.667 | 0/0 |
| denoise | 8 | 0.771 | 0.286 | 0.143 | 0/0 |
| discontinuous | 10 | 0.457 | 0.444 | 9.000 | 3/10 |
| film_monitor | 8 | 0.000 | unavailable | unavailable | 0/0 |
| frame_insert_delete | 10 | 0.495 | 0.778 | 0.333 | 0/0 |
| frame_interpolation | 8 | 0.644 | 0.333 | 0.000 | 0/0 |
| h264_q18 | 8 | 0.771 | 0.286 | 0.143 | 0/0 |
| h264_q35 | 56 | 0.760 | 0.286 | 0.327 | 0/0 |
| h264_q42 | 9 | 0.796 | 0.250 | 0.125 | 0/0 |
| letterbox | 10 | 0.684 | 0.250 | 0.500 | 0/0 |
| logo | 10 | 0.703 | 0.444 | 0.333 | 0/0 |
| mirror | 11 | 0.025 | 2.000 | 7.000 | 0/0 |
| mpeg4 | 10 | 0.817 | 0.222 | 0.111 | 0/0 |
| music_overlay | 9 | 0.767 | 0.250 | 0.375 | 0/0 |
| noise_compression | 9 | 0.794 | 0.250 | 0.000 | 0/0 |
| offcenter25 | 11 | 0.794 | 0.200 | 0.500 | 0/0 |
| perspective | 10 | 0.680 | 0.500 | 0.500 | 0/0 |
| picture_in_picture | 11 | 0.705 | 0.400 | 0.300 | 0/0 |
| pitch_up2 | 9 | 0.767 | 0.250 | 0.375 | 0/0 |
| reaction_layout | 10 | 0.083 | 3.400 | 5.600 | 0/0 |
| reordered | 11 | 0.353 | 1.000 | 1.250 | 3/11 |
| rotate15 | 10 | 0.566 | 0.750 | 1.875 | 0/0 |
| rotate5 | 10 | 0.680 | 0.500 | 0.500 | 0/0 |
| scale360 | 11 | 0.843 | 0.200 | 0.500 | 0/0 |
| scale480 | 11 | 0.833 | 0.200 | 0.100 | 0/0 |
| scale720 | 11 | 0.833 | 0.200 | 0.100 | 0/0 |
| screen_recording | 8 | 0.000 | unavailable | unavailable | 0/0 |
| silence_insertion | 9 | 0.794 | 0.250 | 0.000 | 0/0 |
| speed075 | 10 | 0.417 | 0.875 | 1.312 | 0/0 |
| speed125 | 56 | 0.577 | 0.286 | 0.929 | 0/0 |
| speed150 | 11 | 0.470 | 0.556 | 1.389 | 0/0 |
| subtitles | 56 | 0.760 | 0.286 | 0.327 | 0/0 |
| trim | 56 | 0.760 | 0.286 | 0.327 | 0/0 |
| upscale_lanczos | 8 | 0.781 | 0.286 | 0.000 | 0/0 |

### Reproducibility comparison caveat

Both tested runtimes regenerated all 12 candidate media files with identical bytes; all 12 candidate feature artifacts and all 16 source feature artifacts matched. Recorded score, alignment-coordinate and decode-timestamp deltas were zero. The frozen reproducibility checker compares JSON list rankings against fresh tuple rankings, which makes its `ranking_equal` flag false even for equal contents. A separate serialization-normalized audit matched all 60 same-runtime method/candidate rankings (`reproducibility-ranking-audit.json`). The original TOLERANCE_REPRODUCIBLE labels and raw flags remain unchanged, with this reporting defect disclosed. This is two-runtime reproduction on one machine, not independent-machine evidence.

### Execution and audit notes

The two generation failures were FFmpeg interpolation timeouts (E00501 and E00572); unsupported capture cases remain explicit. The interrupted development pass caused by a transient ground-truth/checksum write race was archived and fully rerun before freezing. All 34 tests passed before the frozen run. Final integrity checks are recorded in `final-audit.json`.

This editorial review clarifies the visual-only harsh-case exclusion, corrects a stale fusion limitation sentence, and clarifies sampled CPU accounting. Original generated reports are retained in `revisions/reporting-review/`. Frozen source code, manifests, feature configuration, thresholds, raw scores, decisions and verdicts are unchanged.

## Stop condition

E1 ends here. No production matcher, dashboard, crawling or enforcement was implemented. The scientific result requires review before further engineering authorization.
