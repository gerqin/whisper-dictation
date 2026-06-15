#!/bin/bash

# Raycast Script Command
# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Dictate
# @raycast.mode silent
# @raycast.icon 🎙

# Optional parameters:
# @raycast.packageName Whisper Dictation

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Sin stdout a propósito: el HUD de Raycast mostraba "Recording..." al iniciar y
# el clipboard ANTERIOR al detener (el nuevo aún no se pegaba) — confuso e inútil.
# El único feedback es la menubar (timer al grabar, spinner al transcribir/pegar).
"$SCRIPT_DIR/whisper-toggle.sh" 2>/dev/null
exit 0
