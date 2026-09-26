"""Offline V1/V2 check for a ClipTrace receipt or evidence bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .crypto import digest, file_digest, verify


def check(value: dict, trusted_receipt_key: str, *, candidate_path: Path | None = None,
          trusted_checkpoint_key: str | None = None) -> dict:
    try:
        return _check(value, trusted_receipt_key, candidate_path=candidate_path,
                      trusted_checkpoint_key=trusted_checkpoint_key)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, OSError) as exc:
        return {"valid": False, "level": "failed", "errors": ["Malformed or missing evidence: " + str(exc)[:200]]}


def _check(value: dict, trusted_receipt_key: str, *, candidate_path: Path | None = None,
           trusted_checkpoint_key: str | None = None) -> dict:
    bundle = value if value.get("schema") == "cliptrace-evidence-bundle-v1" else None
    receipt = bundle["receipt"] if bundle else value
    errors = []
    if not verify(receipt, trusted_receipt_key):
        errors.append("receipt signature or trusted signer mismatch")
        return {"valid": False, "level": "none", "errors": errors}
    payload = receipt["payload"]
    if candidate_path and file_digest(candidate_path) != payload.get("candidate_sha256"):
        errors.append("candidate bytes differ from receipt")
    if not bundle:
        return {"valid": not errors, "level": "V1_signature_only", "errors": errors,
                "note": "V1 proves the trusted key signed the assertion; matcher correctness is not established."}

    snapshot = payload["registry_snapshot"]
    if snapshot["count"] != len(snapshot["registered_assets"]) or digest(snapshot["registered_assets"]) != snapshot["registry_sha256"]:
        errors.append("registry snapshot digest mismatch")
    manifests = bundle.get("origin_manifests", {})
    artifacts = bundle.get("evidence_artifacts", {})
    if set(manifests) != {x["asset_id"] for x in snapshot["registered_assets"]}:
        errors.append("origin manifest coverage mismatch")
    for entry in snapshot["registered_assets"]:
        manifest = manifests.get(entry["asset_id"])
        if not manifest or digest(manifest) != entry["manifest_sha256"] or not verify(manifest, trusted_receipt_key):
            errors.append("origin manifest mismatch: " + entry["asset_id"])
            continue
        origin = manifest["payload"]
        if origin["asset_id"] != entry["asset_id"]:
            errors.append("origin asset identity mismatch")
        feature_sha = origin.get("feature_artifact_sha256")
        if feature_sha and (feature_sha not in artifacts or digest(artifacts[feature_sha]) != feature_sha):
            errors.append("origin feature artifact mismatch: " + entry["asset_id"])
        if feature_sha and feature_sha in artifacts and artifacts[feature_sha].get("media_sha256") != origin["exact_media_sha256"]:
            errors.append("origin feature media hash mismatch: " + entry["asset_id"])
    exact_ids = {item["asset_id"] for item in snapshot["registered_assets"]
                 if item["asset_id"] in manifests and manifests[item["asset_id"]]["payload"]["exact_media_sha256"] == payload["candidate_sha256"]}
    c1 = payload["claims"]["C1_exact_asset"]
    expected_c1 = "exact_registration_conflict" if len(exact_ids) > 1 else "exact_match" if exact_ids else "no_exact_match"
    if c1["state"] != expected_c1 or set(c1["registered_asset_ids"]) != exact_ids:
        errors.append("C1 does not agree with signed registry snapshot")
    candidate_feature = payload.get("feature_artifact_sha256")
    if candidate_feature and (candidate_feature not in artifacts or digest(artifacts[candidate_feature]) != candidate_feature):
        errors.append("candidate feature artifact mismatch")
    if candidate_feature and candidate_feature in artifacts and artifacts[candidate_feature].get("media_sha256") != payload["candidate_sha256"]:
        errors.append("candidate feature media hash mismatch")
    manifest_sha = {digest(x): x for x in bundle.get("derivative_manifests", [])}
    for claim in payload["claims"]["C2_signed_lineage"]["records"]:
        item = manifest_sha.get(claim["manifest_sha256"])
        if not item or not verify(item, trusted_receipt_key) or item["payload"]["child_sha256"] != payload["candidate_sha256"] or item["payload"]["parent_asset_id"] != claim["parent_asset_id"] or item["payload"]["parent_manifest_sha256"] != digest(manifests.get(claim["parent_asset_id"])):
            errors.append("derivative manifest mismatch")
    auth_sha = {digest(x): x for x in bundle.get("authorization_records", [])}
    for claim in payload["claims"]["C7_authorization"]["records"]:
        item = auth_sha.get(claim["record_sha256"])
        if not item or not verify(item, trusted_receipt_key) or item["payload"]["child_sha256"] != payload["candidate_sha256"] or item["payload"]["parent_asset_id"] != claim["parent_asset_id"]:
            errors.append("authorization record mismatch")
    checkpoint = bundle.get("checkpoint_at_export")
    if not checkpoint or not verify(checkpoint, trusted_checkpoint_key):
        errors.append("checkpoint signer mismatch")
    previous = "0" * 64
    events = bundle.get("event_log", [])
    receipt_event_found = False
    for seq, item in enumerate(events, 1):
        event = item.get("event", {})
        if (item.get("seq") != seq or event.get("seq") != seq or
            event.get("previous_hash") != previous or item.get("previous_hash") != previous or
            item.get("event_hash") != digest(event)):
            errors.append("event chain mismatch at sequence " + str(seq))
            break
        previous = item["event_hash"]
        normal = event.get("kind") == "candidate_verified" and event.get("subject_id") == payload["candidate_id"]
        reviewed = (event.get("kind") == "review_recorded" and payload.get("review") and
                    event.get("subject_id") == payload["review"]["review_id"])
        if (normal or reviewed) and event.get("document_sha256") == digest(receipt):
            receipt_event_found = True
    if not receipt_event_found:
        errors.append("receipt is not included in exported event chain")
    if checkpoint and (checkpoint["payload"].get("sequence") != len(events) or checkpoint["payload"].get("log_head_sha256") != previous):
        errors.append("checkpoint does not bind exported event chain")
    return {"valid": not errors, "level": "V2_artifact_integrity" if not errors else "failed",
            "errors": errors, "checked_origin_manifests": len(snapshot["registered_assets"]),
            "checked_artifacts": len(artifacts), "checked_events": len(events),
            "checkpoint_key_independently_supplied": bool(trusted_checkpoint_key),
            "note": "V2 verifies signed data integrity, not the truth of perceptual or legal assertions. A checkpoint key and external copy are needed to detect wholesale log replacement."}


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a signed ClipTrace receipt or evidence bundle offline")
    parser.add_argument("statement", type=Path)
    parser.add_argument("--trusted-receipt-key", type=Path, required=True,
                        help="Public key obtained through an independent trusted channel")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--trusted-checkpoint-key", type=Path)
    args = parser.parse_args()
    value = json.loads(args.statement.read_text(encoding="utf-8"))
    result = check(value, args.trusted_receipt_key.read_text(encoding="ascii"), candidate_path=args.candidate,
                   trusted_checkpoint_key=args.trusted_checkpoint_key.read_text(encoding="ascii") if args.trusted_checkpoint_key else None)
    print(json.dumps(result, indent=2))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
