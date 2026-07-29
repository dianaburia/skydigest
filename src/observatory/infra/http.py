"""Shared HTTP client helpers for collector modules.

Consolidates request timeouts, error logging, and JSON parsing so each
collector focuses on domain logic instead of repeating boilerplate.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """GET a URL and return the parsed JSON body.

    Returns the parsed JSON on success, or None on network or HTTP error.
    All errors are logged with the request URL for debugging.
    """
    try:
        response = httpx.get(url, params=params, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP %s from %s: %s",
            e.response.status_code,
            url,
            e.response.text[:200],
        )
        return None
    except httpx.HTTPError as e:
        logger.error("Request to %s failed: %s", url, e)
        return None

    return response.json()
