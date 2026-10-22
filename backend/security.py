"""Password hashing for Ink2Deck.

New passwords use salted PBKDF2-SHA256. Accounts created by the old Streamlit
app stored a bare, unsalted SHA-256 hex digest. Those still verify, and
`verify_password` tells the caller to re-hash them so they are upgraded the
next time the user logs in.
"""
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    ).hex()
    return f"{ALGORITHM}${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """Return (is_correct, needs_rehash)."""
    if not stored:
        return False, False

    if stored.startswith(ALGORITHM + "$"):
        try:
            _, iterations, salt, expected = stored.split("$")
            actual = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
            ).hex()
        except (ValueError, TypeError):
            return False, False
        return hmac.compare_digest(actual, expected), int(iterations) < ITERATIONS

    # Legacy account from the Streamlit version: unsalted SHA-256.
    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    ok = hmac.compare_digest(legacy, stored)
    return ok, ok


# A throwaway hash used to spend the same time on unknown usernames, so that
# response timing does not reveal which usernames exist.
DUMMY_HASH = hash_password("not-a-real-password")
