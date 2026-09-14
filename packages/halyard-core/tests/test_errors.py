"""Error taxonomy and default classification."""

import pytest

from halyard.core.errors import (
    AttemptTimeout,
    ConfigurationError,
    DeadlineExceeded,
    DefaultErrorClassifier,
    ErrorClass,
    FrameworkError,
    PermanentError,
    TransientError,
)

pytestmark = pytest.mark.unit

classifier = DefaultErrorClassifier()


def test_hierarchy() -> None:
    assert issubclass(TransientError, FrameworkError)
    assert issubclass(PermanentError, FrameworkError)
    assert issubclass(ConfigurationError, PermanentError)
    assert issubclass(DeadlineExceeded, TransientError)
    assert issubclass(AttemptTimeout, TransientError)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (TransientError("boom"), ErrorClass.TRANSIENT),
        (DeadlineExceeded("late"), ErrorClass.TRANSIENT),
        (AttemptTimeout("slow"), ErrorClass.TRANSIENT),
        (PermanentError("no"), ErrorClass.PERMANENT),
        (ConfigurationError("bad"), ErrorClass.PERMANENT),
        (FrameworkError("base"), ErrorClass.PERMANENT),
    ],
)
def test_classify_by_taxonomy(exc: BaseException, expected: ErrorClass) -> None:
    assert classifier.classify(exc) == expected


def test_unknown_exception_is_permanent() -> None:
    """Anything unfamiliar is permanent: retrying bugs in code is worse than not retrying."""
    assert classifier.classify(ValueError("bug")) == ErrorClass.PERMANENT
    assert classifier.classify(TimeoutError("looks transient but is not ours")) == ErrorClass.PERMANENT


def test_custom_classifier_can_widen() -> None:
    class LenientClassifier:
        def classify(self, exc: BaseException) -> ErrorClass:
            if isinstance(exc, ConnectionError):
                return ErrorClass.TRANSIENT
            return classifier.classify(exc)

    lenient = LenientClassifier()
    assert lenient.classify(ConnectionResetError()) == ErrorClass.TRANSIENT
    assert lenient.classify(ValueError()) == ErrorClass.PERMANENT
