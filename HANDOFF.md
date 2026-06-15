# Whisper Dictation — Handoff

Dictado por voz en macOS (M1 Pro, macOS 26.4, Python 3.14 venv). Hotkey toggle
(Raycast doble-tap ⌘) → graba → transcribe → pega (`pbcopy`+⌘V). Cancel ⌘+Esc.
Repo: github.com/gerqin/whisper-dictation. Estado: **FUNCIONAL, sistema de 3 modos.**

## Qué es (arquitectura actual)
Sistema de 3 modos por `DICTATION_MODE` en `config.sh` (mismo hotkey para todos):
- `openai_live` (DEFAULT) — OpenAI Realtime streaming, `gpt-realtime-whisper`. Modo principal.
- `openai_file` — `gpt-4o-transcribe` (archivo, más preciso, más lento).
- `local` — whisper.cpp :8787 (`ggml-large-v3-turbo.bin`), offline.

Fallback: `openai_live` → `openai_file` → `local`. Formato por default: LOCAL mecánico
(`local_format.py`), sin LLM. Cleanup LLM (`gpt-5.4-mini`) disponible con `OPENAI_POSTPROCESS=true`.

Archivos clave: `config.sh`, `whisper-toggle.sh` (orquestador), `whisper-cancel.sh`,
`openai_live.py` (async: captura sox→PCM24k separada del streaming WS + paste-before-teardown),
`openai_file.py`, `local_format.py`, `cleanup_openai.py`, `hallucination_filter.py`,
`dictation_common.py` (run_chain/paste/debug_log/format_output/file_mode_main), `paste.sh`,
`menubar.py`, `ops/bench-latency.py`. Detalle modo local en HANDOFF-ARCHIVE.md.

## NEXT
<!-- ancla ASCII única; backlog durable de checkboxes -->

### ▶ AHORA
- [ ] **Decisión de puntuación** (flagged 2026-06-15): el formato local NO agrega comas
      de estilo ("Okay so" en vez de "Okay, so"; falta coma antes de "and"). Es fiel pero
      pelado. Opciones: (a) aceptarlo; (b) re-activar cleanup con modelo más rápido
      (`gpt-4o-mini`/`nano`) para meter comas con menos latencia que `gpt-5.4-mini`;
      (c) reglas locales de coma (riesgoso, mecánico no distingue bien). Decidir antes de seguir.
- [ ] **Completar benchmark**: faltan ~8 dictados de 5-10s para p50/p90 reales
      (llevamos n=2). Correr `ops/bench-latency.py` cuando haya ~10.

### Backlog
- [ ] menubar: mostrar modo activo / aviso de fallback (cosmético, bajo).
- [ ] Residual P2 conocido: si se cambia `DICTATION_MODE` a local/file Y se re-dispara dentro
      de la ventana ~1s de un live finalizando, el viejo podría borrar el marker del nuevo.
      Cerrar = paths de marker por-sesión. No pasa en uso normal.
- [ ] Evaluar `completed_to_paste_s` ~0.44s (osascript ⌘V) — ¿optimizable?
- [ ] Opcional: 3 hotkeys = 3 modos (hoy es 1 hotkey + editar `config.sh`).
- [ ] Mejora local (no impl.): whisper.cpp con `WHISPER_COREML=1` (~2-3x encoder) para modo local.

### Cerrados (2026-06-15)
- [x] Sistema 3 modos implementado; auditado con codex (varias rondas, terminó 0 P1, sin doble-paste).
- [x] **Paste-before-teardown** en `openai_live.py`: visible_latency ~5s → **~1.24s** (el ~2s de
      cierre del WS ahora va FUERA del camino crítico).
- [x] Cleanup LLM **off** por default + `LOCAL_FORMATTING=true` (formato mecánico).
- [x] Métricas detalladas en debug log (`visible_latency_s` = soltar→pegado) + `ops/bench-latency.py`.
- [x] Menubar: 🔴 fija al grabar + spinner `◐◓◑◒` al procesar; quitados los pop-ups de Raycast.
- [x] `local_format` protege URLs/emails/paths.

## OPEN COMMITMENTS
- [ ] (2026-06-15, "haz ~10 dictados y corro ops/bench-latency.py para darte p50/p90") —
      pendiente: el usuario dicte ~8 más; yo mido. Metas: p50 ≤1.2s, p90 ≤1.8s.

## VERIFY STATUS
- **VERIFIED** `visible_latency_s` ~1.24-1.26s en `openai_live` nuevo — `tail /tmp/whisper-dictation-debug.log`:
  2 dictados reales (18.68s audio → 1.239s; English → 1.264s); teardown 2.08s fuera del path crítico;
  cleanup 0.0; fallback False; used_final_transcript True.
- **VERIFIED** contrato Realtime en vivo (`gpt-realtime-whisper`, `intent=transcription`, eventos
  `...input_audio_transcription.completed`) — probe con `say` (0.80s) + dictados reales.
- **VERIFIED** `local_format` no rompe URLs/emails/paths ni traduce — test directo (juan@empresa.com,
  https://dopabi.com/dashboard, config.sh intactos).
- **VERIFIED** fidelidad cleanup LLM (Tests 1-5 del spec): 0 traducciones, Spanglish preservado.
- **UNVERIFIED** p50/p90 sobre n=10 — solo n=2 medidos.

## METHODS / RUNBOOK
```bash
# Benchmark de latencia (desde el debug log)
.venv/bin/python ops/bench-latency.py [--last 10]
# Último dictado / métricas
tail -40 /tmp/whisper-dictation-debug.log
# Cambiar modo: editar DICTATION_MODE en config.sh  (openai_live|openai_file|local)
# Probar cleanup LLM: OPENAI_POSTPROCESS=true en config.sh
# Daemons (server local + menubar)
launchctl unload ~/Library/LaunchAgents/com.local.whisper-{server,menubar}.plist
launchctl load   ~/Library/LaunchAgents/com.local.whisper-{server,menubar}.plist
```
- `OPENAI_API_KEY`: NO hardcodeada; `config.sh:load_openai_key` la lee de `~/.zshrc`/keychain.
- `openai_live.py` se lanza fresco cada dictado (no hay daemon que recargar). menubar SÍ es daemon.
- `SETUP-ACTUAL.md` / `HANDOFF-OPENAI-LIVE.md`: snapshots para pegar a ChatGPT (no canónicos).
