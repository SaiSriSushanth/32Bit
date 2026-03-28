# core/tools.py
# Safe tool implementations used by modules/toolrunner.py and modules/filesystem.py.
# - run_calc: evaluates a math expression without using eval() on arbitrary code
# - run_open: opens a URL in the default browser
# - run_file_read / run_file_list / run_file_search: read-only filesystem access

import ast
import glob
import operator
import os
import pathlib
import webbrowser

# ── Filesystem safety ─────────────────────────────────────────────────────────

_MAX_READ_CHARS    = 3000
_MAX_LIST_ENTRIES  = 50
_MAX_SEARCH_HITS   = 25

# Substrings that must never appear in a path we read
_BLOCKED_PATTERNS = [
    ".ssh", "id_rsa", "id_dsa", "id_ed25519", "id_ecdsa",
    ".env", "credentials.json", "login data",
    "wallet.dat", ".pem", ".pfx", ".p12", ".key",
    "/sam", "/system", "/security",          # windows registry hives (forward-slash normalised)
    "appdata/roaming/mozilla",               # firefox profile (may contain saved passwords)
    "appdata/local/google/chrome/user data", # chrome profile
]

# Common folder name aliases → full path
def _dir_aliases() -> dict:
    home = str(pathlib.Path.home())
    return {
        "desktop":   os.path.join(home, "Desktop"),
        "documents": os.path.join(home, "Documents"),
        "downloads": os.path.join(home, "Downloads"),
        "pictures":  os.path.join(home, "Pictures"),
        "videos":    os.path.join(home, "Videos"),
        "music":     os.path.join(home, "Music"),
        "home":      home,
        "~":         home,
    }


def _is_blocked(path: str) -> bool:
    normalised = path.lower().replace("\\", "/")
    return any(b in normalised for b in _BLOCKED_PATTERNS)


def _expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path.strip()))


# ── Filesystem tools ──────────────────────────────────────────────────────────

def run_file_read(path: str) -> str:
    """Read a file and return its contents (up to _MAX_READ_CHARS)."""
    path = _expand(path)
    if _is_blocked(path):
        return "[blocked: sensitive file path]"
    try:
        if not os.path.isfile(path):
            # Try resolving a relative/partial path against common roots.
            # Strip drive prefix so "C:/foo/bar.txt" → "foo/bar.txt" for candidate building.
            home = str(pathlib.Path.home())
            _, bare = os.path.splitdrive(path)
            bare = bare.lstrip("/\\")
            candidates = [
                os.path.join("C:/", bare),
                os.path.join("D:/", bare),
                os.path.join(home, bare),
                os.path.join(home, "Desktop", bare),
                os.path.join(home, "Documents", bare),
                os.path.join(home, "Downloads", bare),
            ]
            resolved = next((c for c in candidates if os.path.isfile(c)), None)
            if resolved is None:
                return f"[file not found: {path}]"
            path = resolved
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(_MAX_READ_CHARS)
        note = " ...[file truncated]" if size > _MAX_READ_CHARS else ""
        return content + note
    except PermissionError:
        return "[permission denied]"
    except Exception as e:
        return f"[error reading file: {e}]"


def run_file_list(path: str) -> str:
    """List the contents of a directory."""
    aliases = _dir_aliases()
    resolved = aliases.get(path.strip().lower(), _expand(path))

    # If not found directly, try common root locations.
    # Strip any drive prefix first so that e.g. "C:/AiLeadsPOC" → "AiLeadsPOC"
    # and we correctly try Desktop/Documents/Downloads etc.
    if not os.path.isdir(resolved):
        home = str(pathlib.Path.home())
        _, bare = os.path.splitdrive(path.strip())
        bare = bare.lstrip("/\\")
        candidates = [
            os.path.join("C:/", bare),
            os.path.join("D:/", bare),
            os.path.join(home, bare),
            os.path.join(home, "Desktop", bare),
            os.path.join(home, "Documents", bare),
            os.path.join(home, "Downloads", bare),
            os.path.join(home, "Pictures", bare),
        ]
        for c in candidates:
            if os.path.isdir(c):
                resolved = c
                break

    path = os.path.normpath(resolved)
    try:
        if not os.path.isdir(path):
            # Last resort: search for the deepest path component by name
            folder_name = os.path.basename(path.rstrip("/\\")) or path
            search_result = run_file_search(folder_name)
            if not search_result.startswith("[no files"):
                return f"[Could not find '{path}' directly. Search results for '{folder_name}':\n{search_result}]"
            return f"[directory not found: '{path}']"

        # Use listdir for reliability on Windows (scandir can return empty on some paths)
        names = sorted(os.listdir(path))
        print(f"[filesystem] LIST {path!r} → {len(names)} entries")
        if not names:
            return f"{path}/\n[empty directory]"

        lines = []
        for name in names[:_MAX_LIST_ENTRIES]:
            full = os.path.join(path, name)
            try:
                if os.path.isdir(full):
                    lines.append(f"[DIR]  {name}/")
                else:
                    lines.append(f"[FILE] {name}  ({os.path.getsize(full):,} bytes)")
            except OSError:
                lines.append(f"       {name}  (inaccessible)")

        note = f"\n[showing first {_MAX_LIST_ENTRIES} of {len(names)} entries]" \
               if len(names) > _MAX_LIST_ENTRIES else ""
        return f"{path}/\n" + "\n".join(lines) + note
    except PermissionError:
        return "[permission denied]"
    except Exception as e:
        return f"[error listing directory: {e}]"


def run_file_search(pattern: str) -> str:
    """Search for files by name/glob pattern.
    Supports: '*.pdf', '*.pdf in Downloads', 'budget', 'budget in Documents'."""
    import re as _re
    aliases = _dir_aliases()
    home    = str(pathlib.Path.home())

    # Parse optional "in <dir>" suffix
    m = _re.match(r'^(.+?)\s+in\s+(.+)$', pattern.strip(), _re.IGNORECASE)
    if m:
        file_pat = m.group(1).strip()
        dir_hint = m.group(2).strip()
        base = aliases.get(dir_hint.lower(), _expand(dir_hint))
    else:
        file_pat = pattern.strip()
        base = home

    # No wildcard → name-contains search
    if "*" not in file_pat and "?" not in file_pat:
        file_pat = f"*{file_pat}*"

    try:
        hits = glob.glob(os.path.join(base, "**", file_pat), recursive=True)
        hits = [h for h in hits if not _is_blocked(h)]
        if not hits:
            return f"[no files found matching '{pattern}']"
        lines = []
        for h in sorted(hits)[:_MAX_SEARCH_HITS]:
            if os.path.isfile(h):
                lines.append(f"[FILE] {h}  ({os.path.getsize(h):,} bytes)")
            else:
                lines.append(f"[DIR]  {h}/")
        total = len(hits)
        note = f"\n[showing {min(total, _MAX_SEARCH_HITS)} of {total} results]" \
               if total > _MAX_SEARCH_HITS else ""
        return "\n".join(lines) + note
    except Exception as e:
        return f"[search error: {e}]"

# Whitelist of safe AST node types for the calculator
_SAFE_OPS = {
    ast.Add:      operator.add,
    ast.Sub:      operator.sub,
    ast.Mult:     operator.mul,
    ast.Div:      operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod:      operator.mod,
    ast.Pow:      operator.pow,
    ast.USub:     operator.neg,
    ast.UAdd:     operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if not op_fn:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if not op_fn:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.operand))
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def run_calc(expr: str) -> str:
    """Safely evaluate a math expression and return 'expr = result'."""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
        result = _eval_node(tree.body)
        # Clean up float display: drop .0 for whole numbers, cap precision otherwise
        if isinstance(result, float):
            result = int(result) if result == int(result) else round(result, 8)
        return f"{expr.strip()} = {result}"
    except Exception as e:
        return f"[calc error: {e}]"


def run_open(url: str) -> str:
    """Open a URL or local file in the default browser/app."""
    url = url.strip().replace("\\", "/")
    # Local file path (e.g. C:/Users/... or /home/...)
    if (len(url) >= 2 and url[1] == ":") or url.startswith("/"):
        uri = "file:///" + url.lstrip("/")
        webbrowser.open(uri)
        return f"Opened {url}"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url} in your browser."
