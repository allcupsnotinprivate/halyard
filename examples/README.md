# Halyard usage examples

- `retry_timeout.py` - a timeout link inside a retry link around a misbehaving call.
- `httpx_manual_pipeline.py` - a real httpx GET wrapped in the pipeline by hand.
- `httpx_handrolled.py` - the same resilient call without the framework, for comparison.
- `component_descriptor.py` - a component, its descriptor and settings JSON Schema.
- `telemetry_console.py` - the instrumented chain printing spans and metrics to the console.
