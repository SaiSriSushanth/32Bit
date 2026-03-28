# modules/sound.py
# Plays .wav sounds on startup and on play_sound events using pygame.mixer.

import pygame
from core.registry import registry
from core.events import bus


class SoundModule:
    name = "sound"

    def __init__(self):
        self.sounds: dict = {}
        self._ready = False

    def load(self, config: dict, bus):
        sound_cfg = config.get("sound", {})
        if not sound_cfg.get("enabled", True):
            return
        try:
            pygame.mixer.init()
            pygame.mixer.music.set_volume(sound_cfg.get("volume", 0.6))
            for key in ["startup_sound", "notify_sound"]:
                path = sound_cfg.get(key)
                if path:
                    try:
                        self.sounds[key] = pygame.mixer.Sound(path)
                    except Exception as e:
                        print(f"[sound] Could not load {key}: {e}")
            self._ready = True
        except Exception as e:
            print(f"[sound] pygame.mixer init failed: {e}")
            return

        bus.on("window_open", lambda **kw: self._play(sound_name="startup"))
        bus.on("play_sound", self._play)

    def _play(self, sound_name: str = "", **kwargs):
        if not self._ready:
            return
        key = f"{sound_name}_sound"
        if key in self.sounds:
            self.sounds[key].play()

    def unload(self):
        if self._ready:
            pygame.mixer.quit()


registry.register(SoundModule())
