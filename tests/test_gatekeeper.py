"""Gatekeeper pattern: Quota Manager -> Token Bucket -> DOS Detector (Sec. 9.3.1-9.3.2)."""

import time

from police_thief.infra.gatekeeper import DOSDetector, Gatekeeper, QuotaManager, TokenBucket, build_gatekeeper


# -- QuotaManager -----------------------------------------------------------

def test_quota_manager_allows_up_to_daily_limit():
    quota = QuotaManager(daily_limit=3)
    assert quota.allow() is True
    assert quota.allow() is True
    assert quota.allow() is True
    assert quota.allow() is False  # 4th request exceeds the daily limit


# -- TokenBucket --------------------------------------------------------------

def test_token_bucket_starts_full():
    bucket = TokenBucket(capacity=5, refill_rate=1)
    assert bucket.tokens == 5


def test_token_bucket_allows_while_tokens_available():
    bucket = TokenBucket(capacity=3, refill_rate=0.001)
    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is False  # bucket drained, refill rate too slow to help


def test_token_bucket_refills_over_time():
    bucket = TokenBucket(capacity=1, refill_rate=100)  # fast refill for a quick test
    assert bucket.allow() is True
    assert bucket.allow() is False  # immediately empty
    time.sleep(0.02)  # ~2 tokens' worth at refill_rate=100/sec
    assert bucket.allow() is True


def test_token_bucket_never_exceeds_capacity():
    bucket = TokenBucket(capacity=2, refill_rate=1000)
    time.sleep(0.05)
    bucket._refill()
    assert bucket.tokens <= 2


# -- DOSDetector --------------------------------------------------------------

def test_dos_detector_allows_sparse_sends():
    detector = DOSDetector(max_sends=5, window_sec=10)
    assert detector.check([]) is True


def test_dos_detector_blocks_burst():
    detector = DOSDetector(max_sends=3, window_sec=10)
    now = time.monotonic()
    recent = [now, now, now]  # 3 sends "just now"
    assert detector.check(recent) is False


def test_dos_detector_ignores_old_sends_outside_window():
    detector = DOSDetector(max_sends=2, window_sec=1)
    old = time.monotonic() - 100  # far outside the window
    assert detector.check([old, old, old]) is True


# -- Gatekeeper composition -----------------------------------------------

def test_gatekeeper_allows_send_when_all_gates_pass():
    gk = Gatekeeper(
        quota=QuotaManager(daily_limit=10),
        bucket=TokenBucket(capacity=10, refill_rate=1),
        dos=DOSDetector(max_sends=10, window_sec=10),
    )
    result = gk.try_send(lambda: "sent!")
    assert result == "sent!"


def test_gatekeeper_blocks_when_quota_exhausted():
    gk = Gatekeeper(
        quota=QuotaManager(daily_limit=0),
        bucket=TokenBucket(capacity=10, refill_rate=1),
        dos=DOSDetector(max_sends=10, window_sec=10),
    )
    result = gk.try_send(lambda: "should not run")
    assert result is None


def test_gatekeeper_blocks_when_bucket_empty():
    gk = Gatekeeper(
        quota=QuotaManager(daily_limit=10),
        bucket=TokenBucket(capacity=0, refill_rate=0),
        dos=DOSDetector(max_sends=10, window_sec=10),
    )
    result = gk.try_send(lambda: "should not run")
    assert result is None


def test_gatekeeper_locks_pipeline_on_dos_pattern():
    gk = Gatekeeper(
        quota=QuotaManager(daily_limit=100),
        bucket=TokenBucket(capacity=100, refill_rate=100),
        dos=DOSDetector(max_sends=2, window_sec=10),
    )
    gk.try_send(lambda: "1")
    gk.try_send(lambda: "2")
    result = gk.try_send(lambda: "3 -- should be blocked")
    assert result is None


def test_gatekeeper_passes_through_args_and_kwargs():
    gk = Gatekeeper(
        quota=QuotaManager(daily_limit=10),
        bucket=TokenBucket(capacity=10, refill_rate=1),
        dos=DOSDetector(max_sends=10, window_sec=10),
    )
    result = gk.try_send(lambda a, b, c=None: (a, b, c), 1, 2, c=3)
    assert result == (1, 2, 3)


# -- build_gatekeeper (config/game.json's rate_limiter_gatekeeper section) --

def test_build_gatekeeper_uses_queue_depth_as_daily_cap():
    gk = build_gatekeeper({
        "requests_per_minute": 30, "concurrent_requests": 2,
        "retry_backoff_sec": 5, "max_retries": 3, "queue_depth": 2,
    })
    assert gk.try_send(lambda: "1") == "1"
    assert gk.try_send(lambda: "2") == "2"
    assert gk.try_send(lambda: "3 -- over queue_depth") is None


def test_build_gatekeeper_token_bucket_matches_requests_per_minute():
    gk = build_gatekeeper({
        "requests_per_minute": 30, "concurrent_requests": 2,
        "retry_backoff_sec": 5, "max_retries": 3, "queue_depth": 100,
    })
    assert gk.bucket.capacity == 30
    assert gk.bucket.refill_rate == 0.5
