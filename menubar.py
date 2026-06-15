#!/usr/bin/env python3
"""Whisper dictation status menu bar app.

Estados (sin emojis de color; spinner animado como "loader"):
  ∿              idle
  🔴 mm:ss        grabando (bolita roja fija + timer)
  ◐              transcribiendo/pegando (spinner girando, sin timer)
  ⚠              server local caído (solo relevante para modo local/fallback)

Señales que observa:
  WD_MARKER       grabando (capture activo)
  WD_FINALIZING   soltó hotkey en modo live; transcribiendo/pegando
  WD_AUDIO        WAV presente (modos file/local transcribiendo)
"""
import os
import time
import subprocess
import urllib.request
import urllib.error

import rumps

HOME = os.path.expanduser("~")
MARKER = os.environ.get("WD_MARKER", "/tmp/.whisper_recording")
AUDIO = os.environ.get("WD_AUDIO", "/tmp/whisper_dictate.wav")
FINALIZING = os.environ.get("WD_FINALIZING", "/tmp/.whisper_finalizing")
TOGGLE = os.path.join(HOME, "Dev/whisper-dictation/whisper-toggle.sh")
HEALTH_URL = "http://127.0.0.1:8787/"
MAX_REC_SEC = 300
TICK = 0.12                 # rápido para animar el spinner suave
SPINNER = ["◐", "◓", "◑", "◒"]   # circulito girando
IDLE_GLYPH = "∿"
DOWN_GLYPH = "⚠"
STALE_FINALIZING_SEC = 30   # si el flag queda colgado (proceso muerto), ignóralo


class WhisperStatus(rumps.App):
    def __init__(self):
        super().__init__(IDLE_GLYPH, quit_button=None)
        self.last_health = 0
        self.health_ok = True
        self.last_state = None
        self.frame = 0
        self.process_item = rumps.MenuItem("Process recording", callback=self.process_recording)
        self.discard_item = rumps.MenuItem("Discard recording", callback=self.discard_recording)
        self.process_item.set_callback(None)
        self.discard_item.set_callback(None)
        self.menu = [
            "Toggle dictation",
            "Restart server",
            None,
            self.process_item,
            self.discard_item,
            None,
            "Quit",
        ]
        rumps.Timer(self.tick, TICK).start()

    def check_health(self):
        now = time.time()
        if now - self.last_health < 10:
            return self.health_ok
        self.last_health = now
        try:
            urllib.request.urlopen(HEALTH_URL, timeout=1).read()
            self.health_ok = True
        except (urllib.error.URLError, TimeoutError, OSError):
            self.health_ok = False
        return self.health_ok

    @staticmethod
    def _fresh(path, max_age):
        try:
            return (time.time() - os.path.getmtime(path)) < max_age
        except OSError:
            return False

    def tick(self, _):
        self.frame = (self.frame + 1) % len(SPINNER)
        spin = SPINNER[self.frame]

        # Auto-discard si la grabación excede el tope.
        if os.path.exists(MARKER) and (time.time() - os.path.getmtime(MARKER)) >= MAX_REC_SEC:
            self.discard_recording(None)
            try:
                rumps.notification("Whisper dictation", "Grabación descartada",
                                   f"Se alcanzó el límite de {MAX_REC_SEC // 60} min")
            except Exception:
                pass

        if os.path.exists(MARKER):
            # Grabando: bolita roja FIJA + timer (para cachar grabación accidental).
            elapsed = int(time.time() - os.path.getmtime(MARKER))
            mm, ss = divmod(elapsed, 60)
            title = f"🔴 {mm:02d}:{ss:02d}"
            state = "rec"
        elif os.path.exists(FINALIZING) and self._fresh(FINALIZING, STALE_FINALIZING_SEC):
            # Soltó el hotkey en modo live: transcribiendo/pegando.
            title = spin
            state = "finalizing"
        elif os.path.exists(AUDIO):
            # Modos file/local: WAV presente, transcribiendo.
            title = spin
            state = "transcribing"
        elif not self.check_health():
            title = DOWN_GLYPH
            state = "down"
        else:
            title = IDLE_GLYPH
            state = "idle"

        if title != self.title:
            self.title = title
        self.last_state = state

        active = state == "rec"
        self.process_item.set_callback(self.process_recording if active else None)
        self.discard_item.set_callback(self.discard_recording if active else None)

    @rumps.clicked("Toggle dictation")
    def toggle(self, _):
        subprocess.Popen(["/bin/bash", TOGGLE])

    def process_recording(self, _):
        subprocess.Popen(["/bin/bash", TOGGLE])

    def discard_recording(self, _):
        subprocess.run(["pkill", "-f", "sox.*whisper_dictate"], check=False)
        subprocess.run(["pkill", "-f", "openai_live.py"], check=False)
        for path in (MARKER, AUDIO, FINALIZING, "/tmp/.whisper_sox.pid", "/tmp/.whisper_live.pid"):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    @rumps.clicked("Restart server")
    def restart(self, _):
        plist = os.path.join(HOME, "Library/LaunchAgents/com.local.whisper-server.plist")
        subprocess.run(["launchctl", "unload", plist])
        subprocess.run(["launchctl", "load", plist])
        self.last_health = 0

    @rumps.clicked("Quit")
    def quit(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    WhisperStatus().run()
