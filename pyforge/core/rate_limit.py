"""Sliding-Window Rate Limiter per Endpoint Tier (Section 31)."""
import time
from collections import defaultdict
from typing import Dict, List, Tuple

RATE_LIMIT_TIERS: Dict[str, Tuple[int, float]] = {
    "login": (5, 60.0),           # 5 attempts per 60s
    "register": (5, 60.0),        # 5 registrations per 60s
    "password_reset": (3, 60.0),  # 3 reset requests per 60s
    "execution": (15, 60.0),      # 15 code executions per 60s
    "tutor": (10, 60.0),          # 10 AI tutor requests per 60s
    "api": (120, 60.0),           # 120 general API requests per 60s
}

class RateLimiter:
    def __init__(self) -> None:
        self._buckets: Dict[str, List[float]] = defaultdict(list)

    def check(self, tier: str, subject_key: str, now: float | None = None) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        max_calls, window_sec = RATE_LIMIT_TIERS.get(tier, RATE_LIMIT_TIERS["api"])
        current = now if now is not None else time.monotonic()
        bucket_key = f"{tier}:{subject_key}"
        cutoff = current - window_sec
        timestamps = [t for t in self._buckets[bucket_key] if t > cutoff]
        if len(timestamps) >= max_calls:
            self._buckets[bucket_key] = timestamps
            retry_after = max(1, int(window_sec - (current - timestamps[0])))
            return False, retry_after
        timestamps.append(current)
        self._buckets[bucket_key] = timestamps
        return True, 0

    def reset(self) -> None:
        self._buckets.clear()
