"""Offline tests:  python3 -m unittest discover -s tests -v"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import unittest
import urllib.request
import wave
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import actions  # noqa: E402
import app  # noqa: E402
import brain  # noqa: E402
from scripts.build_ui import build  # noqa: E402
from settings import Config  # noqa: E402


class IntentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = replace(Config.load(), provider="demo", dry_run=True)

    def test_youtube_from_voice_transcript(self) -> None:
        for text in ("youtube", "open youtube", "please open youtube in the browser"):
            with self.subTest(text=text):
                found = actions.detect_intent(text, self.cfg)
                self.assertEqual(found[0]["type"], "open_url")
                self.assertEqual(found[0]["value"], "https://www.youtube.com/")

    def test_arena_agent_alias_beats_generic_arena(self) -> None:
        found = actions.detect_intent("open arena agent", self.cfg)
        self.assertEqual(found[0]["value"], self.cfg.arena_agent_url)

    def test_volume_and_battery_intents(self) -> None:
        self.assertIn({"type": "set_volume", "value": 50, "label": "volume"}, actions.detect_intent("set volume to 50%", self.cfg))
        self.assertIn({"type": "terminal", "value": "battery", "label": "battery"}, actions.detect_intent("check battery", self.cfg))

    def test_unsafe_urls_and_commands_are_blocked(self) -> None:
        self.assertIsNone(actions.valid_url("file:///etc/passwd"))
        self.assertIsNone(actions.valid_url("http://127.0.0.1:8787"))
        self.assertIsNone(actions.valid_url("http://192.168.1.10"))
        self.assertEqual(actions.valid_url("https://www.youtube.com/"), "https://www.youtube.com/")
        self.assertIsNone(actions.normalize_action({"type": "terminal", "value": "rm -rf /"}, self.cfg))
        rejected = actions.validate_actions([{"type": "open_url", "value": "file:///etc/passwd"}], self.cfg)
        self.assertEqual(rejected[0]["type"], "reject_command")

    def test_duplicate_brain_and_intent_actions_run_once(self) -> None:
        intent = actions.detect_intent("open youtube", self.cfg)
        brain_actions = [{"type": "open_url", "value": "https://www.youtube.com/", "label": "YouTube"}]
        merged = actions.merge_actions(brain_actions, intent, self.cfg)
        self.assertEqual(len(merged), 1)


class ExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = replace(Config.load(), provider="demo", dry_run=True)

    def test_dry_run_never_launches_a_process(self) -> None:
        entries = actions.execute_actions(
            [{"type": "open_url", "value": "https://www.youtube.com/", "label": "YouTube"}],
            self.cfg,
            dry_run=True,
        )
        self.assertTrue(entries[0]["simulated"])
        self.assertIn("youtube", entries[0]["command"])

    def test_demo_brain_still_supplies_actions(self) -> None:
        result = brain.think("open youtube", [], self.cfg)
        self.assertEqual(result.provider, "demo")
        self.assertIn("Opening", result.reply)
        self.assertEqual(result.actions[0]["type"], "open_url")

    def test_status_report_is_read_only_stdlib(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "system_report.py"), "status"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Host", proc.stdout)


class UiAndScriptTests(unittest.TestCase):
    def test_generated_ui_is_standalone(self) -> None:
        path = build()
        html = path.read_text(encoding="utf-8")
        self.assertIn("data:image/png;base64,", html)
        self.assertNotIn("__AVATAR_DATA_URI__", html)
        self.assertNotIn('<link rel="stylesheet"', html)
        self.assertIn("/api/chat", html)

    def test_shell_scripts_parse(self) -> None:
        for script in sorted((ROOT / "scripts").glob("*.sh")):
            with self.subTest(script=script.name):
                proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True, check=False)
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_whisper_script_rejects_bad_audio_before_model_load(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.wav"
            bad.write_bytes(b"not a wav")
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "whisper_stt.py"), str(bad)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertIn("error", payload)

    def test_wav_encoder_fixture_is_valid(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "silence.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 1600)
            with wave.open(str(path), "rb") as wav:
                self.assertEqual(wav.getsampwidth(), 2)


class ApiTests(unittest.TestCase):
    def test_chat_endpoint_with_demo_brain_and_dry_run(self) -> None:
        cfg = replace(Config.load(), provider="demo", dry_run=True)
        server = app.AssistantServer(("127.0.0.1", 0), app.make_handler(cfg, True))
        server.assistant_config = cfg  # type: ignore[attr-defined]
        server.assistant_dry_run = True  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(f"http://127.0.0.1:{port}/api/config", timeout=5) as response:
                config = json.loads(response.read())
            self.assertEqual(config["permissionMode"], "guarded")
            self.assertTrue(config["dryRun"])
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/chat",
                data=json.dumps({"text": "open youtube", "history": []}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with opener.open(request, timeout=5) as response:
                payload = json.loads(response.read())
            self.assertIn("Opening", payload["reply"])
            self.assertTrue(any("youtube" in entry["command"] for entry in payload["terminal"]))
            self.assertTrue(any(entry.get("simulated") for entry in payload["terminal"]))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
