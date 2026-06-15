#!/bin/bash
# Cancel whisper dictation — aborta la GRABACIÓN sin transcribir ni pegar nada.
# Cubre los 3 modos. No-op si no hay grabación activa.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/config.sh"

# Solo actúa si hay una grabación en curso.
[ -f "$WD_MARKER" ] || { echo "Nada que cancelar"; exit 0; }

# ── Modo live: SIGTERM SOLO al PID guardado -> aborta sin pegar ──────────
# Acotado al PID para no matar una sesión nueva (race de dos toggles).
LIVE_PID="$(cat "$WD_LIVE_PID" 2>/dev/null)"
if [ -n "$LIVE_PID" ] && kill -0 "$LIVE_PID" 2>/dev/null; then
  kill -TERM "$LIVE_PID" 2>/dev/null
elif [ -z "$LIVE_PID" ]; then
  pkill -f "openai_live.py" 2>/dev/null   # solo si no hay PID: limpiar huérfano
fi

# ── Modos file/local: matar sox (PID guardado) y borrar el WAV ──────────
if [ -f "$WD_SOX_PID" ]; then
  kill "$(cat "$WD_SOX_PID")" 2>/dev/null
  rm -f "$WD_SOX_PID"
else
  pkill -f "sox.*whisper_dictate" 2>/dev/null   # fallback huérfano
fi

# Borrar audio y, al FINAL, el marker (menubar pasa REC -> idle sin flash de ⏳).
rm -f "$WD_AUDIO"
rm -f "$WD_LIVE_PID"
rm -f "$WD_MARKER"

echo "Grabación cancelada"
