# modules/voice.py
# Push-to-talk voice input via faster-whisper.
#
# Flow:
#   1. UI emits "voice_start"  → begins recording from default mic
#   2. UI emits "voice_stop"   → stops recording, transcribes in background
#   3. Emits "voice_result" with text → UI fills the input box
#
# The Whisper model loads once at startup in a background thread so it
# doesn't block the UI. GPU is used if available, falls back to CPU.

import threading
import numpy as np
from core.registry import registry
from core.events import bus


class VoiceModule:
    name = "voice"

    def __init__(self):
        self._model = None
        self._recording = False
        self._frames = []
        self._sample_rate = 16000   # Whisper expects 16 kHz
        self._native_rate = 16000   # actual device rate — detected at first record
        self._device_index = None   # None = system default; set via settings

    def load(self, config: dict, bus):
        mod_cfg = config.get("modules", {}).get("voice", {})
        model_size        = mod_cfg.get("model", "base")
        device            = mod_cfg.get("device", "cpu")
        compute_type      = mod_cfg.get("compute_type", "int8")
        self._device_index = mod_cfg.get("device_index", None)

        threading.Thread(
            target=self._load_model,
            args=(model_size, device, compute_type),
            daemon=True
        ).start()

        bus.on("voice_start", self._on_start)
        bus.on("voice_stop",  self._on_stop)

    def _load_model(self, model_size: str, device: str, compute_type: str):
        # Use a local path to avoid OneDrive sync issues with the HuggingFace cache
        download_root = "C:/whisper_models"
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(model_size, device=device, compute_type=compute_type, download_root=download_root)
            print(f"[voice] Whisper '{model_size}' loaded on {device}")
        except Exception as e:
            if device != "cpu":
                print(f"[voice] Load on {device} failed ({e}), retrying on CPU")
                try:
                    from faster_whisper import WhisperModel
                    self._model = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=download_root)
                    print(f"[voice] Whisper '{model_size}' loaded on CPU")
                    return
                except Exception as e2:
                    print(f"[voice] Model load failed: {e2}")
            else:
                print(f"[voice] Model load failed: {e}")

    def _on_start(self, **kwargs):
        if self._recording:
            return
        self._recording = True
        self._frames = []
        threading.Thread(target=self._record, daemon=True).start()
        print("[voice] Recording…")

    def _record(self):
        try:
            import sounddevice as sd
            device_info = sd.query_devices(self._device_index, kind="input")
            self._native_rate = int(device_info["default_samplerate"])
            channels = max(1, int(device_info["max_input_channels"]))
            print(f"[voice] Input device: {device_info['name']} @ {self._native_rate} Hz, {channels} ch")
            def callback(indata, frames, time, status):
                if self._recording:
                    # Mix down to mono by averaging all channels
                    self._frames.append(indata.mean(axis=1, keepdims=True).copy())
            with sd.InputStream(
                device=self._device_index,
                samplerate=self._native_rate,
                channels=channels,
                dtype="float32",
                callback=callback
            ):
                while self._recording:
                    sd.sleep(50)
        except Exception as e:
            print(f"[voice] Recording error: {e}")
            self._recording = False

    def _on_stop(self, **kwargs):
        if not self._recording:
            return
        self._recording = False
        if not self._frames:
            return
        threading.Thread(target=self._transcribe, daemon=True).start()

    def _transcribe(self):
        if not self._model:
            print("[voice] Model not ready yet — try again in a moment")
            bus.emit("voice_result", text="")
            return
        try:
            bus.emit("voice_transcribing")
            audio = np.concatenate(self._frames, axis=0).flatten()
            print(f"[voice] Audio: {len(audio)} samples @ {self._native_rate} Hz, max amplitude: {audio.max():.4f}")
            if audio.max() < 0.001:
                print("[voice] No audio captured — check microphone / input device")
                bus.emit("voice_result", text="")
                return
            # Resample to 16 kHz if the device recorded at a different rate
            if self._native_rate != self._sample_rate:
                target_len = int(len(audio) * self._sample_rate / self._native_rate)
                audio = np.interp(
                    np.linspace(0, len(audio) - 1, target_len),
                    np.arange(len(audio)),
                    audio
                ).astype(np.float32)
            segments, _ = self._model.transcribe(audio, language="en", beam_size=1)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            print(f"[voice] Transcribed: {text!r}")
            bus.emit("voice_result", text=text)
        except Exception as e:
            print(f"[voice] Transcription failed: {e}")
            # If CUDA runtime libs are missing, fall back to CPU and retry once
            if "dll" in str(e).lower() or "cuda" in str(e).lower() or "cublas" in str(e).lower():
                print("[voice] Falling back to CPU for transcription")
                try:
                    from faster_whisper import WhisperModel
                    self._model = WhisperModel(
                        self._model.model_size_or_path if hasattr(self._model, "model_size_or_path") else "base",
                        device="cpu", compute_type="int8"
                    )
                    audio = np.concatenate(self._frames, axis=0).flatten()
                    segments, _ = self._model.transcribe(audio, language="en", beam_size=1)
                    text = " ".join(seg.text.strip() for seg in segments).strip()
                    print(f"[voice] Transcribed (CPU): {text!r}")
                    bus.emit("voice_result", text=text)
                    return
                except Exception as e2:
                    print(f"[voice] CPU fallback also failed: {e2}")
            bus.emit("voice_result", text="")

    def unload(self):
        self._recording = False


registry.register(VoiceModule())
