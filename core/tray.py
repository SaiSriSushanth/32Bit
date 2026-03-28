# core/tray.py
# Windows system tray icon using pystray.
# Double-click or select "Open Buddy" to show the chat window.

import pystray
from PIL import Image
from core.events import bus


class TrayIcon:
    def __init__(self, config: dict):
        try:
            icon_img = Image.open("assets/icon.ico").convert("RGBA")
        except FileNotFoundError:
            icon_img = Image.new("RGBA", (64, 64), (100, 149, 237, 255))

        menu = pystray.Menu(
            pystray.MenuItem("Open Buddy", self._open, default=True),
            pystray.MenuItem("Clear history", self._clear),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        self.icon = pystray.Icon("Buddy", icon_img, "Buddy", menu)

    def run(self):
        self.icon.run()

    def _open(self, icon, item):
        bus.emit("window_open")

    def _clear(self, icon, item):
        bus.emit("clear_history")

    def _quit(self, icon, item):
        bus.emit("app_quit")
        icon.stop()
