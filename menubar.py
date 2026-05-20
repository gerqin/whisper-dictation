#!/usr/bin/env python3
"""
Whisper dictation status menu bar app.
- Watches /tmp/.whisper_recording (marker) and /tmp/whisper_dictate.wav
- Shows live REC timer, transcribing spinner, idle, or server-down
- Click toggles dictation (same as the Raycast hotkey)
"""
import os
import time
import subprocess
import urllib.request
import urllib.error

import rumps

HOME = os.path.expanduser("~")
MARKER = "/tmp/.whisper_recording"
AUDIO = "/tmp/whisper_dictate.wav"
TOGGLE = os.path.join(HOME, "Dev/whisper-dictation/whisper-toggle.sh")
HEALTH_URL = "http://127.0.0.1:8787/"
WARN_AT_SEC = 60
MAX_REC_SEC = 300


class WhisperStatus(rumps.App):
    def __init__(self):
        super().__init__("🎙", quit_button=None)
        self.last_health = 0
        self.health_ok = True
        self.last_state = None
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
        rumps.Timer(self.tick, 0.5).start()

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

    def tick(self, _):
        # Auto-discard once a recording exceeds the cap (turn off + drop audio).
        if os.path.exists(MARKER) and (time.time() - os.path.getmtime(MARKER)) >= MAX_REC_SEC:
            self.discard_recording(None)
            try:
                rumps.notification(
                    "Whisper dictation", "Grabación descartada",
                    f"Se alcanzó el límite de {MAX_REC_SEC // 60} min",
                )
            except Exception:
                pass

        if os.path.exists(MARKER):
            elapsed = int(time.time() - os.path.getmtime(MARKER))
            mm, ss = divmod(elapsed, 60)
            if elapsed >= WARN_AT_SEC:
                title = f"🟠 REC {mm:02d}:{ss:02d}"
            else:
                title = f"🔴 REC {mm:02d}:{ss:02d}"
            state = "rec"
        elif os.path.exists(AUDIO):
            title = "⏳ …"
            state = "transcribing"
        elif not self.check_health():
            title = "⚠️ off"
            state = "down"
        else:
            title = "🎙"
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
        for path in (MARKER, AUDIO, "/tmp/.whisper_sox.pid"):
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
