#!/usr/bin/env bash
# Install R as a systemd user service on Bazzite Desktop Mode and open its UI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8787}"
PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "❌ python3 was not found. Install it in a Distrobox or layer it with rpm-ostree." >&2
  exit 1
fi

SYSTEMD_DIR="$HOME/.config/systemd/user"
DESKTOP_DIR="$HOME/.local/share/applications"
CONF_DIR="$HOME/.config/rog-assistant"
SESSION_ENV="$CONF_DIR/session.env"
SERVICE="$SYSTEMD_DIR/rog-assistant.service"
DESKTOP_FILE="$DESKTOP_DIR/r-assistant.desktop"

mkdir -p "$SYSTEMD_DIR" "$DESKTOP_DIR" "$CONF_DIR"

# Capture the current graphical-session variables so xdg-open works from the service.
{
  printf 'DISPLAY="%s"\n' "${DISPLAY:-:0}"
  printf 'WAYLAND_DISPLAY="%s"\n' "${WAYLAND_DISPLAY:-wayland-0}"
  printf 'XDG_RUNTIME_DIR="%s"\n' "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  printf 'DBUS_SESSION_BUS_ADDRESS="%s"\n' "${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"
  printf 'XDG_CURRENT_DESKTOP="%s"\n' "${XDG_CURRENT_DESKTOP:-KDE}"
  printf 'PATH="%s"\n' "${PATH:-/usr/bin:/bin}"
} > "$SESSION_ENV"
chmod 600 "$SESSION_ENV"

cat > "$SERVICE" <<EOF
[Unit]
Description=R AI Assistant for ROG Ally X
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory="$ROOT"
EnvironmentFile=-$SESSION_ENV
Environment=PYTHONUNBUFFERED=1
ExecStart="$PYTHON_BIN" "$ROOT/app.py" --host 127.0.0.1 --port $PORT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=R AI Assistant
Comment=Voice AI assistant for the ROG Ally X
Exec=xdg-open http://127.0.0.1:$PORT
Icon=$ROOT/assets/avatar.png
Terminal=false
Categories=Utility;
StartupWMClass=R
EOF
chmod 644 "$SERVICE" "$DESKTOP_FILE"

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  chmod 600 "$ROOT/.env"
  echo "→ Created .env from the template. Add ARENA_API_KEY before using the full brain."
fi

python3 "$ROOT/scripts/build_ui.py" >/dev/null
systemctl --user daemon-reload
systemctl --user enable --now rog-assistant.service
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "✓ R assistant service installed and bound to 127.0.0.1:$PORT"
echo "  Open: http://127.0.0.1:$PORT"
echo "  Logs: journalctl --user -u rog-assistant.service -f"
echo "  Tip: use Chromium/Edge and allow microphone access for localhost."
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1 || true
fi
