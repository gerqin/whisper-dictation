#!/bin/bash
# ── Whisper Dictation — configuración central ─────────────────────────
# Fuente única de verdad. La sourcean los scripts shell y los procesos
# Python heredan estos valores por entorno (os.environ con defaults).

# ── Modo de dictado ───────────────────────────────────────────────────
#   local        → whisper.cpp local (offline, gratis)
#   openai_file  → archivo completo a /v1/audio/transcriptions (precisión) [DEFAULT]
#   openai_live  → Realtime streaming (máxima velocidad percibida, ~9x costo)
# 2026-06-15: default cambiado live→file. Medido: file ~$0.36/hr vs live ~$3.3/hr
# (gpt-4o-transcribe vs gpt-realtime-whisper). Costo a cambio de ~1-1.5s más de
# latencia percibida (file ~2.5s vs live ~1.24s p50) + elimina fallbacks live.
: "${DICTATION_MODE:=openai_file}"

# ── Modelos ───────────────────────────────────────────────────────────
: "${OPENAI_REALTIME_TRANSCRIBE_MODEL:=gpt-realtime-whisper}"
: "${OPENAI_FILE_TRANSCRIBE_MODEL:=gpt-4o-transcribe}"
: "${OPENAI_CLEANUP_MODEL:=gpt-5.4-mini}"

# ── Formato del texto ─────────────────────────────────────────────────
# Por default: formato LOCAL mecánico (rápido, 0 latencia LLM, 100% fiel).
# OPENAI_POSTPROCESS=true activa el cleanup LLM (gpt-5.4-mini) — solo para
# pruebas; agrega ~1.5-2.6s y NO va en el camino crítico del dictado normal.
: "${OPENAI_POSTPROCESS:=false}"
: "${OPENAI_POSTPROCESS_MODE:=minimal}"
: "${LOCAL_FORMATTING:=true}"

# ── Timeouts del modo live (ms) ───────────────────────────────────────
: "${OPENAI_LIVE_FINAL_TIMEOUT_MS:=1200}"      # espera "ideal" del transcript final
: "${OPENAI_LIVE_MAX_WAIT_AFTER_STOP_MS:=1800}" # cap duro tras soltar el hotkey

# ── Cadena de fallback ────────────────────────────────────────────────
: "${OPENAI_LIVE_FALLBACK_TO_FILE:=true}"   # live falla → openai_file (usa WAV guardado)
: "${OPENAI_FALLBACK_TO_LOCAL:=true}"       # openai falla → whisper.cpp local

# ── Server local (whisper.cpp) ────────────────────────────────────────
: "${LOCAL_WHISPER_URL:=http://127.0.0.1:8787/inference}"

# ── Debug ─────────────────────────────────────────────────────────────
: "${DICTATION_DEBUG:=true}"
: "${DICTATION_DEBUG_LOG:=/tmp/whisper-dictation-debug.log}"

# ── Rutas runtime (estado entre los dos taps del toggle) ──────────────
: "${WD_MARKER:=/tmp/.whisper_recording}"     # grabación en curso
: "${WD_AUDIO:=/tmp/whisper_dictate.wav}"     # WAV (modos file/local + fallback de live)
: "${WD_SOX_PID:=/tmp/.whisper_sox.pid}"      # PID de sox (modos file/local)
: "${WD_LIVE_PID:=/tmp/.whisper_live.pid}"    # PID del proceso openai_live.py
: "${WD_FINALIZING:=/tmp/.whisper_finalizing}" # soltó hotkey, transcribiendo/pegando (menubar spinner)
: "${WD_FALLBACK_FLAG:=/tmp/.whisper_fallback}" # lo escribe un backend si degradó (menubar)
: "${WD_MODE_FLAG:=/tmp/.whisper_mode}"       # modo efectivo de la última corrida (menubar)

export DICTATION_MODE OPENAI_REALTIME_TRANSCRIBE_MODEL OPENAI_FILE_TRANSCRIBE_MODEL \
  OPENAI_CLEANUP_MODEL OPENAI_POSTPROCESS OPENAI_POSTPROCESS_MODE LOCAL_FORMATTING \
  OPENAI_LIVE_FINAL_TIMEOUT_MS OPENAI_LIVE_MAX_WAIT_AFTER_STOP_MS \
  OPENAI_LIVE_FALLBACK_TO_FILE OPENAI_FALLBACK_TO_LOCAL LOCAL_WHISPER_URL \
  DICTATION_DEBUG DICTATION_DEBUG_LOG \
  WD_MARKER WD_AUDIO WD_SOX_PID WD_LIVE_PID WD_FINALIZING WD_FALLBACK_FLAG WD_MODE_FLAG

# ── Loader robusto del API key ────────────────────────────────────────
# launchd y Raycast NO cargan ~/.zshrc, así que el key puede no estar en el
# entorno. Orden: entorno → profiles de zsh (export literal) → Keychain.
# NUNCA se hardcodea el valor aquí.
load_openai_key() {
  [ -n "${OPENAI_API_KEY:-}" ] && { export OPENAI_API_KEY; return 0; }
  local f k
  for f in "$HOME/.zshenv" "$HOME/.zprofile" "$HOME/.zshrc"; do
    [ -f "$f" ] || continue
    k=$(grep -E '^[[:space:]]*export[[:space:]]+OPENAI_API_KEY=' "$f" 2>/dev/null \
        | tail -1 | sed -E 's/^[^=]*=//; s/^"//; s/"$//; s/^'\''//; s/'\''$//')
    [ -n "$k" ] && { export OPENAI_API_KEY="$k"; return 0; }
  done
  k=$(security find-generic-password -s OPENAI_API_KEY -w 2>/dev/null)
  [ -n "$k" ] && { export OPENAI_API_KEY="$k"; return 0; }
  return 1
}
