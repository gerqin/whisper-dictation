#!/usr/bin/env python3
"""Utilidades compartidas del dictado: transcripción local (whisper.cpp),
cadena de fallback, paste, escritura de WAV y log de debug.
"""
import json
import os
import subprocess
import sys
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))


# ── env helpers ───────────────────────────────────────────────────────
def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    return env(key, str(default)).lower() in ("1", "true", "yes")


# ── WAV (para fallback de live y modos file/local) ────────────────────
def write_wav(pcm: bytes, path: str, rate: int = 24000):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def wav_duration(path: str) -> float:
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


# ── Transcripción local (whisper.cpp en :8787) ────────────────────────
def local_transcribe(wav_path: str):
    """(text, latency_s). Curl al server local + reconstrucción word-level.
    Lanza si el server no responde."""
    url = env("LOCAL_WHISPER_URL", "http://127.0.0.1:8787/inference")
    t0 = time.time()
    out = subprocess.run(
        ["curl", "-s", "--max-time", "120", url,
         "-F", f"file=@{wav_path}",
         "-F", "response_format=verbose_json",
         "-F", "language=auto",
         "-F", "temperature=0"],
        capture_output=True, text=True, check=True,
    ).stdout
    d = json.loads(out)
    words = [w["word"] for s in d.get("segments", []) for w in s.get("words", [])]
    txt = "".join(words) if words else d.get("text", "")
    import re
    return re.sub(r"\s+", " ", txt).strip(), time.time() - t0


# ── Cadena de fallback ────────────────────────────────────────────────
def run_chain(wav_path: str, chain):
    """Prueba backends en orden. chain: lista de strings en
    {'openai_file','local'}. Devuelve (text, mode_used, latency_s, fell_back).
    Un backend 'falla' si lanza excepción; un resultado vacío salta al
    siguiente. Si todos vacíos -> ('', ultimo_modo, lat, fell_back)."""
    from hallucination_filter import is_hallucination
    fell_back = False
    last_mode = chain[-1] if chain else ""
    for i, mode in enumerate(chain):
        try:
            if mode == "openai_file":
                from openai_file import transcribe_file
                text, lat = transcribe_file(wav_path)
            elif mode == "local":
                text, lat = local_transcribe(wav_path)
            else:
                continue
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"[chain] {mode} failed: {e}\n")
            fell_back = True
            continue
        if text and not is_hallucination(text):
            return text, mode, lat, (fell_back or i > 0)
        # vacío/alucinación: intentar siguiente si hay
        fell_back = fell_back or i > 0
        last_mode = mode
    return "", last_mode, 0.0, fell_back


# ── Formato del texto: local mecánico (default) o cleanup LLM (pruebas) ─
def format_output(raw: str):
    """Devuelve (text, cleanup_latency_s, method). 'cleanup-empty' = el LLM
    vació a propósito (alucinación) -> el caller NO debe pegar el raw."""
    raw = (raw or "").strip()
    if not raw:
        return "", 0.0, "empty"
    if env_bool("OPENAI_POSTPROCESS", False):
        from cleanup_openai import cleanup
        cleaned, _changed, lat, ok = cleanup(raw)
        if ok and cleaned == "":
            return "", lat, "cleanup-empty"
        return (cleaned if cleaned else raw), lat, "llm-cleanup"
    if env_bool("LOCAL_FORMATTING", True):
        from local_format import local_format
        return local_format(raw), 0.0, "local-format"
    return raw, 0.0, "raw"


# ── Paste (pbcopy + Cmd+V vía paste.sh) ───────────────────────────────
def paste(text: str):
    if not text:
        return
    subprocess.run([os.path.join(HERE, "paste.sh")], input=text, text=True)


# ── Flags para la menubar ─────────────────────────────────────────────
def set_flags(mode_used: str, fell_back: bool):
    try:
        with open(env("WD_MODE_FLAG", "/tmp/.whisper_mode"), "w") as f:
            f.write(mode_used)
    except Exception:
        pass
    flag = env("WD_FALLBACK_FLAG", "/tmp/.whisper_fallback")
    try:
        if fell_back:
            open(flag, "w").close()
        elif os.path.exists(flag):
            os.remove(flag)
    except Exception:
        pass


# ── Debug log ─────────────────────────────────────────────────────────
def debug_log(**fields):
    if not env_bool("DICTATION_DEBUG", True):
        return
    path = env("DICTATION_DEBUG_LOG", "/tmp/whisper-dictation-debug.log")
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(path, "a") as f:
            f.write(f"\n===== {ts} =====\n")
            for k in ("mode", "method", "audio_duration_s", "audio_sec",
                      "stop_to_commit_s", "commit_to_completed_s",
                      "completed_to_paste_s", "visible_latency_s",
                      "teardown_latency_s", "transcription_latency_s",
                      "cleanup_latency_s", "total_latency_s",
                      "used_final_transcript", "used_delta_fallback",
                      "fallback_used", "over_ideal_wait", "raw", "cleaned", "final"):
                if k in fields:
                    f.write(f"{k}: {fields[k]}\n")
    except Exception:
        pass


# ── Dispatcher de los modos file/local (lo invoca whisper-toggle.sh) ──
def file_mode_main():
    """Transcribe WD_AUDIO según DICTATION_MODE (openai_file|local) con su
    cadena de fallback, formatea, pega y loggea. Opera sobre el WAV ya grabado.
    t0 ≈ momento de soltar el hotkey (la transcripción empieza justo aquí)."""
    from hallucination_filter import is_hallucination

    t0 = time.time()
    wav = env("WD_AUDIO", "/tmp/whisper_dictate.wav")
    mode = env("DICTATION_MODE", "openai_file")
    if not os.path.exists(wav) or os.path.getsize(wav) == 0:
        return

    chain = ["local"] if mode == "local" else ["openai_file"]
    if mode == "openai_file" and env_bool("OPENAI_FALLBACK_TO_LOCAL", True):
        chain.append("local")

    raw, mode_used, tx_lat, fell_back = run_chain(wav, chain)
    audio_sec = round(wav_duration(wav), 2)
    try:
        os.remove(wav)
    except FileNotFoundError:
        pass

    if not raw or is_hallucination(raw):
        set_flags(mode_used, fell_back)
        debug_log(mode=mode_used, method="-", audio_duration_s=audio_sec,
                  raw=repr(raw), final="", transcription_latency_s=round(tx_lat, 2),
                  cleanup_latency_s=0.0, visible_latency_s=round(time.time() - t0, 2),
                  total_latency_s=round(time.time() - t0, 2), fallback_used=fell_back)
        return

    final_text, clean_lat, method = format_output(raw)
    if method != "cleanup-empty" and not final_text:
        final_text = raw  # local-format no vacía; protege contra vacío espurio
    paste(final_text)
    t_paste = time.time()
    set_flags(mode_used, fell_back)
    debug_log(mode=mode_used, method=method, audio_duration_s=audio_sec,
              raw=repr(raw), final=repr(final_text),
              transcription_latency_s=round(tx_lat, 2),
              cleanup_latency_s=round(clean_lat, 2),
              visible_latency_s=round(t_paste - t0, 2),
              total_latency_s=round(t_paste - t0, 2), fallback_used=fell_back)


if __name__ == "__main__":
    file_mode_main()
