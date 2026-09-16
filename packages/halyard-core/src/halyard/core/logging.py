"""Logging helpers (opt-in).

Halyard follows the library convention: it emits through named loggers under
the ``halyard`` hierarchy and never configures logging itself (a ``NullHandler``
is attached in ``halyard.core`` so records drop silently until an application
opts in). Turn logging on the usual way::

    logging.getLogger("halyard").setLevel(logging.INFO)

This module offers one convenience: a filter that stamps the ambient
correlation id onto records, so it can appear in your format string. Attach it
to your own handler - halyard does not install it for you.
"""

import logging

from .context import current_correlation_id


class CorrelationIdFilter(logging.Filter):
    """Add ``correlation_id`` to every record (empty string when unset).

    Lets a format string reference ``%(correlation_id)s``::

        handler.addFilter(CorrelationIdFilter())
        handler.setFormatter(logging.Formatter("%(correlation_id)s %(message)s"))
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = current_correlation_id() or ""
        return True
