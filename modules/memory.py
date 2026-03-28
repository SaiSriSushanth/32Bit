# modules/memory.py
# Persists conversation history to data/history.json across sessions.
# Loads history on startup, saves after every LLM response.
# Keeps the last MAX_EXCHANGES user+assistant pairs to avoid bloating context.

import json
import os
from core.registry import registry
from core.events import bus

HISTORY_FILE = os.path.join("data", "history.json")
MAX_EXCHANGES = 20  # 20 pairs = 40 messages max in context


class MemoryModule:
    name = "memory"

    def __init__(self):
        self._llm = None

    def set_llm(self, llm):
        self._llm = llm

    def load(self, config: dict, bus):
        os.makedirs("data", exist_ok=True)
        self._load_history()
        bus.on("llm_done", self._save_history)
        bus.on("clear_history", self._clear_history)

    def _load_history(self):
        if not self._llm:
            return
        try:
            with open(HISTORY_FILE) as f:
                history = json.load(f)
            self._llm.history = history
            print(f"[memory] Restored {len(history)} messages from previous session")
        except (FileNotFoundError, json.JSONDecodeError):
            pass  # first run or corrupted file — start fresh

    def _save_history(self, full_text: str, **kwargs):
        if not self._llm:
            return
        # Trim to last MAX_EXCHANGES pairs before saving
        history = self._llm.history[-(MAX_EXCHANGES * 2):]
        try:
            with open(HISTORY_FILE, "w") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"[memory] Save failed: {e}")

    def _clear_history(self, **kwargs):
        try:
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
            print("[memory] History file cleared")
        except Exception as e:
            print(f"[memory] Clear failed: {e}")

    def unload(self):
        pass


registry.register(MemoryModule())
