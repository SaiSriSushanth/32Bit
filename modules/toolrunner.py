# modules/toolrunner.py
# Parses tool calls from LLM responses and executes them.
#
# Supported syntax (LLM writes these anywhere in its response):
#   CALC[expression]   — evaluates a math expression, shows result
#   OPEN[url]          — opens the URL in the default browser
#
# Results are pushed as a [tool] message in the chat after the LLM responds.

import re
from core.registry import registry
from core.events import bus
from core import tools as tool_lib

_OPEN_RE = re.compile(r'OPEN\[([^\]]+)\]')


class ToolRunnerModule:
    name = "toolrunner"

    def load(self, config: dict, bus):
        bus.on("llm_done", self._on_llm_done)

    def _on_llm_done(self, full_text: str, **kwargs):
        results = []

        for match in _OPEN_RE.finditer(full_text):
            result = tool_lib.run_open(match.group(1))
            results.append(result)
            print(f"[tools] OPEN: {match.group(1)}")

        if results:
            bus.emit("push_chat_message", sender="[tool]", text="\n".join(results))

    def unload(self):
        pass


registry.register(ToolRunnerModule())
