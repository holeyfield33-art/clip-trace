"""Exercise the packaged MVP over a real loopback HTTP server."""
from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from cliptrace_mvp.verify_bundle import check


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is required")
def test_live_server_end_to_end(tmp_path):
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    token = "live-e2e-operator-token-1234567890"
    env = os.environ.copy()
    env.update(CLIPTRACE_OPERATOR_TOKEN=token, CLIPTRACE_SIGNING_PASSPHRASE="live-e2e-signing-passphrase",
               CLIPTRACE_DATA_DIR=str(tmp_path / "data"), CLIPTRACE_PORT=str(port))
    process = subprocess.Popen([sys.executable, "-m", "cliptrace_mvp"], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=base, timeout=60) as client:
            for _ in range(100):
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                if process.poll() is not None:
                    pytest.fail(f"ClipTrace exited during startup: {process.stderr.read().decode(errors='replace')}")
                time.sleep(0.1)
            else:
                pytest.fail("ClipTrace did not become healthy")

            assert client.get("/").status_code == 401
            headers = {"Authorization": f"Bearer {token}"}
            assert client.get("/", headers=headers).status_code == 200
            assert client.get("/app.js", headers=headers).status_code == 200
            assert client.get("/docs", headers=headers).status_code == 200

            source = tmp_path / "source.mp4"
            child = tmp_path / "child.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
                            "testsrc2=size=320x180:rate=12:duration=8", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=16000:duration=8", "-c:v", "libx264",
                            "-preset", "ultrafast", "-threads", "1", "-c:a", "aac", str(source)],
                           check=True, timeout=60)
            subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", "1", "-i", str(source),
                            "-t", "6", "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
                            "-c:a", "aac", str(child)], check=True, timeout=60)
            with source.open("rb") as media:
                response = client.post("/api/assets", headers=headers, data={"registrant_assertion": "E2E creator"},
                                       files={"file": (source.name, media, "video/mp4")})
            assert response.status_code == 200, response.text
            asset_id = response.json()["asset_id"]
            assert client.get("/api/assets", headers=headers).json()[0]["asset_id"] == asset_id

            with source.open("rb") as media:
                exact = client.post("/api/candidates", headers=headers,
                                    files={"file": (source.name, media, "video/mp4")})
            assert exact.status_code == 200, exact.text
            assert exact.json()["receipt"]["payload"]["claims"]["C1_exact_asset"]["state"] == "exact_match"

            child_sha = hashlib.sha256(child.read_bytes()).hexdigest()
            now = datetime.now(timezone.utc)
            authorization = client.post("/api/authorizations", headers=headers, json={
                "parent_asset_id": asset_id, "child_sha256": child_sha, "grantee": "E2E editor",
                "valid_from": (now - timedelta(days=1)).isoformat(),
                "valid_until": (now + timedelta(days=1)).isoformat(), "scope_note": "E2E excerpt"})
            assert authorization.status_code == 200, authorization.text
            auth_id = authorization.json()["payload"]["authorization_id"]
            derivative = client.post("/api/derivatives", headers=headers, json={
                "parent_asset_id": asset_id, "child_sha256": child_sha, "source_intervals_s": [[1, 7]],
                "declared_transformations": ["trim"], "authorization_id": auth_id})
            assert derivative.status_code == 200, derivative.text

            with child.open("rb") as media:
                response = client.post("/api/candidates", headers=headers,
                                       files={"file": (child.name, media, "video/mp4")})
            assert response.status_code == 200, response.text
            candidate = response.json()
            claims = candidate["receipt"]["payload"]["claims"]
            assert claims["C2_signed_lineage"]["state"] == "recorded"
            assert claims["C7_authorization"]["state"] == "valid_record"
            assert claims["C3_visual_derivation"]["state"] == "not_established"
            assert candidate["receipt"]["payload"]["review_leads"]

            review = client.post("/api/reviews", headers=headers, json={
                "candidate_id": candidate["candidate_id"], "parent_asset_id": asset_id,
                "reviewer_assertion": "E2E reviewer", "reasoning": "Manually compared the test excerpt",
                "visual_state": "reviewed_support", "audio_state": "insufficient",
                "source_intervals_s": [[1, 7]]})
            assert review.status_code == 200, review.text
            review_id = review.json()["payload"]["review"]["review_id"]
            bundle = client.get(f"/api/reviews/{review_id}/bundle", headers=headers)
            assert bundle.status_code == 200, bundle.text
            keys = client.get("/api/public-keys").json()
            result = check(bundle.json(), keys["receipt_public_key_pem"], candidate_path=child,
                           trusted_checkpoint_key=keys["checkpoint_public_key_pem"])
            assert result["valid"], result
            assert client.post(f"/api/authorizations/{auth_id}/revoke", headers=headers).json()["revoked"]
            with child.open("rb") as media:
                later = client.post("/api/candidates", headers=headers,
                                    files={"file": (child.name, media, "video/mp4")})
            assert later.status_code == 200, later.text
            assert later.json()["receipt"]["payload"]["claims"]["C7_authorization"]["state"] == "unknown"
            assert client.get("/api/checkpoint", headers=headers).json()["chain_verification"]["valid"]
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        process.stderr.close()
