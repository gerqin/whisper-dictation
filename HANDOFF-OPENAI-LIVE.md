# Handoff — Whisper Dictation con OpenAI (continuación)

Estado de implementación para continuar el trabajo. Proyecto:
`~/Dev/whisper-dictation/` (macOS, M1 Pro 32GB, macOS 26.4, Python 3.14 venv).
Dictado por voz: hotkey toggle (Raycast, doble-tap ⌘) → graba → transcribe → pega
con `pbcopy` + ⌘V. Cancel = ⌘+Esc (Hammerspoon → `whisper-cancel.sh`).

## Qué se construyó (DONE)

Sistema de 3 modos seleccionables por `DICTATION_MODE` en `config.sh`. **El mismo
hotkey de siempre** dispara `whisper-toggle.sh`, que lee el modo y despacha. No se
reasignó ningún atajo.

| Modo | Backend | Estado |
|---|---|---|
| `openai_live` (DEFAULT) | OpenAI Realtime streaming, modelo `gpt-realtime-whisper` | ✅ funcionando en vivo |
| `openai_file` | `POST /v1/audio/transcriptions`, `gpt-4o-transcribe` + prompt de contexto | ✅ implementado |
| `local` | whisper.cpp local en :8787 (`ggml-large-v3-turbo.bin`) | ✅ (fallback offline) |

Cadena de fallback: `openai_live` → `openai_file` → `local` (configurable).

### Archivos
```
config.sh              env defaults + loader de OPENAI_API_KEY (env → ~/.zshrc → keychain)
whisper-toggle.sh      orquestador toggle (start/stop, despacha por modo)
whisper-cancel.sh      cancela (SIGTERM al PID live / mata sox); cubre los 3 modos
openai_live.py         streaming async: captura(sox→PCM24k) + stream(WS) + recv + fallback
openai_file.py         transcripción de archivo (gpt-4o-transcribe)
cleanup_openai.py      postproceso MÍNIMO (gpt-5.4-mini); fail-open; guardrail anti-reescritura
hallucination_filter.py filtro compartido (exact-match + frase repetida)
dictation_common.py    run_chain (fallback), paste, debug_log, file_mode_main, write_wav
paste.sh               pbcopy + ⌘V
menubar.py             status app rumps (SIN actualizar para multi-modo — pendiente menor)
```

### Contrato Realtime verificado EN VIVO (no de memoria)
- WS: `client.realtime.connect(extra_query={"intent":"transcription"})` (SDK openai 2.41.1)
- session.update: `{"type":"transcription","audio":{"input":{
  "format":{"type":"audio/pcm","rate":24000},
  "transcription":{"model":"gpt-realtime-whisper"},"turn_detection":null}}}`
- audio: `input_audio_buffer.append(audio=<base64 pcm16 24kHz mono>)`, luego `.commit()`
- eventos: `conversation.item.input_audio_transcription.delta` (`.delta`) y `.completed` (`.transcript`)
- captura: `sox -d -r 24000 -c 1 -b 16 -e signed-integer -t raw -` (PCM crudo a stdout)
- finalizar turno: SIGUSR1 al proceso live (segundo tap). SIGTERM = cancelar sin pegar.

### Config (`config.sh`)
```
DICTATION_MODE=openai_live
OPENAI_REALTIME_TRANSCRIBE_MODEL=gpt-realtime-whisper
OPENAI_FILE_TRANSCRIBE_MODEL=gpt-4o-transcribe
OPENAI_CLEANUP_MODEL=gpt-5.4-mini
OPENAI_POSTPROCESS=true            # postproceso de formato (ver problema #1)
OPENAI_POSTPROCESS_MODE=minimal
OPENAI_LIVE_FINAL_TIMEOUT_MS=1200  # espera "ideal" del final
OPENAI_LIVE_MAX_WAIT_AFTER_STOP_MS=1800  # cap duro tras soltar
OPENAI_LIVE_FALLBACK_TO_FILE=true
OPENAI_FALLBACK_TO_LOCAL=true
DICTATION_DEBUG=true
DICTATION_DEBUG_LOG=/tmp/whisper-dictation-debug.log
```
`OPENAI_API_KEY` NO se hardcodea; el loader la lee de `~/.zshrc` (export literal) /
keychain. En la prueba real Raycast SÍ la resolvió.

## Qué está validado (VERIFIED)

1. **Contrato Realtime en vivo** (probe con voz `say`): 0.80s soltar→final con 4.4s de audio.
2. **Fidelidad del cleanup** — Tests 1-5 del spec: 0 traducciones, Spanglish preservado
   (working, flow, dashboard, CPL, Codex, carousel intactos). 2 de 5 con micro-variación
   de puntuación, ninguna reescritura.
3. **Auditoría codex: 4 rondas → GATE PASS** (0 P1). Se corrigieron: race PID/marker,
   captura separada del streaming (no se pierde audio si el WS cae), WAV de fallback
   por-PID, ownership-guard en cleanup, timeout en ops del WS, `set -u` en config.
4. **Prueba E2E real con voz del usuario** (1 dictado, abajo). Funcionó: `openai_live`,
   sin fallback, pegó correcto.

## PROBLEMA PRINCIPAL: latencia (datos reales de 1 dictado)

Dictado real de 10.48s de audio (`/tmp/whisper-dictation-debug.log`):
```
mode: openai_live      fallback_used: False     over_ideal_wait: False
transcription_latency_s: 2.87
cleanup_latency_s: 2.59
total_latency_s: 5.65   (soltar hotkey → texto pegado)
```
Raw casi perfecto; el cleanup solo corrigió un desliz ("Todos este"→"Todo este").

Dos cuellos detectados:

### #1 — El cleanup cuesta ~2.59s (casi la mitad del total)
`gpt-5.4-mini` con postproceso minimal agrega ~1.1–2.6s y muchas veces solo retoca
puntuación. **Acción inmediata:** `OPENAI_POSTPROCESS=false` → baja a ~2.9s. Decisión
del usuario: ¿vale el postproceso esa latencia? Probable que NO para la mayoría.

### #2 — ~1.7s de teardown del WebSocket EN EL CAMINO CRÍTICO (hipótesis fuerte)
`over_ideal_wait: False` ⇒ el transcript final **llegó en <1.2s** de soltar. Pero
`transcription_latency_s` = 2.87s. El gap (~1.7s) NO es del modelo: es el cierre del
`async with client.realtime.connect()` (teardown del WS) que ocurre ANTES de pegar.
El probe daba 0.8s porque no medía ese cierre.

**Fix propuesto (NO implementado aún):** reordenar `openai_live.py` para **pegar
apenas llega el `.completed`**, y cerrar la conexión después / en background. Objetivo:
total ~1–1.5s sin cleanup. Riesgo a revisar: pegar antes del `__aexit__` y que el
cierre/limpieza no pise el paste ni deje el WS a medias.

## NEXT (pendientes)

- [ ] **Apagar cleanup** (`OPENAI_POSTPROCESS=false`) y medir varios dictados (n>1; 1 muestra no es validación).
- [ ] **Optimizar paste-antes-de-teardown** en `openai_live.py` (problema #2) → apuntar a ~1–1.5s.
- [ ] Más muestras de latencia por largo de audio (5s, 15s, 30s) para curva real.
- [ ] Decidir si el cleanup se queda (y con qué modelo más rápido, p.ej. `gpt-4o-mini`/`nano`) o se elimina.
- [ ] `menubar.py`: mostrar modo activo / aviso de fallback (cosmético, bajo).
- [ ] Residual conocido (P2, no crítico): si se cambia `DICTATION_MODE` a local/file Y se
      re-dispara dentro de la ventana ~1s en que un dictado live está pegando, el proceso
      viejo podría borrar el marker del nuevo. Cerrar = paths de marker por-sesión.
- [ ] Nada commiteado aún: todo en working tree de `~/Dev/whisper-dictation` (branch master).

## Cómo probar / operar
```bash
# Cambiar modo: editar DICTATION_MODE en config.sh
# Ver latencia del último dictado:
tail -40 /tmp/whisper-dictation-debug.log
# El hotkey actual (doble-tap ⌘ en Raycast → dictate.sh → whisper-toggle.sh) ya usa el modo nuevo.
```
