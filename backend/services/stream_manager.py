# filename: backend/services/stream_manager.py
# purpose: Redis connection singleton, XADD/XREAD helpers, stream key constants
# governs: §4.2, §5.2 — stream_manager.py spec

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Stream key constants (§4.2) ───────────────────────────────────────────────
STREAM_FLOWS: str = "argus:flows"
STREAM_CLASSIFIED: str = "argus:classified"

# ── Config from environment ───────────────────────────────────────────────────
_REDIS_URL: str = os.environ.get("ARGUS_REDIS_URL", "redis://localhost:6379")
_STREAM_MAX_LEN: int = int(os.environ.get("ARGUS_STREAM_MAX_LEN", "10000"))

# ── Connection singleton — lazy, not created at import time ───────────────────
_redis_client: Any | None = None


def get_client() -> Any:
    """
    Return the Redis client singleton, creating it on first call.
    Connection is lazy — no socket is opened at import time.
    Raises RuntimeError with a clear message if redis-py is not installed
    or if the server is unreachable.
    """
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    try:
        import redis  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "redis-py is not installed. Run: pip install redis"
        ) from exc

    try:
        client = redis.from_url(_REDIS_URL, decode_responses=True)
        client.ping()
        logger.info("Redis connection established: %s", _REDIS_URL)
        _redis_client = client
        return _redis_client
    except Exception as exc:
        logger.error(
            "Failed to connect to Redis at %s: %s. "
            "Ensure Redis is running (redis-server --daemonize yes).",
            _REDIS_URL,
            exc,
        )
        raise RuntimeError(
            f"Redis connection failed ({_REDIS_URL}): {exc}"
        ) from exc


def xadd(stream: str, payload: dict[str, str]) -> str | None:
    """
    Publish a flat string-valued dict to `stream` via XADD with MAXLEN ~ cap.

    Args:
        stream:  Stream key (use STREAM_FLOWS or STREAM_CLASSIFIED constants).
        payload: Flat dict of field → string value. All values must be strings;
                 callers are responsible for serialisation before calling this.

    Returns:
        The Redis message ID assigned by the server, or None on failure.
    """
    try:
        client = get_client()
        message_id: str = client.xadd(
            stream,
            payload,
            maxlen=_STREAM_MAX_LEN,
            approximate=True,
        )
        return message_id
    except Exception as exc:
        logger.error("XADD to stream %r failed: %s", stream, exc)
        return None


def xread(
    stream: str,
    last_id: str = "$",
    count: int = 100,
    block_ms: int | None = None,
) -> list[tuple[str, dict[str, str]]]:
    """
    Read new messages from `stream` starting after `last_id`.

    Args:
        stream:   Stream key.
        last_id:  Read messages with ID > this value. Use "$" for new-only
                  (non-blocking) or "0" to read from the beginning.
        count:    Maximum number of messages to return per call.
        block_ms: If set, block for up to this many milliseconds waiting for
                  new messages. None = non-blocking.

    Returns:
        List of (message_id, fields_dict) tuples. Empty list if no messages
        are available or on error.
    """
    try:
        client = get_client()
        raw = client.xread(
            {stream: last_id},
            count=count,
            block=block_ms,
        )
        if not raw:
            return []
        # raw shape: [[stream_name, [(id, fields), ...]]]
        _, messages = raw[0]
        return [(msg_id, fields) for msg_id, fields in messages]
    except Exception as exc:
        logger.error("XREAD from stream %r failed: %s", stream, exc)
        return []
