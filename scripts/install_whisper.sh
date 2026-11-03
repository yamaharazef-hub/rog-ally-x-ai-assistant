#!/usr/bin/env bash
# Optional: install faster-whisper into a user venv for offline microphone mode.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${WHISPER_VENV:-$HOME/.local/share/rog-assistant/whisper-venv}"
ENV_FILE="$ROOT/.env"

echo "→ Creating Python venv at $VENV"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install faster-whisper

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

if grep -q '^WHISPER_PYTHON=' "$ENV_FILE"; then
  sed -i "s|^WHISPER_PYTHON=.*|WHISPER_PYTHON=$VENV/bin/python|" "$ENV_FILE"
else
  printf '\nWHISPER_PYTHON=%s\n' "$VENV/bin/python" >> "$ENV_FILE"
fi
if ! grep -q '^WHISPER_MODEL=' "$ENV_FILE"; then
  printf 'WHISPER_MODEL=small.en\n' >> "$ENV_FILE"
fi

echo "✓ Local Whisper is installed."
echo "  Restart the service, then choose 'Local Whisper' in the mic dropdown."
echo "  The first transcription downloads the model, so keep the Ally X online once."
echo "  To use a different model, edit WHISPER_MODEL in .env (tiny.en, base.en, small.en, medium.en)."
