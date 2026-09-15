"""Private module: autodiscovery must skip it."""

raise RuntimeError("private modules must not be imported by autodiscover")
