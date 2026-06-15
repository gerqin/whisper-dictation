#!/usr/bin/env python3
"""Formato LOCAL mecánico del dictado — rápido, determinista, 100% fiel.

NO hace: traducción, paráfrasis, corrección de estilo, cambio de Spanglish,
cambio de palabras. SOLO transformaciones de formato seguras + comandos
hablados multi-palabra obvios.

Uso módulo:  from local_format import local_format
Uso CLI:     echo "texto" | python local_format.py
"""
import re
import sys

# Comandos hablados multi-palabra (poco ambiguos). NO se incluyen "punto"/"coma"
# sueltos: aparecen en demasiados contextos literales para convertirlos a ciegas.
_COMMANDS = [
    (re.compile(r"\s*\bpunto y aparte\b[.,]?\s*", re.IGNORECASE), "\n\n"),
    (re.compile(r"\s*\bnueva l[ií]nea\b[.,]?\s*", re.IGNORECASE), "\n"),
    (re.compile(r"\s*\bdos puntos\b[.,]?\s*", re.IGNORECASE), ": "),
]

# Token "técnico" que NO se debe tocar al espaciar puntuación: URL, email, path,
# dominio/extensión/versión (foo.com, file.txt, v1.2). Evita romper a@b.com -> "a@b. com".
_URLISH = re.compile(r"@|://|/|www\.|\.\w{2,4}\b", re.IGNORECASE)
_PUNCT_GLUE = re.compile(r"([,.;:!?])([^\s\d])")


def _space_after_punct(t: str) -> str:
    # Aplica "espacio tras puntuación" SOLO dentro de tokens normales, saltando
    # los que parezcan URL/email/path/dominio.
    parts = re.split(r"(\s+)", t)
    for i, tok in enumerate(parts):
        if not tok or tok.isspace() or _URLISH.search(tok):
            continue
        parts[i] = _PUNCT_GLUE.sub(r"\1 \2", tok)
    return "".join(parts)


def local_format(text: str) -> str:
    t = text or ""
    if not t.strip():
        return ""
    # 1) comandos hablados -> signos/saltos
    for rx, repl in _COMMANDS:
        t = rx.sub(repl, t)
    # 2) colapsar espacios/tabs múltiples (preservando saltos de línea)
    t = re.sub(r"[ \t]+", " ", t)
    # 3) quitar espacio ANTES de puntuación
    t = re.sub(r"[ \t]+([,.;:!?])", r"\1", t)
    # 4) espacio DESPUÉS de puntuación, protegiendo URLs/emails/paths
    t = _space_after_punct(t)
    # 5) recortar espacios alrededor de saltos de línea
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", t)
    # 6) colapsar 3+ saltos a un párrafo (2)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


if __name__ == "__main__":
    sys.stdout.write(local_format(sys.stdin.read()))
