# Whisper Dictation — Setup actual (para revisión)

Dictado por voz local en macOS. Toggle por hotkey: graba → transcribe → pega en el cursor.
Este documento describe **exactamente lo que está corriendo hoy**, tal cual, para que lo revises.

## Entorno

| | |
|---|---|
| Equipo | Apple M1 Pro, 32 GB RAM |
| macOS | 26.4 (build 25E246) |
| Motor | `whisper-server` de whisper.cpp (Homebrew, ggml 0.9.8) |
| Modelo | `ggml-large-v3-turbo.bin` (1.5 GB) — decoder de 4 capas |
| Backends activos | Metal (MTL), BLAS, CPU. COREML=0, OPENVINO=0 |
| Grabación | `sox` (Homebrew) |
| Trigger | Raycast Script Command con hotkey (doble-tap ⌘) → `dictate.sh` |
| Cancelar | Hotkey Cmd+Esc → `whisper-cancel.sh` (vive en Hammerspoon + Raycast cmd) |
| Menu bar | app `rumps` (Python venv) que muestra estado en vivo |
| Auto-start | 2 launchd agents (server + menubar) al login |

## Arquitectura

```
Hotkey (Raycast, doble-tap ⌘) ─→ dictate.sh ─→ whisper-toggle.sh
                                                   │
  Press 1: touch marker + sox grabando (16kHz mono 16-bit, max 300s)
  Press 2: kill sox → curl POST :8787/inference (verbose_json, language=auto, temperature=0)
                    → reconstruye texto desde segments[].words[].word (Python)
                    → filtro de alucinaciones → pbcopy + ⌘V
```

El server corre como daemon persistente con el modelo en RAM (~1.6 GB) en el puerto 8787.

---

## 1. Flags del server (launchd: `com.local.whisper-server.plist`)

```
/opt/homebrew/bin/whisper-server \
  -m /Users/g/.local/share/whisper-models/ggml-large-v3-turbo.bin \
  -l auto \
  -t 8 \
  -sns \
  --port 8787
```

- `-l auto` — detección automática de idioma (dicto en español E inglés, a veces mezclado)
- `-t 8` — 8 threads
- `-sns` — suppress non-speech tokens (anti-alucinaciones tipo "Thank you")
- **No** se pasa beam-size, best-of, ni initial-prompt → usa defaults del server.

Info del modelo al cargar (del log real):
```
type = 5 (large v3) | n_audio_layer = 32 | n_text_layer = 4 | n_vocab = 51866 | n_mels = 128
system_info: COREML = 0 | OPENVINO = 0 | MTL | NEON | ACCELERATE | OPENMP
```

---

## 2. Captura + transcripción (`whisper-toggle.sh`)

```bash
#!/bin/bash
# Toggle whisper dictation — start/stop recording, transcribe, paste
MARKER="/tmp/.whisper_recording"
PIDFILE="/tmp/.whisper_sox.pid"
AUDIO="/tmp/whisper_dictate.wav"
URL="http://127.0.0.1:8787/inference"
SOX="$(command -v sox || echo /opt/homebrew/bin/sox)"

if [ -f "$MARKER" ]; then
  rm -f "$MARKER"
  # Kill sox by saved PID (reliable), fallback to pkill
  if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
  fi
  pkill -f "sox.*whisper_dictate" 2>/dev/null
  sleep 0.2
  [ ! -s "$AUDIO" ] && exit 0
  RESPONSE=$(curl -s --max-time 120 "$URL" -F "file=@${AUDIO}" -F "response_format=verbose_json" -F "language=auto" -F "temperature=0")
  rm -f "$AUDIO"

  # Rebuild text from word-level tokens (avoids server line-wrapping that breaks
  # mid-word, e.g. "pes\na" -> "pes a"). Drop common hallucinations.
  TEXT=$(printf '%s' "$RESPONSE" | /usr/bin/env python3 -c '
import sys, json, re
try:
    d = json.loads(sys.stdin.read())
except Exception:
    sys.exit(0)
words = [w["word"] for s in d.get("segments", []) for w in s.get("words", [])]
txt = "".join(words) if words else d.get("text", "")
txt = re.sub(r"\s+", " ", txt).strip()
HALLUCINATIONS = {
    "thank you.", "thank you", "thanks for watching.", "thanks for watching",
    "please subscribe.", "please subscribe", "you", ".", "...", "....",
}
low = txt.lower()
if low in HALLUCINATIONS:
    sys.exit(0)
# Repeated-phrase hallucination: "thank you, thank you, thank you..." etc.
# If the output is a short phrase (<=4 words) repeated 3+ times, drop it.
tokens = [t for t in re.split(r"[\s,.\-!?]+", low) if t]
for n in (1, 2, 3, 4):
    if len(tokens) >= n * 3 and len(set(tuple(tokens[i:i+n]) for i in range(0, len(tokens) - n + 1, n))) == 1:
        sys.exit(0)
sys.stdout.write(txt)
')

  [ -z "$TEXT" ] && exit 0
  printf '%s' "$TEXT" | pbcopy
  osascript -e 'tell application "System Events" to keystroke "v" using command down'
else
  rm -f "$AUDIO"
  # Kill any orphaned sox from previous runs
  pkill -f "sox.*whisper_dictate" 2>/dev/null
  touch "$MARKER"
  "$SOX" -d -q -r 16000 -c 1 -b 16 -t wav "$AUDIO" trim 0 300 &
  echo $! > "$PIDFILE"
  disown
fi
```

**Captura sox:** `sox -d -q -r 16000 -c 1 -b 16 -t wav` → micro default, 16 kHz, mono, 16-bit.
Sin normalización de ganancia, sin supresión de ruido, sin AGC. Tope 300 s (`trim 0 300`).

**Request de transcripción:** `verbose_json`, `language=auto`, `temperature=0`. Sin prompt/vocabulario.

---

## 3. Wrappers de Raycast

`dictate.sh` (toggle):
```bash
#!/bin/bash
# @raycast.title Dictate  | @raycast.mode silent | @raycast.icon 🎙
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/whisper-toggle.sh" 2>/dev/null
if [ -f /tmp/.whisper_recording ]; then echo "Recording..."; else echo "$(pbpaste)"; fi
```

`cancel.sh` (cancelar):
```bash
#!/bin/bash
# @raycast.title Cancel Dictation | @raycast.mode silent | @raycast.icon ✕
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/whisper-cancel.sh" 2>/dev/null
```

---

## 4. Cancelar grabación (`whisper-cancel.sh`)

```bash
#!/bin/bash
# Aborta la GRABACIÓN sin transcribir ni pegar. No-op si no hay grabación activa.
MARKER="/tmp/.whisper_recording"
PIDFILE="/tmp/.whisper_sox.pid"
AUDIO="/tmp/whisper_dictate.wav"
[ -f "$MARKER" ] || { echo "Nada que cancelar"; exit 0; }
if [ -f "$PIDFILE" ]; then kill "$(cat "$PIDFILE")" 2>/dev/null; rm -f "$PIDFILE"; fi
pkill -f "sox.*whisper_dictate" 2>/dev/null
rm -f "$AUDIO"
rm -f "$MARKER"
echo "Grabación cancelada"
```

Hotkey Cmd+Esc también ligado en Hammerspoon (`~/.hammerspoon/init.lua`) que ejecuta `whisper-cancel.sh`.

---

## 5. Pipeline de transcripción (nota de diseño)

El server line-wrappea `response_format=text` cada ~60 chars y rompe palabras a la mitad
("pesa" → "pes\na"). Por eso se pide `verbose_json` y se reconstruye el texto desde
`segments[].words[].word` con Python (`"".join(words)`), luego `re.sub(r"\s+", " ", txt).strip()`
para salida de un solo párrafo.

---

## 6. Menu bar (`menubar.py`, rumps)

App de status que observa `/tmp/.whisper_recording` y `/tmp/whisper_dictate.wav`:
`∿` idle · `🔴 REC mm:ss` grabando · `🟠` (>1 min) · `⏳` transcribiendo · `⚠️ off` server caído.
Auto-discard al llegar a 5 min. Menú: Toggle / Restart server / Process / Discard / Quit.
(Periférico al dictado; incluido por completitud.)

---

## 7. Performance actual (medido, M1 Pro)

| Audio | Tiempo de transcripción |
|---|---|
| 10 s | ~1.4 s |
| 1 min | ~3.9 s (≈15× real-time) |
| 5 min | ~19 s |

`flash-attn` y Metal GPU activos. CoreML NO (el build de Homebrew no lo soporta).

---

## 8. Observación cruda de los logs

Con `language=auto`, la detección de idioma a veces sale con baja confianza
(ejemplos reales del `server.log`):
```
auto-detected language: en (p = 0.502872)
auto-detected language: en (p = 0.709708)
auto-detected language: es (p = 0.997680)
```

---

## 9. Operaciones

```bash
# Server
launchctl unload ~/Library/LaunchAgents/com.local.whisper-server.plist
launchctl load   ~/Library/LaunchAgents/com.local.whisper-server.plist
curl -s http://127.0.0.1:8787/

# Menu bar
launchctl unload ~/Library/LaunchAgents/com.local.whisper-menubar.plist
launchctl load   ~/Library/LaunchAgents/com.local.whisper-menubar.plist

# Logs
tail -f ~/Dev/whisper-dictation/server.log
tail -f ~/Dev/whisper-dictation/menubar.log
```

## Dependencias

- Homebrew: `whisper-cpp`, `sox`
- Python venv (`~/Dev/whisper-dictation/.venv`): `rumps`
- Modelo: `~/.local/share/whisper-models/ggml-large-v3-turbo.bin`
