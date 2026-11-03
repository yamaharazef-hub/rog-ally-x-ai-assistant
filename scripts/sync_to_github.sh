#!/usr/bin/env bash
# Commit and push all workstation/project changes to the linked GitHub repo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MESSAGE="${MESSAGE:-Sync ROG Ally X assistant workstation: $(date '+%Y-%m-%d %H:%M:%S')}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "❌ Not a Git repository. Run ./scripts/setup_github.sh first." >&2
  exit 1
fi
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "❌ No 'origin' remote. Run ./scripts/setup_github.sh first." >&2
  exit 1
fi

git add -A
if git diff --cached --name-only | grep -Eq '(^|/)\.env$|(^|/)data/|(^|/)session\.env$|\.log$'; then
  echo "❌ Refusing to commit secrets or local logs:" >&2
  git diff --cached --name-only | grep -E '(^|/)\.env$|(^|/)data/|(^|/)session\.env$|\.log$' >&2 || true
  exit 1
fi
if git diff --cached --quiet; then
  echo "✓ Everything is already in sync."
  exit 0
fi

git commit -m "$MESSAGE"
git push origin HEAD
echo "✓ Pushed to $(git remote get-url origin)"
