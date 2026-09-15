"""Semantic conventions: the fixed telemetry names contract.

Every span, event, attribute and metric name lives here (link-emitted names
are re-exported from ``halyard.core.observe``). These names are a public
contract - dashboards and alerts are built on them, so renaming any of them
is a breaking change. See ``docs/telemetry.md``.

This module is deliberately OTel-import-free: pure constants.
"""

from typing import Final

from halyard.core.observe import (
    ATTR_ATTEMPT_NUMBER,
    ATTR_BACKOFF_DELAY,
    ATTR_BREAKER_STATE,
    EVENT_BREAKER_REJECTED,
    EVENT_RETRY_BACKOFF,
    FACT_CACHE,
    FACT_DEGRADED,
    SPAN_ATTEMPT,
)

__all__ = [
    "ATTR_ATTEMPTS",
    "ATTR_ATTEMPT_NUMBER",
    "ATTR_BACKOFF_DELAY",
    "ATTR_BREAKER_STATE",
    "ATTR_CACHE",
    "ATTR_CORRELATION_ID",
    "ATTR_DEGRADED",
    "ATTR_ERROR_CLASS",
    "ATTR_OPERATION",
    "ATTR_SOURCE",
    "ATTR_STATUS",
    "AXIS_ATTR_PREFIX",
    "EVENT_BREAKER_REJECTED",
    "EVENT_RETRY_BACKOFF",
    "FACT_CACHE",
    "FACT_DEGRADED",
    "INSTRUMENTATION_NAME",
    "METRIC_BREAKER_REJECTIONS",
    "METRIC_CALLS",
    "METRIC_DEGRADATIONS",
    "METRIC_DURATION",
    "SPAN_ATTEMPT",
    "STATUS_ERROR",
    "STATUS_OK",
    "UNIT_CALLS",
    "UNIT_REJECTIONS",
    "UNIT_SECONDS",
]

#: Tracer and meter instrumentation name.
INSTRUMENTATION_NAME: Final = "halyard"

# --- span / metric attribute keys -------------------------------------------
ATTR_OPERATION: Final = "halyard.operation"
ATTR_CORRELATION_ID: Final = "halyard.correlation_id"
ATTR_SOURCE: Final = "halyard.source"
ATTR_DEGRADED: Final = "halyard.degraded"
ATTR_ATTEMPTS: Final = "halyard.attempts"
ATTR_STATUS: Final = "halyard.status"
ATTR_ERROR_CLASS: Final = "halyard.error.class"
ATTR_CACHE: Final = "halyard.cache"
#: Axis attributes are ``halyard.axis.<axis name>`` = axis value.
AXIS_ATTR_PREFIX: Final = "halyard.axis."

#: Values of :data:`ATTR_STATUS`.
STATUS_OK: Final = "ok"
STATUS_ERROR: Final = "error"

# --- metric names and units --------------------------------------------------
METRIC_CALLS: Final = "halyard.calls"
METRIC_DURATION: Final = "halyard.call.duration"
METRIC_DEGRADATIONS: Final = "halyard.degradations"
METRIC_BREAKER_REJECTIONS: Final = "halyard.circuit_breaker.rejections"

UNIT_CALLS: Final = "{call}"
UNIT_SECONDS: Final = "s"
UNIT_REJECTIONS: Final = "{rejection}"
