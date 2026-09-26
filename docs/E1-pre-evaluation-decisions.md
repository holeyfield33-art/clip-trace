# E1 pre-evaluation decisions

This note records the choices made before sealed evaluation. The executable
configuration, operating points, implementation hashes and data hashes are
authoritatively recorded in `results/e1/frozen-evaluation-profile.json` once
calibration finishes.

- Retain the Q0 pHash and basic spectral audio implementations unchanged as
  controls. Use enough pHash samples for full-length E1 clips; the sample cap is
  explicitly recorded rather than retaining Q0's 16-frame truncation.
- Test temporal appearance/XOR-change blocks (V-B) and geometrically verified
  ORB correspondences (V-C). Neither receives ground-truth source identities or
  intervals. Stage 2 verifies only recorded retrieval results.
- Use the official Chromaprint fpcalc 1.6.1 executable, algorithm 2, with raw
  fingerprint sequence comparison. Keep the basic adapter ineligible as the
  final C4 candidate regardless of its new-corpus scores.
- The development probe demonstrated execution, a useful local-feature crop
  response, weak heavy-layout behavior, and a pronounced Chromaprint score
  decrease on audio replacement. These observations do not establish operating
  points or E1 success.
- Calibration alone selects thresholds and the smallest qualifying tested
  duration at or above five seconds. One-, two- and three-second cases remain
  diagnostic, with no automatic support merely from a high score. Null
  operating points remain null.
- Qualification maximizes correct-parent sensitivity under the original
  modality FPR bounds. Failed positives remain in its sensitivity denominator;
  missing negative scoring cannot establish a qualifying operating point.
- Ambiguity margin is fixed at 0.05. Parent disagreement between supported
  modalities causes ambiguity. Convex fusion is considered only if both
  constituent modalities qualify and identity-held-out calibration supports it.
  It does not replace separate modality decisions.
- Use the full 1,512-row fractional design within the pre-run resource estimate.
  No live/physical capture is substituted with simulated capture. Per-candidate
  generation timeouts remain explicit failures.
- Original works, shared-content components, and all their transformed
  candidates remain inside one partition. Each active registry includes only
  that partition's registered sources. Small registries limit retrieval claims.
- Optional pretrained embeddings are deferred within this experiment's local
  implementation and CPU budget. No claim of hardware infeasibility is made.
- Lanczos, optical-flow interpolation and denoising are conventional open-source
  operations, not evidence of neural or generative reconstruction robustness.
  Registered references are normalized to 720p; 720p is a control level and
  480p/360p are reductions. Native 1080p-to-720p qualification is not claimed.
- The repeated subset regenerates candidate media, re-extracts registry and
  candidate features, repeats retrieval/verification, and additionally performs
  focused re-extraction. Compare artifact hashes, numeric scores, intervals and
  decode timestamps. A second Python runtime is available on the same machine;
  this is distinct from independent-machine reproduction.

After evaluation begins, no algorithm, threshold, ambiguity, fusion or duration
repair is allowed. E1 reports its failures as observed; repairs belong to E2.
Production ClipTrace remains outside this authorization.

## Pre-freeze execution corrections

An identity audit found shared generated intro artwork across development and
evaluation. Before evaluation feature extraction, evaluation artwork in S07,
N18 and N21 was replaced and all 98 affected candidates regenerated. The
original manifests and preliminary runs remain archived under
`results/e1/revisions/intro-isolation-v1/`.

The audio qualification subset was corrected before threshold selection to
include every waveform-preserving transformation, including harsh cases.
Only visual qualification excludes harsh positives. The interrupted calibration
pass and its implementation snapshot remain archived under
`results/e1/revisions/audio-gate-pre-freeze/`; calibration was restarted.

Development encountered a transient hash mismatch while corpus regeneration
was writing the final ground-truth file and checksum. The final ground truth
verified successfully after writing finished. The interrupted development pass
was archived under `results/e1/revisions/development-ground-truth-write-race/`
and a complete clean pass was started against the finalized corpus. No scoring
or threshold changes were made to resolve this execution failure.
