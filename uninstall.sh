#!/bin/bash
echo "==> Uninstalling whisper-dictation"

launchctl unload "$HOME/Library/LaunchAgents/com.local.whisper-server.plist" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/com.local.whisper-server.plist"
pkill -f "sox.*whisper_dictate" 2>/dev/null
rm -f /tmp/.whisper_recording /tmp/whisper_dictate.wav

echo "==> Daemon removed. Model and brew packages left in place."
echo "   To remove model: rm ~/.local/share/whisper-models/ggml-large-v3-turbo.bin"
echo "   To remove brew packages: brew uninstall whisper-cpp sox"
