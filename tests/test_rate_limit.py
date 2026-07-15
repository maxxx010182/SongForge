"""Rate limit + beta guards unit tests."""

from backend.services.rate_limit import RateLimiter
from backend.services.beta_guards import BetaGuards


def test_rate_limiter_allows_then_blocks():
    rl = RateLimiter()
    assert rl.allow("k", limit=2, window_sec=60) is True
    assert rl.allow("k", limit=2, window_sec=60) is True
    assert rl.allow("k", limit=2, window_sec=60) is False


def test_rate_limiter_separate_keys():
    rl = RateLimiter()
    assert rl.allow("a", limit=1, window_sec=60) is True
    assert rl.allow("b", limit=1, window_sec=60) is True
    assert rl.allow("a", limit=1, window_sec=60) is False


def test_beta_guards_slot_full():
    g = BetaGuards()
    try:
        g.assert_slot_available(count_generating=99, count_user_generating=0)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "много людей" in str(exc).lower() or "подождите" in str(exc).lower()


def test_beta_guards_user_slot():
    g = BetaGuards()
    try:
        g.assert_slot_available(count_generating=0, count_user_generating=5)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "уже идёт" in str(exc).lower() or "дождитесь" in str(exc).lower()
