"""ClipTrace product workflow. Similarity outputs are review leads, not claims."""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .crypto import digest, file_digest, public_pem, sign, verify
from .store import Store, now

SCHEMA = "cliptrace-mvp-v1"
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_DURATION_S = 3600


def _identity(prefix: str) -> str:
    return prefix + "_" + uuid4().hex


def _media_properties(path: Path) -> dict:
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                          capture_output=True, timeout=30)
    if proc.returncode:
        raise ValueError("FFprobe could not read this media file")
    try:
        probe = json.loads(proc.stdout)
        video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
        duration = float(probe["format"].get("duration", video.get("duration", 0)))
    except (KeyError, StopIteration, ValueError, TypeError) as exc:
        raise ValueError("Upload must contain a readable video stream") from exc
    if not math.isfinite(duration) or duration <= 0 or duration > MAX_DURATION_S:
        raise ValueError("Video duration must be between 0 and 3600 seconds")
    return {"duration_s": duration, "width": int(video.get("width", 0)),
            "height": int(video.get("height", 0)), "video_codec": video.get("codec_name"),
            "has_audio": any(s["codec_type"] == "audio" for s in probe["streams"]),
            "ffprobe_format": probe["format"].get("format_name")}


def _feature(path: Path, work: Path) -> tuple[dict | None, str]:
    # E1 code is imported unchanged. Its research thresholds are never promoted
    # to automatic C3/C4 assertions in the product receipt.
    try:
        from cliptrace_e1 import e1_features
        configured = os.getenv("CLIPTRACE_FPCALC") or shutil.which("fpcalc")
        if configured and Path(configured).is_file():
            e1_features.FPCALC = Path(configured)
        value, _ = e1_features.extract(path, work=work)
        return value, "indexed"
    except Exception as exc:
        return None, "unavailable: " + type(exc).__name__ + ": " + str(exc)[:180]


def _stamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Expected an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


class ClipTrace:
    def __init__(self, store: Store):
        self.store = store

    def _trusted_assets(self) -> list[dict]:
        trusted_pem = public_pem(self.store.receipt_key.public_key())
        assets = self.store.assets()
        for asset in assets:
            manifest = asset["manifest"]
            if (not verify(manifest, trusted_pem) or manifest["payload"]["asset_id"] != asset["id"] or
                manifest["payload"]["exact_media_sha256"] != asset["sha256"] or
                manifest["payload"]["feature_artifact_sha256"] != asset["features_sha256"]):
                raise ValueError("Registered asset manifest integrity failure")
        return assets

    def _exact_assets(self, sha256: str) -> list[dict]:
        return [asset for asset in self._trusted_assets() if asset["sha256"] == sha256]

    def register(self, staged: Path, filename: str, registrant_assertion: str, *, index: bool = True) -> dict:
        if not registrant_assertion.strip():
            raise ValueError("Registrant assertion is required")
        if staged.stat().st_size <= 0 or staged.stat().st_size > MAX_UPLOAD_BYTES:
            raise ValueError("Upload size is outside the supported range")
        media = _media_properties(staged)
        sha256 = file_digest(staged)
        conflicts = [item["id"] for item in self._exact_assets(sha256)]
        path = self.store.persist_media(staged, sha256)
        features, status = _feature(path, self.store.tmp_dir / ("source_" + uuid4().hex)) if index else (None, "not_indexed")
        feature_sha = self.store.put_artifact(features) if features else None
        asset_id = _identity("asset")
        created = now()
        payload = {"schema": SCHEMA, "document_type": "origin_manifest", "asset_id": asset_id,
                   "exact_media_sha256": sha256, "media_size_bytes": path.stat().st_size,
                   "original_filename": Path(filename).name[:255], "media_properties": media,
                   "registrant_assertion": registrant_assertion.strip(), "registered_at": created,
                   "feature_artifact_sha256": feature_sha, "fingerprint_status": status,
                   "registration_conflicts": conflicts,
                   "claim_scope": "This account registered these bytes and asserted origin; creation and ownership are not established."}
        envelope = sign(payload, self.store.receipt_key)
        self.store.insert_asset({"id": asset_id, "sha256": sha256, "filename": payload["original_filename"],
                                 "size_bytes": path.stat().st_size, "created_at": created, "manifest": envelope,
                                 "features_sha256": feature_sha, "fingerprint_status": status})
        return {"asset_id": asset_id, "manifest": envelope, "exact_conflicts": conflicts,
                "fingerprint_status": status}

    def _snapshot(self) -> dict:
        items = [{"asset_id": a["id"], "manifest_sha256": digest(a["manifest"])} for a in self._trusted_assets()]
        return {"registered_assets": items, "registry_sha256": digest(items), "count": len(items)}

    def _leads(self, candidate: dict) -> list[dict]:
        from cliptrace_e1.e1_features import match
        assets = self._trusted_assets()
        registry = {a["id"]: self.store.get_artifact(a["features_sha256"])
                    for a in assets if a["features_sha256"]}
        if not registry:
            return []
        results = match(candidate, registry)
        leads = []
        for method in ["V-C", "A-chromaprint"]:
            for pair in results[method]["pairs"][:5]:
                if pair.get("score") is None or pair["score"] <= 0:
                    continue
                leads.append({"registered_asset_id": pair["parent"], "method": method,
                              "score": pair["score"], "candidate_intervals_s": [b["candidate"] for b in pair.get("blocks", [])[:40]],
                              "source_intervals_s": [b["source"] for b in pair.get("blocks", [])[:40]],
                              "state": "review_lead", "caution": "Experimental matcher; E1 failed specificity. This score does not establish derivation."})
        return sorted(leads, key=lambda x: (-x["score"], x["registered_asset_id"], x["method"]))

    def _lineage(self, child_sha256: str, checked_at: str) -> tuple[list[dict], list[dict]]:
        recorded, authorized = [], []
        for d in self.store.derivatives(child_sha256):
            trusted_pem = public_pem(self.store.receipt_key.public_key())
            if not verify(d["envelope"], trusted_pem):
                continue
            parent = self.store.asset(d["parent_id"])
            if (not parent or not verify(parent["manifest"], trusted_pem) or
                d["envelope"]["payload"].get("child_sha256") != child_sha256 or
                d["envelope"]["payload"].get("parent_asset_id") != d["parent_id"] or
                d["envelope"]["payload"].get("parent_manifest_sha256") != digest(parent["manifest"])):
                continue
            recorded.append({"derivative_id": d["id"], "parent_asset_id": d["parent_id"],
                             "manifest_sha256": digest(d["envelope"])})
            auth_id = d["authorization_id"]
            auth = self.store.authorization(auth_id) if auth_id else None
            if (auth and not auth["revoked_at"] and auth["parent_id"] == d["parent_id"] and
                auth["child_sha256"] == child_sha256 and verify(auth["envelope"], trusted_pem) and
                auth["envelope"]["payload"].get("authorization_id") == auth_id and
                auth["envelope"]["payload"].get("parent_asset_id") == d["parent_id"] and
                auth["envelope"]["payload"].get("child_sha256") == child_sha256 and
                auth["envelope"]["payload"].get("valid_from") == auth["valid_from"] and
                auth["envelope"]["payload"].get("valid_until") == auth["valid_until"] and
                _stamp(auth["valid_from"]) <= _stamp(checked_at) <= _stamp(auth["valid_until"])):
                authorized.append({"authorization_id": auth_id, "parent_asset_id": d["parent_id"],
                                   "derivative_id": d["id"], "record_sha256": digest(auth["envelope"])})
        return recorded, authorized

    def _receipt(self, candidate_id: str, sha256: str, filename: str, media: dict, feature_sha: str | None,
                 fingerprint_status: str, leads: list[dict], *, review: dict | None = None) -> dict:
        exact = self._exact_assets(sha256)
        checked = now()
        lineage, authorization = self._lineage(sha256, checked)
        claims = {
            "C1_exact_asset": {"state": "exact_registration_conflict" if len(exact) > 1 else "exact_match" if exact else "no_exact_match",
                               "registered_asset_ids": [a["id"] for a in exact]},
            "C2_signed_lineage": {"state": "recorded" if lineage else "absent", "records": lineage},
            "C3_visual_derivation": {"state": review["visual_state"] if review else "not_established", "basis": "human_review" if review else "experimental_leads_only"},
            "C4_audio_derivation": {"state": review["audio_state"] if review else "not_established", "basis": "human_review" if review else "experimental_leads_only"},
            "C5_transcript_derivation": {"state": "not_evaluated"},
            "C6_watermark_attribution": {"state": "not_evaluated"},
            "C7_authorization": {"state": "valid_record" if authorization else "unknown", "records": authorization},
            "C8_publication": {"state": "not_evaluated"},
            "C9_ownership": {"state": "not_determined"},
        }
        payload = {"schema": SCHEMA, "document_type": "verification_receipt", "candidate_id": candidate_id,
                   "candidate_sha256": sha256, "candidate_filename": filename, "media_properties": media,
                   "checked_at": checked, "registry_snapshot": self._snapshot(), "claims": claims,
                   "feature_artifact_sha256": feature_sha, "fingerprint_status": fingerprint_status,
                   "review_leads": leads, "review": review,
                   "matcher_profile": "E1 frozen algorithms as exploratory leads; no automatic perceptual support",
                   "limitations": ["Similarity scores and intervals are not proof of ancestry.",
                                   "Human review is an assertion by the operator, not cryptographic proof of correctness.",
                                   "Registration and authorization records do not determine legal ownership.",
                                   "A self-contained signature needs an externally trusted public key or checkpoint to establish who signed it."]}
        return sign(payload, self.store.receipt_key)

    def verify_candidate(self, staged: Path, filename: str, *, compare: bool = True) -> dict:
        if staged.stat().st_size <= 0 or staged.stat().st_size > MAX_UPLOAD_BYTES:
            raise ValueError("Upload size is outside the supported range")
        media = _media_properties(staged)
        sha256 = file_digest(staged)
        path = self.store.persist_media(staged, sha256)
        exact = self._exact_assets(sha256)
        features, status = ((None, "skipped_exact_match") if exact or not compare else
                            _feature(path, self.store.tmp_dir / ("candidate_" + uuid4().hex)))
        feature_sha = self.store.put_artifact(features) if features else None
        leads = self._leads(features) if features else []
        candidate_id = _identity("candidate")
        receipt = self._receipt(candidate_id, sha256, Path(filename).name[:255], media, feature_sha, status, leads)
        self.store.insert_candidate({"id": candidate_id, "sha256": sha256, "filename": Path(filename).name[:255],
                                     "size_bytes": path.stat().st_size, "created_at": now(), "receipt": receipt,
                                     "features_sha256": feature_sha, "leads": leads})
        return {"candidate_id": candidate_id, "receipt": receipt}

    def create_authorization(self, parent_id: str, child_sha256: str, grantee: str,
                             valid_from: str, valid_until: str, scope_note: str) -> dict:
        if not any(a["id"] == parent_id for a in self._trusted_assets()):
            raise ValueError("Unknown parent asset")
        self.store.media_path(child_sha256)
        if _stamp(valid_until) <= _stamp(valid_from):
            raise ValueError("Authorization validity must end after it starts")
        if not grantee.strip() or not scope_note.strip():
            raise ValueError("Grantee and scope are required")
        auth_id = _identity("auth")
        payload = {"schema": SCHEMA, "document_type": "authorization_record", "authorization_id": auth_id,
                   "parent_asset_id": parent_id, "child_sha256": child_sha256, "grantee_assertion": grantee.strip(),
                   "valid_from": _stamp(valid_from).isoformat(), "valid_until": _stamp(valid_until).isoformat(),
                   "scope_note": scope_note.strip(), "signed_at": now(),
                   "claim_scope": "Operator assertion of authorization for this exact child hash and parent, subject to revocation."}
        envelope = sign(payload, self.store.receipt_key)
        self.store.insert_authorization({"id": auth_id, "parent_id": parent_id, "child_sha256": child_sha256,
                                         "valid_from": payload["valid_from"], "valid_until": payload["valid_until"],
                                         "envelope": envelope})
        return envelope

    def create_derivative(self, parent_id: str, child_sha256: str, intervals: list[list[float]],
                          transformations: list[str], authorization_id: str | None = None) -> dict:
        parent = next((a for a in self._trusted_assets() if a["id"] == parent_id), None)
        if not parent:
            raise ValueError("Unknown parent asset")
        self.store.media_path(child_sha256)
        duration = parent["manifest"]["payload"]["media_properties"]["duration_s"]
        if not intervals or any(len(x) != 2 or not all(math.isfinite(float(v)) for v in x)
                                or float(x[0]) < 0 or float(x[1]) <= float(x[0]) or float(x[1]) > duration for x in intervals):
            raise ValueError("Source intervals must be within the registered video")
        if authorization_id:
            auth = self.store.authorization(authorization_id)
            if not auth or auth["parent_id"] != parent_id or auth["child_sha256"] != child_sha256:
                raise ValueError("Authorization does not cover this exact parent and child")
        derivative_id = _identity("derivative")
        payload = {"schema": SCHEMA, "document_type": "derivative_manifest", "derivative_id": derivative_id,
                   "parent_asset_id": parent_id, "parent_manifest_sha256": digest(parent["manifest"]),
                   "child_sha256": child_sha256, "declared_source_intervals_s": intervals,
                   "declared_transformations": transformations, "authorization_id": authorization_id,
                   "signed_at": now(), "claim_scope": "Operator-declared exact child/parent lineage; interval truth is an assertion."}
        envelope = sign(payload, self.store.receipt_key)
        self.store.insert_derivative({"id": derivative_id, "parent_id": parent_id,
                                      "child_sha256": child_sha256, "authorization_id": authorization_id,
                                      "envelope": envelope})
        return envelope

    def review(self, candidate_id: str, parent_id: str, reviewer_assertion: str, note: str,
               visual_state: str, audio_state: str, source_intervals_s: list[list[float]]) -> dict:
        candidate = self.store.candidate(candidate_id)
        parent = next((a for a in self._trusted_assets() if a["id"] == parent_id), None)
        if not candidate or not parent:
            raise ValueError("Unknown candidate or parent")
        if (not verify(candidate["receipt"], public_pem(self.store.receipt_key.public_key())) or
            candidate["receipt"]["payload"].get("candidate_sha256") != candidate["sha256"] or
            candidate["receipt"]["payload"].get("candidate_id") != candidate_id):
            raise ValueError("Stored candidate receipt integrity failure")
        if visual_state not in {"reviewed_support", "insufficient", "ambiguous"} or audio_state not in {"reviewed_support", "insufficient", "ambiguous"}:
            raise ValueError("Invalid review state")
        if not reviewer_assertion.strip() or not note.strip():
            raise ValueError("Reviewer assertion and reasoning are required")
        if (visual_state == "reviewed_support" or audio_state == "reviewed_support") and not source_intervals_s:
            raise ValueError("A reviewed support claim needs declared source intervals")
        duration = parent["manifest"]["payload"]["media_properties"]["duration_s"]
        if any(len(x) != 2 or not all(math.isfinite(float(v)) for v in x) or float(x[0]) < 0
               or float(x[1]) <= float(x[0]) or float(x[1]) > duration for x in source_intervals_s):
            raise ValueError("Review intervals must be within the registered video")
        review = {"review_id": _identity("review"), "registered_asset_id": parent_id,
                  "reviewer_assertion": reviewer_assertion.strip(), "reasoning": note.strip(),
                  "visual_state": visual_state, "audio_state": audio_state,
                  "declared_source_intervals_s": source_intervals_s, "reviewed_at": now(),
                  "scope": "Human assertion after inspecting evidence; not an automatic matcher conclusion."}
        media = candidate["receipt"]["payload"]["media_properties"]
        receipt = self._receipt(candidate_id, candidate["sha256"], candidate["filename"], media,
                                candidate["features_sha256"], candidate["receipt"]["payload"]["fingerprint_status"],
                                candidate["leads"], review=review)
        self.store.insert_review({"id": review["review_id"], "candidate_id": candidate_id, "receipt": receipt})
        return receipt
