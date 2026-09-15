# Halyard usage examples

- `retry_timeout.py` - a timeout link inside a retry link around a misbehaving call.
- `httpx_manual_pipeline.py` - a real httpx GET wrapped in the pipeline by hand.
- `httpx_handrolled.py` - the same resilient call without the framework, for comparison.
- `component_descriptor.py` - a component, its descriptor and settings JSON Schema.
- `telemetry_console.py` - the instrumented chain printing spans and metrics to the console.
- `composition_container.py` - registering components and driving them through a container.
- `testing_a_component.py` - testing a component with `halyard.core.testing` (drive + scenarios).
- `runtime_app.py` - halyard-runtime: @component, App, env config and a typed proxy.
