#!/usr/bin/env bash
# Create the public GitHub repository from YOUR signed-in account and push.
# Run this on the ROG Ally X (or any machine where you can sign in to GitHub).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
REPO_NAME="${REPO_NAME:-rog-ally-x-ai-assistant}"
VISIBILITY="${VISIBILITY:-public}"   # public | private
BRANCH="${BRANCH:-main}"

if ! command -v git >/dev/null 2>&1; then
  echo "❌ git is not installed." >&2
  exit 1
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "❌ GitHub CLI (gh) is not installed." >&2
  echo "   On Bazzite, Homebrew is available: brew install gh" >&2
  echo "   Or install it inside your preferred Distrobox/container." >&2
  exit 1
fi
if [[ "$VISIBILITY" != "public" && "$VISIBILITY" != "private" ]]; then
  echo "❌ VISIBILITY must be 'public' or 'private'." >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "→ Signing in to GitHub in your browser…"
  gh auth login --web --git-protocol https
fi
gh auth setup-git >/dev/null 2>&1 || true

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init -b "$BRANCH"
fi
git branch -M "$BRANCH"

# Link commits to the signed-in GitHub account when no local identity is forced.
if [[ "${KEEP_GIT_IDENTITY:-0}" != "1" ]]; then
  GH_LOGIN="$(gh api user --jq .login)"
  GH_ID="$(gh api user --jq .id)"
  GH_NAME="$(gh api user --jq '(.name // .login)')"
  GH_EMAIL="$(gh api user --jq '(.email // empty)')"
  if [[ -z "$GH_EMAIL" ]]; then
    GH_EMAIL="${GH_ID}+${GH_LOGIN}@users.noreply.github.com"
  fi
  git config --local user.name "$GH_NAME"
  git config --local user.email "$GH_EMAIL"
  echo "→ Git author: $GH_NAME <$GH_EMAIL>"
  # This workspace may already contain a neutral setup commit. Re-author only
  # that exact initial commit so the public repo is linked to your account.
  if git rev-parse --verify HEAD >/dev/null 2>&1; then
    HEAD_SUBJECT="$(git log -1 --pretty=%s)"
    HEAD_AUTHOR="$(git log -1 --pretty=%ae)"
    if [[ "$HEAD_SUBJECT" == "Initial commit: R AI assistant for ROG Ally X on Bazzite" || "$HEAD_AUTHOR" == "r-assistant@localhost" ]]; then
      git commit --amend --reset-author --no-edit >/dev/null
      echo "→ Re-authored the setup commit for $GH_LOGIN"
    fi
  fi
fi

git add -A
if git diff --cached --name-only | grep -Eq '(^|/)\.env$|(^|/)data/|(^|/)session\.env$|\.log$'; then
  echo "❌ Refusing to commit secrets or local logs. Check .gitignore and unstage the file:" >&2
  git diff --cached --name-only | grep -E '(^|/)\.env$|(^|/)data/|(^|/)session\.env$|\.log$' >&2 || true
  exit 1
fi
if ! git diff --cached --quiet; then
  git commit -m "Initial commit: R AI assistant for ROG Ally X on Bazzite"
else
  echo "→ No new local changes to commit."
fi

OWNER="$(gh api user --jq .login)"
REPO_FULL="$OWNER/$REPO_NAME"
REPO_URL="https://github.com/$REPO_FULL.git"
echo "→ GitHub account: $OWNER"
echo "→ Repository:     $REPO_FULL ($VISIBILITY)"

if gh repo view "$REPO_FULL" >/dev/null 2>&1; then
  echo "→ Repository already exists; linking remote and pushing."
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$REPO_URL"
  else
    git remote add origin "$REPO_URL"
  fi
  git push -u origin "$BRANCH"
else
  echo "→ Creating repository and pushing…"
  gh repo create "$REPO_NAME" \
    "--$VISIBILITY" \
    --description "R: a local voice AI assistant for the ROG Ally X running Bazzite, with Arena API brain and guarded system control" \
    --source=. \
    --remote=origin \
    --push
fi

echo
echo "✓ Done: https://github.com/$REPO_FULL"
echo "  Sync later with: ./scripts/sync_to_github.sh"
