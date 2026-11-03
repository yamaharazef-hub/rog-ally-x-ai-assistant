"""Guarded system-action dispatcher for the R assistant.

The AI brain may *request* actions, but it never gets a raw shell. Every action
is normalized, validated and mapped here to an argv list with shell=False.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from settings import ROOT, Config

SYSTEM_REPORT = ROOT / "scripts" / "system_report.py"

SITES: dict[str, tuple[str, tuple[str, ...]]] = {
    "arena_agent": ("", ("arena agent", "arena.ai/agent", "agent mode")),
    "youtube": ("https://www.youtube.com/", ("youtube", "yt", "youtube.com")),
    "github": ("https://github.com/", ("github", "github.com")),
    "gmail": ("https://mail.google.com/", ("gmail", "google mail")),
    "google": ("https://www.google.com/", ("google", "google.com")),
    "arena": ("https://arena.ai/", ("arena ai", "arena.ai")),
    "chatgpt": ("https://chatgpt.com/", ("chatgpt",)),
    "reddit": ("https://www.reddit.com/", ("reddit",)),
    "twitch": ("https://www.twitch.tv/", ("twitch",)),
    "netflix": ("https://www.netflix.com/", ("netflix",)),
    "spotify_web": ("https://open.spotify.com/", ("spotify web",)),
    "steam_store": ("https://store.steampowered.com/", ("steam store",)),
    "proton_db": ("https://www.protondb.com/", ("protondb", "proton db")),
    "bazzite_docs": ("https://docs.bazzite.gg/", ("bazzite docs", "bazzite documentation")),
}

APP_ALIASES: dict[str, tuple[str, ...]] = {
    "steam": ("steam",),
    "firefox": ("firefox", "firefox browser"),
    "chromium": ("chromium", "chromium browser", "chrome browser"),
    "edge": ("microsoft edge", "edge browser"),
    "discord": ("discord",),
    "spotify": ("spotify", "spotify app"),
    "terminal": ("terminal", "konsole", "gnome terminal"),
    "files": ("file manager", "files", "dolphin", "nautilus"),
    "settings": ("settings", "system settings"),
    "heroic": ("heroic", "heroic games launcher"),
    "bazzite_portal": ("bazzite portal",),
    "calculator": ("calculator",),
    "text_editor": ("text editor", "kate", "gedit"),
}

# Ordered candidates; the first executable found wins.
APPS: dict[str, list[list[str]]] = {
    "steam": [["steam"], ["flatpak", "run", "com.valvesoftware.Steam"], ["gtk-launch", "steam"]],
    "firefox": [["firefox"], ["flatpak", "run", "org.mozilla.firefox"], ["gtk-launch", "org.mozilla.firefox"]],
    "chromium": [["chromium"], ["chromium-browser"], ["flatpak", "run", "org.chromium.Chromium"]],
    "edge": [["microsoft-edge"], ["flatpak", "run", "com.microsoft.Edge"]],
    "discord": [["discord"], ["flatpak", "run", "com.discordapp.Discord"]],
    "spotify": [["spotify"], ["flatpak", "run", "com.spotify.Client"]],
    "terminal": [["kgx"], ["konsole"], ["gnome-terminal"], ["xterm"]],
    "files": [["dolphin"], ["nautilus"], ["thunar"]],
    "settings": [["systemsettings"], ["gnome-control-center"]],
    "heroic": [["heroic"], ["flatpak", "run", "com.heroicgameslauncher.hgl"]],
    "bazzite_portal": [["flatpak", "run", "io.github.ublue_os.BazzitePortal"]],
    "calculator": [["kcalc"], ["gnome-calculator"]],
    "text_editor": [["kate"], ["gedit"], ["gnome-text-editor"]],
}

FOLDERS: dict[str, tuple[str, ...]] = {
    "home": ("home folder", "home directory"),
    "downloads": ("downloads", "downloads folder"),
    "documents": ("documents", "documents folder"),
    "desktop": ("desktop", "desktop folder"),
    "pictures": ("pictures", "pictures folder"),
    "music": ("music", "music folder"),
    "videos": ("videos", "videos folder"),
    "project": ("project folder", "assistant folder", "workstation"),
}

# Each logical query maps to one or more argv-only commands.
SAFE_COMMANDS: dict[str, list[list[str]]] = {
    "status": [[sys.executable, str(SYSTEM_REPORT), "status"]],
    "battery": [[sys.executable, str(SYSTEM_REPORT), "battery"]],
    "temperature": [[sys.executable, str(SYSTEM_REPORT), "temperature"]],
    "network": [[sys.executable, str(SYSTEM_REPORT), "network"], ["ip", "-brief", "address"]],
    "updates": [[sys.executable, str(SYSTEM_REPORT), "updates"]],
    "processes": [[sys.executable, str(SYSTEM_REPORT), "processes"]],
    "memory": [["free", "-h"]],
    "disk": [["df", "-h", "--total"]],
    "time": [["date", "+%A, %d %B %Y • %H:%M:%S %Z"]],
    "whoami": [["whoami"]],
    "hostname": [["hostname"]],
    "os": [["cat", "/etc/os-release"]],
    "flatpaks": [["flatpak", "list", "--app", "--columns=name,application"]],
}


def clip(text: str, limit: int) -> str:
    text = text.rstrip()
    if len(text) > limit:
        return text[:limit] + f"\n… output clipped at {limit} characters"
    return text


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    uid = os.getuid() if hasattr(os, "getuid") else 1000
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
    env.setdefault("DISPLAY", ":0")
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    env.setdefault("XDG_CURRENT_DESKTOP", "KDE")
    env.setdefault("GDK_BACKEND", "wayland,x11")
    env.setdefault("HOME", str(Path.home()))
    return env


def command_string(argv: list[str]) -> str:
    return shlex.join(argv)


def _entry(
    command: str,
    *,
    ok: bool = True,
    stdout: str = "",
    stderr: str = "",
    note: str = "",
    simulated: bool = False,
    action: str = "",
) -> dict:
    return {
        "command": command,
        "ok": ok,
        "stdout": clip(stdout, 6000),
        "stderr": clip(stderr, 2000),
        "note": note,
        "simulated": simulated,
        "action": action,
    }


def valid_url(url: str) -> str | None:
    url = (url or "").strip()
    if len(url) > 2000 or not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return None
    if host.endswith((".localhost", ".local", ".internal")):
        return None
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return None
    except ValueError:
        pass
    return url


def site_url(key: str, cfg: Config) -> str:
    if key == "arena_agent":
        return cfg.arena_agent_url
    return SITES[key][0]


def detect_intent(text: str, cfg: Config) -> list[dict]:
    """Deterministic backup so 'youtube' always works, even offline."""
    raw = (text or "").strip()
    low = " " + raw.lower() + " "
    found: list[dict] = []

    def add(action: dict) -> None:
        if action not in found:
            found.append(action)

    # Explicit URL or search request.
    url_match = re.search(r"https?://[^\s<>\"']+", raw, re.I)
    if url_match and re.search(r"\b(open|go to|visit|browse)\b", low):
        add({"type": "open_url", "value": url_match.group(0), "label": "that link"})
    search = re.search(r"\b(?:search(?: the web)? for|google|look up|find me)\s+(.+?)\s*[?.!]*$", raw, re.I)
    if search:
        query = search.group(1).strip(" \"'")
        if query:
            add({"type": "open_url", "value": f"https://www.google.com/search?q={quote_plus(query)}", "label": f"search: {query}"})

    # Longest aliases first so 'arena agent' beats 'arena'.
    aliases: list[tuple[str, str]] = []
    for key, (_url, names) in SITES.items():
        for alias in names:
            aliases.append((alias, key))
    for alias, key in sorted(aliases, key=lambda item: len(item[0]), reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", low):
            add({"type": "open_url", "value": site_url(key, cfg), "label": alias})
            break

    for key, names in APP_ALIASES.items():
        for alias in names:
            if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", low) and re.search(
                r"\b(open|launch|start|run)\b", low
            ):
                add({"type": "open_app", "value": key, "label": alias})
                break
        if found and any(a.get("type") == "open_app" for a in found):
            break

    for key, names in FOLDERS.items():
        for alias in names:
            if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", low) and re.search(
                r"\b(open|show|go to)\b", low
            ):
                add({"type": "open_folder", "value": key, "label": alias})
                break

    # Audio and display.
    volume = re.search(r"\b(?:set )?volume(?: to| at)?\s*(\d{1,3})\s*%?", low)
    if volume:
        add({"type": "set_volume", "value": int(volume.group(1)), "label": "volume"})
    elif re.search(r"\bvolume\s+(up|down)\b", low):
        add({"type": "set_volume", "value": "up" if re.search(r"volume\s+up", low) else "down", "label": "volume"})
    elif re.search(r"\bunmute\b", low):
        add({"type": "set_volume", "value": "unmute", "label": "volume"})
    elif re.search(r"\bmute\b", low):
        add({"type": "set_volume", "value": "mute", "label": "volume"})

    brightness = re.search(r"\b(?:set )?brightness(?: to| at)?\s*(\d{1,3})\s*%?", low)
    if brightness:
        add({"type": "set_brightness", "value": int(brightness.group(1)), "label": "brightness"})

    if re.search(r"\b(lock|lock screen|lock the screen)\b", low):
        add({"type": "power", "value": "lock", "label": "screen lock"})
    elif re.search(r"\b(suspend|sleep|sleep mode)\b", low):
        add({"type": "power", "value": "suspend", "label": "suspend"})

    if re.search(r"\b(screenshot|take a screenshot|capture screen)\b", low):
        add({"type": "screenshot", "value": "screen", "label": "screenshot"})
    if re.search(r"\b(notify|notification)\b", low) and re.search(r"\b(test|send)\b", low):
        add({"type": "notify", "value": "R is online and ready.", "label": "notification"})

    # Read-only system reports.
    report_patterns: list[tuple[str, str]] = [
        ("status", r"\b(system status|system info|system report|device status)\b"),
        ("battery", r"\b(battery|battery level|battery status|charge level)\b"),
        ("temperature", r"\b(temperature|cpu temp|thermals|how hot)\b"),
        ("network", r"\b(network status|ip address|network info|wifi status)\b"),
        ("updates", r"\b(check updates|update status|system updates|bazzite version)\b"),
        ("processes", r"\b(running processes|top processes|process list)\b"),
        ("memory", r"\b(memory|ram usage|ram)\b"),
        ("disk", r"\b(disk space|storage|free space)\b"),
        ("time", r"\b(what time|current time|what is the time|date and time|what's the date)\b"),
        ("whoami", r"\b(who am i|current user)\b"),
        ("hostname", r"\b(hostname|device name)\b"),
        ("os", r"\b(operating system|os version|bazzite info)\b"),
        ("flatpaks", r"\b(installed flatpaks|flatpak list|list flatpaks)\b"),
    ]
    for key, pattern in report_patterns:
        if re.search(pattern, low):
            add({"type": "terminal", "value": key, "label": key})

    # Give a clear terminal answer instead of silently ignoring a raw shell request.
    if not found and (raw.startswith("$ ") or re.search(r"\b(run|execute)\b.+\b(rm |sudo |dd |mkfs|chmod |chown |curl |wget |bash |sh -c)", low)):
        add({"type": "reject_command", "value": "Raw shell commands are disabled in guarded mode.", "label": "blocked"})

    return found


def normalize_action(action: object, cfg: Config) -> dict | None:
    if not isinstance(action, dict):
        return None
    kind = str(action.get("type", "")).strip().lower()
    value = action.get("value")
    label = str(action.get("label", "")).strip()[:80]

    if kind == "open_url":
        url = valid_url(str(value or ""))
        return {"type": "open_url", "value": url, "label": label or "link"} if url else {"type": "reject_command", "value": "Blocked a non-public or non-HTTP URL.", "label": "blocked"}
    if kind == "open_app":
        key = str(value or "").strip().lower()
        return {"type": "open_app", "value": key, "label": label or key} if key in APPS else None
    if kind == "open_folder":
        key = str(value or "").strip().lower()
        return {"type": "open_folder", "value": key, "label": label or key} if key in FOLDERS else None
    if kind == "terminal":
        key = str(value or "").strip().lower()
        return {"type": "terminal", "value": key, "label": label or key} if key in SAFE_COMMANDS else None
    if kind == "set_volume":
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            number = int(value)
            if 0 <= number <= 100:
                return {"type": "set_volume", "value": number, "label": label or "volume"}
        elif value in {"up", "down", "mute", "unmute", "toggle"}:
            return {"type": "set_volume", "value": value, "label": label or "volume"}
        return None
    if kind == "set_brightness":
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return {"type": "set_brightness", "value": max(0, min(100, number)), "label": label or "brightness"}
    if kind == "power":
        return {"type": "power", "value": value, "label": label or str(value)} if value in {"lock", "suspend"} else None
    if kind == "screenshot":
        return {"type": "screenshot", "value": "screen", "label": label or "screenshot"}
    if kind == "notify":
        return {"type": "notify", "value": str(value or "R is online.")[:200], "label": label or "notification"}
    if kind == "reject_command":
        return {"type": "reject_command", "value": str(value or "Command blocked by guarded mode.")[:200], "label": label or "blocked"}
    return None


def validate_actions(raw_actions: list[object], cfg: Config) -> list[dict]:
    valid: list[dict] = []
    seen: set[str] = set()
    for action in raw_actions:
        normalized = normalize_action(action, cfg)
        if normalized is None:
            normalized = {"type": "reject_command", "value": "Unsupported AI action blocked by guarded mode.", "label": "blocked"}
        # Labels are cosmetic; two actions with the same type+value should run once.
        identity = {k: v for k, v in normalized.items() if k != "label"}
        key = json.dumps(identity, sort_keys=True)
        if key not in seen:
            valid.append(normalized)
            seen.add(key)
    return valid[: cfg.max_actions]


def merge_actions(brain_actions: list[object], intent_actions: list[dict], cfg: Config) -> list[dict]:
    # Local intent is the safety net; brain actions are optional and validated.
    return validate_actions(list(intent_actions) + list(brain_actions), cfg)


def describe_action(action: dict) -> str:
    kind = action["type"]
    label = action.get("label") or action.get("value")
    if kind == "open_url":
        return f"Opening {label} in your browser."
    if kind == "open_app":
        return f"Launching {label}."
    if kind == "open_folder":
        return f"Opening the {label}."
    if kind == "terminal":
        return f"Running a guarded {label} check. The terminal output is shown below."
    if kind == "set_volume":
        return f"Setting the {label}."
    if kind == "set_brightness":
        return f"Setting {label}."
    if kind == "power":
        return f"Requesting {label}."
    if kind == "screenshot":
        return "Taking a screenshot."
    if kind == "notify":
        return "Sending a desktop notification."
    if kind == "reject_command":
        return "I blocked that command because guarded mode only allows approved system actions."
    return "Done."


def quick_action_catalog(cfg: Config) -> list[dict]:
    return [
        {"id": "youtube", "label": "YouTube", "glyph": "▶", "action": {"type": "open_url", "value": "https://www.youtube.com/", "label": "YouTube"}},
        {"id": "arena", "label": "Arena Agent", "glyph": "✦", "action": {"type": "open_url", "value": cfg.arena_agent_url, "label": "Arena Agent"}},
        {"id": "status", "label": "System status", "glyph": "▤", "action": {"type": "terminal", "value": "status", "label": "system status"}},
        {"id": "battery", "label": "Battery", "glyph": "▰", "action": {"type": "terminal", "value": "battery", "label": "battery"}},
        {"id": "volume", "label": "Volume 50%", "glyph": "◖", "action": {"type": "set_volume", "value": 50, "label": "volume"}},
        {"id": "lock", "label": "Lock screen", "glyph": "▣", "action": {"type": "power", "value": "lock", "label": "screen lock"}},
    ]


def _first_available(candidates: list[list[str]]) -> list[str] | None:
    for argv in candidates:
        if argv and shutil.which(argv[0]):
            return argv
    return None


def _spawn(argv: list[str], cfg: Config, dry_run: bool, action: str, note: str = "") -> dict:
    command = command_string(argv)
    if dry_run:
        return _entry(command, note=note or "Simulated — no process launched (dry-run mode).", simulated=True, action=action)
    if not shutil.which(argv[0]):
        return _entry(command, ok=False, note=f"Executable not found: {argv[0]}. Install the app or set BROWSER_COMMAND.", action=action)
    try:
        subprocess.Popen(
            argv,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            env=build_env(),
        )
        return _entry(command, note=note or "Launch request sent.", action=action)
    except OSError as exc:
        return _entry(command, ok=False, stderr=str(exc), note="Could not launch the process.", action=action)


def _run_capture(argv: list[str], cfg: Config, dry_run: bool, action: str) -> dict:
    command = command_string(argv)
    if dry_run:
        return _entry(command, note="Simulated — command not executed (dry-run mode).", simulated=True, action=action)
    if not shutil.which(argv[0]):
        return _entry(command, ok=False, note=f"Command not available: {argv[0]}.", action=action)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=cfg.command_timeout,
            env=build_env(),
            check=False,
        )
        return _entry(
            command,
            ok=proc.returncode == 0,
            stdout=clip(proc.stdout, cfg.max_output_chars),
            stderr=clip(proc.stderr, min(2000, cfg.max_output_chars)),
            note=f"exit={proc.returncode} • {int((time.monotonic() - started) * 1000)} ms",
            action=action,
        )
    except subprocess.TimeoutExpired:
        return _entry(command, ok=False, stderr=f"Timed out after {cfg.command_timeout}s.", action=action)
    except OSError as exc:
        return _entry(command, ok=False, stderr=str(exc), action=action)


def folder_path(key: str) -> Path:
    home = Path.home()
    if key == "project":
        return ROOT
    return home / key.capitalize() if key != "home" else home


def volume_argv(value: object) -> list[list[str]]:
    if isinstance(value, int):
        pct = f"{value}%"
        return [
            ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", pct],
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", pct],
            ["amixer", "-D", "pulse", "sset", "Master", pct],
        ]
    if value in {"up", "down"}:
        delta = "+5%" if value == "up" else "-5%"
        wp_delta = "5%+" if value == "up" else "5%-"
        return [
            ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", wp_delta],
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", delta],
        ]
    if value == "mute":
        return [["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"], ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"]]
    if value == "unmute":
        return [["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"]]
    return [["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"], ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"]]


def execute_action(action: dict, cfg: Config, dry_run: bool | None = None) -> list[dict]:
    dry = cfg.dry_run if dry_run is None else dry_run
    kind = action["type"]
    value = action.get("value")

    if kind == "reject_command":
        return [_entry("# blocked by guarded mode", ok=False, note=str(value), action=kind)]
    if kind == "open_url":
        url = str(value)
        candidates = [cfg.browser_argv + [url], ["xdg-open", url], ["gio", "open", url], ["flatpak-spawn", "--host", "xdg-open", url]]
        argv = _first_available(candidates) if not dry else candidates[0]
        return [_spawn(argv or candidates[0], cfg, dry, kind, note="Browser open request sent.")]
    if kind == "open_app":
        candidates = APPS.get(str(value), [])
        argv = _first_available(candidates) if not dry else (candidates[0] if candidates else ["echo", "app"])
        if not argv:
            return [_entry(f"# launch {value}", ok=False, note="No launcher found for this app.", action=kind)]
        return [_spawn(argv, cfg, dry, kind)]
    if kind == "open_folder":
        path = folder_path(str(value))
        return [_spawn(["xdg-open", str(path)], cfg, dry, kind)]
    if kind == "terminal":
        return [_run_capture(argv, cfg, dry, kind) for argv in SAFE_COMMANDS[str(value)]]
    if kind == "set_volume":
        candidates = volume_argv(value)
        argv = _first_available(candidates) if not dry else candidates[0]
        if not argv:
            return [_entry("# set volume", ok=False, note="Install PipeWire tools (wpctl or pactl) to control volume.", action=kind)]
        return [_run_capture(argv, cfg, dry, kind)]
    if kind == "set_brightness":
        argv = ["brightnessctl", "set", f"{int(value)}%"]
        return [_run_capture(argv, cfg, dry, kind)]
    if kind == "power":
        if value == "lock":
            candidates = [["loginctl", "lock-session"], ["xdg-screensaver", "lock"], ["gnome-screensaver-command", "--lock"]]
        else:
            candidates = [["systemctl", "suspend"]]
        argv = _first_available(candidates) if not dry else candidates[0]
        return [_run_capture(argv, cfg, dry, kind)]
    if kind == "screenshot":
        pictures = Path.home() / "Pictures"
        target = pictures / f"R-screenshot-{time.strftime('%Y%m%d-%H%M%S')}.png"
        candidates = [["spectacle", "-b", "-n", "-o", str(target)], ["gnome-screenshot", "-f", str(target)]]
        argv = _first_available(candidates) if not dry else candidates[0]
        return [_spawn(argv, cfg, dry, kind, note=f"Saving to {target}.")]
    if kind == "notify":
        return [_run_capture(["notify-send", "R Assistant", str(value)], cfg, dry, kind)]
    return [_entry(f"# unsupported action: {kind}", ok=False, note="Blocked.", action=kind)]


def execute_actions(actions: list[dict], cfg: Config, dry_run: bool | None = None) -> list[dict]:
    entries: list[dict] = []
    for action in actions:
        entries.extend(execute_action(action, cfg, dry_run=dry_run))
    return entries
