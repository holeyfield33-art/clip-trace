"""Product behavior checks: cryptographic claims stay distinct from match leads."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cliptrace_mvp.crypto import verify
from cliptrace_mvp.verify_bundle import check
from cliptrace_mvp.web import create_app


def _video(path: Path, *, seconds: int = 8, start: float = 0) -> bytes:
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", str(start),
                    "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12:duration=12",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=12",
                    "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
                    "-c:a", "aac", str(path)], check=True, timeout=60)
    return path.read_bytes()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is required")
def test_registration_verification_lineage_revocation_and_offline_bundle(tmp_path):
    token = "a" * 40
    app = create_app(tmp_path / "data", token=token, passphrase="passphrase-for-test-only-1234")
    client = TestClient(app)
    assert client.get("/api/assets").status_code == 401
    headers = {"Authorization": "Bearer " + token}
    original = _video(tmp_path / "source.mp4")
    response = client.post("/api/assets", headers=headers, data={"registrant_assertion": "Creator A"},
                           files={"file": ("source.mp4", original, "video/mp4")})
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["fingerprint_status"] == "indexed"
    assert verify(first["manifest"])
    assert first["manifest"]["payload"]["exact_media_sha256"] == hashlib.sha256(original).hexdigest()

    duplicate = client.post("/api/assets", headers=headers,
                            data={"registrant_assertion": "Competing registrant", "index_features": "false"},
                            files={"file": ("source-copy.mp4", original, "video/mp4")}).json()
    assert duplicate["exact_conflicts"] == [first["asset_id"]]
    exact = client.post("/api/candidates", headers=headers,
                        files={"file": ("exact.mp4", original, "video/mp4")}).json()
    claims = exact["receipt"]["payload"]["claims"]
    assert claims["C1_exact_asset"]["state"] == "exact_registration_conflict"
    assert set(claims["C1_exact_asset"]["registered_asset_ids"]) == {first["asset_id"], duplicate["asset_id"]}
    assert claims["C3_visual_derivation"]["state"] == "not_established"
    assert claims["C9_ownership"]["state"] == "not_determined"

    child = _video(tmp_path / "child.mp4", seconds=6, start=1)
    child_sha = hashlib.sha256(child).hexdigest()
    window = datetime.now(timezone.utc)
    auth = client.post("/api/authorizations", headers=headers, json={
        "parent_asset_id": first["asset_id"], "child_sha256": child_sha, "grantee": "Clip editor",
        "valid_from": (window - timedelta(days=1)).isoformat(),
        "valid_until": (window + timedelta(days=1)).isoformat(), "scope_note": "One promotional excerpt"
    })
    assert auth.status_code == 200, auth.text
    auth_id = auth.json()["payload"]["authorization_id"]
    derivative = client.post("/api/derivatives", headers=headers, json={
        "parent_asset_id": first["asset_id"], "child_sha256": child_sha,
        "source_intervals_s": [[1, 7]], "declared_transformations": ["trim"],
        "authorization_id": auth_id})
    assert derivative.status_code == 200, derivative.text
    checked = client.post("/api/candidates", headers=headers,
                          files={"file": ("excerpt.mp4", child, "video/mp4")})
    assert checked.status_code == 200, checked.text
    checked = checked.json()
    claims = checked["receipt"]["payload"]["claims"]
    assert claims["C1_exact_asset"]["state"] == "no_exact_match"
    assert claims["C2_signed_lineage"]["state"] == "recorded"
    assert claims["C7_authorization"]["state"] == "valid_record"
    assert claims["C3_visual_derivation"]["state"] == "not_established"
    assert checked["receipt"]["payload"]["review_leads"]

    keys = client.get("/api/public-keys").json()
    bundle = client.get(f'/api/candidates/{checked["candidate_id"]}/bundle', headers=headers)
    assert bundle.status_code == 200, bundle.text
    candidate_path = tmp_path / "child.mp4"
    result = check(bundle.json(), keys["receipt_public_key_pem"], candidate_path=candidate_path,
                   trusted_checkpoint_key=keys["checkpoint_public_key_pem"])
    assert result["valid"] and result["level"] == "V2_artifact_integrity", result
    tampered = bundle.json()
    tampered["receipt"]["payload"]["claims"]["C7_authorization"]["state"] = "unknown"
    assert not check(tampered, keys["receipt_public_key_pem"])["valid"]
    artifact_tampered = bundle.json()
    first_digest = next(iter(artifact_tampered["evidence_artifacts"]))
    artifact_tampered["evidence_artifacts"][first_digest]["media_sha256"] = "0" * 64
    assert not check(artifact_tampered, keys["receipt_public_key_pem"])["valid"]
    chain_tampered = bundle.json()
    chain_tampered["event_log"][0]["event"]["subject_id"] = "different"
    assert not check(chain_tampered, keys["receipt_public_key_pem"])["valid"]

    reviewed = client.post("/api/reviews", headers=headers, json={
        "candidate_id": checked["candidate_id"], "parent_asset_id": first["asset_id"],
        "reviewer_assertion": "Operator 1", "reasoning": "Frames and audio compared by a human reviewer",
        "visual_state": "reviewed_support", "audio_state": "insufficient", "source_intervals_s": [[1, 7]]})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["payload"]["claims"]["C3_visual_derivation"]["basis"] == "human_review"
    assert reviewed.json()["payload"]["claims"]["C4_audio_derivation"]["state"] == "insufficient"
    review_id = reviewed.json()["payload"]["review"]["review_id"]
    assert client.get('/api/reviews/' + review_id + '/receipt', headers=headers).status_code == 200
    review_bundle = client.get('/api/reviews/' + review_id + '/bundle', headers=headers)
    assert review_bundle.status_code == 200
    assert check(review_bundle.json(), keys["receipt_public_key_pem"], candidate_path=candidate_path,
                 trusted_checkpoint_key=keys["checkpoint_public_key_pem"])["valid"]
    assert not check({"schema": "cliptrace-evidence-bundle-v1"}, keys["receipt_public_key_pem"])["valid"]

    assert client.post(f"/api/authorizations/{auth_id}/revoke", headers=headers).status_code == 200
    after = client.post("/api/candidates", headers=headers,
                        files={"file": ("excerpt.mp4", child, "video/mp4")}).json()
    assert after["receipt"]["payload"]["claims"]["C7_authorization"]["state"] == "unknown"
    assert client.get("/api/checkpoint", headers=headers).json()["chain_verification"]["valid"]


def test_key_is_required_and_receipt_tamper_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        create_app(tmp_path, token="short", passphrase="long enough passphrase")
    app = create_app(tmp_path / "state", token="x" * 40, passphrase="long enough passphrase")
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("operator", "x" * 40)).status_code == 200
    assert client.get("/app.js", auth=("operator", "x" * 40)).status_code == 200
    assert client.post("/api/assets", auth=("operator", "x" * 40)).status_code == 403
    browser_write = client.post("/api/assets", auth=("operator", "x" * 40),
                                headers={"Origin": "http://testserver"},
                                data={"registrant_assertion": "A"},
                                files={"file": ("fake.mp4", b"not a video", "video/mp4")})
    assert browser_write.status_code == 400
    bad = client.post("/api/assets", headers={"Authorization": "Bearer " + "x" * 40},
                      data={"registrant_assertion": "A"}, files={"file": ("fake.mp4", b"not a video", "video/mp4")})
    assert bad.status_code == 400
