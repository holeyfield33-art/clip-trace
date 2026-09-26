# CLIPTRACE-E1

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

MIT
