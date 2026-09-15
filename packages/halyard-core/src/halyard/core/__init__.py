"""Halyard core: foundation and interceptor pipeline"""

from importlib.metadata import version
import logging

# Library logging: attach a NullHandler to the whole "halyard" hierarchy so
# records are dropped silently until an application configures logging. We never
# set a level or add real handlers - that is the application's job.
logging.getLogger("halyard").addHandler(logging.NullHandler())

__version__ = version("halyard-core")
