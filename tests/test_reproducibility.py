from cliptrace_e1.hashing import sha256_bytes


def test_hash_stable_across_calls():
    payload = b"reproducibility-check"
    assert sha256_bytes(payload) == sha256_bytes(payload)
