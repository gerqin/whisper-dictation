# Whisper Dictation — Handoff ARCHIVE

Sesiones viejas. El HANDOFF.md vigente vive en la raíz.

---

## Arquitectura original (solo local whisper.cpp) — superada por el sistema de 3 modos

Dictado por voz local en macOS usando whisper-cpp (large-v3-turbo). Toggle con hotkey:
graba → transcribe → pega. Menu bar app muestra estado en vivo.

### Server local (sigue siendo el modo `local` / fallback offline)
```
whisper-server -m ggml-large-v3-turbo.bin -l auto -t 8 -sns --port 8787
```
- `-t 8` threads · `-sns` suppress non-speech (anti-alucinaciones) · `-l auto` ES/EN

### Pipeline de transcripción local (modo `local`)
El server line-wrappea `response_format=text` cada ~60 chars y rompe palabras
("pesa" → "pes\na"). Solución: `verbose_json` + reconstruir desde
`segments[].words[].word` con Python (`"".join(words)`), luego
`re.sub(r'\s+', ' ', txt).strip()`. Implementado en `dictation_common.local_transcribe()`.

### Performance del modelo local (M1 Pro)
| Audio | Tiempo |
|---|---|
| 10s | ~1.4s |
| 1 min | ~3.9s (15x real-time) |
| 5 min | ~19s |
`flash-attn` + Metal GPU activos. CoreML NO (el build de brew no lo soporta).
Mejora posible no implementada: recompilar whisper.cpp con `WHISPER_COREML=1` (~2-3x encoder).

### Daemons launchd
- `com.local.whisper-server.plist` — server :8787 (sigue activo para modo local/fallback)
- `com.local.whisper-menubar.plist` — menubar app
