"""Degradation link: substitute a stub when the component is unavailable.

Sliced per instance. In the pipeline this link is only wired for components
whose criticality is ``optional`` - a required component must fail loudly, not
degrade. That gating happens where the pipeline meets components; the link
itself just needs a stub to fall back to.

Degradation triggers only on *unavailability* - transient failures (the service
is down, retries exhausted, breaker open, deadline gone). A permanent error
(a bad request, a validation failure) is a real error and is re-raised: masking
it with a stub would hide a bug.

The result is never substituted silently: a stubbed outcome carries
``source = "stub"`` and ``degraded = True``, and the substitution is counted for
metrics (not only reflected in health) and marked in ``ctx.bag``.
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from halyard.core.axes import EMPTY_SCOPE, ScopeKey, ScopeSpec
from halyard.core.context import InvocationContext
from halyard.core.errors import DefaultErrorClassifier, ErrorClass, ErrorClassifier
from halyard.core.observe import FACT_DEGRADED
from halyard.core.outcome import Outcome
from halyard.core.pipeline.interceptor import Interceptor, Next
from halyard.core.unit import Identity

#: Produces the fallback value for a degraded call. Receives the context so the
#: stub can depend on the operation or arguments.
StubProvider = Callable[[InvocationContext], Any]


class DegradationSettings(BaseModel):
    """Settings of the degradation link."""

    degrade_on: ErrorClass = Field(
        default=ErrorClass.TRANSIENT,
        description="Error class treated as unavailability and replaced by the stub",
    )


class DegradationInterceptor:
    """Falls back to a stub on unavailability, counting each substitution."""

    settings_model: type[BaseModel] | None = DegradationSettings

    def __init__(
        self,
        settings: DegradationSettings,
        stub: StubProvider,
        classifier: ErrorClassifier | None = None,
        identity: Identity | None = None,
    ) -> None:
        self.identity = identity or Identity.of("degradation")
        self._settings = settings
        self._stub = stub
        self._classifier = classifier or DefaultErrorClassifier()
        self._degraded_count = 0

    @property
    def degraded_count(self) -> int:
        """How many calls this instance has degraded (for metrics)."""
        return self._degraded_count

    async def call(self, next: Next, ctx: InvocationContext) -> Outcome[object]:
        try:
            return await next(ctx)
        except Exception as exc:
            if self._classifier.classify(exc) != self._settings.degrade_on:
                raise  # not unavailability: a real error must surface
            self._degraded_count += 1
            ctx.bag[FACT_DEGRADED] = True
            return Outcome(value=self._stub(ctx), source="stub", degraded=True)


class DegradationFactory:
    """Factory of the degradation link. One instance per instance slice."""

    settings_model: type[BaseModel] | None = DegradationSettings
    #: Instance slice. The endpoint axis is not involved; the empty spec is a
    #: placeholder until the pipeline is wired to instances.
    state_scope: ScopeSpec = EMPTY_SCOPE

    def __init__(
        self,
        settings: DegradationSettings,
        stub: StubProvider,
        classifier: ErrorClassifier | None = None,
    ) -> None:
        self.identity = Identity.of("degradation")
        self._settings = settings
        self._stub = stub
        self._classifier = classifier

    def create(self, key: ScopeKey) -> Interceptor:
        return DegradationInterceptor(self._settings, self._stub, self._classifier, identity=self.identity)
