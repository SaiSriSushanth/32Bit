# Adding a New Module to Buddy

A module is a Python class with:

| Method / Attribute  | Required | Description                                    |
|---------------------|----------|------------------------------------------------|
| `name: str`         | yes      | Unique key — must match entry in settings.json |
| `load(config, bus)` | yes      | Called at startup. Subscribe to events here.   |
| `unload()`          | no       | Called on app quit. Clean up resources.        |
| `set_llm(llm)`      | no       | Add this if your module needs to call Ollama.  |

## Steps

1. Create `modules/your_module.py`
2. Define your class (see template below)
3. At the bottom: `registry.register(YourModule())`
4. In `core/app.py`, add: `import modules.your_module`
5. In `config/settings.json > modules`, add: `"your_module": { "enabled": true }`

## Module Template

```python
from core.registry import registry
from core.events import bus

class MyModule:
    name = "my_module"

    def load(self, config: dict, bus):
        self.config = config
        bus.on("window_open", self._on_open)

    def _on_open(self, **kwargs):
        bus.emit("push_chat_message", sender="Buddy", text="Hello from my module!")

    def unload(self):
        pass

registry.register(MyModule())
```

## Available Events

| Event                 | Payload              | When                             |
|-----------------------|----------------------|----------------------------------|
| `window_open`         | —                    | Chat window opens                |
| `window_close`        | —                    | Chat window closes               |
| `user_message`        | `text: str`          | User sends a message             |
| `llm_token`           | `token: str`         | Each streaming token from Ollama |
| `llm_done`            | `full_text: str`     | Ollama finishes responding       |
| `sprite_state_change` | `state: str`         | Change sprite animation state    |
| `play_sound`          | `sound_name: str`    | Trigger a named sound            |
| `push_chat_message`   | `sender, text: str`  | Push a message into chat         |
| `clear_history`       | —                    | Conversation history cleared     |

## Future Module Ideas

- `modules/voice.py`     — speech-to-text input via `faster-whisper`
- `modules/reminders.py` — scheduled pop-up reminders stored in JSON
- `modules/calendar.py`  — Google Calendar or Outlook integration
- `modules/weather.py`   — morning weather from wttr.in (no API key)
- `modules/clipboard.py` — watch clipboard, offer to summarise/translate
- `modules/pomodoro.py`  — focus timer with sprite state changes
- `modules/news.py`      — morning headlines via RSS feed
- `modules/hotkey.py`    — global hotkey to open/hide Buddy
