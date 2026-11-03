# Full installation guide — ROG Ally X + Bazzite

This is the complete copy-paste path from the Arena workspace to a working assistant on your handheld. Follow it in **Bazzite Desktop Mode**. The live preview in this Arena workspace uses the demo brain and dry-run mode; the installation below uses the real Arena API and real guarded system actions.

---

## 0. What you need before starting

- ROG Ally X booted into **Bazzite Desktop Mode** with internet access.
- A GitHub account.
- An Arena API key from <https://platform.arena.ai/dashboard/keys> [2](https://platform.arena.ai/docs). The assistant uses Arena's OpenAI-compatible `https://api.arena.ai/v1` endpoint [5](https://platform.arena.ai/docs/opencode).
- **Chromium, Chrome or Edge** for browser speech recognition and microphone access.
- The project files: `rog-ally-x-ai-assistant.zip` from this workspace, or the `rog-ally-x-ai-assistant/` folder.

Do **not** paste your Arena key into chat or commit it. It stays in `.env` on the Ally X.

---

## 1. Copy the project to the Ally X

If you downloaded the zip:

```bash
cd ~
unzip ~/Downloads/rog-ally-x-ai-assistant.zip
cd ~/rog-ally-x-ai-assistant
```

If you copied the folder directly (USB drive, `scp`, `rsync`), just:

```bash
cd ~/rog-ally-x-ai-assistant
```

Check the files are there:

```bash
ls
python3 --version
git --version
```

You should see `app.py`, `brain.py`, `actions.py`, `README.md`, `scripts/`, `static/index.html`, `assets/`, and `.env.example`.

> Python 3 and Git are normally available on Bazzite. If `python3` is missing, install it inside Distrobox or layer it with `rpm-ostree`; do not use `dnf` against the immutable base.

---

## 2. Add your Arena API key

```bash
cd ~/rog-ally-x-ai-assistant
cp .env.example .env
chmod 600 .env
nano .env
```

Find this line and paste your key after the equals sign:

```ini
ARENA_API_KEY=your_key_here
```

Leave the defaults in place unless your key requires another model:

```ini
AI_PROVIDER=arena
ARENA_BASE_URL=https://api.arena.ai/v1
ARENA_MODEL=coding-router-preview
ARENA_AGENT_URL=https://arena.ai/agent
HOST=127.0.0.1
PORT=8787
PERMISSION_MODE=guarded
ASSISTANT_DRY_RUN=0
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano).

If Arena returns `403 organization_client_restricted`, your key is probably a free-router key limited to Claude Code. Use a workspace with API access or set `ARENA_MODEL` to a model enabled for your key [2](https://platform.arena.ai/docs). The app shows this as a readable warning and falls back to the offline demo brain rather than crashing.

### Optional first test, without installing the service

```bash
python3 app.py --host 127.0.0.1 --port 8787 --open
```

Open `http://127.0.0.1:8787`, allow microphone access, and check the badge says `ARENA • coding-router-preview` rather than `DEMO BRAIN`. Type `open youtube` and watch the **Guarded terminal** panel. Press `Ctrl+C` to stop before continuing.

To test without a key or without executing commands:

```bash
python3 app.py --dry-run --open
python3 cli.py --demo --dry-run "open youtube"
```

---

## 3. Create your public GitHub repository

The GitHub connector is not available inside this Arena session, so the repository must be created from your own signed-in account on the Ally X. The included script does that.

Install GitHub CLI if needed:

```bash
command -v gh || brew install gh
```

> On Bazzite, Homebrew is the usual route. You can also install `gh` inside Distrobox or a container if you prefer.

Then run:

```bash
cd ~/rog-ally-x-ai-assistant
./scripts/setup_github.sh
```

The script will:

1. open your browser for `gh auth login --web --git-protocol https`,
2. set the local Git author from your GitHub account,
3. re-author the neutral setup commit with your GitHub identity,
4. refuse to stage `.env`, `data/`, logs or recorded audio,
5. create `rog-ally-x-ai-assistant` as a **public** repository,
6. add `origin` and push `main`.

Override the defaults if you want:

```bash
REPO_NAME=my-ally-assistant VISIBILITY=public ./scripts/setup_github.sh
# VISIBILITY=private is also supported if you change your mind.
```

At the end it prints:

```text
https://github.com/<your-account>/rog-ally-x-ai-assistant
```

If that repository already exists, the script links the remote and pushes instead of failing.

---

## 4. Install the Bazzite systemd service

Stay in Desktop Mode:

```bash
cd ~/rog-ally-x-ai-assistant
./scripts/install_bazzite.sh
```

This creates:

- `~/.config/systemd/user/rog-assistant.service`
- `~/.config/rog-assistant/session.env` with your Wayland/D-Bus session variables
- `~/.local/share/applications/r-assistant.desktop` with the robot icon
- a service bound to `http://127.0.0.1:8787`

It also rebuilds `static/index.html`, enables the service, and opens the UI. If `.env` is missing, it creates one from the template — but you should already have added your key in step 2.

Useful service commands:

```bash
systemctl --user status rog-assistant.service
systemctl --user restart rog-assistant.service
systemctl --user stop rog-assistant.service
journalctl --user -u rog-assistant.service -f
```

> Steam Gaming Mode may not expose the same desktop session variables that `xdg-open` needs. Install and test in Desktop Mode first; afterwards you can add the desktop launcher to Steam as a non-Steam game.

The installed service does **not** use `--dry-run`, so saying `youtube` really opens YouTube in your default browser. It still uses the guarded allowlist: no raw shell, no sudo, no OS package changes.

---

## 5. Optional: enable offline Local Whisper

Browser speech recognition is already available in Chromium/Edge. For fully local speech-to-text:

```bash
cd ~/rog-ally-x-ai-assistant
./scripts/install_whisper.sh
systemctl --user restart rog-assistant.service
```

The script creates a venv at `~/.local/share/rog-assistant/whisper-venv`, installs `faster-whisper`, and writes `WHISPER_PYTHON` into `.env`.

Then in the UI, change **Mic engine** to **Local Whisper** and tap the microphone. The first transcription downloads the model, so stay online once. Change `WHISPER_MODEL` in `.env` (`tiny.en`, `base.en`, `small.en`, `medium.en`) to trade speed for accuracy.

Typed input always works, even if neither microphone engine is available.

---

## 6. Verify the installation

Run these checks:

```bash
cd ~/rog-ally-x-ai-assistant

# Service and API
systemctl --user status rog-assistant.service --no-pager
curl http://127.0.0.1:8787/api/health

# Offline test suite
python3 -m unittest discover -s tests -v

# GitHub link
git remote -v
git log -1 --pretty='%h %s | %an <%ae>'
```

Open the UI:

```text
http://127.0.0.1:8787
```

Then try:

| Request | Expected result |
|---|---|
| `open youtube` | Opens `https://www.youtube.com/`; terminal shows `xdg-open ...` |
| `check battery` | Read-only battery report in the terminal panel |
| `system status` | Host, OS, uptime, memory, disk and battery summary |
| `set volume to 50%` | Guarded `wpctl`/`pactl` command |
| `open Arena Agent` | Opens `https://arena.ai/agent` |
| `run sudo rm -rf /` | Blocked, with an explanation in the terminal |

Terminal-only client:

```bash
python3 cli.py
python3 cli.py "check battery"
```

---

## 7. Keep workstation files linked to GitHub

After editing any project file:

```bash
cd ~/rog-ally-x-ai-assistant
./scripts/sync_to_github.sh
```

With a custom message:

```bash
MESSAGE="Add a new guarded action" ./scripts/sync_to_github.sh
```

The sync script also refuses to stage `.env`, `data/`, logs or audio. If you edit UI sources, rebuild first:

```bash
python3 scripts/build_ui.py
./scripts/sync_to_github.sh
```

To remove only the service and launcher while keeping project files:

```bash
./scripts/uninstall_bazzite.sh
```

---

## 8. Quick troubleshooting

| Symptom | Fix |
|---|---|
| `DEMO BRAIN` badge | Add `ARENA_API_KEY` to `.env`, then `systemctl --user restart rog-assistant.service`. |
| Arena `403` | Use a workspace key with API access or an enabled `ARENA_MODEL`. |
| Mic button does nothing | Use Chromium/Edge, open `http://127.0.0.1:8787`, allow mic permission for localhost. |
| Local Whisper says not installed | Run `./scripts/install_whisper.sh`, check `WHISPER_PYTHON` in `.env`, restart the service. |
| YouTube does not open | Set `BROWSER_COMMAND` in `.env`, e.g. `BROWSER_COMMAND=flatpak run org.mozilla.firefox`, then restart. |
| Volume/brightness command unavailable | Make sure `wpctl`/`pactl` or `brightnessctl` is available in your Bazzite setup. |
| `gh: command not found` | `brew install gh`, then rerun `./scripts/setup_github.sh`. |
| Service will not start | `journalctl --user -u rog-assistant.service -n 80 --no-pager`. |
| Want to inspect without executing | Run `python3 app.py --dry-run` or set `ASSISTANT_DRY_RUN=1`. |

---

## 9. Security reminders

- The installed service binds to `127.0.0.1`, not the LAN. Use `--host 0.0.0.0` only on a trusted network with authentication in front of it.
- `.env`, `data/conversation.jsonl`, logs and audio are gitignored.
- The AI brain can only request named actions; `actions.py` validates them and runs `argv` lists with `shell=False`.
- `open_url` accepts public HTTP/HTTPS only. Localhost, private IPs, `.local` and credentials-in-URL are rejected.
- Bazzite's system files are not modified by the assistant; app installs and OS updates remain under your control.

Full reference: [README.md](README.md) · File map: [WORKSPACE.md](WORKSPACE.md) · Official Arena docs: [dashboard/docs](https://platform.arena.ai/docs) [2](https://platform.arena.ai/docs), [OpenAI-compatible setup](https://platform.arena.ai/docs/opencode) [5](https://platform.arena.ai/docs/opencode).
