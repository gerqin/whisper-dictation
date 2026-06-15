#!/usr/bin/env python3
"""Benchmark de latencia del dictado a partir del debug log.

Parsea /tmp/whisper-dictation-debug.log (bloques separados por '====='),
extrae `visible_latency_s` (soltar hotkey -> texto pegado, la métrica que
siente el usuario) y reporta promedio / p50 / p90 / peor caso / fallbacks.

Uso:
  python ops/bench-latency.py            # todos los dictados con visible_latency_s
  python ops/bench-latency.py --last 10  # solo los últimos 10
  python ops/bench-latency.py --log /ruta/otro.log
"""
import argparse
import os
import re

DEFAULT_LOG = os.environ.get("DICTATION_DEBUG_LOG", "/tmp/whisper-dictation-debug.log")


def parse_blocks(path):
    if not os.path.exists(path):
        return []
    blocks = []
    cur = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        if line.startswith("====="):
            if cur:
                blocks.append(cur)
            cur = {}
            continue
        m = re.match(r"^(\w+):\s*(.*)$", line.rstrip("\n"))
        if m:
            cur[m.group(1)] = m.group(2)
    if cur:
        blocks.append(cur)
    return blocks


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pct(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--last", type=int, default=0, help="solo los últimos N (0=todos)")
    args = ap.parse_args()

    blocks = parse_blocks(args.log)
    # solo los que tienen visible_latency_s (formato nuevo)
    runs = [b for b in blocks if fnum(b.get("visible_latency_s")) is not None]
    if args.last:
        runs = runs[-args.last:]

    if not runs:
        print("Sin dictados con visible_latency_s en", args.log)
        print("(¿corriste dictados después del cambio de métricas?)")
        return

    vis = sorted(fnum(b["visible_latency_s"]) for b in runs)
    fallbacks = sum(1 for b in runs if b.get("fallback_used", "").lower() == "true")
    teardowns = [fnum(b.get("teardown_latency_s")) for b in runs if fnum(b.get("teardown_latency_s")) is not None]
    cleanups = [fnum(b.get("cleanup_latency_s")) for b in runs if fnum(b.get("cleanup_latency_s"))]

    p50, p90 = pct(vis, 50), pct(vis, 90)
    print(f"== Benchmark visible_latency_s (soltar hotkey -> pegado) ==")
    print(f"n              : {len(runs)}")
    print(f"promedio       : {sum(vis)/len(vis):.2f}s")
    print(f"p50            : {p50:.2f}s   (meta <= 1.20s) {'✅' if p50 and p50 <= 1.2 else '❌'}")
    print(f"p90            : {p90:.2f}s   (meta <= 1.80s) {'✅' if p90 and p90 <= 1.8 else '❌'}")
    print(f"mejor / peor   : {vis[0]:.2f}s / {vis[-1]:.2f}s")
    print(f"fallbacks      : {fallbacks}/{len(runs)}")
    if teardowns:
        print(f"teardown medio : {sum(teardowns)/len(teardowns):.2f}s  (fuera del camino crítico)")
    if cleanups:
        print(f"cleanup medio  : {sum(cleanups)/len(cleanups):.2f}s  (LLM; 0 si formato local)")
    print()
    print("Por dictado (visible | audio | método | fallback):")
    for b in runs:
        print(f"  {fnum(b['visible_latency_s']):.2f}s | "
              f"{b.get('audio_duration_s','?')}s | {b.get('method','?')} | "
              f"{'FB' if b.get('fallback_used','').lower()=='true' else '-'}")


if __name__ == "__main__":
    main()
