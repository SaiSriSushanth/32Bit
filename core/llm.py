# core/llm.py
# Ollama client with streaming support.
# Streams tokens from the local Ollama server and emits them via the event bus.
# Uses /api/chat endpoint for multi-turn conversation history.

import requests
import threading
import json
from core.events import bus

OLLAMA_CHAT_ENDPOINT = "/api/chat"


class LLMClient:
    def __init__(self, config: dict):
        llm_cfg = config["llm"]
        self.base_url = llm_cfg["ollama_url"]
        self.model = llm_cfg["model"]
        self.max_tokens = llm_cfg.get("max_tokens", 512)
        self.temperature = llm_cfg.get("temperature", 0.8)
        self.system_prompt = llm_cfg["system_prompt"].format(
            username=config.get("username", "User")
        )
        self.history: list[dict] = []
        self._context_hooks: list = []

    def add_context_hook(self, fn):
        """Register a callable(message: str) -> str that injects extra context before each LLM call."""
        self._context_hooks.append(fn)

    def chat(self, user_message: str):
        """Send a message and stream the response. Non-blocking."""
        self.history.append({"role": "user", "content": user_message})
        bus.emit("sprite_state_change", state="thinking")
        threading.Thread(target=self._stream, args=(user_message,), daemon=True).start()

    def chat_silent(self, hidden_prompt: str):
        """Send a hidden follow-up prompt (not shown in chat UI). Skips context hooks.
        Used after tool execution so the LLM can summarize results already in history."""
        self.history.append({"role": "user", "content": hidden_prompt})
        bus.emit("sprite_state_change", state="thinking")
        threading.Thread(
            target=self._stream, args=(hidden_prompt,), kwargs={"skip_hooks": True},
            daemon=True
        ).start()

    def _stream(self, user_message: str, skip_hooks: bool = False):
        full_text = ""
        # Gather context from registered hooks (e.g. web search results)
        context_parts = []
        if not skip_hooks:
            for hook in self._context_hooks:
                try:
                    result = hook(user_message)
                    if result:
                        context_parts.append(result)
                except Exception as e:
                    print(f"[llm] context hook error: {e}")

        history = list(self.history)
        if context_parts:
            # Prepend context to the last user message without altering stored history
            context_block = "\n\n".join(context_parts)
            history[-1] = {
                "role": "user",
                "content": (
                    f"[Background context — use this to answer accurately, "
                    f"do not mention it was injected]\n{context_block}\n\n"
                    f"User message: {user_message}"
                )
            }

        messages = [{"role": "system", "content": self.system_prompt}] + history
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "num_predict": self.max_tokens,
                "temperature": self.temperature,
            }
        }
        try:
            response = requests.post(
                f"{self.base_url}{OLLAMA_CHAT_ENDPOINT}",
                json=payload,
                stream=True,
                timeout=60
            )
            response.raise_for_status()
            bus.emit("sprite_state_change", state="speaking")
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line.decode("utf-8"))
                token = data.get("message", {}).get("content", "")
                if token:
                    full_text += token
                    bus.emit("llm_token", token=token)
                if data.get("done", False):
                    break
            self.history.append({"role": "assistant", "content": full_text})
            bus.emit("llm_done", full_text=full_text)
        except requests.exceptions.ConnectionError:
            err = "Ollama isn't running. Start it with: ollama serve"
            bus.emit("llm_done", full_text=f"[{err}]")
        except Exception as e:
            bus.emit("llm_done", full_text=f"[Error: {e}]")
        finally:
            bus.emit("sprite_state_change", state="idle")

    def one_shot(self, prompt: str) -> str:
        """Synchronous single call — used by modules at startup. Does not affect history."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": 128, "temperature": self.temperature},
        }
        try:
            response = requests.post(
                f"{self.base_url}{OLLAMA_CHAT_ENDPOINT}",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except requests.exceptions.ConnectionError:
            return "Ollama isn't running — start it with: ollama serve"
        except Exception as e:
            return f"[Error: {e}]"

    def reset_history(self):
        self.history = []
