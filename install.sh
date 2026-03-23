#!/bin/bash
set -e

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_DIR="$HOME/.local/share/whisper-models"
MODEL_FILE="$MODEL_DIR/ggml-large-v3-turbo.bin"
PLIST_NAME="com.local.whisper-server"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "==> Installing whisper-dictation"

# 1. Install dependencies
echo "==> Installing brew dependencies (whisper-cpp, sox)..."
brew install whisper-cpp sox

# 2. Download model
if [ -f "$MODEL_FILE" ]; then
  echo "==> Model already exists, skipping download"
else
  echo "==> Downloading whisper large-v3-turbo model (~1.5GB)..."
  mkdir -p "$MODEL_DIR"
  curl -L -o "$MODEL_FILE" "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"
fi

# 3. Make scripts executable
chmod +x "$INSTALL_DIR/whisper-toggle.sh"
chmod +x "$INSTALL_DIR/dictate.sh"

# 4. Patch scripts with actual paths
sed -i '' "s|/opt/homebrew/bin/sox|$(which sox)|g" "$INSTALL_DIR/whisper-toggle.sh"
sed -i '' "s|/Users/g/Dev/whisper-dictation|$INSTALL_DIR|g" "$INSTALL_DIR/dictate.sh"

# 5. Install launchd service
echo "==> Installing whisper-server daemon..."
launchctl unload "$PLIST_PATH" 2>/dev/null || true

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(which whisper-server)</string>
        <string>-m</string>
        <string>$MODEL_FILE</string>
        <string>-l</string>
        <string>auto</string>
        <string>--port</string>
        <string>8787</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/server.log</string>
    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/server.log</string>
</dict>
</plist>
EOF

launchctl load "$PLIST_PATH"

# 6. Wait for server
echo "==> Waiting for whisper-server to start..."
for i in $(seq 1 15); do
  if curl -s http://127.0.0.1:8787/health >/dev/null 2>&1; then
    echo "==> Server is running"
    break
  fi
  sleep 1
done

# 7. Raycast integration
echo ""
echo "==> Done! To set up Raycast:"
echo "   1. Open Raycast Settings → Extensions → + → Add Script Directory"
echo "   2. Select: $INSTALL_DIR"
echo "   3. Assign a hotkey to 'Dictate'"
echo ""
echo "   First hotkey press → starts recording"
echo "   Second press → stops, transcribes, pastes"
echo ""
echo "   Grant Accessibility permission to Raycast if prompted."
