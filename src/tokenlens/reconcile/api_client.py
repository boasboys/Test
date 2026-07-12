"""Admin Usage & Cost API client — the ONLY module allowed network I/O.

CLAUDE.md invariant 2: no network calls anywhere except this file.
CLAUDE.md invariant 3: admin key comes from the ANTHROPIC_ADMIN_KEY env var
and must never be printed or logged.

Lands with Issue 8 (docs/issues/issue-08.md).
"""

from __future__ import annotations

import os

ADMIN_KEY_ENV_VAR = "ANTHROPIC_ADMIN_KEY"


class MissingAdminKeyError(Exception):
    """Raised when the admin key env var is unset. Never includes key material."""


def _admin_key() -> str:
    key = os.environ.get(ADMIN_KEY_ENV_VAR)
    if not key:
        raise MissingAdminKeyError(f"set {ADMIN_KEY_ENV_VAR} (read-only Admin API key)")
    return key
