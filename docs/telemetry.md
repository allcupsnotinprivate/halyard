# Telemetry

Warpweft instruments every invocation with OpenTelemetry: one span per call,
child spans per retry attempt, and four metrics. This page is the **stability
contract**: dashboards and alerts are built on these names, so renaming any
span, event, attribute or metric listed here is a breaking change.

## Design rules

- **Not a link. Always outside, always on.** Telemetry wraps the assembled
  chain from the outside (`warpweft.core.telemetry.instrument.instrument`) and
  is not part of the policy chain. A link inside the chain could not see a
  circuit-breaker rejection the call never reached, nor measure total latency
  with retries included. There is no setting to turn it off.
- **Instrumented is not collecting.** The core depends on `opentelemetry-api`
  only. Until the host application configures an SDK (or passes explicit
  providers), every span and metric is a no-op costing microseconds. The
  collection switch belongs to the application, not to component settings.
- **The pipeline is OTel-free.** Links emit through the neutral
  `warpweft.core.observe.Observer` seam found in the context `bag`; only the
  `warpweft.core.telemetry` package imports OpenTelemetry.

## Enabling collection

```python
from warpweft.core.telemetry.instrument import instrument

chain = build_chain([...], store, registry, base)
wrapped = instrument(chain)  # uses OTel globals
wrapped = instrument(
    chain,
    tracer_provider=tp,  # or explicit providers
    meter_provider=mp,
)
```

Configure an SDK the usual OTel way (globals or explicit providers). Without
one, `instrument` is a transparent pass-through. See
`examples/telemetry_console.py` for a runnable console setup.

## Spans

| Span | Name | Attributes |
|---|---|---|
| Invocation | `ctx.operation` | start: `warpweft.operation`, `warpweft.correlation_id`, `warpweft.axis.<name>` per scope pair; end: `warpweft.source`, `warpweft.degraded`, `warpweft.attempts`, `warpweft.cache` (if the cache link ran); on error: `warpweft.error.class` |
| Attempt | `warpweft.attempt` | `warpweft.attempt.number` (numbering starts at 1) |

A successful span keeps status `UNSET` (per OTel spec, instrumentation does
not set `OK`). A failing span gets status `ERROR` and an `exception` event -
including each failed attempt span, not just the invocation.

## Events

| Event | Emitted by | Attributes |
|---|---|---|
| `warpweft.retry.backoff` | retry, right before the backoff sleep (lands on the invocation span) | `warpweft.backoff.delay` (seconds), `warpweft.attempt.number` (upcoming attempt) |
| `warpweft.circuit_breaker.rejected` | circuit breaker, on rejecting a call | `warpweft.circuit_breaker.state` = `open` \| `half_open` |

## Metrics

| Metric | Instrument | Unit | Attributes | Axis values |
|---|---|---|---|---|
| `warpweft.calls` | Counter | `{call}` | `warpweft.operation`, `warpweft.status` (`ok`/`error`), `warpweft.source`, `warpweft.degraded`; `warpweft.error.class` when status=`error` | when status=`error`, or allowlisted |
| `warpweft.call.duration` | Histogram | `s` | `warpweft.operation`, `warpweft.status` | only allowlisted |
| `warpweft.degradations` | Counter | `{call}` | `warpweft.operation` | always |
| `warpweft.circuit_breaker.rejections` | Counter | `{rejection}` | `warpweft.operation`, `warpweft.circuit_breaker.state` | always |

`warpweft.circuit_breaker.rejections` counts every rejection **at the moment
the breaker rejects**, not when an exception escapes: an outer retry may
recover from a rejection, and a degradation stub may swallow it - the counter
still moves.

## Cardinality policy

Axis values as metric attributes are the classic way to explode a time-series
database, so:

- **Error and rejection counters carry axes always** - failures are where the
  per-slice breakdown pays off, and their volume is expected to be low.
- **The duration histogram (and ok-status call counts) never carry axes by
  default.**
- `TelemetryConfig(axis_allowlist=frozenset({...}))` grants full breakdown to
  specific axis *values*: matching pairs are then attached to the histogram
  and ok-status counts too. The allowlist is value-based; a value shared by
  two different axes (e.g. `"prod"`) unlocks both pairs.

## Semantics worth knowing

- **Cancellation** is not an error: a cancelled call closes its span with
  status `UNSET` and records no metric point.
- **Coalesced cache waiters** (single-flight) get their own invocation span
  that shows only the wait; the real work happened under the leader's spans.
- Duration is measured with the framework `Clock` (explicit parameter, else
  `ctx.clock`, else the system clock), so tests never sleep for real.
