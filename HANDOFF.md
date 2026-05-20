# Whisper Dictation — Handoff

## Qué es
Dictado por voz local en macOS usando whisper-cpp (large-v3-turbo). Toggle con hotkey: graba → transcribe → pega. Menu bar app muestra estado en vivo (idle / REC con timer / transcribiendo / off).

## Estado actual: FUNCIONAL
- Dictado end-to-end working
- Server daemon en port 8787, modelo en RAM (~2GB), auto-start al login
- Menu bar app con timer de grabación en vivo, auto-start al login
- Hard timeout sox 5min + auto-discard al alcanzar el límite (sin transcribir)
- Output limpio (single-paragraph, sin word-breaks de word-wrap)
- Filtro de alucinaciones: exact-match + frase corta repetida 3+ veces
- Repo: https://github.com/gerqin/whisper-dictation

## Arquitectura

```
Hotkey (Raycast) ─→ dictate.sh ─→ whisper-toggle.sh
                                      │
                                      ├─ Press 1: touch marker + sox grabando (max 300s)
                                      │
                                      └─ Press 2: kill sox → curl :8787/inference (verbose_json)
                                                         → reconstruct text from words[] (Python)
                                                         → pbcopy + ⌘V

Menu bar (rumps, port-less): observa /tmp/.whisper_recording + /tmp/whisper_dictate.wav
  🎙 idle | 🔴 REC mm:ss | 🟠 (>1min) | ⏳ transcribing | ⚠️ off
  Al llegar a 5min: auto-discard (kill sox + borra archivos + notif), NO transcribe.
  Menú: Toggle / Restart server / Process recording / Discard recording / Quit
    (Process/Discard activos sólo durante grabación: cortar antes de tiempo o cancelar)
```

### Componentes
| Componente | Path | Rol |
|---|---|---|
| whisper-server | daemon launchd port 8787 | Modelo en RAM, HTTP inference |
| whisper-toggle.sh | ~/Dev/whisper-dictation/ | Toggle start/stop + transcribe + paste |
| dictate.sh | ~/Dev/whisper-dictation/ | Raycast Script Command wrapper |
| menubar.py | ~/Dev/whisper-dictation/ | rumps menu bar app (status + manual toggle) |
| install.sh | ~/Dev/whisper-dictation/ | Instalador portable (genera plists) |
| uninstall.sh | ~/Dev/whisper-dictation/ | Desinstalador (server + menubar) |
| server plist | ~/Library/LaunchAgents/com.local.whisper-server.plist | Daemon server |
| menubar plist | ~/Library/LaunchAgents/com.local.whisper-menubar.plist | Daemon menubar |
| venv | ~/Dev/whisper-dictation/.venv | Python + rumps (no contamina sistema) |
| modelo | ~/.local/share/whisper-models/ggml-large-v3-turbo.bin | 1.5GB |

### Dependencias
- brew: whisper-cpp, sox
- Python venv: rumps

## Configuración del server (flags clave)
```
whisper-server -m <model> -l auto -t 8 -sns --port 8787
```
- `-t 8` — 8 threads (M1 Pro 8 perf cores)
- `-sns` — suppress non-speech tokens (anti-hallucinations "Thank you" etc.)
- `-l auto` — detecta español/inglés/mezcla

## Pipeline de transcripción
Server line-wrappea `response_format=text` cada ~60 chars, rompiendo palabras
("pesa" → "pes\na"). Solución: `verbose_json` + reconstruir desde `segments[].words[].word`
con Python. Cada `word` es atómico, `''.join(words)` da texto perfecto.
Final: `re.sub(r'\s+', ' ', txt).strip()` para single-paragraph output.

## Performance (M1 Pro, 32GB)
| Audio | Tiempo transcripción |
|---|---|
| 10s | ~1.4s |
| 1 min | ~3.9s (15x real-time) |
| 5 min | ~19s |

`flash-attn` activo, Metal GPU activo, CoreML NO (build de brew no lo soporta).
Para 2-3x más speed: compilar whisper.cpp desde source con `WHISPER_COREML=1`
y convertir encoder a `.mlmodelc`. No implementado.

## Operaciones
```bash
# Server
launchctl unload ~/Library/LaunchAgents/com.local.whisper-server.plist
launchctl load   ~/Library/LaunchAgents/com.local.whisper-server.plist
curl -s http://127.0.0.1:8787/

# Menu bar app
launchctl unload ~/Library/LaunchAgents/com.local.whisper-menubar.plist
launchctl load   ~/Library/LaunchAgents/com.local.whisper-menubar.plist

# Logs
tail -f ~/Dev/whisper-dictation/server.log
tail -f ~/Dev/whisper-dictation/menubar.log
```

## Pendientes / posibles mejoras
- **CoreML build** — recompilar whisper.cpp con `WHISPER_COREML=1` para ANE encoder
  acceleration (~2-3x speedup en encoder). Trade-off: queda fuera del brew, hay
  que mantener manualmente. Plan: clonar whisper.cpp, brew install coremltools-deps,
  `WHISPER_COREML=1 cmake -B build && cmake --build build`, convertir encoder
  con `models/generate-coreml-model.sh`, repointar plist al binario nuevo.
- **Models submenu** en menubar.py — listar `~/.local/share/whisper-models/*.bin` y
  permitir switch (editar plist + reload daemon).
- **Server health en menubar** — botón Start/Stop server además del Restart actual.
- **Recording sound feedback** — beep corto al iniciar/parar (afplay con sonido sistema).
