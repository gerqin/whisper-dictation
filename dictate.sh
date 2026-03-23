#!/bin/bash

# Raycast Script Command
# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Dictate
# @raycast.mode silent
# @raycast.icon 🎙

# Optional parameters:
# @raycast.packageName Whisper Dictation

/Users/g/Dev/whisper-dictation/whisper-toggle.sh 2>/dev/null
if [ -f /tmp/.whisper_recording ]; then
  echo "Recording..."
else
  echo "$(pbpaste)"
fi
