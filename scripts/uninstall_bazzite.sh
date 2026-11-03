#!/usr/bin/env bash
# Remove the systemd user service and desktop launcher (keeps project files).
set -euo pipefail

SERVICE="$HOME/.config/systemd/user/rog-assistant.service"
DESKTOP_FILE="$HOME/.local/share/applications/r-assistant.desktop"
SESSION_DIR="$HOME/.config/rog-assistant"

if systemctl --user list-unit-files 2>/dev/null | grep -q '^rog-assistant.service'; then
  systemctl --user disable --now rog-assistant.service >/dev/null 2>&1 || true
fi
rm -f "$SERVICE" "$DESKTOP_FILE"
rm -rf "$SESSION_DIR"
systemctl --user daemon-reload >/dev/null 2>&1 || true
echo "✓ R assistant service and launcher removed. Project files were kept."
