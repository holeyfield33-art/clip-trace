"""Single-organization operator UI and JSON API."""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .crypto import digest, public_pem
from .service import ClipTrace, MAX_UPLOAD_BYTES
from .store import Store

STATIC = Path(__file__).with_name("static")


class AuthorizationInput(BaseModel):
    parent_asset_id: str
    child_sha256: str
    grantee: str
    valid_from: str
    valid_until: str
    scope_note: str


class DerivativeInput(BaseModel):
    parent_asset_id: str
    child_sha256: str
    source_intervals_s: list[list[float]] = Field(min_length=1)
    declared_transformations: list[str] = []
    authorization_id: str | None = None


class ReviewInput(BaseModel):
    candidate_id: str
    parent_asset_id: str
    reviewer_assertion: str
    reasoning: str
    visual_state: str
    audio_state: str
    source_intervals_s: list[list[float]] = []


def create_app(data_dir: Path | None = None, token: str | None = None, passphrase: str | None = None) -> FastAPI:
    token = token or os.getenv("CLIPTRACE_OPERATOR_TOKEN", "")
    passphrase = passphrase or os.getenv("CLIPTRACE_SIGNING_PASSPHRASE", "")
    if len(token) < 32:
        raise ValueError("Set CLIPTRACE_OPERATOR_TOKEN to a random secret of at least 32 characters")
    if len(passphrase) < 16:
        raise ValueError("Set CLIPTRACE_SIGNING_PASSPHRASE to at least 16 characters")
    store = Store(Path(data_dir or os.getenv("CLIPTRACE_DATA_DIR", ".cliptrace-data")), passphrase)
    service = ClipTrace(store)
    app = FastAPI(title="ClipTrace MVP", version="0.1.0",
                  description="Single-organization exact provenance and human-reviewed similarity leads")
    app.state.store = store
    app.state.service = service

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        if request.url.path not in {"/health", "/api/public-keys"}:
            header = request.headers.get("authorization", "")
            candidate = ""
            if header.startswith("Bearer "):
                candidate = header[7:]
            elif header.startswith("Basic "):
                try:
                    decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
                    username, candidate = decoded.split(":", 1)
                    if username != "operator":
                        candidate = ""
                except (ValueError, UnicodeError):
                    candidate = ""
            if not candidate or not secrets.compare_digest(candidate, token):
                return JSONResponse({"detail": "Operator authentication required"}, status_code=401,
                                    headers={"WWW-Authenticate": 'Basic realm="ClipTrace operator"', "Cache-Control": "no-store"})
            if header.startswith("Basic ") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                expected_origin = os.getenv("CLIPTRACE_PUBLIC_ORIGIN", str(request.base_url).rstrip("/"))
                if request.headers.get("origin") != expected_origin:
                    return JSONResponse({"detail": "Same-origin browser request required"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    async def stage(upload: UploadFile) -> Path:
        path = store.tmp_dir / (uuid4().hex + ".upload")
        size = 0
        try:
            with path.open("xb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, "File exceeds the 512 MiB MVP limit")
                    output.write(chunk)
            if size == 0:
                raise HTTPException(400, "Empty upload")
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

    def value_error(exc: ValueError):
        raise HTTPException(400, str(exc)) from exc

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "cliptrace-mvp"}

    @app.get("/api/public-keys")
    def public_keys():
        return {"receipt_public_key_pem": public_pem(store.receipt_key.public_key()),
                "checkpoint_public_key_pem": public_pem(store.checkpoint_key.public_key()),
                "note": "Trust these keys only after comparing with a copy obtained outside this server."}

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/app.js")
    def script():
        return FileResponse(STATIC / "app.js", media_type="application/javascript")

    @app.get("/app.css")
    def style():
        return FileResponse(STATIC / "app.css", media_type="text/css")

    @app.get("/api/assets")
    def assets():
        return [{"asset_id": a["id"], "filename": a["filename"], "sha256": a["sha256"],
                 "created_at": a["created_at"], "fingerprint_status": a["fingerprint_status"],
                 "manifest": a["manifest"]} for a in store.assets()]

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str):
        record = store.asset(asset_id)
        if not record:
            raise HTTPException(404, "Unknown asset")
        return record

    @app.post("/api/assets")
    async def register(file: UploadFile = File(...), registrant_assertion: str = Form(...), index_features: bool = Form(True)):
        staged = await stage(file)
        try:
            return await run_in_threadpool(service.register, staged, file.filename or "upload", registrant_assertion, index=index_features)
        except ValueError as exc:
            value_error(exc)
        finally:
            staged.unlink(missing_ok=True)

    @app.get("/api/candidates")
    def candidates():
        return store.candidates()

    @app.post("/api/candidates")
    async def verify_candidate(file: UploadFile = File(...), compare: bool = Form(True)):
        staged = await stage(file)
        try:
            return await run_in_threadpool(service.verify_candidate, staged, file.filename or "upload", compare=compare)
        except ValueError as exc:
            value_error(exc)
        finally:
            staged.unlink(missing_ok=True)

    @app.get("/api/candidates/{candidate_id}")
    def candidate(candidate_id: str):
        record = store.candidate(candidate_id)
        if not record:
            raise HTTPException(404, "Unknown candidate")
        return record

    @app.get("/api/candidates/{candidate_id}/receipt")
    def receipt(candidate_id: str):
        record = store.candidate(candidate_id)
        if not record:
            raise HTTPException(404, "Unknown candidate")
        return record["receipt"]

    @app.get("/api/candidates/{candidate_id}/bundle")
    def bundle(candidate_id: str):
        record = store.candidate(candidate_id)
        if not record:
            raise HTTPException(404, "Unknown candidate")
        return build_bundle(record["receipt"])

    def build_bundle(receipt: dict) -> dict:
        snapshot = receipt["payload"]["registry_snapshot"]["registered_assets"]
        manifests = {}
        artifacts = {}
        for entry in snapshot:
            asset = store.asset(entry["asset_id"])
            if not asset or digest(asset["manifest"]) != entry["manifest_sha256"]:
                raise HTTPException(409, "Registry manifest changed")
            manifests[asset["id"]] = asset["manifest"]
            if asset["features_sha256"]:
                artifacts[asset["features_sha256"]] = store.get_artifact(asset["features_sha256"])
        feature_sha = receipt["payload"]["feature_artifact_sha256"]
        if feature_sha:
            artifacts[feature_sha] = store.get_artifact(feature_sha)
        lineage, authorizations = [], []
        candidate_sha = receipt["payload"]["candidate_sha256"]
        for claim in receipt["payload"]["claims"]["C2_signed_lineage"]["records"]:
            for item in store.derivatives(candidate_sha):
                if item["id"] == claim["derivative_id"]:
                    lineage.append(item["envelope"])
        for claim in receipt["payload"]["claims"]["C7_authorization"]["records"]:
            item = store.authorization(claim["authorization_id"])
            if item:
                authorizations.append(item["envelope"])
        return {"schema": "cliptrace-evidence-bundle-v1", "receipt": receipt,
                "origin_manifests": manifests, "evidence_artifacts": artifacts,
                "derivative_manifests": lineage, "authorization_records": authorizations,
                "checkpoint_at_export": store.checkpoint(), "event_log": store.event_log(),
                "limitations": "Artifact verification checks signed hashes, not the truth of visual or audio findings. Revocation history is a server assertion unless separately audited."}

    @app.get("/api/reviews/{review_id}/bundle")
    def review_bundle(review_id: str):
        record = store.review(review_id)
        if not record:
            raise HTTPException(404, "Unknown review")
        return build_bundle(record["receipt"])

    @app.get("/api/reviews/{review_id}/receipt")
    def review_receipt(review_id: str):
        record = store.review(review_id)
        if not record:
            raise HTTPException(404, "Unknown review")
        return record["receipt"]

    @app.post("/api/reviews")
    def review(body: ReviewInput):
        try:
            return service.review(body.candidate_id, body.parent_asset_id, body.reviewer_assertion,
                                  body.reasoning, body.visual_state, body.audio_state, body.source_intervals_s)
        except ValueError as exc:
            value_error(exc)

    @app.post("/api/authorizations")
    def authorize(body: AuthorizationInput):
        try:
            return service.create_authorization(body.parent_asset_id, body.child_sha256,
                                                body.grantee, body.valid_from, body.valid_until, body.scope_note)
        except ValueError as exc:
            value_error(exc)

    @app.post("/api/authorizations/{authorization_id}/revoke")
    def revoke(authorization_id: str):
        if not store.revoke_authorization(authorization_id):
            raise HTTPException(404, "Unknown authorization")
        return {"authorization_id": authorization_id, "revoked": True}

    @app.post("/api/derivatives")
    def derivative(body: DerivativeInput):
        try:
            return service.create_derivative(body.parent_asset_id, body.child_sha256, body.source_intervals_s,
                                             body.declared_transformations, body.authorization_id)
        except ValueError as exc:
            value_error(exc)

    @app.get("/api/evidence/{sha256}")
    def artifact(sha256: str):
        try:
            return store.get_artifact(sha256)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/checkpoint")
    def checkpoint():
        return {"latest": store.checkpoint(), "chain_verification": store.verify_log(),
                "note": "Export the checkpoint to independently controlled storage."}

    return app


def run() -> None:
    import uvicorn
    uvicorn.run(create_app(), host=os.getenv("CLIPTRACE_HOST", "127.0.0.1"),
                port=int(os.getenv("CLIPTRACE_PORT", "8765")))


if __name__ == "__main__":
    run()
