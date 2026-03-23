#!/bin/bash
# Toggle whisper dictation — called by Automator/shortcut
MARKER="/tmp/.whisper_recording"
AUDIO="/tmp/whisper_dictate.wav"
URL="http://127.0.0.1:8787/inference"

if [ -f "$MARKER" ]; then
  rm -f "$MARKER"
  pkill -INT -f "sox.*whisper_dictate" 2>/dev/null
  sleep 0.8
  [ ! -s "$AUDIO" ] && exit 0
  TEXT=$(curl -s "$URL" -F "file=@${AUDIO}" -F "response_format=text" -F "language=auto" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  rm -f "$AUDIO"
  [ -z "$TEXT" ] || [ "$TEXT" = "." ] && exit 0
  echo -n "$TEXT" | pbcopy
  osascript -e 'tell application "System Events" to keystroke "v" using command down'
else
  rm -f "$AUDIO"
  touch "$MARKER"
  /opt/homebrew/bin/sox -d -q -r 16000 -c 1 -b 16 -t wav "$AUDIO" &
  disown
fi
