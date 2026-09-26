# ClipTrace

ClipTrace is a self-hosted, single-organization workspace for recording video provenance and checking candidate media. It stores exact file hashes, signed origin and derivative declarations, scoped authorization records, human review findings, and exportable evidence bundles. A local visual/audio matcher can suggest leads for review; similarity alone does not establish derivation, ownership, authorization, or infringement.

The repository also contains the frozen E1 matching experiment. Its evaluation found useful signals but unacceptable false positives for automatic visual or audio derivation claims. The MVP therefore keeps those scores separate from signed assertions and human findings. See [the MVP evidence model](docs/ClipTrace-MVP.md) and [the E1 report](results/e1/report.md).

## Run the MVP

Requires Python 3.10+, FFmpeg and ffprobe on `PATH`. `fpcalc` is optional for audio leads. On Windows PowerShell:

```powershell
python -m pip install -e ".[mvp]"
$env:CLIPTRACE_OPERATOR_TOKEN = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$env:CLIPTRACE_SIGNING_PASSPHRASE = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$env:CLIPTRACE_DATA_DIR = ".cliptrace-data"
python -m cliptrace_mvp
```

Open <http://127.0.0.1:8765/> and sign in as `operator` with the token. **Save both secrets** in a password manager. The same signing passphrase is required to reopen an existing data directory. The default server listens only on loopback.

The [run manual](docs/Run-Manual.md) covers first run, routine workflow, offline bundle verification, backups, restarts, and troubleshooting. The JSON API is available at `/docs` after signing in.

## Verify the checkout

```powershell
python -m pip install -e ".[dev,mvp]"
python -m pytest -q
python -c "from cliptrace_e1.e1_run import evaluation_guard; evaluation_guard()"
```

The test suite includes a media workflow with registration, exact and nonexact checks, authorization, derivative declaration, review, revocation, bundle export, and tamper detection.

## Repository map

- `src/cliptrace_mvp/` — self-hosted service, operator UI, signed evidence, and offline verifier.
- `docs/Run-Manual.md` — operating instructions.
- `docs/ClipTrace-MVP.md` — product scope and evidence limitations.
- `src/cliptrace_e1/`, `configs/`, `corpus/`, `results/e1/` — frozen experiment and reproducibility records. Media files are not included.
- `tests/` — automated checks.

The code is [Apache-2.0 licensed](LICENSE). Third-party corpus media and external tools keep their own licenses. This MVP has one shared operator credential and no tenant isolation or billing; deploy a separate instance per organization.
