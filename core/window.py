# core/window.py
# Two-window layout:
#   sprite_win  — always-visible borderless transparent widget, bottom-right corner
#   chat_win    — retro RPG-style dialogue panel that pops up below the sprite on click
#
# Clicking the sprite toggles the chat panel.
# Tray "Open Buddy" also shows the chat panel via the window_open event.
# Escape or the X button collapses it back to just the sprite.

import tkinter as tk
import tkinter.font as tkfont
import customtkinter as ctk
from core.events import bus
from core.sprite import SpriteAnimator

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Chat panel dimensions
CHAT_H = 240
TAIL_H = 14
TAIL_W = 24

# RPG colour palette
_BG        = "#0d0d1a"   # main background
_BORDER    = "#4a4a8a"   # border / accent
_TITLEBAR  = "#1a1a3a"   # title bar background
_TITLE_FG  = "#8888ff"   # title label text
_CLOSE_FG  = "#ff6666"   # close button
_TEXT_FG   = "#ccccff"   # chat history text (soft lavender)
_INPUT_BG  = "#1a1a3a"   # input field background
_INPUT_FG  = "#ffffff"   # input text
_PH_FG     = "#555577"   # placeholder text colour
_PH_TEXT   = "Say something..."
_BTN_OFF   = "#8888ff"   # search toggle OFF colour
_BTN_ON    = "#ffff44"   # search toggle ON colour
_BUBBLE_BUDDY = "#1a1a3a"  # Buddy bubble background
_BUBBLE_YOU   = "#2a2a5a"  # Your bubble background
_SYSTEM_FG    = "#555577"  # System / tool message text

TRANSPARENT = "#ff00ff"


def _get_pixel_font(size: int = 11) -> tuple:
    """Return the best available monospaced pixel-style font."""
    try:
        available = set(tkfont.families())
        for name in ("Courier New", "Lucida Console", "Consolas"):
            if name in available:
                return (name, size)
    except Exception:
        pass
    return ("TkFixedFont", size)


class ChatWindow:
    def __init__(self, config: dict, llm_client):
        self.config = config
        self.llm = llm_client
        self.sprite_win = None
        self.chat_win = None
        self._streaming = False
        self._chat_visible = False
        self._web_search_on = False
        self._message_buffer: list[tuple[str, str]] = []

        # Chat window title-bar drag state
        self._chat_drag_x = 0
        self._chat_drag_y = 0

        # Bubble / streaming state
        self._msg_canvas: tk.Canvas | None = None
        self._msg_frame: tk.Frame | None = None
        self._frame_id = None
        self._streaming_widget: tk.Text | None = None
        self._last_buddy_widget: tk.Text | None = None  # kept after streaming ends
        self._mic_btn = None
        self._mic_active = False

        bus.on("llm_token",           self._on_token)
        bus.on("llm_done",            self._on_done)
        bus.on("push_chat_message",   self._on_push_message)
        bus.on("window_open",         self._show_chat)
        bus.on("window_close",        self._hide_chat)
        bus.on("app_quit",            self._on_app_quit)
        bus.on("voice_result",        self._on_voice_result)
        bus.on("voice_transcribing",  self._on_voice_transcribing)

    # ── Entry point ───────────────────────────────────────────────────────────

    def launch(self):
        """Create the sprite window and enter Tk mainloop. Blocking."""
        self._create_sprite_window()
        self.sprite_win.mainloop()

    # ── Sprite window ─────────────────────────────────────────────────────────

    def _create_sprite_window(self):
        sprite_cfg = self.config["sprite"]
        size = sprite_cfg["frame_width"] * sprite_cfg["display_scale"]
        margin = 4

        self.sprite_win = tk.Tk()
        self.sprite_win.overrideredirect(True)
        self.sprite_win.attributes("-topmost", True)
        self.sprite_win.attributes("-transparentcolor", TRANSPARENT)
        self.sprite_win.resizable(False, False)
        self.sprite_win.configure(bg=TRANSPARENT)

        self.canvas = tk.Canvas(
            self.sprite_win, width=size, height=size,
            bg=TRANSPARENT, highlightthickness=0, cursor="hand2"
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>",        self._on_sprite_press)
        self.canvas.bind("<B1-Motion>",       self._on_sprite_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_sprite_release)
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._dragging = False

        self.sprite = SpriteAnimator(self.canvas, self.config)

        self.sprite_win.update_idletasks()
        sw = self.sprite_win.winfo_screenwidth()
        sh = self.sprite_win.winfo_screenheight()
        x = sw - size - margin
        y = sh - size - margin - 48
        self.sprite_win.geometry(f"{size}x{size}+{x}+{y}")

        bus.emit("sprite_state_change", state="wakeup")

    # ── Sprite drag ───────────────────────────────────────────────────────────

    def _on_sprite_press(self, event):
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._dragging = False

    def _on_sprite_drag(self, event):
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        if not self._dragging and (abs(dx) > 4 or abs(dy) > 4):
            self._dragging = True
        if self._dragging:
            x = self.sprite_win.winfo_x() + dx
            y = self.sprite_win.winfo_y() + dy
            self.sprite_win.geometry(f"+{x}+{y}")
            self._drag_start_x = event.x_root
            self._drag_start_y = event.y_root
            if self._chat_visible and self.chat_win:
                self._reposition_chat_panel()

    def _on_sprite_release(self, event):
        if not self._dragging:
            self._toggle_chat()
        self._dragging = False

    def _chat_position(self):
        """Return (chat_x, chat_y) using the sprite's current absolute screen coordinates.
        Works correctly across multiple monitors."""
        chat_w    = self.config["window"]["width"]
        sprite_sz = (self.config["sprite"]["frame_width"]
                     * self.config["sprite"]["display_scale"])
        total_h   = CHAT_H + TAIL_H

        self.sprite_win.update_idletasks()
        sx = self.sprite_win.winfo_x()
        sy = self.sprite_win.winfo_y()
        sw = self.sprite_win.winfo_width()
        sh = self.sprite_win.winfo_height()

        chat_x = sx + (sw // 2) - (chat_w // 3)
        chat_x = min(chat_x, sx + 600)
        chat_y = sy + sh + 8

        return chat_x, chat_y

    def _reposition_chat_panel(self):
        chat_x, chat_y = self._chat_position()
        self.chat_win.geometry(f"+{chat_x}+{chat_y}")

    def _start_position_sync(self):
        """Poll every 500 ms and snap chat panel back to sprite if it has drifted."""
        if not self._chat_visible or not self.chat_win:
            return
        expected_x, expected_y = self._chat_position()
        actual_x = self.chat_win.winfo_x()
        actual_y = self.chat_win.winfo_y()
        if abs(actual_x - expected_x) > 2 or abs(actual_y - expected_y) > 2:
            self.chat_win.geometry(f"+{expected_x}+{expected_y}")
        self.sprite_win.after(500, self._start_position_sync)

    # ── Chat panel toggle ─────────────────────────────────────────────────────

    def _toggle_chat(self):
        if self._chat_visible:
            self._hide_chat()
        else:
            self._show_chat()

    def _show_chat(self, **kwargs):
        if self._chat_visible:
            if self.chat_win:
                self.chat_win.deiconify()
                self.chat_win.lift()
                self.input_box.focus_set()
            return

        self._chat_visible = True

        if self.chat_win is None:
            self._create_chat_panel()
            self.sprite_win.after(50, lambda: bus.emit("window_open"))
        else:
            self._reposition_chat_panel()
            self.chat_win.deiconify()
            self.chat_win.lift()
            self.input_box.focus_set()

        self.sprite_win.after(500, self._start_position_sync)

    def _hide_chat(self, **kwargs):
        if not self._chat_visible:
            return
        self._chat_visible = False
        if self.chat_win:
            self.chat_win.withdraw()

    # ── Chat window title-bar drag ─────────────────────────────────────────────

    def _on_chat_drag_start(self, event):
        self._chat_drag_x = event.x_root
        self._chat_drag_y = event.y_root

    def _on_chat_drag_motion(self, event):
        dx = event.x_root - self._chat_drag_x
        dy = event.y_root - self._chat_drag_y
        x = self.chat_win.winfo_x() + dx
        y = self.chat_win.winfo_y() + dy
        self.chat_win.geometry(f"+{x}+{y}")
        self._chat_drag_x = event.x_root
        self._chat_drag_y = event.y_root

    # ── Chat panel construction ───────────────────────────────────────────────

    def _create_chat_panel(self):
        chat_w  = self.config["window"]["width"]
        total_h = CHAT_H + TAIL_H

        self.sprite_win.update_idletasks()

        self.chat_win = ctk.CTkToplevel(self.sprite_win)
        self.chat_win.overrideredirect(True)
        self.chat_win.attributes("-topmost", True)
        self.chat_win.attributes("-transparentcolor", TRANSPARENT)
        self.chat_win.resizable(False, False)
        self.chat_win.configure(fg_color=_BG)
        chat_x, chat_y = self._chat_position()
        self.chat_win.geometry(f"{chat_w}x{total_h}+{chat_x}+{chat_y}")

        self.chat_win.update_idletasks()

        pixel_font    = _get_pixel_font(11)
        pixel_font_lg = _get_pixel_font(13)
        pixel_font_sm = _get_pixel_font(9)

        # ── Tail strip ───────────────────────────────────────────────────────
        tail_canvas = tk.Canvas(
            self.chat_win, width=chat_w, height=TAIL_H,
            bg=_BG, highlightthickness=0
        )
        tail_canvas.pack(side="bottom", fill="x")

        # ── Border frame ─────────────────────────────────────────────────────
        border_frame = tk.Frame(self.chat_win, bg=_BORDER, bd=0, highlightthickness=0)
        border_frame.pack(fill="both", expand=True)

        inner = tk.Frame(border_frame, bg=_BG, bd=0, highlightthickness=0)
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        # ── Custom title bar ──────────────────────────────────────────────────
        title_bar = tk.Frame(inner, bg=_TITLEBAR, height=24, bd=0, highlightthickness=0)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)
        title_bar.bind("<ButtonPress-1>", self._on_chat_drag_start)
        title_bar.bind("<B1-Motion>",     self._on_chat_drag_motion)

        title_lbl = tk.Label(
            title_bar, text="[ BUDDY ]",
            bg=_TITLEBAR, fg=_TITLE_FG, font=pixel_font
        )
        title_lbl.pack(side="left", padx=8)
        title_lbl.bind("<ButtonPress-1>", self._on_chat_drag_start)
        title_lbl.bind("<B1-Motion>",     self._on_chat_drag_motion)

        close_lbl = tk.Label(
            title_bar, text="✕",
            bg=_TITLEBAR, fg=_CLOSE_FG, font=pixel_font,
            cursor="hand2", padx=8
        )
        close_lbl.pack(side="right")
        close_lbl.bind("<Button-1>", lambda e: self._hide_chat())

        # ── Input row ─────────────────────────────────────────────────────────
        input_frame = tk.Frame(inner, bg=_BG, bd=0, highlightthickness=0)
        input_frame.pack(side="bottom", fill="x", padx=6, pady=(0, 6))

        self.input_box = tk.Entry(
            input_frame,
            font=pixel_font,
            bg=_INPUT_BG,
            fg=_PH_FG,
            insertbackground=_INPUT_FG,
            relief="flat",
            bd=0,
            highlightbackground=_BORDER,
            highlightthickness=1,
        )
        self.input_box.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=4)
        self.input_box.insert(0, _PH_TEXT)
        self.input_box.bind("<FocusIn>",  self._on_input_focus_in)
        self.input_box.bind("<FocusOut>", self._on_input_focus_out)
        self.input_box.bind("<Return>",   self._on_send)
        self.input_box.bind("<Escape>",   lambda e: self._hide_chat())

        self._web_toggle_btn = tk.Button(
            input_frame,
            text="🔍",
            font=pixel_font_lg,
            bg=_INPUT_BG,
            fg=_BTN_OFF,
            activebackground=_TITLEBAR,
            activeforeground=_BTN_OFF,
            relief="flat",
            bd=0,
            highlightbackground=_BORDER,
            highlightthickness=1,
            cursor="hand2",
            width=3,
            command=self._toggle_web_search,
        )
        self._web_toggle_btn.pack(side="right", ipady=2)

        self._mic_btn = tk.Button(
            input_frame,
            text="🎤",
            font=pixel_font_lg,
            bg=_INPUT_BG,
            fg=_BTN_OFF,
            activebackground=_TITLEBAR,
            activeforeground=_BTN_OFF,
            relief="flat",
            bd=0,
            highlightbackground=_BORDER,
            highlightthickness=1,
            cursor="hand2",
            width=3,
        )
        self._mic_btn.pack(side="right", ipady=2, padx=(0, 4))
        self._mic_btn.bind("<ButtonPress-1>",   self._on_mic_press)
        self._mic_btn.bind("<ButtonRelease-1>", self._on_mic_release)

        # ── Scrollable bubble area ─────────────────────────────────────────────
        self._msg_canvas = tk.Canvas(
            inner, bg=_BG, highlightthickness=0, bd=0
        )
        self._msg_canvas.pack(fill="both", expand=True, pady=(4, 4))

        self._msg_frame = tk.Frame(self._msg_canvas, bg=_BG)
        self._frame_id = self._msg_canvas.create_window(
            (0, 0), window=self._msg_frame, anchor="nw"
        )

        self._msg_frame.bind("<Configure>", self._on_msg_frame_configure)
        self._msg_canvas.bind("<Configure>", self._on_msg_canvas_configure)
        self._msg_canvas.bind("<MouseWheel>", self._on_mousewheel)

        # Flush buffered messages
        for sender, text in self._message_buffer:
            self._append(sender, text)
        self._message_buffer.clear()

        self.input_box.focus_set()

    # ── Scroll helpers ────────────────────────────────────────────────────────

    def _on_msg_frame_configure(self, event=None):
        self._msg_canvas.configure(scrollregion=self._msg_canvas.bbox("all"))

    def _on_msg_canvas_configure(self, event):
        self._msg_canvas.itemconfig(self._frame_id, width=event.width)

    def _on_mousewheel(self, event):
        self._msg_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_scroll(self, widget):
        """Recursively bind mousewheel on all bubble child widgets to the canvas scroller."""
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_scroll(child)

    def _resize_text_widget(self, widget: tk.Text):
        """Resize a Text widget's height to match its wrapped content."""
        try:
            result = widget.count("1.0", "end", "displaylines")
            h = max(1, result[0] if result else 1)
            widget.configure(height=h)
        except Exception:
            pass

    def _scroll_to_bottom(self):
        self._msg_canvas.update_idletasks()
        self._msg_canvas.configure(scrollregion=self._msg_canvas.bbox("all"))
        self._msg_canvas.yview_moveto(1.0)

    # ── Input placeholder helpers ─────────────────────────────────────────────

    def _on_input_focus_in(self, event=None):
        if self.input_box.get() == _PH_TEXT:
            self.input_box.delete(0, "end")
            self.input_box.configure(fg=_INPUT_FG)

    def _on_input_focus_out(self, event=None):
        if not self.input_box.get():
            self.input_box.insert(0, _PH_TEXT)
            self.input_box.configure(fg=_PH_FG)

    # ── Web search toggle ─────────────────────────────────────────────────────

    def _toggle_web_search(self):
        self._web_search_on = not self._web_search_on
        if self._web_search_on:
            self._web_toggle_btn.configure(fg=_BTN_ON, text="◈")
        else:
            self._web_toggle_btn.configure(fg=_BTN_OFF, text="🔍")
        bus.emit("websearch_force", enabled=self._web_search_on)

    # ── Voice input ───────────────────────────────────────────────────────────

    def _on_mic_press(self, event=None):
        if self._mic_active:
            return
        self._mic_active = True
        if self._mic_btn:
            self._mic_btn.configure(fg="#ff4444", text="⏹")
        bus.emit("voice_start")

    def _on_mic_release(self, event=None):
        if not self._mic_active:
            return
        self._mic_active = False
        if self._mic_btn:
            self._mic_btn.configure(fg="#ffaa00", text="…")
        bus.emit("voice_stop")

    def _on_voice_transcribing(self, **kwargs):
        if self.sprite_win and self._mic_btn:
            self.sprite_win.after(0, lambda: self._mic_btn.configure(fg="#ffaa00", text="…"))

    def _on_voice_result(self, text: str = "", **kwargs):
        def _apply():
            if self._mic_btn:
                self._mic_btn.configure(fg=_BTN_OFF, text="🎤")
            if not text:
                return
            # Fill input box with transcribed text and send
            self.input_box.configure(fg=_INPUT_FG)
            self.input_box.delete(0, "end")
            self.input_box.insert(0, text)
            self._on_send()
        if self.sprite_win:
            self.sprite_win.after(0, _apply)

    # ── Messaging ─────────────────────────────────────────────────────────────

    def _on_send(self, event=None):
        text = self.input_box.get().strip()
        if not text or text == _PH_TEXT or self._streaming:
            return
        self.input_box.delete(0, "end")
        self._append("You", text)
        self._first_token = True
        self._thinking_anim_id = None
        self._streaming = True
        self._append("Buddy", "▪")
        self._start_thinking_anim()
        bus.emit("sprite_state_change", state="listening")
        self.llm.chat(text)

    def _add_bubble(self, sender: str, text: str) -> tk.Text:
        """Create a chat bubble widget and return the tk.Text for streaming updates."""
        chat_w        = self.config["window"]["width"]
        pixel_font    = _get_pixel_font(11)
        pixel_font_sm = _get_pixel_font(9)
        # Width in characters: Courier New 11px ≈ 7px/char
        char_width    = max(10, int(chat_w * 0.64) // 7)

        is_buddy = (sender == "Buddy")
        is_you   = (sender == "You")

        row = tk.Frame(self._msg_frame, bg=_BG)
        row.pack(fill="x", padx=6, pady=(2, 0))

        # System / tool messages — centred, dim label (no bubble)
        if not is_buddy and not is_you:
            lbl = tk.Label(
                row, text=text,
                bg=_BG, fg=_SYSTEM_FG,
                font=pixel_font_sm,
                wraplength=chat_w - 24,
                justify="center",
            )
            lbl.pack(anchor="center", pady=2)
            self._bind_scroll(row)
            # Wrap in a dummy Text so callers always get a consistent return type
            dummy = tk.Text(row, width=1, height=1)
            dummy.pack_forget()
            return dummy

        if is_buddy:
            bubble_bg = _BUBBLE_BUDDY
            bubble_fg = _TEXT_FG
            name_fg   = _TITLE_FG
            side      = "left"
        else:
            bubble_bg = _BUBBLE_YOU
            bubble_fg = _INPUT_FG
            name_fg   = "#aaaaff"
            side      = "right"

        if is_buddy:
            tk.Label(
                row, text="▶",
                bg=_BG, fg=name_fg, font=pixel_font
            ).pack(side="left", anchor="n", padx=(0, 4), pady=(4, 0))

        bubble = tk.Frame(row, bg=bubble_bg, padx=8, pady=4)
        bubble.pack(side=side, anchor="n")

        # Sender name
        tk.Label(
            bubble, text=sender,
            bg=bubble_bg, fg=name_fg, font=pixel_font_sm
        ).pack(anchor="w" if is_buddy else "e")

        # Message text — tk.Text so user can select and copy
        msg_text = tk.Text(
            bubble,
            font=pixel_font,
            bg=bubble_bg, fg=bubble_fg,
            relief="flat", bd=0, highlightthickness=0,
            wrap="word",
            width=char_width,
            height=1,
            cursor="xterm",
            exportselection=True,
            selectbackground=_BORDER,
            selectforeground=_INPUT_FG,
            inactiveselectbackground=_BORDER,
            spacing1=1, spacing3=1,
        )
        if text:
            msg_text.insert("1.0", text)
            msg_text.configure(state="disabled")
            self._resize_text_widget(msg_text)
        else:
            msg_text.configure(state="disabled")

        msg_text.pack(anchor="w" if is_buddy else "e")
        msg_text.bind("<Configure>", lambda e: self._resize_text_widget(msg_text))

        self._bind_scroll(row)
        return msg_text

    def _append(self, sender: str, text: str):
        if not self.chat_win:
            return
        widget = self._add_bubble(sender, text)
        if sender == "Buddy":
            self._streaming_widget = widget
            self._last_buddy_widget = widget
        self._scroll_to_bottom()

    _THINKING_FRAMES = ["▪", "▪▪", "▪▪▪", "▪▪"]

    def _start_thinking_anim(self, frame: int = 0):
        if not self._streaming_widget or not self._first_token:
            return
        w = self._streaming_widget
        chars = self._THINKING_FRAMES[frame % len(self._THINKING_FRAMES)]
        w.configure(state="normal")
        w.delete("1.0", "end")
        w.insert("1.0", chars)
        w.configure(state="disabled", fg=_SYSTEM_FG)
        self._resize_text_widget(w)
        self._scroll_to_bottom()
        self._thinking_anim_id = self.sprite_win.after(
            400, lambda: self._start_thinking_anim(frame + 1)
        )

    def _stop_thinking_anim(self):
        if self._thinking_anim_id:
            self.sprite_win.after_cancel(self._thinking_anim_id)
            self._thinking_anim_id = None

    def _on_token(self, token: str, **kwargs):
        if not self.chat_win or not self._chat_visible:
            return
        if self._streaming_widget:
            if self._first_token:
                self._stop_thinking_anim()
                self._first_token = False
                self._streaming_widget.configure(state="normal", fg=_TEXT_FG)
                self._streaming_widget.delete("1.0", "end")
            self._streaming_widget.configure(state="normal")
            self._streaming_widget.insert("end", token)
            self._resize_text_widget(self._streaming_widget)
            self._streaming_widget.configure(state="disabled")
            self._scroll_to_bottom()

    def _on_done(self, full_text: str, **kwargs):
        self._stop_thinking_anim()
        self._first_token = False
        self._streaming = False
        self._streaming_widget = None

    def _on_push_message(self, sender: str, text: str, **kwargs):
        if self.chat_win:
            self._append(sender, text)
        else:
            self._message_buffer.append((sender, text))

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _on_app_quit(self, **kwargs):
        if self.chat_win:
            self.chat_win.destroy()
        if self.sprite_win:
            self.sprite_win.destroy()
