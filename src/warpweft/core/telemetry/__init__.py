"""Telemetry: the always-on instrumentation wrapper around a pipeline.

Not a link. The wrapper sits outside the chain (a link inside could not see a
circuit-breaker rejection the call never reached, nor measure total latency
with retries) and is meant to be applied unconditionally. Collection is the
host application's choice: with only ``opentelemetry-api`` installed and no
SDK configured, everything is a no-op.

Import `warpweft.core.telemetry.instrument.instrument` to wrap a chain;
``conventions`` holds the fixed names contract.
"""
