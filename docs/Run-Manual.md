# ClipTrace run manual

This manual is for a single-organization, self-hosted MVP instance. One shared operator credential controls the browser and API. Keep each customer's data directory and secrets separate.

## 1. Prepare the host

Install Python 3.10 or newer, FFmpeg and ffprobe, and this repository. Confirm the tools are available:

```powershell
python --version
ffmpeg -version
ffprobe -version
python -m pip install -e ".[mvp]"
```

`fpcalc` is optional for audio review leads. On a host without the E1 Windows tool, install Chromaprint's `fpcalc` and set `CLIPTRACE_FPCALC` to its executable path. Visual leads and exact-hash evidence do not depend on it.

## 2. Set secrets and start

Create a random operator token of at least 32 characters and a signing passphrase of at least 16 characters. The following PowerShell commands generate 64-character values for a first run:

```powershell
$env:CLIPTRACE_OPERATOR_TOKEN = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$env:CLIPTRACE_SIGNING_PASSPHRASE = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$env:CLIPTRACE_DATA_DIR = ".cliptrace-data"
python -m cliptrace_mvp
```

Copy the secrets into your password manager **before** closing that shell. The process needs the same signing passphrase and data directory on every restart; generating a new passphrase for an existing directory will not reopen its encrypted signing keys. Stop with Ctrl+C. To restart, restore the saved environment values and run `python -m cliptrace_mvp` again.

The default address is `http://127.0.0.1:8765/`. Log in with username `operator` and the token as the password. `GET /health` responds without authentication; all other endpoints except `/api/public-keys` require the token. The authenticated API reference is at `/docs`.

`CLIPTRACE_HOST` and `CLIPTRACE_PORT` change the bind address and port. For remote use, put the instance behind an HTTPS reverse proxy, keep the service and data directory private, and set `CLIPTRACE_PUBLIC_ORIGIN` to the external origin (for example `https://cliptrace.example.org`) so browser writes pass the same-origin check. Do not expose the default HTTP listener directly to the Internet.

## 3. Operate the evidence workflow

1. **Register a source.** In the browser, enter the registrant assertion and upload the original video. Record the returned asset ID and SHA-256. Feature indexing is optional; it enables later review leads. Registering identical bytes again records a conflict rather than deciding which registrant is right.
2. **Check a candidate.** Upload a candidate video. An exact hash match supports C1. For a nonexact file, visual/audio scores and approximate intervals, when available, are leads only. C3/C4 remain `not_established` unless separately reviewed. An upload is limited to 512 MiB and one hour of video.
3. **Review a lead.** Enter the candidate ID and parent asset ID, reviewer assertion, reasoning, visual/audio states, and any source intervals. This creates a separately signed human finding; the reviewer name is asserted within the shared operator session, not independently authenticated.
4. **Record permission and lineage when applicable.** Hash the exact child file, create a time-bounded authorization for that child SHA-256 and parent asset, then declare the derivative with its intervals, transformations, and authorization ID. These are signed operator declarations, not proof of legal authority. Revoking an authorization affects later checks; prior receipts remain historical records.
5. **Export evidence.** Download a candidate or review receipt and its evidence bundle from the API. For a candidate ID, use `/api/candidates/{id}/receipt` or `/api/candidates/{id}/bundle`; for a review ID, use `/api/reviews/{id}/receipt` or `/api/reviews/{id}/bundle`. Save the JSON with the related candidate file and the public keys.

For API calls from a script, send `Authorization: Bearer <operator-token>`. Browser Basic-auth writes require an `Origin` matching the service origin. The browser workspace covers the main workflow; `/docs` lists request fields and response schemas.

## 4. Verify an exported bundle offline

Obtain receipt and checkpoint public keys through a channel you trust independently of the server. `/api/public-keys` gives their current values, but fetching keys and evidence solely from one server only establishes internal consistency. Save the two PEM values as `receipt-public.pem` and `checkpoint-public.pem`, then run:

```powershell
python -m cliptrace_mvp.verify_bundle .\bundle.json --trusted-receipt-key .\receipt-public.pem --trusted-checkpoint-key .\checkpoint-public.pem --candidate .\candidate.mp4
```

Exit code zero and `"valid": true` mean the signatures, exact candidate hash, linked artifacts, and exported event chain/checkpoint passed the verifier. This does not prove that a visual matcher or human reviewer was correct. Preserve externally saved checkpoints if you need to detect replacement of the entire server history.

## 5. Back up and restore

Stop the service before copying the data directory so the SQLite database, media, evidence artifacts, encrypted keys, and event chain form one consistent snapshot. Store the copy privately, alongside a secure record of the signing passphrase and operator token. To restore, place the complete directory at `CLIPTRACE_DATA_DIR`, set the saved secrets, start the service, and inspect `/api/checkpoint` for `chain_verification.valid: true`. Keep an independently exported checkpoint and trusted public keys outside this data directory.

## 6. Check health and troubleshoot

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
python -m pytest -q
python -c "from cliptrace_e1.e1_run import evaluation_guard; evaluation_guard()"
```

If startup rejects a secret, check its minimum length and whether the signing passphrase matches the existing data directory. If video processing fails, confirm `ffmpeg` and `ffprobe` are on `PATH` and the file is a supported video. Missing `fpcalc` removes audio leads; it does not invalidate exact-hash checks. A `401` means the operator token is absent or wrong. A `403` on a browser write usually means the proxy origin differs from `CLIPTRACE_PUBLIC_ORIGIN`. Inspect `/api/checkpoint` and verify exported bundles after restoring from backup.

The service processes uploads synchronously in a worker thread and scans the local source registry for review leads. This is suitable for a small private deployment; sustained traffic or a large corpus needs a job queue and search index. The evidence and deployment boundaries are described in [ClipTrace-MVP.md](ClipTrace-MVP.md).
