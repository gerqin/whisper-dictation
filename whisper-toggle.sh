#!/bin/bash
# Toggle whisper dictation — start/stop recording, transcribe, paste
MARKER="/tmp/.whisper_recording"
PIDFILE="/tmp/.whisper_sox.pid"
AUDIO="/tmp/whisper_dictate.wav"
URL="http://127.0.0.1:8787/inference"
SOX="$(command -v sox || echo /opt/homebrew/bin/sox)"

if [ -f "$MARKER" ]; then
  rm -f "$MARKER"
  # Kill sox by saved PID (reliable), fallback to pkill
  if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
  fi
  pkill -f "sox.*whisper_dictate" 2>/dev/null
  sleep 0.2
  [ ! -s "$AUDIO" ] && exit 0
  RESPONSE=$(curl -s --max-time 120 "$URL" -F "file=@${AUDIO}" -F "response_format=verbose_json" -F "language=auto" -F "temperature=0")
  rm -f "$AUDIO"

  # Rebuild text from word-level tokens (avoids server line-wrapping that breaks
  # mid-word, e.g. "pes\na" -> "pes a"). Drop common hallucinations.
  TEXT=$(printf '%s' "$RESPONSE" | /usr/bin/env python3 -c '
import sys, json, re
try:
    d = json.loads(sys.stdin.read())
except Exception:
    sys.exit(0)
words = [w["word"] for s in d.get("segments", []) for w in s.get("words", [])]
txt = "".join(words) if words else d.get("text", "")
txt = re.sub(r"\s+", " ", txt).strip()
HALLUCINATIONS = {
    "thank you.", "thank you", "thanks for watching.", "thanks for watching",
    "please subscribe.", "please subscribe", "you", ".", "...", "....",
}
low = txt.lower()
if low in HALLUCINATIONS:
    sys.exit(0)
# Repeated-phrase hallucination: "thank you, thank you, thank you..." etc.
# If the output is a short phrase (<=4 words) repeated 3+ times, drop it.
tokens = [t for t in re.split(r"[\s,.\-!?]+", low) if t]
for n in (1, 2, 3, 4):
    if len(tokens) >= n * 3 and len(set(tuple(tokens[i:i+n]) for i in range(0, len(tokens) - n + 1, n))) == 1:
        sys.exit(0)
sys.stdout.write(txt)
')

  [ -z "$TEXT" ] && exit 0
  printf '%s' "$TEXT" | pbcopy
  osascript -e 'tell application "System Events" to keystroke "v" using command down'
else
  rm -f "$AUDIO"
  # Kill any orphaned sox from previous runs
  pkill -f "sox.*whisper_dictate" 2>/dev/null
  touch "$MARKER"
  "$SOX" -d -q -r 16000 -c 1 -b 16 -t wav "$AUDIO" trim 0 300 &
  echo $! > "$PIDFILE"
  disown
fi
