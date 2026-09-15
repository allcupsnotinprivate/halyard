"""Baseline: the SAME resilient GET, hand-rolled, no framework.

Kept next to ``httpx_manual_pipeline.py`` only to count boilerplate honestly:
this is the resilience glue a plain integration carries when it wants the same
guarantees (retry on transient, full-jitter backoff, per-attempt timeout,
overall-deadline priority). It is not wired into anything.

Everything between the BEGIN/END markers is resilience boilerplate that the
pipeline version replaces with declarative settings + one reusable classifier.
"""

from __future__ import annotations

import random
import time
from typing import Any

import anyio
import httpx

BASE = "https://httpbin.org"


async def resilient_get(
    client: httpx.AsyncClient,
    path: str,
    correlation_id: str,
    *,
    attempts: int,
    base_delay: float,
    max_delay: float,
    per_attempt: float,
    deadline: float,  # absolute, time.monotonic()
) -> dict[str, Any]:
    # --- BEGIN resilience boilerplate --------------------------------------
    rng = random.Random()  # noqa: S311 - jitter only needs to desynchronize clients
    for attempt in range(1, attempts + 1):
        now = time.monotonic()
        if now >= deadline:
            raise TimeoutError(f"deadline exhausted before attempt {attempt}")
        remaining = deadline - now
        limit = min(per_attempt, remaining)
        try:
            with anyio.fail_after(limit):
                resp = await client.get(
                    f"{BASE}{path}",
                    headers={"X-Correlation-Id": correlation_id},
                    timeout=limit,
                )
            resp.raise_for_status()
        except (httpx.TimeoutException, TimeoutError, httpx.TransportError):
            transient = True
        except httpx.HTTPStatusError as exc:
            transient = exc.response.status_code >= 500
            if not transient:
                raise
        else:
            return {"status": resp.status_code, "len": len(resp.content)}

        if attempt == attempts:
            raise TimeoutError(f"all {attempts} attempts failed")
        exponent = attempt - 1
        delay = min(base_delay * (2.0**exponent), max_delay)
        delay = rng.uniform(0.0, delay)  # full jitter
        remaining = deadline - time.monotonic()
        if delay >= remaining:
            raise TimeoutError("backoff would exceed the remaining budget")
        await anyio.sleep(delay)
    raise AssertionError("unreachable")
    # --- END resilience boilerplate ----------------------------------------


async def main() -> None:
    async with httpx.AsyncClient() as client:
        result = await resilient_get(
            client,
            "/get",
            "handrolled-1",
            attempts=3,
            base_delay=0.1,
            max_delay=1.0,
            per_attempt=5.0,
            deadline=time.monotonic() + 10.0,
        )
        print(result)


if __name__ == "__main__":
    anyio.run(main)
