#!/bin/bash

# Raycast Script Command
# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Dictate
# @raycast.mode silent
# @raycast.icon 🎙

# Optional parameters:
# @raycast.packageName Whisper Dictation

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/whisper-toggle.sh" 2>/dev/null
if [ -f /tmp/.whisper_recording ]; then
  echo "Recording..."
else
  echo "$(pbpaste)"
fi
