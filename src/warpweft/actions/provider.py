"""``Provider``: a component used only as a dependency, never an entry point.

A provider is infrastructure - a pool, a client, a gateway - wired into other
components through dependency injection. Unlike an action it has no single
``execute`` contract and is never exposed as a tool (``entrypoint = False``),
which is enforced when tools are collected. Its methods may still be
``@invocable`` to get a policy chain when invoked through the container; a
provider with no invocables at all is allowed (reached only through raw
dependency access).
"""

from typing import ClassVar, TypeVar

from pydantic import BaseModel

from warpweft.core.component import AComponent

TSettings = TypeVar("TSettings", bound=BaseModel)


class Provider(AComponent[TSettings, None, None]):
    """Base class for providers. Parameterised as ``Provider[Settings]``."""

    entrypoint: ClassVar[bool] = False
