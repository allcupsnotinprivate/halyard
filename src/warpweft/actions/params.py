"""``ActionParams``: base for an action's input model.

A thin, explicit base over ``pydantic.BaseModel`` for symmetry and readable
signatures. Any ``BaseModel`` works as an action's params type - subclassing
``ActionParams`` is a convention, not a requirement.
"""

from pydantic import BaseModel


class ActionParams(BaseModel):
    """Base class for the single model an action's ``execute`` takes."""
