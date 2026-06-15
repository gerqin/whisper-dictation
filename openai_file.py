#!/usr/bin/env python3
"""Backend openai_file — transcripción de archivo completo.

POST /v1/audio/transcriptions con gpt-4o-transcribe. Mayor precisión que
live, más latencia. También se usa como fallback del modo live.

- response_format=text
- SIN language fijo (autodetección: ES mexicano / EN / Spanglish)
- prompt de contexto con vocabulario propio (no traducir, preservar términos)

Uso módulo:  from openai_file import transcribe_file -> (text, latency_s)
Uso CLI:     python openai_file.py /ruta/al.wav
"""
import os
import sys
import time

CONTEXT_PROMPT = (
    "The user dictates naturally and may switch between Mexican Spanish, "
    "English, and Spanglish within the same sentence. Transcribe in the "
    "language actually spoken. Do not translate. Preserve code-switching, "
    "English terms, acronyms, brand names, product names, people names, and "
    "technical terms. Use natural punctuation when obvious, but do not rewrite "
    "or paraphrase.\n"
    "Common terms and names:\n"
    "DopamineLab, GoHighLevel, ManyChat, Kommo, Karly, Alberto, 11:11 Fitness, "
    "G2 PubliDepot, Meta Ads, WhatsApp, CRM, API, webhook, funnel, lead, leads, "
    "flow, ROAS, CPL, CAC, LTV, dashboard, landing page, copy, pixel, campaign, "
    "ad set, creative, Codex, Claude, ChatGPT, Raycast, Hammerspoon, whisper.cpp."
)


def transcribe_file(wav_path: str):
    """Devuelve (text, latency_s). Lanza excepción si la API falla
    (el caller decide el fallback)."""
    model = os.environ.get("OPENAI_FILE_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
    t0 = time.time()
    from openai import OpenAI
    client = OpenAI()
    with open(wav_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=model,
            file=f,
            response_format="text",
            prompt=CONTEXT_PROMPT,
        )
    # response_format=text -> resp es str (o tiene .text según versión)
    text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
    return text.strip(), time.time() - t0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("uso: openai_file.py <wav>\n")
        sys.exit(1)
    txt, lat = transcribe_file(sys.argv[1])
    sys.stderr.write(f"[openai_file] {lat:.2f}s\n")
    sys.stdout.write(txt)
