# R • ROG Ally X AI Assistant

A local, voice-driven assistant for a **ROG Ally X running Bazzite OS**. It uses your uploaded robot as its avatar, listens when you tap the microphone, replies through an **Arena API brain**, opens YouTube (or another approved app/site) when you ask, and prints every guarded system action in a terminal-style panel.

Built to your choices: **official Arena API key**, **guarded allowlist**, **public GitHub repository**, and **browser speech plus optional local Whisper**.

> **New here?** Use the complete copy-paste walkthrough in **[INSTALL.md](INSTALL.md)**.

> **Status of this workspace:** the app, UI, terminal client, tests, Bazzite installer and GitHub scripts are complete and tested here in dry-run mode. Two steps must happen on your Ally X because they need *your* credentials and hardware: adding the Arena API key, and signing in to GitHub to create/push the repository. The Arena GitHub connector is not available in this session, so I cannot create the repo as you from here.

---

## 1. What it does

- **Avatar:** your `unnamed.jpg` is included as `assets/avatar.jpg`; `assets/avatar.png` is a transparent-background version used by the UI.
- **Click-to-listen:** big microphone button with animated listening/speaking states.
- **Two mic engines:**
  - `Browser STT` — Chromium/Edge Web Speech API, no install.
  - `Local Whisper` — browser records PCM WAV → `/api/transcribe` → optional `faster-whisper` venv.
- **AI brain:** official Arena API, OpenAI-compatible `POST /v1/chat/completions` with `ARENA_API_KEY` [5](https://platform.arena.ai/docs/opencode). Also supports generic OpenAI-compatible endpoints, local Ollama, and an offline demo brain.
- **Arena Agent handoff:** header button opens `https://arena.ai/agent` and copies your last prompt to the clipboard.
- **System control, safely:** the brain can only *request* named actions. `actions.py` validates them and maps them to `argv` lists with `shell=False`. No raw shell, no sudo, no `dnf`/`rpm-ostree install`.
- **Terminal replies:** every AI call and system command appears in the **Guarded terminal** panel with stdout/stderr. `cli.py` gives the same experience over SSH.
- **Bazzite-ready:** installs as a `systemd --user` service bound to `127.0.0.1`, with a desktop launcher. Bazzite's atomic/immutable base is left alone [1](https://docs.bazzite.gg/General/FAQ/).
- **GitHub-ready:** `.gitignore` excludes `.env`, `data/`, logs and audio. `setup_github.sh` creates a **public** repo under your signed-in account and pushes; `sync_to_github.sh` pushes later workstation changes.

### Example voice commands

| Say or type | What happens |
|---|---|
| `youtube` / `open youtube in the browser` | `xdg-open 'https://www.youtube.com/'` |
| `open Arena Agent` | opens `https://arena.ai/agent` |
| `check battery` / `system status` | read-only Python report in the terminal panel |
| `set volume to 50%` | `wpctl` or `pactl` guarded command |
| `brightness 70%` | `brightnessctl set 70%` |
| `open Steam` / `open Firefox` / `open terminal` | first available launcher or Flatpak app ID |
| `open downloads` | opens `~/Downloads` |
| `lock screen` / `suspend` | `loginctl` / `systemctl` guarded command |
| `search for Bazzite ROG Ally X TDP` | opens a Google search |
| `run sudo rm -rf /` | **blocked**, with a terminal explanation |

---

## 2. Quick start on the Ally X

Copy this whole `rog-ally-x-ai-assistant/` folder to the Ally X (USB drive, `scp`, or download it from this workspace). Then:

```bash
cd ~/rog-ally-x-ai-assistant
cp .env.example .env
chmod 600 .env
# edit .env and set ARENA_API_KEY=...
nano .env
python3 app.py --host 127.0.0.1 --port 8787 --open
```

Open `http://127.0.0.1:8787` in **Chromium or Edge** and allow microphone access for localhost.

No `pip install` is needed for the main app. For a quick offline test without a key:

```bash
python3 app.py --dry-run --open
python3 cli.py --demo --dry-run "open youtube"
```

`--dry-run` shows the exact commands in the terminal panel but does not launch anything. Remove it for real system control.

### Get the Arena key

1. Open <https://platform.arena.ai/dashboard/keys> and create a key [2](https://platform.arena.ai/docs).
2. Put only the key in `.env` on the Ally X. Never paste it into chat or commit it.
3. Restart the service. The UI badge changes from `DEMO BRAIN` to `ARENA • <model>`.

The default model is `coding-router-preview`. If you get a `403 organization_client_restricted` reply, your key is likely a free-router key limited to Claude Code; use a workspace with API access or set `ARENA_MODEL` to a model enabled for your key [2](https://platform.arena.ai/docs). The app automatically falls back to the offline demo brain and shows a readable warning instead of crashing.

---

## 3. Install as a Bazzite service

Run in **Desktop Mode** first:

```bash
cd ~/rog-ally-x-ai-assistant
./scripts/install_bazzite.sh
```

That script:

- creates `~/.config/systemd/user/rog-assistant.service`,
- captures `DISPLAY`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR` and the D-Bus address so `xdg-open` works from the service,
- binds the server to `127.0.0.1:8787`,
- adds an `R AI Assistant` desktop launcher using the avatar icon,
- enables the service and opens the UI.

Useful commands:

```bash
systemctl --user status rog-assistant.service
journalctl --user -u rog-assistant.service -f
systemctl --user restart rog-assistant.service
./scripts/uninstall_bazzite.sh
```

> Steam Gaming Mode may not expose the same desktop session variables. Install and test in Desktop Mode; add the desktop launcher to Steam as a non-Steam game afterwards if you want it in Game Mode.

---

## 4. Optional offline microphone

```bash
cd ~/rog-ally-x-ai-assistant
./scripts/install_whisper.sh
systemctl --user restart rog-assistant.service
```

Then choose **Local Whisper** in the mic dropdown. The script creates a venv at `~/.local/share/rog-assistant/whisper-venv`, installs `faster-whisper`, and writes `WHISPER_PYTHON` into `.env`. The first transcription downloads the model, so stay online once. Change `WHISPER_MODEL` (`tiny.en`, `base.en`, `small.en`, `medium.en`) to trade speed for accuracy.

Browser STT remains the default because it needs no model download; typed input always works.

---

## 5. Create your public GitHub repository

From the project folder on the Ally X:

```bash
brew install gh                 # if GitHub CLI is missing
./scripts/setup_github.sh        # opens browser for `gh auth login`
```

A local `main` branch and neutral setup commit are already present in this workspace. The script:

1. signs you in with `gh auth login --web --git-protocol https`,
2. sets the local Git author from your GitHub account (or a GitHub noreply address) and re-authors that exact setup commit,
3. refuses to stage `.env`, `data/`, logs or audio,
4. creates `rog-ally-x-ai-assistant` as a **public** repo under your account,
5. adds `origin` and pushes `main`.

Override the defaults if needed:

```bash
REPO_NAME=my-ally-assistant VISIBILITY=public ./scripts/setup_github.sh
```

Later, sync workstation changes:

```bash
./scripts/sync_to_github.sh
# or: MESSAGE="Add a new guarded action" ./scripts/sync_to_github.sh
```

If the repo already exists, `setup_github.sh` links the remote and pushes instead of failing. `KEEP_GIT_IDENTITY=1` preserves an existing local Git identity.

---

## 6. Terminal-only client

```bash
python3 cli.py                         # interactive REPL
python3 cli.py "check battery"          # one-shot
python3 cli.py --demo --dry-run "youtube"
```

It prints the assistant reply, then `$ r.brain --ask ...` and every guarded command with its output.

---

## 7. Configuration

All settings are in `.env` (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `AI_PROVIDER` | `arena` | `arena`, `openai`, `ollama`, or `demo` |
| `ARENA_API_KEY` | empty | Arena API key from your dashboard |
| `ARENA_BASE_URL` | `https://api.arena.ai/v1` | Official OpenAI-compatible base URL |
| `ARENA_MODEL` | `coding-router-preview` | Any model enabled for your key |
| `ARENA_AGENT_URL` | `https://arena.ai/agent` | Handoff button target |
| `HOST` / `PORT` | `127.0.0.1` / `8787` | Local bind address |
| `PERMISSION_MODE` | `guarded` | Only guarded mode is implemented |
| `ASSISTANT_DRY_RUN` | `0` | `1` simulates system actions |
| `BROWSER_COMMAND` | `xdg-open` | e.g. `flatpak run org.mozilla.firefox` |
| `SPEECH_LANG` | `en-US` | Browser STT and TTS language |
| `WHISPER_PYTHON` | current Python | Venv Python with `faster-whisper` |
| `WHISPER_MODEL` | `small.en` | Local Whisper model |

The UI shows a safe config summary; it never receives the API key.

---

## 8. Architecture

```text
Browser (Chromium/Edge)
  ├─ Mic button → Web Speech API  ─────────────┐
  └─ Mic button → MediaRecorder → WAV → /api/transcribe → faster-whisper
        │
        ▼  POST /api/chat {text, history}
Python stdlib server (app.py)
  ├─ brain.py → Arena API / OpenAI / Ollama / demo
  ├─ actions.detect_intent() → deterministic safety net
  ├─ actions.validate_actions() → allowlist + URL checks
  └─ actions.execute_actions() → argv only, shell=False
        │
        ▼  JSON {reply, provider, warning, terminal[]}
Chat + Guarded terminal panel + browser speechSynthesis
```

`brain.py` asks the model for strict JSON with a short `reply` and optional named `actions`. Even if the model misbehaves, `detect_intent()` still catches `youtube`, and `validate_actions()` blocks anything not in `actions.py`.

### Add an action

Edit `actions.py`:

- add a site to `SITES`,
- add a launcher to `APPS`,
- add a read-only report to `SAFE_COMMANDS`, or
- add a new `kind` to `normalize_action()` and `execute_action()`.

Never concatenate user text into a shell string. Return an `argv` list and let `_run_capture()` or `_spawn()` handle it.

---

## 9. Security notes

- Default bind is `127.0.0.1`. Use `--host 0.0.0.0` only on a trusted LAN; it exposes system-action endpoints.
- The AI brain cannot execute arbitrary commands. Unknown actions become a visible `reject_command` terminal entry.
- `open_url` accepts public `http/https` only; localhost, private IPs, `.local` and credentials-in-URL are rejected.
- `Bazzite` system files are not modified by the assistant. App installs and OS updates remain under your control.
- `.env`, transcript logs and recorded audio are gitignored. `setup_github.sh` and `sync_to_github.sh` refuse to stage them.
- There is no authentication on the local API because it is localhost-only by design. If you expose it beyond localhost, put it behind a reverse proxy with authentication first.

---

## 10. Tests

```bash
cd ~/rog-ally-x-ai-assistant
python3 -m unittest discover -s tests -v
```

Tests cover YouTube intent detection, Arena Agent alias, unsafe URL/command rejection, dry-run execution, demo brain fallback, the standalone UI build, shell script syntax, WAV handling, and `/api/chat` against a temporary local server.

After editing `ui/styles.css`, `ui/app.js`, `ui/index.template.html`, or `assets/avatar.png`, rebuild the standalone page:

```bash
python3 scripts/build_ui.py
```

---

## 11. Troubleshooting

| Problem | Fix |
|---|---|
| `DEMO BRAIN` badge | Add `ARENA_API_KEY` to `.env`, then restart. |
| Arena `403` | Use a workspace key with API access or an enabled model; free-router keys can be client-restricted. |
| Mic button does nothing | Use Chromium/Edge, open `http://127.0.0.1:8787`, and allow mic permission. Switch to Browser STT or type. |
| Local Whisper says not installed | Run `./scripts/install_whisper.sh`, verify `WHISPER_PYTHON` in `.env`, restart the service. |
| YouTube does not open | Set `BROWSER_COMMAND` in `.env`, e.g. `BROWSER_COMMAND=flatpak run org.mozilla.firefox`. |
| Volume/brightness command missing | Install/enable PipeWire tools (`wpctl`/`pactl`) or `brightnessctl` via your preferred Bazzite method. |
| `gh: command not found` | `brew install gh`, then rerun `./scripts/setup_github.sh`. |
| Want to inspect without executing | Run `python3 app.py --dry-run` or set `ASSISTANT_DRY_RUN=1`. |

---

## 12. File map

See [WORKSPACE.md](WORKSPACE.md) for the full path map and what is intentionally excluded from Git.

Official references: Arena API dashboard/docs [2](https://platform.arena.ai/docs), Arena OpenAI-compatible setup [5](https://platform.arena.ai/docs/opencode), Bazzite FAQ [1](https://docs.bazzite.gg/General/FAQ/).
