"""Gatekeeper pattern: three cumulative protection gates in front of the
Gmail API (Sec. 9.3.1-9.3.2) -- Quota Manager -> Token Bucket -> DOS Detector.

NOTE: these are rate-tokens for load regulation, unrelated to LLM tokens
or OAuth tokens (see the terminology box in Sec. 9.3.1).
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class QuotaManager:
    """Daily operation counter; blocks once the daily safety threshold is hit."""

    daily_limit: int
    _count: int = 0

    def allow(self) -> bool:
        if self._count >= self.daily_limit:
            return False
        self._count += 1
        return True


@dataclass
class TokenBucket:
    """tokens <- min(C, tokens + r*dt); allow iff tokens >= 1 (Sec. 9.3.2)."""

    capacity: float
    refill_rate: float
    tokens: float = 0.0
    last: float = 0.0

    def __post_init__(self) -> None:
        self.tokens = self.capacity
        self.last = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last = now

    def allow(self, cost: float = 1.0) -> bool:
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


class DOSDetector:
    """Flags anomalous send patterns (e.g. an infinite-loop bug) and locks
    the whole pipeline (circuit breaker) to protect the account."""

    def __init__(self, *, max_sends: int = 5, window_sec: float = 10.0):
        self.max_sends = max_sends
        self.window_sec = window_sec

    def check(self, recent_send_timestamps: list[float]) -> bool:
        """True if it's safe to proceed; False if the recent pattern looks
        like a bug/infinite loop and the pipeline should lock (Fig. 13)."""
        now = time.monotonic()
        recent = [t for t in recent_send_timestamps if now - t <= self.window_sec]
        return len(recent) < self.max_sends


class Gatekeeper:
    """Composes QuotaManager -> TokenBucket -> DOSDetector in front of
    infra.email_sender.send_report (Fig. 13)."""

    def __init__(self, quota: QuotaManager, bucket: TokenBucket, dos: DOSDetector):
        self.quota = quota
        self.bucket = bucket
        self.dos = dos
        self._recent_sends: list[float] = []

    def try_send(self, send_fn, *args, **kwargs):
        """Route a send through all three gates; returns send_fn's result,
        or None if blocked at any gate. A block is an expected outcome
        (fail fast, Fig. 13), not an error -- never raises on its own."""
        if not self.quota.allow():
            return None
        if not self.bucket.allow():
            return None
        if not self.dos.check(self._recent_sends):
            return None
        self._recent_sends.append(time.monotonic())
        return send_fn(*args, **kwargs)


def build_gatekeeper(rate_limiter_config: dict) -> Gatekeeper:
    """Build a Gatekeeper from config/game.json's `rate_limiter_gatekeeper`
    section (requests_per_minute, queue_depth; retry_backoff_sec/max_retries
    govern connection retry elsewhere -- infra/mcp_client.py -- not this
    gate). That section has no explicit daily cap, so `queue_depth` -- the
    largest bound the config actually specifies -- doubles as the
    QuotaManager's safety ceiling; DOSDetector reuses the same per-minute
    window as a secondary burst breaker alongside the smooth token bucket."""
    requests_per_minute = rate_limiter_config["requests_per_minute"]
    return Gatekeeper(
        quota=QuotaManager(daily_limit=rate_limiter_config["queue_depth"]),
        bucket=TokenBucket(capacity=requests_per_minute, refill_rate=requests_per_minute / 60.0),
        dos=DOSDetector(max_sends=requests_per_minute, window_sec=60.0),
    )
