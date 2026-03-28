# modules/filesystem.py
# Gives Buddy read-only access to the local filesystem.
#
# Works as a pre-response context hook (like websearch) — not a post-response parser.
# When the user's message looks like a filesystem query:
#   1. A focused LLM call extracts the operation and path/pattern
#   2. The tool runs and the result is injected as context before the main LLM call
#   3. The main LLM just answers from the provided context — no tool syntax needed
#
# Supported operations (detected automatically):
#   LIST  — list a directory
#   SEARCH — find files by name/pattern
#   READ  — read file contents

import requests as _requests
from core.registry import registry
from core.events import bus
from core import tools as tool_lib

_FILESYSTEM_TRIGGERS = {
    "list", "what's in", "whats in", "what is in",
    "inside", "contents of", "files in", "folders in",
    "find", "search for", "look for", "locate", "where is",
    "read", "open the file", "show the file",
    "in my downloads", "in my documents", "in my desktop",
    "in my pictures", "in my videos", "in my music",
    "my downloads", "my documents", "my desktop",
    "find files", "find all files", "find a file", "find the file",
    "list files", "list my files",
    "search my files", "search my computer", "on my computer",
    "directory", "folder", "folders", "subfolder",
    "find folder", "find directory",
    ".txt", ".py", ".json", ".md", ".csv", ".exe", ".zip", ".pdf",
    ".docx", ".xlsx", ".html", ".js", ".ts", ".yaml", ".yml", ".ini", ".cfg", ".log",
}

# Navigation intent — should not trigger filesystem
_NAV_TRIGGERS = {"open", "go to", "visit", "navigate", "launch"}


def _is_filesystem_query(message: str) -> bool:
    lower = message.lower()
    padded = f" {lower} "
    if any(f" {nav} " in padded for nav in _NAV_TRIGGERS):
        return False
    return any(trigger in lower for trigger in _FILESYSTEM_TRIGGERS)


class FilesystemModule:
    name = "filesystem"

    def __init__(self):
        self._llm = None

    def set_llm(self, llm):
        self._llm = llm
        llm.add_context_hook(self._fetch_context)

    def load(self, config: dict, bus):
        pass

    def _extract_operation(self, message: str):
        """Single focused LLM call to extract operation + argument.
        Returns (op, arg) where op is LIST/SEARCH/READ, or None."""
        try:
            # Include last assistant message so the model can pick up full paths
            # from previous results (e.g. reading a file listed moments ago)
            last_assistant = ""
            if self._llm and self._llm.history:
                for turn in reversed(self._llm.history[-4:]):
                    if turn["role"] == "assistant":
                        last_assistant = turn["content"][:600]
                        break

            context_note = f"Previous assistant message:\n{last_assistant}\n\n" if last_assistant else ""

            messages = [
                {
                    "role": "system",
                    "content": (
                        "Extract the filesystem operation from the user message. "
                        "Output ONLY one line in exactly this format:\n"
                        "LIST:<path_or_alias>\n"
                        "SEARCH:<name_or_pattern>\n"
                        "READ:<file_path>\n"
                        "NONE\n\n"
                        "Rules:\n"
                        "- LIST for directory listing. Use alias (Downloads, Desktop, Documents) or full path.\n"
                        "- SEARCH when looking for a file/folder by name. Use 'pattern in dir' if a location is mentioned.\n"
                        "- READ for reading file contents. Use full path from context if available.\n"
                        "- NONE if this is not a filesystem request.\n\n"
                        "Examples:\n"
                        "list my downloads → LIST:Downloads\n"
                        "what's in C:/Projects → LIST:C:/Projects\n"
                        "what's inside the Hexaware folder → LIST:Hexaware\n"
                        "find AiLeadsPOC → SEARCH:AiLeadsPOC\n"
                        "find all PDFs in Downloads → SEARCH:*.pdf in Downloads\n"
                        "read requirements.txt → READ:requirements.txt\n"
                        "what's the weather → NONE"
                    )
                },
                {
                    "role": "user",
                    "content": f"{context_note}User message: {message}"
                }
            ]
            payload = {
                "model": self._llm.model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": 30, "temperature": 0.1},
            }
            resp = _requests.post(
                f"{self._llm.base_url}/api/chat",
                json=payload,
                timeout=15
            )
            resp.raise_for_status()
            answer = resp.json()["message"]["content"].strip()

            for op in ("LIST", "SEARCH", "READ"):
                if answer.upper().startswith(op + ":"):
                    arg = answer[len(op) + 1:].strip()
                    if arg:
                        print(f"[filesystem] Extracted: {op}:{arg!r} for {message!r}")
                        return op, arg

            print(f"[filesystem] No operation extracted for: {message!r}")
            return None
        except Exception as e:
            print(f"[filesystem] extraction failed: {e}")
            return None

    def _fetch_context(self, message: str) -> str:
        if not _is_filesystem_query(message):
            return ""

        result = self._extract_operation(message)
        if result is None:
            return ""

        op, arg = result

        if op == "LIST":
            output = tool_lib.run_file_list(arg)
        elif op == "SEARCH":
            output = tool_lib.run_file_search(arg)
        elif op == "READ":
            output = tool_lib.run_file_read(arg)
        else:
            return ""

        return f"Filesystem result ({op} {arg}):\n{output}"

    def unload(self):
        pass


registry.register(FilesystemModule())
