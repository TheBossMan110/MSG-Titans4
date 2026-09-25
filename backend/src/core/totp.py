"""
Time-based one-time passwords (RFC 6238) and the secret's encryption at rest.

Written against the standard library rather than a dependency: TOTP is
HMAC-SHA1 over a 30-second counter, truncated to six digits, and the whole of
it fits on this page where it can be read and checked.

The secret is stored encrypted (Fernet: AES-128-CBC + HMAC-SHA256) under a key
derived from ``JWT_SECRET``, so a copy of the ``users`` table alone does not
let anyone generate a user's codes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import settings

DIGITS = 6
STEP_SECONDS = 30
# Codes from one step either side are accepted: phone clocks drift, and a
# code typed at 29 seconds arrives at 31.
DRIFT_STEPS = 1


def new_secret() -> str:
    """A 160-bit secret, base32 as authenticator apps expect it."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def now_code(secret: str, at: float | None = None) -> str:
    return _code(secret, int((at if at is not None else time.time()) // STEP_SECONDS))


def verify(secret: str, code: str, at: float | None = None) -> bool:
    """Constant-time check of ``code`` against the current step and its neighbours."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != DIGITS:
        return False
    counter = int((at if at is not None else time.time()) // STEP_SECONDS)
    return any(
        hmac.compare_digest(_code(secret, counter + delta), code)
        for delta in range(-DRIFT_STEPS, DRIFT_STEPS + 1)
    )


def provisioning_uri(secret: str, account: str, issuer: str = "SupportNova") -> str:
    """The otpauth:// link an authenticator app scans from a QR code."""
    label = quote(f"{issuer}:{account}")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


# ── at rest ──────────────────────────────────────────────────
def _fernet() -> Fernet:
    key = hashlib.sha256(f"supportnova-mfa:{settings.jwt_secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


# ── recovery codes ───────────────────────────────────────────
def new_recovery_codes(count: int = 8) -> list[str]:
    """Readable one-time codes: ``7K4Q-9MXD``. No 0/O or 1/I to confuse."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return [
        "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(2))
        for _ in range(count)
    ]


def hash_recovery(code: str) -> str:
    normalised = "".join(ch for ch in code.upper() if ch.isalnum())
    return hashlib.sha256(f"recovery:{normalised}".encode()).hexdigest()
