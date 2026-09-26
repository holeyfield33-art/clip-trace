from cliptrace_e1.hashing import sha256_bytes, sha256_json


def test_sha256_bytes_deterministic():
    a = sha256_bytes(b"cliptrace-e1")
    b = sha256_bytes(b"cliptrace-e1")
    assert a == b
    assert len(a) == 64


def test_sha256_json_order_independent():
    d1 = {"b": 2, "a": 1}
    d2 = {"a": 1, "b": 2}
    assert sha256_json(d1) == sha256_json(d2)
