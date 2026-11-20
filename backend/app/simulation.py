"""X-Simulate-Failure header parsing (failover test hook).

Format: comma-separated ``<key_id>=<status>`` pairs, ``*`` meaning every key.
Allowed statuses: 429, 500, 502, 503. Parsing is whitespace- and case-tolerant.

Decision: the hook is a test aid, so it is *lenient* - malformed pairs, unknown
statuses and unknown key ids are ignored (and logged) instead of failing the
request with 422. Specific pairs override ``*``: ``*=429,key_2=500`` makes key_2
fail with 500 and every other key with 429.

The result is a plain dict built per request and passed down the call stack, so
there is no global state: concurrent requests can never see each other's
simulation.
"""

from __future__ import annotations

import logging

from .llm_gateway import SIMULATABLE_STATUSES

logger = logging.getLogger("app.simulation")

HEADER_NAME = "X-Simulate-Failure"


def parse_simulation_header(raw: str | None, key_ids: list[str]) -> dict[str, int] | None:
    """Return None when no simulation is requested, else key_id -> status."""
    if raw is None or not raw.strip():
        return None
    wildcard: int | None = None
    specific: dict[str, int] = {}
    for part in raw.split(","):
        if not part.strip():
            continue
        key, sep, status_raw = part.partition("=")
        key, status_raw = key.strip().lower(), status_raw.strip()
        try:
            status = int(status_raw)
        except ValueError:
            status = None
        if not sep or not key or status not in SIMULATABLE_STATUSES:
            logger.warning("ignoring malformed X-Simulate-Failure pair", extra={"pair": part.strip()[:64]})
            continue
        if key == "*":
            wildcard = status
        elif key in key_ids:
            specific[key] = status
        else:
            logger.warning("ignoring unknown key id in X-Simulate-Failure", extra={"pair": part.strip()[:64]})
    plan = {key_id: wildcard for key_id in key_ids} if wildcard is not None else {}
    plan.update(specific)
    return plan
