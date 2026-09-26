# ClipTrace single-organization MVP

This service implements a usable, private ClipTrace evidence workflow. An operator can register an original video, check a candidate, inspect similarity leads, record a reviewed finding, sign an exact derivative declaration and a scoped authorization, revoke authorization, and export a signed receipt with its evidence bundle. The browser workspace and JSON API use the same records.

E1 remains frozen at `results/e1/frozen-evaluation-profile.json`. E1 found useful matching signals, but the selected visual method produced 12/48 false positives and the selected audio method produced 3/80 false positives on held-out qualification cases. The product therefore displays their output as **review leads only**. It does not issue automatic C3 or C4 derivation support. A human can sign a separately labeled review assertion. C1 exact bytes, C2 signed lineage, C7 authorization, and C9 ownership retain different meanings.

## Run locally

Use Python 3.10 or newer, FFmpeg/ffprobe on `PATH`, and a locally available `fpcalc` if you want audio leads. The existing E1 Windows binary is found automatically in this checkout; for another installation set `CLIPTRACE_FPCALC` to the local executable. Visual leads work without it. The service does not distribute FFmpeg or fpcalc binaries.

```powershell
python -m pip install -e ".[mvp]"
$env:CLIPTRACE_OPERATOR_TOKEN = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$env:CLIPTRACE_SIGNING_PASSPHRASE = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$env:CLIPTRACE_DATA_DIR = ".cliptrace-data"
python -m cliptrace_mvp
```

Open `http://127.0.0.1:8765/`. The browser prompts for username `operator` and the operator token. Keep both secrets in a password manager; restarting with an existing data directory needs the **same signing passphrase**. Back up the data directory, including media, SQLite database, evidence artifacts and encrypted key files. The default bind address is loopback. Remote hosting needs HTTPS through a trusted reverse proxy, private backups, secret management and operational monitoring. Set `CLIPTRACE_PUBLIC_ORIGIN` to the external `https://...` origin when browser traffic passes through a proxy. This is a single-organization service with one operator secret; it has no tenant isolation or billing.

The API is documented at `/docs`. All routes except `/health` and `/api/public-keys` require `Authorization: Bearer <token>` or browser Basic auth. Browser writes require a matching `Origin`. Uploads are limited to 512 MiB and one hour of video. The original bytes are stored under their SHA-256 digest; upload names are metadata only.

## Evidence flow

1. Register a source. The signed origin manifest records the exact file hash, media properties, registrant assertion, and optional feature artifact hash. Re-registering identical bytes creates an explicit conflict; neither registrant wins automatically.
2. Upload a candidate. An exact match creates C1 evidence. If no exact match exists, available E1 visual/audio scores and approximate intervals appear only as review leads. The receipt keeps C3/C4 `not_established` until an operator records a separate human review.
3. Optionally sign an authorization for a specific parent ID and child SHA-256, with a time window. Sign a derivative manifest binding the same exact child hash to parent, declared intervals and transformations. A matching candidate can then receive C2 `recorded` and C7 `valid_record` at verification time. Revocation affects later checks.
4. Export `/api/candidates/{id}/receipt` or `/api/candidates/{id}/bundle`; reviewed findings also have `/api/reviews/{id}/receipt` and `/api/reviews/{id}/bundle`. A bundle contains the signed receipt, the registry snapshot's origin manifests, referenced feature artifacts, applicable lineage/authorization records, the event chain, and a current signed checkpoint.

Authorization and derivative records are operator assertions. The service signs what was declared; it does not establish the declarant's legal authority, the truth of an interval, or ownership. C5, C6 and C8 are not evaluated. C9 remains `not_determined`.
The reviewer name is also an assertion entered during a shared operator session; this version does not authenticate individual reviewers.

## Independent checks

Save a receipt or bundle as JSON. Obtain the receipt and checkpoint public keys through a channel you independently trust; fetching them only from the same server proves self-consistency. Then run:

```powershell
python -m cliptrace_mvp.verify_bundle .\bundle.json --trusted-receipt-key .\receipt-public.pem --trusted-checkpoint-key .\checkpoint-public.pem --candidate .\candidate.mp4
```

The verifier checks the trusted receipt signature, the candidate's exact SHA-256 when supplied, the registry snapshot, signed origin manifests, referenced feature artifacts, and inclusion of the receipt in the exported event chain and checkpoint. This is V1 signature / V2 artifact integrity. It does **not** prove that a matcher or human reviewer was correct. V3 computational reproduction is not yet implemented in the MVP.

Every write appends an event with the prior log hash and signs a checkpoint using a separate key. Export checkpoints to storage outside this service to detect wholesale history replacement. A current checkpoint fetched only from the same server cannot provide that protection.

## Product boundary

This MVP can be deployed as a private single-organization instance or licensed for a customer's own instance. The current retrieval pass scans registered sources and upload processing runs synchronously in a worker thread, so large registries and sustained traffic need an index and job queue. Before an internet-facing commercial launch it also needs tenant accounts or a documented per-customer deployment model, managed TLS and secrets, operator audit and recovery procedures, abuse/rate controls, independent checkpoint publication, and a new blinded matcher evaluation before any automatic C3/C4 claim. E1's test set cannot serve as training data for tuning that next matcher and then as its final test.

The source code is separate from `cliptrace_e1`; the E1 matcher and frozen evaluation files are unchanged. The repository's Apache-2.0 license covers project code only. Source corpus and external media/tools retain their own terms.
