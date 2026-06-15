#!/usr/bin/env python3
"""Filtro de alucinaciones compartido.

Uso como módulo:  from hallucination_filter import is_hallucination, collapse_ws
Uso como CLI:     echo "texto" | python hallucination_filter.py
                  -> imprime el texto si es válido, vacío si es alucinación.
"""
import re
import sys

# Frases que Whisper/transcriptores escupen sobre silencio o ruido.
HALLUCINATIONS = {
    "thank you.", "thank you", "thanks for watching.", "thanks for watching",
    "please subscribe.", "please subscribe", "you", ".", "...", "....",
    "gracias.", "gracias", "subtítulos realizados por la comunidad de amara.org",
    "¡gracias por ver el video!", "subscribe", "bye", "bye.",
}


def collapse_ws(text: str) -> str:
    """Colapsa whitespace a un solo párrafo."""
    return re.sub(r"\s+", " ", text or "").strip()


def is_hallucination(text: str) -> bool:
    """True si el texto es claramente una alucinación (exact-match o frase
    corta repetida 3+ veces). NO sobre-filtra dictado real."""
    txt = collapse_ws(text)
    if not txt:
        return True
    low = txt.lower()
    if low in HALLUCINATIONS:
        return True
    # Frase corta (<=4 palabras) repetida 3+ veces: "thank you, thank you, ..."
    tokens = [t for t in re.split(r"[\s,.\-!?]+", low) if t]
    for n in (1, 2, 3, 4):
        if len(tokens) >= n * 3:
            chunks = {tuple(tokens[i:i + n]) for i in range(0, len(tokens) - n + 1, n)}
            if len(chunks) == 1:
                return True
    return False


if __name__ == "__main__":
    raw = sys.stdin.read()
    txt = collapse_ws(raw)
    if is_hallucination(txt):
        sys.exit(0)  # vacío
    sys.stdout.write(txt)
