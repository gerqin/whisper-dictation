#!/bin/bash
# Cancel whisper dictation — aborta la GRABACIÓN sin transcribir ni pegar nada.
# Pensado para un hotkey (Cmd+Esc vía Raycast). No-op si no hay grabación activa.
MARKER="/tmp/.whisper_recording"
PIDFILE="/tmp/.whisper_sox.pid"
AUDIO="/tmp/whisper_dictate.wav"

# Solo actúa si hay una grabación en curso. Si no, no toca nada
# (no mata transcripciones legítimas en vuelo).
[ -f "$MARKER" ] || { echo "Nada que cancelar"; exit 0; }

# 1) Matar sox primero (deja de escribir el wav). PID guardado, fallback pkill.
if [ -f "$PIDFILE" ]; then
  kill "$(cat "$PIDFILE")" 2>/dev/null
  rm -f "$PIDFILE"
fi
pkill -f "sox.*whisper_dictate" 2>/dev/null

# 2) Borrar el audio y, al FINAL, el marker.
#    Marker al final → la menu bar pasa REC → idle directo, sin flash de ⏳.
rm -f "$AUDIO"
rm -f "$MARKER"

echo "Grabación cancelada"
