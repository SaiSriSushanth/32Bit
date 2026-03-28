# modules/filesystem.py
# Gives Buddy read-only access to the local filesystem.
#
# The LLM writes tool calls anywhere in its response:
#   FILE_READ[C:/path/to/file.txt]       — read file contents
#   FILE_LIST[Documents]                 — list a directory (alias or full path)
#   FILE_SEARCH[*.pdf in Downloads]      — find files by name/pattern
#
# Results are pushed to the chat as a [file] message AND injected into LLM
# history so Buddy can reference the content in follow-up responses.

import re
from core.registry import registry
from core.events import bus
from core import tools as tool_lib

_READ_RE   = re.compile(r'FILE_READ\[([^\]]+)\]')
_LIST_RE   = re.compile(r'FILE_LIST\[([^\]]+)\]')
_SEARCH_RE = re.compile(r'FILE_SEARCH\[([^\]]+)\]')


class FilesystemModule:
    name = "filesystem"

    def __init__(self):
        self._llm = None

    def set_llm(self, llm):
        self._llm = llm

    def load(self, config: dict, bus):
        bus.on("llm_done", self._on_llm_done)

    def _on_llm_done(self, full_text: str, **kwargs):
        results = []

        for match in _READ_RE.finditer(full_text):
            arg = match.group(1).strip()
            result = tool_lib.run_file_read(arg)
            results.append(("FILE_READ", arg, result))
            print(f"[filesystem] READ: {arg}")

        for match in _LIST_RE.finditer(full_text):
            arg = match.group(1).strip()
            result = tool_lib.run_file_list(arg)
            results.append(("FILE_LIST", arg, result))
            print(f"[filesystem] LIST: {arg}")

        for match in _SEARCH_RE.finditer(full_text):
            arg = match.group(1).strip()
            result = tool_lib.run_file_search(arg)
            results.append(("FILE_SEARCH", arg, result))
            print(f"[filesystem] SEARCH: {arg}")

        if not results:
            return

        # Trim the assistant bubble to only what came before the first tool call.
        # Everything after is hallucinated content the model added before seeing real results.
        first_tool = re.search(r'FILE_(READ|LIST|SEARCH)\[', full_text)
        pre_tool_text = full_text[:first_tool.start()].strip() if first_tool else ""
        bus.emit("replace_last_bubble", text=pre_tool_text)

        # Also trim the stored assistant history entry to avoid polluting future context
        if self._llm and self._llm.history and self._llm.history[-1]["role"] == "assistant":
            self._llm.history[-1]["content"] = pre_tool_text

        # Display format uses >>> to clearly differ from FILE_*(tool call) syntax
        # so the model doesn't copy the result format as if it were a tool call
        display = "\n\n".join(
            f">>> {op}({arg})\n{res}" for op, arg, res in results
        )
        bus.emit("push_chat_message", sender="[file]", text=display)

        if self._llm:
            self._llm.history.append({
                "role": "user",
                "content": (
                    "[File operation results — use these to answer the user's question]\n"
                    + display
                )
            })
            bus.emit(
                "tool_followup",
                prompt="Based ONLY on the file operation results just provided above, answer the user's question concisely. Do not add information from memory or prior context."
            )

    def unload(self):
        pass


registry.register(FilesystemModule())
