"""Shared HTTP client helpers for collector modules.

Consolidates request timeouts, error logging, and JSON parsing so each
collector focuses on domain logic instead of repeating boilerplate.
"""

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0
DEFAULT_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 30.0


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    attempts: int = DEFAULT_ATTEMPTS,
    retry_delay: float = RETRY_DELAY_SECONDS,
) -> Any:
    """GET a URL and return the parsed JSON body.

    Retries transient failures (5xx, network errors) up to ``attempts``
    times with ``retry_delay`` seconds in between; client errors (4xx)
    fail immediately since a retry cannot change the outcome. Returns
    the parsed JSON on success, or None once all attempts are exhausted.
    All errors are logged with the request URL for debugging.
    """
    for attempt in range(1, attempts + 1):
        try:
            response = httpx.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                logger.error(
                    "HTTP %s from %s: %s",
                    e.response.status_code,
                    url,
                    e.response.text[:200],
                )
                return None
            logger.warning(
                "HTTP %s from %s (attempt %d/%d)",
                e.response.status_code,
                url,
                attempt,
                attempts,
            )
        except httpx.HTTPError as e:
            logger.warning(
                "Request to %s failed (attempt %d/%d): %s", url, attempt, attempts, e
            )
        if attempt < attempts:
            time.sleep(retry_delay)

    logger.error("Giving up on %s after %d attempts", url, attempts)
    return None
