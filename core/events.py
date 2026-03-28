# core/events.py
# Simple synchronous event bus for inter-module communication.
# Usage:
#   bus.on("startup_complete", my_callback)
#   bus.emit("startup_complete", payload={})

from collections import defaultdict
from typing import Callable


class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, callback: Callable):
        """Register a listener for an event."""
        self._listeners[event].append(callback)

    def emit(self, event: str, **kwargs):
        """Fire an event, calling all registered listeners."""
        for cb in self._listeners.get(event, []):
            cb(**kwargs)


bus = EventBus()
