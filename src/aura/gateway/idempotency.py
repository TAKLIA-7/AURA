"""AURA Idempotency & Concurrency Manager — protects against ingestion attacks and race conditions."""
from __future__ import annotations
import asyncio
from collections import defaultdict, deque
import hashlib
import json
import time
from typing import Any, Dict, Optional, Tuple

from aura.models import ActionRequest, ActionResult


class IdempotencyRecord:
    def __init__(self, key: str, status: str = "in_progress", ttl_seconds: float = 300.0) -> None:
        self.key = key
        self.status = status  # "in_progress", "completed", "failed"
        self.created_at = time.monotonic()
        self.ttl_seconds = ttl_seconds
        self.result: Optional[ActionResult] = None
        self.event = asyncio.Event()

    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > self.ttl_seconds


class IdempotencyManager:
    """
    Guarantees idempotency and protects against race conditions & ingestion attacks:
      1. Canonical Idempotency Keys: Deterministic hashing of agent, tool, and arguments.
      2. In-Flight Mutual Exclusion: Prevents concurrent duplicate executions of the same tool call.
      3. TTL-based Result Caching: Repeated identical calls within TTL receive cached results without re-execution.
      4. Sliding-Window Rate Limiting: Mitigates flood ingestion attacks per agent and tool.
    """

    def __init__(self, default_ttl_seconds: float = 300.0) -> None:
        self.default_ttl = default_ttl_seconds
        self._records: Dict[str, IdempotencyRecord] = {}
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._global_lock = asyncio.Lock()
        # Sliding-window timestamps for rate limiting: key -> deque of timestamps
        self._rate_limit_windows: Dict[str, deque] = defaultdict(deque)

    def compute_key(self, request: ActionRequest) -> str:
        """Compute a canonical SHA-256 idempotency key for an ActionRequest."""
        if request.idempotency_key:
            return request.idempotency_key

        canonical_args = json.dumps(request.arguments, sort_keys=True, default=str)
        payload = f"{request.agent_id}:{request.tool}:{request.operation}:{canonical_args}:{request.target}"
        return f"idemp_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"

    def check_rate_limit(
        self,
        identifier: str,
        max_requests: int = 60,
        window_seconds: float = 60.0,
    ) -> Tuple[bool, str]:
        """
        Sliding-window rate limiter to protect against flood ingestion attacks.
        Returns (allowed, reason).
        """
        now = time.monotonic()
        timestamps = self._rate_limit_windows[identifier]

        # Evict timestamps outside the sliding window
        while timestamps and (now - timestamps[0]) > window_seconds:
            timestamps.popleft()

        if len(timestamps) >= max_requests:
            return False, f"Rate limit exceeded for '{identifier}': {len(timestamps)} requests in {window_seconds}s (limit={max_requests})"

        timestamps.append(now)
        return True, "Rate limit OK"

    async def check_and_reserve(
        self,
        request: ActionRequest,
        ttl_seconds: Optional[float] = None,
    ) -> Tuple[str, Optional[ActionResult], bool]:
        """
        Check if request is cached or in flight, or reserve execution.
        Returns:
          (key, cached_result, is_in_flight)
          - If cached_result is not None: caller should return cached result.
          - If is_in_flight is True: another identical request is currently executing (race condition detected).
          - If (None, False): reserved successfully, caller proceeds to execute tool.
        """
        key = self.compute_key(request)
        ttl = ttl_seconds or self.default_ttl

        async with self._global_lock:
            record = self._records.get(key)
            if record and not record.is_expired():
                if record.status == "completed" and record.result:
                    # Return cached result with idempotent flag
                    cached = record.result.model_copy()
                    cached.idempotent_cached = True
                    return key, cached, False
                elif record.status == "in_progress":
                    # Concurrent duplicate / race condition!
                    return key, None, True
            # Reserve in-progress slot
            new_record = IdempotencyRecord(key=key, status="in_progress", ttl_seconds=ttl)
            self._records[key] = new_record
            return key, None, False

    async def record_completion(self, key: str, result: ActionResult) -> None:
        """Record the successful or failed result of a tool execution and notify waiters."""
        async with self._global_lock:
            record = self._records.get(key)
            if record:
                record.status = "completed" if result.success else "failed"
                record.result = result
                record.event.set()

    async def wait_for_in_flight(self, key: str, timeout: float = 30.0) -> Optional[ActionResult]:
        """Wait for an in-flight tool execution to complete and return its result."""
        record = self._records.get(key)
        if not record:
            return None
        try:
            await asyncio.wait_for(record.event.wait(), timeout=timeout)
            if record.result:
                cached = record.result.model_copy()
                cached.idempotent_cached = True
                return cached
            return None
        except asyncio.TimeoutError:
            return None

    def purge_expired(self) -> int:
        """Purge expired cache entries."""
        expired = [k for k, v in self._records.items() if v.is_expired()]
        for k in expired:
            del self._records[k]
        return len(expired)

