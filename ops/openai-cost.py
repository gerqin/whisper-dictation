#!/usr/bin/env python3
"""Consulta el gasto real de OpenAI (org) vía la Costs API, por modelo y día.

Requiere un ADMIN key (sk-admin-…, scope api.usage.read) — el key de proyecto
(sk-proj-…) NO tiene permiso. Se busca en Keychain como OPENAI_ADMIN_KEY:
    security add-generic-password -a "$USER" -s OPENAI_ADMIN_KEY -w 'sk-admin-...'

Uso:
    python ops/openai-cost.py                 # mes actual, por modelo
    python ops/openai-cost.py 2026-06-16      # desde esa fecha
    python ops/openai-cost.py 2026-06-01 --by-day

Modelos del proyecto whisper: gpt-realtime-whisper (live, ~$0.055/min),
gpt-4o-transcribe (file, ~$0.006/min), gpt-5.4-mini (cleanup, normalmente off).
"""
import json
import subprocess
import sys
import time
import urllib.request


def get_key():
    try:
        k = subprocess.check_output(
            ["security", "find-generic-password", "-s", "OPENAI_ADMIN_KEY", "-w"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        if k:
            return k
    except subprocess.CalledProcessError:
        pass
    sys.exit("No hay OPENAI_ADMIN_KEY en Keychain. Guárdalo con:\n"
             "  security add-generic-password -a \"$USER\" -s OPENAI_ADMIN_KEY -w 'sk-admin-...'")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    by_day = "--by-day" in sys.argv
    start_date = args[0] if args else time.strftime("%Y-%m-01")
    start = int(time.mktime(time.strptime(start_date, "%Y-%m-%d")))

    key = get_key()
    url = (f"https://api.openai.com/v1/organization/costs"
           f"?start_time={start}&limit=180&group_by=line_item")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    page = json.load(urllib.request.urlopen(req))

    total = 0.0
    by_item, by_dayd = {}, {}
    for b in page["data"]:
        day = b["start_time_iso"][:10]
        for r in b.get("results", []):
            amt = float(r["amount"]["value"])
            total += amt
            it = r.get("line_item") or "(sin item)"
            by_item[it] = by_item.get(it, 0) + amt
            by_dayd[day] = by_dayd.get(day, 0) + amt

    print(f"=== GASTO TOTAL (org) desde {start_date}: ${total:.4f} USD ===\n")
    print("--- Por modelo/servicio ---")
    for k, v in sorted(by_item.items(), key=lambda x: -x[1]):
        if v > 0:
            print(f"  ${v:9.5f}  {k}")
    if by_day:
        print("\n--- Por día (con gasto) ---")
        for k, v in sorted(by_dayd.items()):
            if v > 0:
                print(f"  {k}: ${v:.5f}")


if __name__ == "__main__":
    main()
