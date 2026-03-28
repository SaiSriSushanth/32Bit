# core/app.py
# AppController — loads config, wires up core systems, injects LLM into modules, starts tray.

import json
import threading
from core.events import bus
from core.llm import LLMClient
from core.tray import TrayIcon
from core.window import ChatWindow
from core.registry import registry

# Import modules so they self-register
import modules.sound
import modules.daily_summary
import modules.greeting
import modules.websearch
import modules.memory
import modules.context
import modules.toolrunner
import modules.filesystem
import modules.voice


class AppController:
    def __init__(self):
        with open("config/settings.json") as f:
            self.config = json.load(f)

        self.llm = LLMClient(self.config)
        self.window = ChatWindow(self.config, self.llm)
        self.tray = TrayIcon(self.config)

        bus.on("app_quit", self._on_quit)
        bus.on("clear_history", lambda **kw: self.llm.reset_history())

        # Inject LLM into any module that declares set_llm()
        for mod in registry._modules.values():
            if hasattr(mod, "set_llm"):
                mod.set_llm(self.llm)

    def start(self):
        registry.load_all(self.config, bus)
        threading.Thread(target=self.tray.run, daemon=True).start()
        self.window.launch()  # blocks — runs Tk mainloop on main thread

    def _on_quit(self, **kwargs):
        registry.unload_all()
