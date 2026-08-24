from core.security import hash_api_key, hash_password, verify_password


def test_hash_and_verify_password_round_trip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_hash_api_key_is_deterministic_sha256():
    import hashlib

    raw = "some-service-key"
    assert hash_api_key(raw) == hashlib.sha256(raw.encode()).hexdigest()
