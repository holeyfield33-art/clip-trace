# CLIPTRACE-E1

The new single-organization ClipTrace service is documented in
[`docs/ClipTrace-MVP.md`](docs/ClipTrace-MVP.md). It runs separately from this
frozen research harness and keeps experimental similarity scores as review
leads rather than automatic derivation claims.

Experimental harness for evaluating whether locally runnable media-matching methods can reliably detect real video derivation under realistic transformations **without** unacceptable false positives or fabricated temporal provenance.

**This is not the ClipTrace production service.**

## Scientific boundary

E1 evaluates only the empirical components behind:

- **C3** Visual Derivation
- **C4** Audio Derivation
- **C5** Transcript Derivation (exploratory)

E1 does **not** test C1 (beyond SHA-256 bookkeeping), C2, C7, C8, or C9.

Perceptual similarity is never used to infer ownership, authorization, infringement, or authorship.

## Quick start (smoke pipeline)

```bash
# Install
pip install -e ".[dev]"

# Record environment
python -m cliptrace_e1.cli env record

# Validate / build minimal corpus (smoke)
python -m cliptrace_e1.cli corpus smoke

# Generate a few candidates
python -m cliptrace_e1.cli candidates generate --config configs/transforms-v1.yaml --smoke

# Run fingerprints + retrieval + alignment on smoke set
python -m cliptrace_e1.cli run --config configs/experiment-v1.yaml --smoke

# Metrics + report
python -m cliptrace_e1.cli metrics --run-id <run_id>
python -m cliptrace_e1.cli report --run-id <run_id>
```

## Repository layout

See the project root tree. Large media, fingerprints, and result artifacts are git-ignored.

## Design rules

- Ground truth is generated from the transformation process, never from matcher output.
- Matchers never receive ground truth.
- Retrieval (Stage 1) and alignment/verification (Stage 2) are measured separately.
- Failed processing becomes an explicit result state (`not_evaluated`), never a silent zero.
- Configuration is immutable per run; runs are never overwritten.
- The experiment is allowed to conclude **CORE NO-GO**.

## License

Apache-2.0

## Full E1 experiment

The full experiment is separate from the Q0 runner. Its scientific outputs live
under `results/e1/`, including the corpus/partition manifests, frozen profile,
candidate journals, calibration curves, sealed results, and `report.md`.
Media retain their individual licenses and attribution in `corpus-manifest.json`;
the repository Apache-2.0 license does not replace third-party media licenses.

Prerequisites: FFmpeg/ffprobe, Python with the project dependencies plus
`opencv-python-headless`, `scipy`, and `psutil`; official Chromaprint fpcalc 1.6.1
under `tools/chromaprint/`. Corpus generation uses Windows offline speech and
Arial for the self-created controls. It does not require production services.

```powershell
python tools/e1_discover.py
python tools/e1_acquire.py
python tools/e1_controls.py
python tools/e1_pilot.py
python -m cliptrace_e1.e1_design
python -m cliptrace_e1.e1_run development
# Complete development diagnosis before calibration; do not inspect evaluation scores.
python -m cliptrace_e1.e1_run calibration
python -m cliptrace_e1.e1_run freeze
python -m cliptrace_e1.e1_run evaluation
python -m cliptrace_e1.e1_report reproduce
python -m cliptrace_e1.e1_report
```

The frozen profile binds the implementation and principal input hashes.
Re-running a completed partition preserves its results. A changed implementation
cannot resume an existing scoring run. Generation failures and unsupported
capture cases retain explicit rows; none are removed from denominators.
`tools/e1_monitor.py <label> <command...>` records sampled process-tree resource
usage for a stage. Second-runtime reproduction uses the same frozen code with
`python -m cliptrace_e1.e1_report reproduce-cross` in the separate runtime.

Do not restart or tune the sealed evaluation. A repair after final scoring is E2.
