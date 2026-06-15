#!/usr/bin/env python3
"""Backend openai_live — transcripción Realtime en streaming (modo principal).

Se lanza al PRIMER tap (empieza a grabar+streamear). Al SEGUNDO tap el
orquestador le manda SIGUSR1 -> finaliza el turno, toma el transcript final,
limpia (opcional), y pega. SIGTERM (cancelar) aborta sin pegar.

Diseño validado: audio se procesa mientras hablas, así la latencia percibida
soltar->texto es ~sub-segundo. Si la conexión live falla, cae a la cadena
openai_file -> local usando el WAV que va guardando en paralelo.
"""
import asyncio
import base64
import contextlib
import os
import signal
import sys
import time

import dictation_common as dc
from hallucination_filter import is_hallucination

RATE = 24000
CHUNK = RATE * 2 // 10  # 100 ms @ 24kHz mono 16-bit

# ── Señales a nivel módulo: capturan un STOP/CANCEL que llegue ANTES de que
# el loop asyncio instale sus handlers (ventana entre exec y conexión). Sin
# esto, un SIGUSR1 temprano usaría la disposición default (terminar) y se
# perdería el turno. Estos flags se vuelcan a los Events apenas arranca run().
_EARLY = {"stop": False, "cancel": False}
signal.signal(signal.SIGUSR1, lambda *_: _EARLY.__setitem__("stop", True))
signal.signal(signal.SIGTERM, lambda *_: (_EARLY.__setitem__("stop", True),
                                          _EARLY.__setitem__("cancel", True)))

MARKER = dc.env("WD_MARKER", "/tmp/.whisper_recording")
LIVE_PID = dc.env("WD_LIVE_PID", "/tmp/.whisper_live.pid")
FINALIZING = dc.env("WD_FINALIZING", "/tmp/.whisper_finalizing")
# WAV de fallback POR-PID (no el compartido WD_AUDIO): así un START nuevo que
# hace `rm -f WD_AUDIO` no borra el audio de una sesión live finalizando.
FALLBACK_WAV = f"/tmp/whisper_live_{os.getpid()}.wav"
MODEL = dc.env("OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-realtime-whisper")
MAX_WAIT = int(dc.env("OPENAI_LIVE_MAX_WAIT_AFTER_STOP_MS", "1800")) / 1000.0
WS_OP_TIMEOUT = 5.0  # cap por operación WS (append/commit); si excede -> fallback


def _cleanup_runtime():
    # FALLBACK_WAV (por-PID) y FINALIZING (transitorio): siempre seguro borrarlos.
    for p in (FALLBACK_WAV, FINALIZING):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    # Ownership guard sobre el estado COMPARTIDO (marker/pid): si otra sesión
    # ya sobrescribió WD_LIVE_PID con su PID, no lo tocamos — es del nuevo.
    try:
        owner = open(LIVE_PID).read().strip() == str(os.getpid())
    except Exception:
        owner = True  # sin pid file -> asumimos que es nuestro
    if not owner:
        return
    for p in (LIVE_PID, MARKER):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


async def run():
    stop = asyncio.Event()      # SIGUSR1: soltar hotkey -> finalizar
    cancel = asyncio.Event()    # SIGTERM: cancelar -> abortar sin pegar
    t_stop = [None]             # instante de soltar el hotkey (SIGUSR1) = inicio de latencia visible

    def _on_stop():
        if t_stop[0] is None:
            t_stop[0] = time.time()
        stop.set()

    def _on_cancel():
        if t_stop[0] is None:
            t_stop[0] = time.time()
        cancel.set()
        stop.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGUSR1, _on_stop)
    loop.add_signal_handler(signal.SIGTERM, _on_cancel)
    if _EARLY["stop"]:
        _on_stop()
    if _EARLY["cancel"]:
        _on_cancel()

    with open(LIVE_PID, "w") as f:
        f.write(str(os.getpid()))

    pcm = bytearray()
    deltas = []
    final = {"text": None, "failed": False, "error": None, "t": None}
    done = asyncio.Event()
    live_ok = False
    audio_q = asyncio.Queue()
    t_commit = [None]
    t_paste = [None]
    pasted = [False]
    res = {"raw": "", "final_text": "", "method": "-", "clean_lat": 0.0,
           "mode": "openai_live", "fell_back": False, "used_deltas": False}

    # ── sox: micro -> PCM16 24kHz mono crudo a stdout ─────────────────
    sox = await asyncio.create_subprocess_exec(
        "sox", "-d", "-q", "-r", str(RATE), "-c", "1", "-b", "16",
        "-e", "signed-integer", "-t", "raw", "-", "trim", "0", "300",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )

    # ── Captura: corre SIEMPRE, independiente del WS. Llena `pcm` (para el
    # fallback file/local) y empuja a una cola que el streamer drena al WS.
    # Así, si la conexión live falla, el audio NO se pierde. ──────────────
    async def capture():
        while not stop.is_set():
            try:
                chunk = await asyncio.wait_for(sox.stdout.read(CHUNK), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            if not chunk:
                break
            pcm.extend(chunk)
            audio_q.put_nowait(chunk)
        try:
            sox.terminate()
        except ProcessLookupError:
            pass
        try:
            rest = await asyncio.wait_for(sox.stdout.read(), timeout=0.3)
            if rest:
                pcm.extend(rest)
                audio_q.put_nowait(rest)
        except Exception:
            pass
        audio_q.put_nowait(None)  # sentinela de fin de audio

    capture_task = asyncio.create_task(capture())

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        async with client.realtime.connect(extra_query={"intent": "transcription"}) as conn:
            await conn.session.update(session={
                "type": "transcription",
                "audio": {"input": {
                    "format": {"type": "audio/pcm", "rate": RATE},
                    "transcription": {"model": MODEL},
                    "turn_detection": None,
                }},
            })

            async def stream():
                # Drena la cola de captura hacia el WS hasta el sentinela.
                # Cada op del WS va con timeout: si el socket se traba sin lanzar,
                # el TimeoutError propaga -> except -> live_ok=False -> fallback.
                while True:
                    chunk = await audio_q.get()
                    if chunk is None:
                        break
                    if not cancel.is_set():
                        await asyncio.wait_for(
                            conn.input_audio_buffer.append(audio=base64.b64encode(chunk).decode()),
                            timeout=WS_OP_TIMEOUT)
                if not cancel.is_set():
                    await asyncio.wait_for(conn.input_audio_buffer.commit(), timeout=WS_OP_TIMEOUT)
                    t_commit[0] = time.time()

            async def recv():
                async for ev in conn:
                    t = ev.type
                    if t.endswith("input_audio_transcription.delta"):
                        deltas.append(getattr(ev, "delta", "") or "")
                    elif t.endswith("input_audio_transcription.completed"):
                        final["text"] = getattr(ev, "transcript", None)
                        final["t"] = time.time()
                        done.set()
                        return
                    elif t.endswith("input_audio_transcription.failed"):
                        final["failed"] = True
                        done.set()
                        return
                    elif t == "error":
                        final["error"] = str(getattr(ev, "error", ev))
                        done.set()
                        return

            recv_task = asyncio.create_task(recv())
            try:
                await stream()  # retorna tras el sentinela (es decir, tras stop)
                if not cancel.is_set():
                    # Esperar el transcript final hasta el cap duro (MAX_WAIT).
                    try:
                        await asyncio.wait_for(done.wait(), timeout=MAX_WAIT)
                    except asyncio.TimeoutError:
                        pass
            finally:
                # SIEMPRE cancelar+await recv: no deja tareas colgadas. final["text"]
                # se lee después, así un 'completed' del borde igual se aprovecha.
                recv_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await recv_task

            # ── PASTE-BEFORE-TEARDOWN: pegar AQUÍ, antes de cerrar el WS ──
            # El cierre del WebSocket (~2s) NO debe bloquear el paste; por eso
            # formateamos y pegamos dentro del `async with`, y el teardown ocurre
            # al salir (fuera del camino crítico que siente el usuario).
            if not cancel.is_set():
                raw = (final["text"] or "").strip() or "".join(deltas).strip()
                if raw and not is_hallucination(raw):
                    res["raw"] = raw
                    res["used_deltas"] = final["text"] is None
                    ftext, clat, method = dc.format_output(raw)
                    res["method"] = method
                    res["clean_lat"] = clat
                    if method == "cleanup-empty":
                        pasted[0] = True   # LLM lo juzgó alucinación -> nada que pegar, sin fallback
                    elif ftext:
                        dc.paste(ftext)
                        t_paste[0] = time.time()
                        res["final_text"] = ftext
                        pasted[0] = True
            live_ok = True
    except Exception as e:  # noqa: BLE001 — conexión live cayó -> fallback
        sys.stderr.write(f"[openai_live] live error: {e}\n")
        live_ok = False
    finally:
        # Esperar SIEMPRE a que la captura termine (corre hasta stop): así
        # `pcm` queda completo para el fallback aunque el WS haya muerto.
        with contextlib.suppress(Exception):
            await capture_task
        try:
            sox.kill()
        except Exception:
            pass

    t_ws_closed = time.time()

    # ── Cancelado: abortar sin pegar ──────────────────────────────────
    if cancel.is_set():
        _cleanup_runtime()
        return

    # ── Fallback SOLO si NO se pegó (live falló o no produjo texto usable).
    # Si ya pegamos, NO hacemos fallback aunque el cierre del WS haya fallado. ─
    if not pasted[0]:
        chain = []
        if dc.env_bool("OPENAI_LIVE_FALLBACK_TO_FILE", True):
            chain.append("openai_file")
        if dc.env_bool("OPENAI_FALLBACK_TO_LOCAL", True):
            chain.append("local")
        if chain and len(pcm) > RATE:  # al menos ~0.5s de audio
            dc.write_wav(bytes(pcm), FALLBACK_WAV)
            ftext, fmode, _flat, _fb = dc.run_chain(FALLBACK_WAV, chain)
            if ftext:
                res["raw"] = ftext
                res["mode"] = fmode
                res["fell_back"] = True
                final_text, clat, method = dc.format_output(ftext)
                res["method"], res["clean_lat"] = method, clat
                if method != "cleanup-empty":
                    final_text = final_text or ftext
                    dc.paste(final_text)
                    t_paste[0] = time.time()
                    res["final_text"] = final_text
                    pasted[0] = True

    # ── Métricas (la principal: visible_latency_s = soltar hotkey -> pegado) ─
    def _d(a, b):
        return round(a - b, 3) if (a is not None and b is not None) else None
    audio_dur = round(len(pcm) / (RATE * 2), 2)
    visible = _d(t_paste[0], t_stop[0])
    dc.set_flags(res["mode"], res["fell_back"])
    dc.debug_log(
        mode=res["mode"], method=res["method"], audio_duration_s=audio_dur,
        stop_to_commit_s=_d(t_commit[0], t_stop[0]),
        commit_to_completed_s=_d(final["t"], t_commit[0]),
        completed_to_paste_s=_d(t_paste[0], final["t"]),
        visible_latency_s=visible,
        teardown_latency_s=_d(t_ws_closed, t_paste[0]),
        cleanup_latency_s=round(res["clean_lat"], 3),
        total_latency_s=_d(t_ws_closed, t_stop[0]),
        used_final_transcript=(final["text"] is not None),
        used_delta_fallback=res["used_deltas"],
        fallback_used=res["fell_back"],
        raw=repr(res["raw"]), final=repr(res["final_text"]))
    _cleanup_runtime()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    finally:
        _cleanup_runtime()
