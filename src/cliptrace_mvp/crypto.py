"""Canonical signed statements and independent signature verification."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def public_pem(key: Ed25519PublicKey) -> str:
    return key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")


def key_id(key: Ed25519PublicKey) -> str:
    return hashlib.sha256(public_pem(key).encode("ascii")).hexdigest()


def create_key(path: Path, passphrase: str) -> None:
    if path.exists():
        return
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.BestAvailableEncryption(passphrase.encode("utf-8")))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_key(path: Path, passphrase: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=passphrase.encode("utf-8"))
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Expected an Ed25519 private key")
    return key


def sign(payload: dict, key: Ed25519PrivateKey) -> dict:
    pub = key.public_key()
    return {"payload": payload, "signature_algorithm": "Ed25519",
            "signing_key_id": key_id(pub), "public_key_pem": public_pem(pub),
            "signature_base64": base64.b64encode(key.sign(canonical(payload))).decode("ascii")}


def verify(envelope: dict, trusted_public_key_pem: str | None = None) -> bool:
    try:
        if envelope["signature_algorithm"] != "Ed25519":
            return False
        pem = envelope["public_key_pem"]
        if trusted_public_key_pem is not None and pem != trusted_public_key_pem:
            return False
        pub = serialization.load_pem_public_key(pem.encode("ascii"))
        if not isinstance(pub, Ed25519PublicKey) or envelope["signing_key_id"] != key_id(pub):
            return False
        pub.verify(base64.b64decode(envelope["signature_base64"], validate=True), canonical(envelope["payload"]))
        return True
    except (KeyError, ValueError, InvalidSignature, TypeError, UnicodeError):
        return False
