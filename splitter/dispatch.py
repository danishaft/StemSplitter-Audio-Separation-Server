"""Compatibility imports for the infrastructure dispatch adapters."""

from .infrastructure.dispatch import (
    DispatchError,
    JobDispatcher,
    RQJobDispatcher,
    ThreadJobDispatcher,
)

__all__ = [
    "DispatchError",
    "JobDispatcher",
    "RQJobDispatcher",
    "ThreadJobDispatcher",
]
