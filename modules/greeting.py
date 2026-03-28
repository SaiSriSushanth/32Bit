# modules/greeting.py
# Generates a personalised Ollama greeting on the first window open.
# Uses one_shot() so it does not pollute the main conversation history.

import threading
import datetime
from core.registry import registry
from core.events import bus


class GreetingModule:
    name = "greeting"

    def __init__(self):
        self._llm = None
        self._greeted = False

    def set_llm(self, llm):
        self._llm = llm

    def load(self, config: dict, bus):
        self.config = config
        bus.on("window_open", self._on_window_open)

    def _on_window_open(self, **kwargs):
        if self._greeted or not self._llm:
            return
        self._greeted = True
        threading.Thread(target=self._generate, daemon=True).start()

    def _generate(self):
        hour = datetime.datetime.now().hour
        time_of_day = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
        username = self.config.get("username", "there")
        prompt = (
            f"Say a short, friendly good {time_of_day} greeting to {username}. "
            f"One sentence only. Warm and slightly playful. No emojis."
        )
        bus.emit("sprite_state_change", state="thinking")
        greeting = self._llm.one_shot(prompt)
        bus.emit("push_chat_message", sender="Buddy", text=greeting)
        bus.emit("sprite_state_change", state="idle")

    def unload(self):
        pass


registry.register(GreetingModule())
