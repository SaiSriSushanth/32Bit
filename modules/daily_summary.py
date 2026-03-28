# modules/daily_summary.py
# Posts today's date and day of week into chat on first window open.
# Extend this module to add weather, calendar events, or task lists.

import datetime
from core.registry import registry
from core.events import bus


class DailySummaryModule:
    name = "daily_summary"

    def __init__(self):
        self._fired = False

    def load(self, config: dict, bus):
        bus.on("window_open", self._on_window_open)

    def _on_window_open(self, **kwargs):
        if self._fired:
            return
        self._fired = True
        now = datetime.datetime.now()
        date_str = now.strftime("%A, %B %d %Y")
        bus.emit("push_chat_message", sender="Buddy", text=f"Today is {date_str}.")

    def unload(self):
        pass

    # --- Future extension points ---
    # def _fetch_weather(self):   GET https://wttr.in/?format=3  (no API key)
    # def _fetch_calendar(self):  Google Calendar API or local .ics file
    # def _fetch_tasks(self):     Local tasks.json or Todoist API


registry.register(DailySummaryModule())
