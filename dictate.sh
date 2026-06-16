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
# Redirigir stdout Y stderr + cerrar stdin: si un hijo en background (sox) hereda
# el stdout-pipe de Raycast, Raycast cree que este comando silent sigue "corriendo"
# y el siguiente doble-tap NO dispara el STOP. Era la causa del "no deja de grabar".
"$SCRIPT_DIR/whisper-toggle.sh" </dev/null >/dev/null 2>&1
exit 0
