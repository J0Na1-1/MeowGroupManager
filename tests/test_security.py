from datetime import timedelta
from app.services.security import CleanupPolicy, ExternalLookup, LookupResult, TokenService, utcnow


def test_token_is_target_bound_and_expires():
    service = TokenService("secret")
    token = service.issue(42, ttl_seconds=10)
    assert service.validate(token.value, 42)
    assert not service.validate(token.value, 43)
    assert not service.validate(token.value, 42, token.expires_at + timedelta(seconds=1))


class Lookup(ExternalLookup):
    async def lookup(self, user_id):
        return LookupResult(exists=False, active=False)


class Broken(ExternalLookup):
    async def lookup(self, user_id):
        raise RuntimeError("network")


async def test_cleanup_defaults_to_dry_run_and_never_kicks_on_failure():
    assert await CleanupPolicy().evaluate(1, Lookup()) == "would_remove"
    assert await CleanupPolicy(dry_run=False).evaluate(1, Lookup()) == "remove"
    assert await CleanupPolicy(dry_run=False).evaluate(1, Broken()) == "lookup_failed_no_action"
