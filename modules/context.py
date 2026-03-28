# modules/context.py
# Injects ambient context (time, date, season, OS) before every LLM call.
# Registered as a context hook so the LLM always knows when "now" is
# without needing to be asked.

import datetime
import platform
from core.registry import registry


def _get_season(month: int) -> str:
    if month in (12, 1, 2):  return "winter"
    if month in (3, 4, 5):   return "spring"
    if month in (6, 7, 8):   return "summer"
    return "autumn"


class ContextModule:
    name = "context"

    def __init__(self):
        self._llm = None

    def set_llm(self, llm):
        self._llm = llm
        llm.add_context_hook(self._get_context)

    def load(self, config: dict, bus):
        pass

    def _get_context(self, message: str) -> str:
        now = datetime.datetime.now()
        season = _get_season(now.month)
        return (
            f"Current date/time: {now.strftime('%A, %B %d %Y, %I:%M %p')} ({season})\n"
            f"User OS: {platform.system()} {platform.release()}"
        )

    def unload(self):
        pass


registry.register(ContextModule())
