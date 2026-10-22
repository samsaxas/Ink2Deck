import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))
from security import hash_password, verify_password  # noqa: E402


def test_new_hash_verifies_and_is_salted():
    first, second = hash_password("correct horse"), hash_password("correct horse")
    assert first != second
    assert verify_password("correct horse", first) == (True, False)
    assert verify_password("wrong", first) == (False, False)


def test_legacy_sha256_still_verifies_and_asks_for_upgrade():
    legacy = hashlib.sha256(b"old-password").hexdigest()
    assert verify_password("old-password", legacy) == (True, True)
    assert verify_password("nope", legacy) == (False, False)


def test_malformed_hash_is_rejected():
    assert verify_password("x", "pbkdf2_sha256$not$valid") == (False, False)
    assert verify_password("x", "") == (False, False)
