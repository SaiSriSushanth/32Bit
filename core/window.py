# core/window.py
# Two-window layout:
#   sprite_win  — always-visible borderless transparent widget, bottom-right corner
#   chat_win    — compact speech-bubble panel that pops up above the sprite on click
#
# Clicking the sprite toggles the chat panel.
# Tray "Open Buddy" also shows the chat panel via the window_open event.
# Escape or the X button collapses it back to just the sprite.

import customtkinter as ctk
import tkinter as tk
from core.events import bus
from core.sprite import SpriteAnimator

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Chat panel dimensions — compact, proportional to sprite
CHAT_H = 240
TAIL_H = 14
TAIL_W = 24


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

        bus.on("llm_token",         self._on_token)
        bus.on("llm_done",          self._on_done)
        bus.on("push_chat_message", self._on_push_message)
        bus.on("window_open",       self._show_chat)
        bus.on("window_close",      self._hide_chat)
        bus.on("app_quit",          self._on_app_quit)

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

        TRANSPARENT = "#ff00ff"

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
        Works correctly across multiple monitors — coordinates may be negative or exceed
        primary screen bounds when secondary monitors are involved."""
        chat_w    = self.config["window"]["width"]
        sprite_sz = (self.config["sprite"]["frame_width"]
                     * self.config["sprite"]["display_scale"])
        total_h   = CHAT_H + TAIL_H

        # Always read fresh — sprite may have been dragged to a different monitor
        self.sprite_win.update_idletasks()
        sx = self.sprite_win.winfo_x()
        sy = self.sprite_win.winfo_y()
        sw = self.sprite_win.winfo_width()
        sh = self.sprite_win.winfo_height()

        # Horizontal: sprite sits ~30% from left edge of chat panel
        chat_x = sx + (sw // 2) - (chat_w // 3)
        # Clamp so chat never flies off-screen to the right of the sprite
        chat_x = min(chat_x, sx + 600)

        # Vertical: always below the sprite
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
            # Re-read sprite position every open — sprite may have moved monitors
            self._reposition_chat_panel()
            self.chat_win.deiconify()
            self.chat_win.lift()
            self.input_box.focus_set()

        # Start drift-correction loop for while chat is open
        self.sprite_win.after(500, self._start_position_sync)

    def _hide_chat(self, **kwargs):
        if not self._chat_visible:
            return
        self._chat_visible = False
        if self.chat_win:
            self.chat_win.withdraw()

    # ── Chat panel construction ───────────────────────────────────────────────

    def _create_chat_panel(self):
        chat_w    = self.config["window"]["width"]
        sprite_sz = (self.config["sprite"]["frame_width"]
                     * self.config["sprite"]["display_scale"])
        total_h = CHAT_H + TAIL_H
        self.sprite_win.update_idletasks()



        self.chat_win = ctk.CTkToplevel(self.sprite_win)
        self.chat_win.overrideredirect(True)
        self.chat_win.attributes("-topmost", True)
        self.chat_win.resizable(False, False)
        # Position after window exists so winfo_screenwidth reads the right monitor
        chat_x, chat_y = self._chat_position()
        self.chat_win.geometry(f"{chat_w}x{total_h}+{chat_x}+{chat_y}")

        





        # Grab the actual CTk background color for the tail to match exactly
        self.chat_win.update_idletasks()
        try:
            panel_bg = self.chat_win._fg_frame.cget("fg_color")
            if isinstance(panel_bg, (list, tuple)):
                panel_bg = panel_bg[1]  # index 1 = dark mode
        except Exception:
            panel_bg = "#2b2b2b"
    

        tail_cx = chat_w - sprite_sz // 2
        tail_cx = max(TAIL_W + 4, min(chat_w - TAIL_W - 4, tail_cx))
        tail_canvas = tk.Canvas(
            self.chat_win, width=chat_w, height=TAIL_H,
            bg=panel_bg, highlightthickness=0
        )
        tail_canvas.pack(side="bottom", fill="x")
        tail_canvas.create_polygon(
            tail_cx - TAIL_W // 2, 0,
            tail_cx + TAIL_W // 2, 0,
            tail_cx,               TAIL_H,
            fill=panel_bg, outline=""
        )
        # Custom title bar
        title_bar = ctk.CTkFrame(self.chat_win, height=32, corner_radius=0)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)
        ctk.CTkLabel(
            title_bar, text="Buddy", font=("Segoe UI", 11, "bold")
        ).pack(side="left", padx=10)
        ctk.CTkButton(
            title_bar, text="X", width=32, height=32,
            corner_radius=0, fg_color="transparent",
            hover_color="#c42b1c", font=("Segoe UI", 10, "bold"),
            command=self._hide_chat
        ).pack(side="right")

        # Input row — pack before chat box so it anchors to bottom of content
        input_frame = ctk.CTkFrame(self.chat_win, fg_color="transparent")
        input_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 8))

        self.input_box = ctk.CTkEntry(
            input_frame, placeholder_text="Say something...", font=("Segoe UI", 12)
        )
        self.input_box.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.input_box.bind("<Return>", self._on_send)
        self.input_box.bind("<Escape>", lambda e: self._hide_chat())

        # Web search icon toggle — replaces Send button + old labeled toggle
        self._web_toggle_btn = ctk.CTkButton(
            input_frame,
            text="🔍",
            width=34, height=34,
            corner_radius=6,
            font=("Segoe UI", 15),
            fg_color="#1f538d" if self._web_search_on else "#3a3a3a",
            hover_color="#2a6ab5" if self._web_search_on else "#4a4a4a",
            command=self._toggle_web_search
        )
        self._web_toggle_btn.pack(side="right")

        # Chat history — fills remaining space between title bar and input
        self.chat_box = ctk.CTkTextbox(
            self.chat_win, state="disabled", font=("Segoe UI", 12), wrap="word"
        )
        self.chat_box.pack(fill="both", expand=True, padx=10, pady=(4, 4))

        # Flush messages that arrived before the panel existed
        for sender, text in self._message_buffer:
            self._append(sender, text)
        self._message_buffer.clear()

        self.input_box.focus_set()

    # ── Web search toggle ─────────────────────────────────────────────────────

    def _toggle_web_search(self):
        self._web_search_on = not self._web_search_on
        if self._web_search_on:
            self._web_toggle_btn.configure(
                fg_color="#1f538d", hover_color="#2a6ab5"
            )
        else:
            self._web_toggle_btn.configure(
                fg_color="#3a3a3a", hover_color="#4a4a4a"
            )
        bus.emit("websearch_force", enabled=self._web_search_on)

    # ── Messaging ─────────────────────────────────────────────────────────────

    def _on_send(self, event=None):
        text = self.input_box.get().strip()
        if not text or self._streaming:
            return
        self.input_box.delete(0, "end")
        self._append("You", text)
        self._append("Buddy", "")
        self._streaming = True
        bus.emit("sprite_state_change", state="listening")
        self.llm.chat(text)

    def _append(self, sender: str, text: str):
        if not self.chat_win:
            return
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{sender}: {text}\n\n")
        self.chat_box.configure(state="disabled")
        self.chat_box.see("end")

    def _on_token(self, token: str, **kwargs):
        if not self.chat_win or not self._chat_visible:
            return
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end-2c", token)
        self.chat_box.configure(state="disabled")
        self.chat_box.see("end")

    def _on_done(self, full_text: str, **kwargs):
        self._streaming = False

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
