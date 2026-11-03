"""Configuration for the R assistant.

The main app intentionally uses only the Python standard library. Secrets live in
`.env` (which is gitignored) and are never sent to the browser.
"""
from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
STATIC_DIR = ROOT / "static"
ASSETS_DIR = ROOT / "assets"
DATA_DIR = ROOT / "data"


def load_dotenv(path: Path = ENV_FILE) -> None:
    """Load a tiny .env format without overriding the real process environment."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"')
        if quoted:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key:
            os.environ.setdefault(key, value)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _browser_argv() -> list[str]:
    raw = os.environ.get("BROWSER_COMMAND", "").strip()
    if raw:
        try:
            argv = shlex.split(raw)
            if argv:
                return argv
        except ValueError:
            pass
    return ["xdg-open"]


@dataclass(frozen=True)
class Config:
    root: Path
    provider: str
    arena_api_key: str
    arena_base_url: str
    arena_model: str
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    ollama_base_url: str
    ollama_model: str
    arena_agent_url: str
    permission_mode: str
    dry_run: bool
    host: str
    port: int
    speech_lang: str
    whisper_python: str
    whisper_model: str
    whisper_language: str
    whisper_beam_size: int
    browser_argv: list[str]
    max_actions: int
    command_timeout: int
    brain_timeout: int
    max_output_chars: int

    @classmethod
    def load(cls) -> "Config":
        load_dotenv()
        provider = os.environ.get("AI_PROVIDER", "arena").strip().lower()
        if provider not in {"arena", "openai", "ollama", "demo"}:
            provider = "demo"
        permission_mode = os.environ.get("PERMISSION_MODE", "guarded").strip().lower()
        if permission_mode != "guarded":
            # This build implements the guarded dispatcher chosen for Bazzite.
            permission_mode = "guarded"
        return cls(
            root=ROOT,
            provider=provider,
            arena_api_key=os.environ.get("ARENA_API_KEY", "").strip(),
            arena_base_url=os.environ.get("ARENA_BASE_URL", "https://api.arena.ai/v1").rstrip("/"),
            arena_model=os.environ.get("ARENA_MODEL", "coding-router-preview").strip(),
            openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip(),
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2").strip(),
            arena_agent_url=os.environ.get("ARENA_AGENT_URL", "https://arena.ai/agent").strip(),
            permission_mode=permission_mode,
            dry_run=env_bool("ASSISTANT_DRY_RUN", False),
            host=os.environ.get("HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=int(os.environ.get("PORT", "8787")),
            speech_lang=os.environ.get("SPEECH_LANG", "en-US").strip() or "en-US",
            whisper_python=os.environ.get("WHISPER_PYTHON", sys.executable).strip() or sys.executable,
            whisper_model=os.environ.get("WHISPER_MODEL", "small.en").strip() or "small.en",
            whisper_language=os.environ.get("WHISPER_LANGUAGE", "en").strip() or "en",
            whisper_beam_size=int(os.environ.get("WHISPER_BEAM_SIZE", "5")),
            browser_argv=_browser_argv(),
            max_actions=3,
            command_timeout=8,
            brain_timeout=45,
            max_output_chars=6000,
        )

    @property
    def brain_configured(self) -> bool:
        if self.provider == "arena":
            return bool(self.arena_api_key)
        if self.provider == "openai":
            return bool(self.openai_api_key)
        if self.provider == "ollama":
            return True
        return True  # demo is intentionally self-contained

    @property
    def model_name(self) -> str:
        return {
            "arena": self.arena_model,
            "openai": self.openai_model,
            "ollama": self.ollama_model,
            "demo": "local-rules",
        }[self.provider]

    def public_status(self) -> dict:
        """Safe configuration fields for the browser; never include secrets."""
        return {
            "provider": self.provider,
            "model": self.model_name,
            "brainConfigured": self.brain_configured,
            "permissionMode": self.permission_mode,
            "dryRun": self.dry_run,
            "speechLang": self.speech_lang,
            "arenaAgentUrl": self.arena_agent_url,
            "whisperModel": self.whisper_model,
            "whisperConfigured": bool(self.whisper_python),
            "service": "R • ROG Ally X Assistant",
        }
