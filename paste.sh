#!/bin/bash
# Pega texto en el cursor: copia al clipboard y simula Cmd+V.
# Recibe el texto por stdin (preserva el UX actual de pbcopy + ⌘V).
TEXT="$(cat)"
[ -z "$TEXT" ] && exit 0
printf '%s' "$TEXT" | pbcopy
osascript -e 'tell application "System Events" to keystroke "v" using command down'
