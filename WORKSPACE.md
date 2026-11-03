# Workstation / file map

This document is the "link" between the project files, the Ally X workstation, and the GitHub repository. Copy the entire `rog-ally-x-ai-assistant/` folder to the handheld; `setup_github.sh` then commits this file map (excluding secrets and local state) to your public repo.

## Repository root

Suggested path on the Ally X:

```text
~/rog-ally-x-ai-assistant/
```

| Path | Purpose | In Git? |
|---|---|---|
| `app.py` | Standard-library HTTP server, `/api/chat`, `/api/action`, `/api/transcribe`, config, transcript export | yes |
| `brain.py` | Arena API / OpenAI-compatible / Ollama / demo brain adapters and strict-JSON parser | yes |
| `actions.py` | Guarded intent detection, URL validation, allowlist, argv-only system execution | yes |
| `settings.py` | `.env` loader and safe public configuration | yes |
| `cli.py` | Terminal-only REPL / one-shot client | yes |
| `static/index.html` | Generated standalone UI: inline CSS, inline JS, embedded avatar data URI | yes |
| `ui/index.template.html` | Source HTML template | yes |
| `ui/styles.css` | Source stylesheet | yes |
| `ui/app.js` | Source browser client | yes |
| `assets/avatar.jpg` | Your original uploaded avatar | yes |
| `assets/avatar.png` | Transparent-background avatar derived from the JPG | yes |
| `scripts/build_ui.py` | Rebuilds `static/index.html` from `ui/` + avatar | yes |
| `scripts/system_report.py` | Read-only Bazzite hardware/status reports | yes |
| `scripts/whisper_stt.py` | Optional `faster-whisper` WAV transcription adapter | yes |
| `scripts/setup_github.sh` | Sign in with `gh`, create public repo, set author, commit, push | yes |
| `scripts/sync_to_github.sh` | Commit/push later workstation changes safely | yes |
| `scripts/install_bazzite.sh` | systemd user service + desktop launcher installer | yes |
| `scripts/uninstall_bazzite.sh` | Removes service/launcher, keeps project files | yes |
| `scripts/install_whisper.sh` | Optional Whisper venv installer | yes |
| `tests/test_assistant.py` | Offline unit/API tests | yes |
| `.env.example` | Configuration template | yes |
| `.gitignore` | Keeps secrets, logs, audio and caches out of Git | yes |
| `README.md` | Full reference, usage, security and troubleshooting guide | yes |
| `INSTALL.md` | Complete copy-paste installation walkthrough for the Ally X | yes |
| `WORKSPACE.md` | This file map | yes |
| `LICENSE` | MIT license | yes |

## Machine-local files (never committed)

| Path | Purpose |
|---|---|
| `.env` | Arena API key and local settings; `chmod 600` |
| `data/conversation.jsonl` | Local chat transcript (exportable from the UI) |
| `data/*.wav` / temporary recordings | Short-lived audio |
| `*.log` | Optional local logs |
| `__pycache__/`, `.venv/`, caches | Generated Python/build state |

## Paths created on Bazzite by the installer

| Path | Purpose |
|---|---|
| `~/.config/systemd/user/rog-assistant.service` | Auto-start service |
| `~/.config/rog-assistant/session.env` | Captured Wayland/D-Bus/session variables |
| `~/.local/share/applications/r-assistant.desktop` | Desktop launcher |
| `~/.local/share/rog-assistant/whisper-venv/` | Optional Whisper venv |
| `http://127.0.0.1:8787` | Local assistant UI |

## GitHub link

`scripts/setup_github.sh` uses `gh auth login` on your own machine and creates:

```text
https://github.com/<your-account>/rog-ally-x-ai-assistant
```

It defaults to **public** because that was your selection. Set `VISIBILITY=private` or `REPO_NAME=...` to override. The remote is named `origin`; `scripts/sync_to_github.sh` keeps subsequent workstation edits linked to it.

## Source-to-generated relationships

```text
uploads/unnamed.jpg  ──► assets/avatar.jpg ──► assets/avatar.png
                                           │
ui/index.template.html + ui/styles.css + ui/app.js ──► scripts/build_ui.py ──► static/index.html
```

If you change the avatar or any `ui/` source file, run `python3 scripts/build_ui.py` before syncing to GitHub.
