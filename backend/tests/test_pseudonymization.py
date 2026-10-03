from app.core.security import pseudonymize_identifier, verify_device_signature


def test_pseudonymize_identifier_deterministic():
    mac1 = "00:11:22:33:44:55"
    hash1 = pseudonymize_identifier(mac1)
    hash2 = pseudonymize_identifier(mac1)
    # Must be deterministic and prefix with hmac:
    assert hash1 == hash2
    assert hash1.startswith("hmac:")
    assert len(hash1) == 21  # "hmac:" + 16 hex chars


def test_pseudonymize_case_insensitivity():
    mac_lower = "aa:bb:cc:dd:ee:ff"
    mac_upper = "AA:BB:CC:DD:EE:FF"
    assert pseudonymize_identifier(mac_lower) == pseudonymize_identifier(mac_upper)


def test_pseudonymize_different_inputs():
    hash_a = pseudonymize_identifier("00:11:22:33:44:55")
    hash_b = pseudonymize_identifier("AA:BB:CC:DD:EE:FF")
    assert hash_a != hash_b


def test_device_signature_verification():
    secret = "collector_secret_key_123"
    payload = b'{"status": "ready"}'
    import hmac, hashlib
    valid_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    assert verify_device_signature(payload, valid_sig, secret) is True
    assert verify_device_signature(payload, "invalid_signature", secret) is False
