#!/bin/bash
# Toggle whisper dictation — start/stop recording, transcribe, paste
MARKER="/tmp/.whisper_recording"
AUDIO="/tmp/whisper_dictate.wav"
URL="http://127.0.0.1:8787/inference"
SOX="$(command -v sox || echo /opt/homebrew/bin/sox)"

if [ -f "$MARKER" ]; then
  rm -f "$MARKER"
  pkill -INT -f "sox.*whisper_dictate" 2>/dev/null
  sleep 0.8
  [ ! -s "$AUDIO" ] && exit 0
  RAW=$(curl -s "$URL" -F "file=@${AUDIO}" -F "response_format=text" -F "language=auto")
  rm -f "$AUDIO"

  # Clean whisper hallucinations
  TEXT=$(echo "$RAW" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | \
    # Strip hallucination prefixes glued to real text
    sed 's/^[Tt]hank you\.//; s/^[Tt]hanks for watching\.//; s/^[Pp]lease subscribe\.//' | \
    # Remove full-line hallucination patterns (case-insensitive)
    grep -iv '^\*.*music\*$' | \
    grep -iv '^\*.*applause\*$' | \
    grep -iv '^\*.*laughter\*$' | \
    grep -iv '^\*.*silence\*$' | \
    grep -iv '^[[:space:]]*thank you\.\?[[:space:]]*$' | \
    grep -iv '^[[:space:]]*thanks for watching\.\?[[:space:]]*$' | \
    grep -iv '^[[:space:]]*please subscribe\.\?[[:space:]]*$' | \
    grep -iv '^[[:space:]]*you$' | \
    grep -iv '^[[:space:]]*\.\.\.\.*[[:space:]]*$' | \
    # Collapse duplicate consecutive lines
    awk 'NR==1{prev=$0;next} $0!=prev{print prev;prev=$0} END{if(NR)print prev}' | \
    # Final trim
    sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

  [ -z "$TEXT" ] || [ "$TEXT" = "." ] && exit 0
  echo -n "$TEXT" | pbcopy
  osascript -e 'tell application "System Events" to keystroke "v" using command down'
else
  rm -f "$AUDIO"
  touch "$MARKER"
  "$SOX" -d -q -r 16000 -c 1 -b 16 -t wav "$AUDIO" &
  disown
fi
