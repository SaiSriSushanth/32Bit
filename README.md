# Buddy — Local Desktop AI Companion

A modular, always-on desktop assistant that lives in the corner of your screen. Fully local — no cloud, no API keys. Powered by Ollama.

---

## Requirements

- Python 3.9+
- [Ollama](https://ollama.com) running locally (`ollama serve`)
- Model pulled: `ollama pull llama3.2:3b`

```
pip install -r requirements.txt
```

---

## Running

```
python main.py
```

Buddy appears as a sprite in the bottom-right corner. Click it to open the chat panel.

---

## Features & How to Trigger Them

### 💬 Chat

Just type anything and press Enter. Buddy keeps full conversation history.

---

### 🔍 Web Search

Automatically triggered when your message contains real-time intent keywords.

**Trigger keywords:**
> news, latest, current, today, now, recent, breaking, price, stock, score, weather,
> who is, what is, when did, when is, how much, update, new, released, happened,
> did, does, is there, has, have, still, available, check, look up, tell me about,
> what happened, any news, status, launched, online, web search

**Examples:**

- "What's the latest news on GPT-5?"
- "What is the current price of Bitcoin?"
- "Did Apple release anything new?"

**Manual override:** Click the 🔍 button in the chat to force web search on/off for any message.

> Web search uses DuckDuckGo (no API key) and scrapes the top result via Jina Reader for full content. An LLM judge confirms intent before searching to avoid false triggers.

---

### 📁 Filesystem Access (read-only)

Automatically triggered when your message references files, folders, or extensions.

**Trigger keywords:**
> list, what's in, find, search for, look for, read, inside, contents of,
> files in, folders in, directory, folder, my downloads, my documents, my desktop,
> .pdf, .txt, .py, .json, .docx, .xlsx, .zip, .md, and other file extensions

**Examples:**

- "What's in my Downloads folder?"
- "Find X on my desktop"
- "Read requirements.txt"
- "List X Files in Folder"
- "Find all PDFs in Documents"

**Supported directory aliases:** Desktop, Documents, Downloads, Pictures, Videos, Music

---

### 🌐 Open URLs / Browser Navigation

Triggered when you ask Buddy to open, visit, or navigate somewhere.

**Trigger phrases:**
> open, go to, visit, show me, navigate, launch, search on, search in

**Examples:**

- "Open YouTube"
- "Go to github.com"
- "Search for lofi music on YouTube"
- "Open Spotify and search for Blinding Lights"

---

### 🧮 Calculator

Triggered automatically when the response includes a math expression.

**Examples:**

- "What is 15% of 340?"
- "Calculate 2^10"
- "How much is 1250 * 12?"

---

### 🎤 Voice Input (Push-to-Talk)

Hold the 🎤 button in the chat panel while speaking. Release to transcribe and send.

Powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — runs fully offline.

> Model: `base` by default. Change to `small` in `config/settings.json` for better accuracy (~3–5s transcription on CPU).

---

### 🧠 Memory

Buddy remembers key facts about you across conversations. Stored locally in `data/memory.json`.

---

## Configuration

All settings are in `config/settings.json`:

| Setting | Description |
|---|---|
| `username` | Your name — used in the system prompt |
| `llm.model` | Ollama model to use |
| `llm.temperature` | Response creativity (0.0–1.0) |
| `llm.max_tokens` | Max tokens per response |
| `modules.websearch.max_results` | Number of DDG results to fetch |
| `modules.voice.model` | Whisper model size (`tiny`, `base`, `small`, `medium`) |
| `modules.voice.device_index` | Override mic device (see terminal on startup for device list) |
| `window.always_on_top` | Keep Buddy above all other windows |
| `window.position` | Sprite position (`bottom-right`, etc.) |

---

## Project Structure

```
CGAI/
├── main.py                  # Entry point
├── config/
│   └── settings.json        # All configuration
├── core/
│   ├── app.py               # App controller — wires everything together
│   ├── llm.py               # Ollama streaming client
│   ├── window.py            # Tkinter UI (sprite + chat panel)
│   ├── events.py            # Event bus
│   ├── registry.py          # Module registry
│   ├── sprite.py            # Sprite animator
│   ├── tools.py             # Tool implementations (calc, open, filesystem)
│   └── tray.py              # System tray icon
├── modules/
│   ├── websearch.py         # DuckDuckGo search + Jina scraping
│   ├── filesystem.py        # Local file access (list, search, read)
│   ├── voice.py             # Whisper speech-to-text
│   ├── memory.py            # Persistent memory
│   ├── context.py           # Date/time context injection
│   ├── toolrunner.py        # OPEN[] browser tool
│   ├── greeting.py          # Startup greeting
│   ├── daily_summary.py     # Daily summary on first open
│   └── sound.py             # Sound effects (optional)
└── assets/
    └── sprite_sheet.png     # 128×128 sprite frames
```

---

## Adding a Module

1. Create `modules/yourmodule.py` with a class that has `name`, `load()`, and optionally `set_llm()` and `unload()`
2. Call `registry.register(YourModule())` at the bottom
3. Import it in `core/app.py`
4. Add an entry under `modules` in `config/settings.json`

Modules can register **context hooks** (inject info before each LLM call) or listen to **bus events** (`llm_done`, `llm_token`, etc.).
