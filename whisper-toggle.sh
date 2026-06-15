#!/bin/bash
# ── Whisper Dictation — orquestador toggle (3 modos) ──────────────────
# Primer tap: empieza a grabar. Segundo tap: detiene, transcribe y pega.
# Modo según DICTATION_MODE (config.sh): openai_live | openai_file | local
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/config.sh"
PY="$SCRIPT_DIR/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 || echo python3)"   # fallback si falta el venv
SOX="$(command -v sox || echo /opt/homebrew/bin/sox)"

is_alive() { [ -n "$1" ] && kill -0 "$1" 2>/dev/null; }

# ════════════════════════ STOP (hay grabación en curso) ═══════════════
if [ -f "$WD_MARKER" ]; then
  rm -f "$WD_MARKER"

  if [ "$DICTATION_MODE" = "openai_live" ]; then
    # El proceso live finaliza el turno, transcribe y pega al recibir USR1.
    LIVE_PID="$(cat "$WD_LIVE_PID" 2>/dev/null)"
    if is_alive "$LIVE_PID"; then
      kill -USR1 "$LIVE_PID" 2>/dev/null
      touch "$WD_FINALIZING"   # menubar: spinner mientras transcribe/pega
    else
      # Proceso live muerto/ausente: limpiar estado stale.
      rm -f "$WD_LIVE_PID"
      pkill -f "openai_live.py" 2>/dev/null
    fi
    exit 0
  fi

  # ── Modos file/local: detener sox y transcribir el WAV ──────────────
  if [ -f "$WD_SOX_PID" ]; then
    kill "$(cat "$WD_SOX_PID")" 2>/dev/null
    rm -f "$WD_SOX_PID"
  fi
  pkill -f "sox.*whisper_dictate" 2>/dev/null
  sleep 0.2
  [ ! -s "$WD_AUDIO" ] && exit 0
  load_openai_key  # openai_file lo necesita (local no, pero es barato)
  "$PY" "$SCRIPT_DIR/dictation_common.py"   # file_mode_main(): chain + cleanup + paste
  exit 0
fi

# ════════════════════════ START (no hay grabación) ════════════════════
rm -f "$WD_AUDIO"

if [ "$DICTATION_MODE" = "openai_live" ]; then
  # NO se hace pkill aquí: START solo corre sin marker, y un openai_live.py
  # vivo en ese estado es uno FINALIZANDO (pegando) un dictado previo — matarlo
  # perdería ese paste. Cada proceso usa un ownership-guard sobre WD_LIVE_PID.
  load_openai_key
  if [ -z "${OPENAI_API_KEY:-}" ]; then
    # Sin key no hay live: degradar a local para no dejar al user sin dictado.
    export DICTATION_MODE=local
  fi
fi

if [ "$DICTATION_MODE" = "openai_live" ]; then
  # openai_live.py graba+streamea; pega al recibir USR1.
  nohup "$PY" "$SCRIPT_DIR/openai_live.py" >>"${DICTATION_DEBUG_LOG:-/tmp/whisper-dictation-debug.log}" 2>&1 &
  LIVE_PID=$!
  # Escribir PID y marker ANTES de devolver, en ese orden: así un STOP que
  # llegue justo después SIEMPRE encuentra el PID (cierra la race PID/marker).
  echo "$LIVE_PID" >"$WD_LIVE_PID"
  touch "$WD_MARKER"
  disown
  exit 0
fi

# ── Modos file/local: grabar WAV con sox (16kHz para whisper.cpp local) ──
pkill -f "sox.*whisper_dictate" 2>/dev/null
touch "$WD_MARKER"
"$SOX" -d -q -r 16000 -c 1 -b 16 -t wav "$WD_AUDIO" trim 0 300 &
echo $! >"$WD_SOX_PID"
disown
