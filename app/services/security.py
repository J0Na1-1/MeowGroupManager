from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import secrets


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class VerificationToken:
    value: str
    target_user_id: int
    expires_at: datetime


class TokenService:
    """One-time, target-bound tokens. Persistence is injected by the caller."""

    def __init__(self, secret: str):
        self._secret = secret.encode()

    def issue(self, user_id: int, ttl_seconds: int = 900) -> VerificationToken:
        nonce = secrets.token_bytes(4)
        expires = int(utcnow().timestamp()) + ttl_seconds
        payload = f"{user_id}.{expires}." + base64.urlsafe_b64encode(nonce).decode().rstrip("=")
        sig = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()[:8]
        return VerificationToken(f"{payload}.{sig}", user_id, datetime.fromtimestamp(expires, timezone.utc))

    def validate(self, token: str, user_id: int, now: datetime | None = None) -> bool:
        try:
            target, expires, nonce, signature = token.split(".", 3)
            payload = f"{target}.{expires}.{nonce}"
            valid_sig = hmac.compare_digest(
                signature, hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()[:8]
            )
            current = int((now or utcnow()).timestamp())
            return valid_sig and int(target) == user_id and current <= int(expires)
        except (ValueError, TypeError):
            return False


@dataclass(frozen=True)
class LookupResult:
    exists: bool
    active: bool
    source: str = "external"


class ExternalLookup:
    async def lookup(self, user_id: int) -> LookupResult:
        raise NotImplementedError


class CleanupPolicy:
    """Never kick when lookup fails; dry-run is the safe default."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run

    async def evaluate(self, user_id: int, lookup: ExternalLookup) -> str:
        try:
            result = await lookup.lookup(user_id)
        except Exception:
            return "lookup_failed_no_action"
        if not result.exists or not result.active:
            return "would_remove" if self.dry_run else "remove"
        return "keep"
