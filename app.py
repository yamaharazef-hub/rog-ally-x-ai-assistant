#!/usr/bin/env python3
"""R • ROG Ally X AI Assistant — local web server and API.

Standard-library only. Bind to 127.0.0.1 on the handheld; use --host 0.0.0.0
only when you intentionally want LAN/preview access.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import actions
import brain
from settings import ASSETS_DIR, DATA_DIR, STATIC_DIR, Config

MAX_BODY = 64 * 1024
MAX_AUDIO = 20 * 1024 * 1024
WHISPER_SCRIPT = Path(__file__).resolve().parent / "scripts" / "whisper_stt.py"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_transcript(record: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with (DATA_DIR / "conversation.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def brain_terminal_entry(text: str, result: brain.BrainResult) -> dict:
    short = text.replace("\n", " ")
    if len(short) > 70:
        short = short[:67] + "…"
    return {
        "command": f'$ r.brain --ask "{short}"',
        "ok": True,
        "stdout": result.reply,
        "stderr": "",
        "note": f"provider={result.provider} • model={result.model}" + (" • fallback" if result.fallback else ""),
        "simulated": False,
        "action": "brain",
    }


def make_handler(cfg: Config, dry_run_override: bool | None = None) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "RAssistant/1.0"
        sys_version = ""
        cfg = None  # set below
        dry_run = None

        def _send_bytes(self, status: int, body: bytes, content_type: str, cache: str = "no-store") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, body, "application/json; charset=utf-8")

        def _error(self, status: int, message: str, **extra: object) -> None:
            self._send_json(status, {"error": message, **extra})

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                raise ValueError("Empty request body")
            if length > MAX_BODY:
                raise ValueError("Request body is too large")
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Invalid JSON body") from exc
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def _serve_file(self, path: Path, content_type: str | None = None) -> None:
            if not path.exists() or not path.is_file():
                self._error(404, "Not found")
                return
            if content_type is None:
                content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self._send_bytes(200, path.read_bytes(), content_type, cache="no-cache")

        def _config(self) -> Config:
            return self.server.assistant_config  # type: ignore[attr-defined]

        def _dry(self) -> bool:
            return self.server.assistant_dry_run  # type: ignore[attr-defined]

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def do_GET(self) -> None:  # noqa: N802
            cfg = self._config()
            path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
            if path in {"/", "/index.html"}:
                index = STATIC_DIR / "index.html"
                if not index.exists():
                    try:
                        from scripts.build_ui import build

                        build()
                    except Exception as exc:  # pragma: no cover - defensive
                        self._error(500, f"Could not build the UI: {exc}")
                        return
                self._serve_file(index, "text/html; charset=utf-8")
                return
            if path == "/api/health":
                self._send_json(200, {"ok": True, "service": "R • ROG Ally X Assistant", "time": now_iso(), **cfg.public_status()})
                return
            if path == "/api/config":
                self._send_json(200, {**cfg.public_status(), "quickActions": actions.quick_action_catalog(cfg), "time": now_iso()})
                return
            if path == "/api/actions":
                self._send_json(200, {"actions": actions.quick_action_catalog(cfg)})
                return
            if path == "/api/transcript":
                transcript = DATA_DIR / "conversation.jsonl"
                lines = transcript.read_text(encoding="utf-8").splitlines()[-100:] if transcript.exists() else []
                records = []
                for line in lines:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                self._send_json(200, {"records": records})
                return
            if path.startswith("/assets/"):
                name = path.removeprefix("/assets/")
                if name in {"avatar.png", "avatar.jpg"}:
                    self._serve_file(ASSETS_DIR / name)
                    return
            self._error(404, "Not found")

        def do_POST(self) -> None:  # noqa: N802
            cfg = self._config()
            path = urllib.parse.urlparse(self.path).path.rstrip("/")
            if path == "/api/chat":
                self._post_chat(cfg)
            elif path == "/api/action":
                self._post_action(cfg)
            elif path == "/api/transcribe":
                self._post_transcribe(cfg)
            else:
                self._error(404, "Not found")

        def _post_chat(self, cfg: Config) -> None:
            try:
                data = self._read_json()
            except ValueError as exc:
                self._error(400, str(exc))
                return
            text = str(data.get("text") or "").strip()
            if not text:
                self._error(400, "Missing 'text'")
                return
            if len(text) > 3000:
                text = text[:3000]
            history = data.get("history") if isinstance(data.get("history"), list) else []
            result = brain.think(text, history, cfg)
            intent_actions = actions.detect_intent(text, cfg)
            final_actions = actions.merge_actions(result.actions, intent_actions, cfg)
            terminal = [brain_terminal_entry(text, result)]
            terminal.extend(actions.execute_actions(final_actions, cfg, dry_run=self._dry()))
            payload = {
                "reply": result.reply,
                "provider": {
                    "name": result.provider,
                    "model": result.model,
                    "configured": result.configured,
                    "fallback": result.fallback,
                },
                "warning": result.warning,
                "actions": final_actions,
                "terminal": terminal,
                "time": now_iso(),
            }
            append_transcript({"ts": payload["time"], "user": text, "reply": result.reply, "provider": result.provider, "actions": final_actions})
            self._send_json(200, payload)

        def _post_action(self, cfg: Config) -> None:
            try:
                data = self._read_json()
            except ValueError as exc:
                self._error(400, str(exc))
                return
            raw = data.get("action") if isinstance(data.get("action"), dict) else data
            final = actions.validate_actions([raw], cfg)
            terminal = actions.execute_actions(final, cfg, dry_run=self._dry())
            payload = {
                "reply": actions.describe_action(final[0]) if final else "Nothing to do.",
                "actions": final,
                "terminal": terminal,
                "time": now_iso(),
            }
            self._send_json(200, payload)

        def _post_transcribe(self, cfg: Config) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                self._error(400, "No audio received")
                return
            if length > MAX_AUDIO:
                self._error(413, "Audio clip is too large (20 MB max)")
                return
            audio = self.rfile.read(length)
            if not (audio.startswith(b"RIFF") and b"WAVE" in audio[:12]):
                self._error(415, "Expected a WAV recording from the browser")
                return
            try:
                python_argv = shlex.split(cfg.whisper_python) or [sys.executable]
            except ValueError:
                python_argv = [sys.executable]
            with tempfile.TemporaryDirectory(prefix="r-whisper-") as tmp:
                wav_path = Path(tmp) / "speech.wav"
                wav_path.write_bytes(audio)
                argv = [
                    *python_argv,
                    str(WHISPER_SCRIPT),
                    str(wav_path),
                    "--model",
                    cfg.whisper_model,
                    "--language",
                    cfg.whisper_language,
                    "--beam-size",
                    str(cfg.whisper_beam_size),
                ]
                try:
                    proc = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=150, check=False)
                except subprocess.TimeoutExpired:
                    self._error(504, "Whisper transcription timed out")
                    return
                except OSError as exc:
                    self._error(500, f"Could not start Whisper: {exc}", hint=f"Check WHISPER_PYTHON={cfg.whisper_python}")
                    return
                stdout = proc.stdout.strip()
                try:
                    parsed = json.loads(stdout.splitlines()[-1] if stdout else "{}")
                except json.JSONDecodeError:
                    parsed = {"error": (stdout or proc.stderr or "Whisper returned no result").strip()[:400]}
            if parsed.get("error"):
                self._error(503, parsed["error"], hint="Install faster-whisper in a venv and set WHISPER_PYTHON in .env, or switch to browser speech recognition.")
                return
            self._send_json(200, {"text": str(parsed.get("text") or "").strip(), "engine": "faster-whisper", "model": cfg.whisper_model})

        def log_message(self, fmt: str, *args: object) -> None:
            if os.environ.get("ASSISTANT_VERBOSE"):
                super().log_message(fmt, *args)

    Handler.cfg = cfg
    Handler.dry_run = dry_run_override
    return Handler


class AssistantServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(host: str, port: int, cfg: Config, dry_run: bool | None = None, open_browser: bool = False) -> None:
    handler = make_handler(cfg, dry_run)
    httpd = AssistantServer((host, port), handler)
    httpd.assistant_config = cfg  # type: ignore[attr-defined]
    httpd.assistant_dry_run = cfg.dry_run if dry_run is None else dry_run  # type: ignore[attr-defined]
    actual_port = httpd.server_address[1]
    if host == "0.0.0.0":
        print("⚠  Listening on all interfaces. On the Ally X, prefer 127.0.0.1 so system actions stay local.", flush=True)
    if httpd.assistant_dry_run:  # type: ignore[attr-defined]
        print("ℹ  Dry-run mode: system actions are simulated and shown in the terminal panel.", flush=True)
    print(f"✓ R assistant ready at http://127.0.0.1:{actual_port}  (brain={cfg.provider}/{cfg.model_name}, configured={cfg.brain_configured})", flush=True)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(f"http://127.0.0.1:{actual_port}")).start()
    try:
        httpd.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping R assistant…", flush=True)
    finally:
        httpd.server_close()


def main() -> int:
    base = Config.load()
    parser = argparse.ArgumentParser(description="R • ROG Ally X AI Assistant")
    parser.add_argument("--host", default=base.host, help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=base.port, help="Port (default: 8787)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate system actions instead of executing them")
    parser.add_argument("--open", action="store_true", help="Open the default browser after startup")
    args = parser.parse_args()
    cfg = replace(base, host=args.host, port=args.port)
    dry_run = True if args.dry_run else None
    try:
        from scripts.build_ui import build

        if not (STATIC_DIR / "index.html").exists():
            build()
    except Exception as exc:
        print(f"Could not prepare UI: {exc}", file=sys.stderr)
        return 1
    serve(args.host, args.port, cfg, dry_run=dry_run, open_browser=args.open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
