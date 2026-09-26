"""Local durable records, content-addressed artifacts, and signed event checkpoints."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .crypto import canonical, create_key, digest, file_digest, load_key, sign, verify


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root: Path, passphrase: str):
        if len(passphrase) < 16:
            raise ValueError("CLIPTRACE_SIGNING_PASSPHRASE must be at least 16 characters")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.media_dir = self.root / "media"
        self.artifact_dir = self.root / "artifacts"
        self.tmp_dir = self.root / "tmp"
        for directory in [self.media_dir, self.artifact_dir, self.tmp_dir]:
            directory.mkdir(exist_ok=True)
        self.db_path = self.root / "cliptrace.sqlite3"
        create_key(self.root / "keys" / "receipt-key.pem", passphrase)
        create_key(self.root / "keys" / "checkpoint-key.pem", passphrase)
        self.receipt_key = load_key(self.root / "keys" / "receipt-key.pem", passphrase)
        self.checkpoint_key = load_key(self.root / "keys" / "checkpoint-key.pem", passphrase)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, filename TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL, created_at TEXT NOT NULL,
                    manifest_json TEXT NOT NULL, features_sha256 TEXT,
                    fingerprint_status TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS assets_sha ON assets(sha256);
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, filename TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL, created_at TEXT NOT NULL,
                    receipt_json TEXT NOT NULL, features_sha256 TEXT, leads_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS authorizations (
                    id TEXT PRIMARY KEY, parent_id TEXT NOT NULL, child_sha256 TEXT NOT NULL,
                    valid_from TEXT NOT NULL, valid_until TEXT NOT NULL, revoked_at TEXT,
                    envelope_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS derivatives (
                    id TEXT PRIMARY KEY, parent_id TEXT NOT NULL, child_sha256 TEXT NOT NULL,
                    authorization_id TEXT, envelope_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, receipt_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY, previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL, event_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                    seq INTEGER PRIMARY KEY, envelope_json TEXT NOT NULL
                );
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def artifact_path(self, sha256: str) -> Path:
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            raise ValueError("Invalid artifact digest")
        return self.artifact_dir / sha256[:2] / (sha256 + ".json")

    def put_artifact(self, value: dict) -> str:
        sha256 = digest(value)
        path = self.artifact_path(sha256)
        path.parent.mkdir(exist_ok=True)
        if not path.exists():
            path.write_bytes(canonical(value))
        elif file_digest(path) != sha256:
            raise ValueError("Existing evidence artifact was changed")
        return sha256

    def get_artifact(self, sha256: str) -> dict:
        path = self.artifact_path(sha256)
        if file_digest(path) != sha256:
            raise ValueError("Evidence artifact integrity failure")
        return json.loads(path.read_bytes())

    def media_path(self, sha256: str) -> Path:
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            raise ValueError("Invalid media digest")
        return self.media_dir / sha256[:2] / (sha256 + ".bin")

    def persist_media(self, staged: Path, sha256: str) -> Path:
        if file_digest(staged) != sha256:
            raise ValueError("Staged media digest mismatch")
        destination = self.media_path(sha256)
        destination.parent.mkdir(exist_ok=True)
        if destination.exists():
            if file_digest(destination) != sha256:
                raise ValueError("Stored media integrity failure")
            staged.unlink()
        else:
            staged.replace(destination)
        return destination

    def _event(self, db: sqlite3.Connection, kind: str, subject_id: str, document_sha256: str) -> None:
        last = db.execute("SELECT seq, event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        seq = (last["seq"] + 1) if last else 1
        previous = last["event_hash"] if last else "0" * 64
        event = {"seq": seq, "previous_hash": previous, "kind": kind,
                 "subject_id": subject_id, "document_sha256": document_sha256, "recorded_at": now()}
        event_hash = digest(event)
        db.execute("INSERT INTO events VALUES(?,?,?,?)", (seq, previous, event_hash, canonical(event).decode()))
        checkpoint = sign({"schema": "cliptrace-checkpoint-v1", "sequence": seq,
                           "log_head_sha256": event_hash, "signed_at": now()}, self.checkpoint_key)
        db.execute("INSERT INTO checkpoints VALUES(?,?)", (seq, canonical(checkpoint).decode()))

    def insert_asset(self, item: dict) -> None:
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO assets VALUES(?,?,?,?,?,?,?,?)",
                       (item["id"], item["sha256"], item["filename"], item["size_bytes"],
                        item["created_at"], canonical(item["manifest"]).decode(),
                        item["features_sha256"], item["fingerprint_status"]))
            self._event(db, "origin_registered", item["id"], digest(item["manifest"]))

    def insert_candidate(self, item: dict) -> None:
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?)",
                       (item["id"], item["sha256"], item["filename"], item["size_bytes"],
                        item["created_at"], canonical(item["receipt"]).decode(),
                        item["features_sha256"], canonical(item["leads"]).decode()))
            self._event(db, "candidate_verified", item["id"], digest(item["receipt"]))

    def insert_authorization(self, item: dict) -> None:
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO authorizations VALUES(?,?,?,?,?,?,?)",
                       (item["id"], item["parent_id"], item["child_sha256"], item["valid_from"],
                        item["valid_until"], None, canonical(item["envelope"]).decode()))
            self._event(db, "authorization_recorded", item["id"], digest(item["envelope"]))

    def revoke_authorization(self, authorization_id: str) -> bool:
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revoked_at FROM authorizations WHERE id=?", (authorization_id,)).fetchone()
            if row is None:
                return False
            if row["revoked_at"] is None:
                stamp = now()
                db.execute("UPDATE authorizations SET revoked_at=? WHERE id=?", (stamp, authorization_id))
                self._event(db, "authorization_revoked", authorization_id, digest({"revoked_at": stamp}))
            return True

    def insert_derivative(self, item: dict) -> None:
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO derivatives VALUES(?,?,?,?,?)",
                       (item["id"], item["parent_id"], item["child_sha256"],
                        item["authorization_id"], canonical(item["envelope"]).decode()))
            self._event(db, "derivative_recorded", item["id"], digest(item["envelope"]))

    def insert_review(self, item: dict) -> None:
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO reviews VALUES(?,?,?)",
                       (item["id"], item["candidate_id"], canonical(item["receipt"]).decode()))
            self._event(db, "review_recorded", item["id"], digest(item["receipt"]))

    def assets(self) -> list[dict]:
        with self.db() as db:
            return [self._asset(r) for r in db.execute("SELECT * FROM assets ORDER BY created_at,id")]

    @staticmethod
    def _asset(row) -> dict:
        item = dict(row)
        item["manifest"] = json.loads(item.pop("manifest_json"))
        return item

    def asset(self, asset_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
            return self._asset(row) if row else None

    def matching_assets(self, sha256: str) -> list[dict]:
        with self.db() as db:
            return [self._asset(r) for r in db.execute("SELECT * FROM assets WHERE sha256=? ORDER BY created_at,id", (sha256,))]

    def candidate(self, candidate_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            item["receipt"] = json.loads(item.pop("receipt_json"))
            item["leads"] = json.loads(item.pop("leads_json"))
            return item

    def candidates(self) -> list[dict]:
        with self.db() as db:
            return [{"id": r["id"], "sha256": r["sha256"], "filename": r["filename"],
                     "created_at": r["created_at"]} for r in db.execute("SELECT id,sha256,filename,created_at FROM candidates ORDER BY created_at DESC LIMIT 50")]

    def authorizations(self, parent_id: str, child_sha256: str) -> list[dict]:
        with self.db() as db:
            rows = db.execute("SELECT * FROM authorizations WHERE parent_id=? AND child_sha256=?", (parent_id, child_sha256))
            return [dict(r) | {"envelope": json.loads(r["envelope_json"])} for r in rows]

    def authorization(self, authorization_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT * FROM authorizations WHERE id=?", (authorization_id,)).fetchone()
            return dict(row) | {"envelope": json.loads(row["envelope_json"])} if row else None

    def derivatives(self, child_sha256: str) -> list[dict]:
        with self.db() as db:
            rows = db.execute("SELECT * FROM derivatives WHERE child_sha256=?", (child_sha256,))
            return [dict(r) | {"envelope": json.loads(r["envelope_json"])} for r in rows]

    def review(self, review_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
            return dict(row) | {"receipt": json.loads(row["receipt_json"])} if row else None

    def checkpoint(self) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT envelope_json FROM checkpoints ORDER BY seq DESC LIMIT 1").fetchone()
            return json.loads(row["envelope_json"]) if row else None

    def event_log(self) -> list[dict]:
        with self.db() as db:
            return [dict(r) | {"event": json.loads(r["event_json"])}
                    for r in db.execute("SELECT * FROM events ORDER BY seq")]

    def verify_log(self) -> dict:
        with self.db() as db:
            rows = db.execute("SELECT * FROM events ORDER BY seq").fetchall()
            checkpoints = db.execute("SELECT * FROM checkpoints ORDER BY seq").fetchall()
        previous = "0" * 64
        for index, row in enumerate(rows, 1):
            event = json.loads(row["event_json"])
            if row["seq"] != index or row["previous_hash"] != previous or event["previous_hash"] != previous or event["seq"] != index or row["event_hash"] != digest(event):
                return {"valid": False, "reason": "event_chain_mismatch", "sequence": index}
            previous = row["event_hash"]
        if len(checkpoints) != len(rows):
            return {"valid": False, "reason": "checkpoint_count_mismatch"}
        for row, checkpoint in zip(rows, checkpoints):
            envelope = json.loads(checkpoint["envelope_json"])
            if (checkpoint["seq"] != row["seq"] or not verify(envelope) or
                envelope["public_key_pem"] != sign({}, self.checkpoint_key)["public_key_pem"] or
                envelope["payload"]["log_head_sha256"] != row["event_hash"] or
                envelope["payload"]["sequence"] != row["seq"]):
                return {"valid": False, "reason": "checkpoint_mismatch", "sequence": row["seq"]}
        return {"valid": True, "events": len(rows), "head_sha256": previous,
                "limitation": "Export the signed checkpoint outside this server to detect wholesale history replacement."}
