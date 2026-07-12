"""Admin Usage & Cost API client — the ONLY module allowed network I/O.

CLAUDE.md invariant 2: no network calls anywhere except this file.
CLAUDE.md invariant 3: the admin key comes from the ANTHROPIC_ADMIN_KEY env
var and must never be printed or logged — error messages carry no key
material, and the fetcher is injectable so tests never touch the network.

Read-only: this module only GETs the organization cost report.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections.abc import Callable

API_BASE = "https://api.anthropic.com"
COST_REPORT_PATH = "/v1/organizations/cost_report"
ANTHROPIC_VERSION = "2023-06-01"
ADMIN_KEY_ENV_VAR = "ANTHROPIC_ADMIN_KEY"

# A fetcher takes (url, headers) and returns the decoded JSON body.
Fetcher = Callable[[str, dict[str, str]], dict]


class MissingAdminKeyError(Exception):
    """Raised when the admin key env var is unset. Never includes key material."""


class ApiError(Exception):
    """Raised when the API returns an unusable response. Never includes the key."""


def _admin_key() -> str:
    key = os.environ.get(ADMIN_KEY_ENV_VAR)
    if not key:
        raise MissingAdminKeyError(
            f"set {ADMIN_KEY_ENV_VAR} to a read-only Admin API key to reconcile"
        )
    return key


def _default_fetcher(url: str, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict):
        raise ApiError("cost report response was not a JSON object")
    return body


def fetch_cost_buckets(
    starting_at: str,
    ending_at: str,
    fetcher: Fetcher | None = None,
) -> list[dict]:
    """Fetch daily cost-report buckets for [starting_at, ending_at), UTC.

    Timestamps are RFC3339 (e.g. 2026-07-01T00:00:00Z). Follows pagination
    until has_more is false. Returns the raw bucket dicts; normalization
    lives in tieout.py.
    """
    key = _admin_key()
    fetch = fetcher or _default_fetcher
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}

    buckets: list[dict] = []
    page: str | None = None
    while True:
        params: dict[str, str] = {
            "starting_at": starting_at,
            "ending_at": ending_at,
            "bucket_width": "1d",
        }
        if page:
            params["page"] = page
        url = f"{API_BASE}{COST_REPORT_PATH}?{urllib.parse.urlencode(params)}"
        body = fetch(url, headers)
        data = body.get("data")
        if not isinstance(data, list):
            raise ApiError("cost report response missing 'data' list")
        buckets.extend(entry for entry in data if isinstance(entry, dict))
        if not body.get("has_more"):
            return buckets
        page = body.get("next_page")
        if not page:
            raise ApiError("cost report claims has_more but gave no next_page")
