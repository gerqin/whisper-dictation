#!/usr/bin/env python3
"""Postprocesamiento MÍNIMO de dictado (formato, no reescritura).

Limpia puntuación/mayúsculas/espacios y comandos hablados ("punto", "coma",
"nueva línea") SIN parafrasear, traducir, ni formalizar. Preserva el
Spanglish, términos en inglés, nombres propios, etc.

Fail-open: si la API falla o postproceso está apagado, devuelve el texto
crudo (nunca bloquea el dictado).

Uso módulo:  from cleanup_openai import cleanup -> (text, changed, latency_s, ok)
Uso CLI:     echo "texto" | python cleanup_openai.py
"""
import os
import re
import sys
import time

# Palabras de comandos de puntuación hablados: se permiten desaparecer del
# output (se convierten en signos), así que no cuentan para el guardrail.
_PUNCT_WORDS = {"punto", "coma", "dos", "puntos", "nueva", "linea", "línea",
                "aparte", "y"}


def _content_words(s: str):
    return set(re.findall(r"[0-9a-zñáéíóúü]+", (s or "").lower())) - _PUNCT_WORDS


SYSTEM_PROMPT = """You are a minimal dictation formatting engine.
Your job is NOT to rewrite. Your job is only to make the transcript paste-ready.
Rules:
- Preserve the exact meaning and wording as much as possible.
- Do not paraphrase.
- Do not translate.
- Do not make the text more formal.
- Do not make the text sound more polished than the user.
- Preserve the user's natural mix of Mexican Spanish, English, and Spanglish.
- Preserve casual phrasing.
- Preserve English words inside Spanish sentences.
- Preserve Spanish words inside English sentences.
- Preserve product names, acronyms, brand names, people names, numbers, URLs, emails, and technical terms.
- Fix only punctuation, capitalization, spacing, obvious casing, and paragraph breaks.
- Convert spoken punctuation commands when obvious:
  - "punto" -> "."
  - "coma" -> ","
  - "dos puntos" -> ":"
  - "punto y aparte" -> new paragraph
  - "nueva linea" -> line break
- Remove only clear accidental filler, duplicate stutters, or repeated fragments that add no meaning.
- Do not remove intentional fillers if they affect tone, like "jaja", "pues", "o sea", "perdon", "no se".
- If the transcript is a message to someone, output only the message.
- If the transcript is empty, nonsensical, or only a hallucination such as "thank you", "thanks for watching", ".", or "...", return an empty string.
- Return only the final text.
- No explanation.
- No quotes."""


def _enabled() -> bool:
    return os.environ.get("OPENAI_POSTPROCESS", "true").lower() in ("1", "true", "yes")


def cleanup(text: str):
    """Devuelve (cleaned_text, changed, latency_s, ok). Fail-open al crudo."""
    text = (text or "").strip()
    if not text or not _enabled():
        return text, False, 0.0, True

    model = os.environ.get("OPENAI_CLEANUP_MODEL", "gpt-5.4-mini")
    effort = os.environ.get("OPENAI_CLEANUP_REASONING_EFFORT", "minimal")
    t0 = time.time()
    try:
        from openai import OpenAI
        client = OpenAI()
        # Salida corta y proporcional al input (gpt-5.x: max_completion_tokens).
        cap = max(300, min(4000, len(text) * 2))
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            max_completion_tokens=cap,
        )
        # reasoning_effort solo lo aceptan los modelos gpt-5.x; si no, reintenta sin él.
        try:
            resp = client.chat.completions.create(reasoning_effort=effort, **kwargs)
        except Exception:
            resp = client.chat.completions.create(**kwargs)
        out = (resp.choices[0].message.content or "").strip()
        latency = time.time() - t0
        if not out:
            # El modelo decidió que era alucinación/vacío -> respetarlo.
            return "", text != "", latency, True
        # Guardrail anti-catástrofe: si el cleanup conservó < 50% de las
        # palabras de contenido del crudo, es sospecha de traducción/reescritura
        # -> fail-open al crudo (fiel aunque sin pulir). Protege el requisito
        # #4 "NUNCA reescribir". No dispara con puntuación/relleno normales.
        rw = _content_words(text)
        if rw and (len(rw & _content_words(out)) / len(rw)) < 0.5:
            sys.stderr.write("[cleanup_openai] guardrail: demasiadas palabras "
                             "cambiadas, fail-open al crudo\n")
            return text, False, latency, True
        return out, out != text, latency, True
    except Exception as e:  # noqa: BLE001 — fail-open SIEMPRE
        sys.stderr.write(f"[cleanup_openai] fail-open: {e}\n")
        return text, False, time.time() - t0, False


if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    out, _changed, _lat, _ok = cleanup(raw)
    sys.stdout.write(out)
