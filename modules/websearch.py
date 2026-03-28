# modules/websearch.py
# Injects real-time DuckDuckGo search results as context before each LLM call.
# Uses duckduckgo-search (pip install duckduckgo-search) — no API key required.
#
# How it works:
#   1. Registers a context hook on the LLM client
#   2. Before each Ollama call, reformulates the query using LLM + history
#   3. Searches DDG, then scrapes the top result via Jina Reader for full content
#   4. Injects results as context so Buddy can answer with current info
#
# Skips search for short/conversational messages to avoid unnecessary latency.

import json
import requests as _requests
from core.registry import registry
from core.events import bus

_JINA_BASE = "https://r.jina.ai/"
_JINA_SNIPPET_CHARS = 1500  # truncate scraped page to keep context reasonable
_JINA_TIMEOUT = 8

# Keywords that suggest the user wants real-time info
_SEARCH_TRIGGERS = {
    "news", "latest", "current", "today", "now", "recent", "breaking",
    "price", "stock", "score", "weather", "who is", "what is", "when did",
    "when is", "how much", "update", "new", "released", "happened",
    "did", "does", "is there", "has", "have", "discontinued", "discontinue",
    "still", "available", "find", "look up", "check", "tell me about",
    "what happened", "any news", "status", "out", "launched",
}

# Navigation intent — these should be handled by the OPEN tool, not websearch
_NAV_TRIGGERS = {
    "open", "go to", "visit", "navigate", "show me", "launch", "search for",
    "search on", "search in", "search youtube", "find on", "look up on",
}

_MIN_WORDS_FOR_SEARCH = 2


def _should_search(message: str) -> bool:
    lower = message.lower()
    words = lower.split()
    if len(words) < _MIN_WORDS_FOR_SEARCH:
        return False
    # Skip search if this is a navigation request — let toolrunner handle it.
    # Pad with spaces so "open" doesn't match inside "openai".
    padded = f" {lower} "
    if any(f" {nav} " in padded for nav in _NAV_TRIGGERS):
        return False
    return any(trigger in lower for trigger in _SEARCH_TRIGGERS)


class WebSearchModule:
    name = "websearch"

    def __init__(self):
        self._llm = None
        self._max_results = 3
        self._force_search = False

    def set_llm(self, llm):
        self._llm = llm
        llm.add_context_hook(self._fetch_context)

    def load(self, config: dict, bus):
        mod_cfg = config.get("modules", {}).get("websearch", {})
        self._max_results = mod_cfg.get("max_results", 3)
        bus.on("websearch_force", self._on_toggle)

    def _on_toggle(self, enabled: bool, **kwargs):
        self._force_search = enabled
        state = "ON" if enabled else "OFF"
        print(f"[websearch] Manual override: {state}")

    def _reformulate_query(self, message: str) -> str:
        """Ask the LLM to rewrite the user's message into a concise web search query.
        Uses a direct Ollama call with a neutral system prompt so the model cannot
        apply tools like OPEN[] — it only outputs plain search keywords."""
        try:
            history = self._llm.history[-6:]
            history_text = ""
            for turn in history[:-1]:
                role = "User" if turn["role"] == "user" else "Assistant"
                history_text += f"{role}: {turn['content']}\n"

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a search query generator. "
                        "Given a conversation, output ONLY a short plain-text web search query (5 words or fewer). "
                        "No URLs. No brackets. No OPEN[]. No special syntax. Just plain keywords."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Conversation:\n{history_text}"
                        f"User: {message}\n\n"
                        "Search query:"
                    )
                }
            ]
            payload = {
                "model": self._llm.model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": 20, "temperature": 0.2},
            }
            resp = _requests.post(
                f"{self._llm.base_url}/api/chat",
                json=payload,
                timeout=15
            )
            resp.raise_for_status()
            query = resp.json()["message"]["content"].strip().strip('"').strip("'")
            # Sanity check — reject anything that looks like a URL or tool call
            if not query or len(query) > 120 or "OPEN[" in query or "http" in query:
                return message
            print(f"[websearch] Reformulated: {message!r} → {query!r}")
            return query
        except Exception as e:
            print(f"[websearch] query reformulation failed: {e}")
            return message

    def _scrape_top_result(self, url: str) -> str:
        """Fetch a URL via Jina Reader and return a truncated plain-text snippet."""
        try:
            resp = _requests.get(
                _JINA_BASE + url,
                headers={"Accept": "text/plain"},
                timeout=_JINA_TIMEOUT
            )
            resp.raise_for_status()
            text = resp.text.strip()
            if len(text) > _JINA_SNIPPET_CHARS:
                text = text[:_JINA_SNIPPET_CHARS] + "…"
            print(f"[websearch] Scraped {len(text)} chars from {url}")
            return text
        except Exception as e:
            print(f"[websearch] Jina scrape failed for {url}: {e}")
            return ""

    def _fetch_context(self, message: str) -> str:
        if not self._force_search and not _should_search(message):
            return ""
        try:
            from ddgs import DDGS
            query = self._reformulate_query(message)
            results = DDGS().text(query, max_results=self._max_results)
            if not results:
                return ""

            lines = []
            for r in results:
                title = r.get("title", "")
                body  = r.get("body", "")
                href  = r.get("href", "")
                lines.append(f"- {title}: {body} ({href})")

            # Scrape the top result for full content
            top_url = results[0].get("href", "")
            scraped = self._scrape_top_result(top_url) if top_url else ""

            print(f"[websearch] Injecting {len(results)} results for query: {query!r}")

            parts = ["Web search results:\n" + "\n".join(lines)]
            if scraped:
                parts.append(f"Full content from top result ({top_url}):\n{scraped}")
            return "\n\n".join(parts)
        except ImportError:
            print("[websearch] ddgs not installed. Run: pip install ddgs")
            return ""
        except Exception as e:
            print(f"[websearch] search failed: {e}")
            return ""

    def unload(self):
        pass


registry.register(WebSearchModule())
