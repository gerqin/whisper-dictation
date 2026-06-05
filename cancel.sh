#!/bin/bash

# Raycast Script Command
# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Cancel Dictation
# @raycast.mode silent

# Optional parameters:
# @raycast.icon ✕
# @raycast.packageName Whisper Dictation

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/whisper-cancel.sh" 2>/dev/null
