"""AI brain adapters.

Default: official Arena API, using its OpenAI-compatible /chat/completions
endpoint. Also supports generic OpenAI-compatible endpoints, local Ollama, and
an offline demo brain. Secrets stay server-side.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from actions import describe_action, detect_intent
from settings import Config

SYSTEM_PROMPT = """You are R, a friendly AI assistant living on a ROG Ally X handheld running Bazzite OS.
Your avatar is a small white-and-blue robot. Be concise, warm and a little playful.
The user may be using voice input, so write replies that sound natural when read aloud.

You can request guarded system actions. Return STRICT JSON ONLY, with this shape:
{"reply":"short spoken answer","actions":[{"type":"open_url","value":"https://www.youtube.com/","label":"YouTube"}]}

Allowed action types:
- open_url: a public https URL. Use https://www.youtube.com/ for YouTube, and the configured Arena Agent URL for Arena Agent.
- open_app: one of steam, firefox, chromium, edge, discord, spotify, terminal, files, settings, heroic, bazzite_portal, calculator, text_editor.
- open_folder: one of home, downloads, documents, desktop, pictures, music, videos, project.
- terminal: one of status, battery, temperature, network, updates, processes, memory, disk, time, whoami, hostname, os, flatpaks. These are read-only reports.
- set_volume: integer 0-100, or up, down, mute, unmute, toggle.
- set_brightness: integer 0-100.
- power: lock or suspend.
- screenshot: value "screen".
- notify: a short message.

Never return raw shell commands, sudo, file paths, JavaScript, or URLs pointing to localhost/private IPs.
The server independently validates and executes actions; unrecognized actions are blocked.
If the user only wants conversation, return an empty actions array.
Do not wrap the JSON in markdown. Do not include any text outside the JSON object.
"""


@dataclass
class BrainResult:
    reply: str
    actions: list[dict] = field(default_factory=list)
    provider: str = "demo"
    model: str = "local-rules"
    configured: bool = True
    warning: str = ""
    fallback: bool = False


class BrainError(RuntimeError):
    pass


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _messages(text: str, history: list[dict]) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    clean_history: list[dict] = []
    for item in (history or [])[-12:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            clean_history.append({"role": role, "content": _clip(content, 1500)})
    if clean_history and clean_history[-1]["role"] == "user" and clean_history[-1]["content"] == text:
        clean_history.pop()
    messages.extend(clean_history)
    messages.append({"role": "user", "content": _clip(text, 3000)})
    return messages


def _http_json(url: str, payload: dict, headers: dict[str, str], timeout: int) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "rog-ally-x-r-assistant/1.0", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        detail = re.sub(r"(sk|Bearer)[A-Za-z0-9_\-]{12,}", r"\1[REDACTED]", detail, flags=re.I)
        raise BrainError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BrainError(f"network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise BrainError("request timed out") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise BrainError("upstream returned non-JSON") from exc


def _chat_completion_content(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise BrainError("unexpected chat-completions response shape") from exc


def call_arena(text: str, history: list[dict], cfg: Config) -> str:
    payload = {
        "model": cfg.arena_model,
        "messages": _messages(text, history),
        "temperature": 0.35,
        "stream": False,
    }
    data = _http_json(
        f"{cfg.arena_base_url}/chat/completions",
        payload,
        {"Authorization": f"Bearer {cfg.arena_api_key}"},
        cfg.brain_timeout,
    )
    return _chat_completion_content(data)


def call_openai(text: str, history: list[dict], cfg: Config) -> str:
    payload = {
        "model": cfg.openai_model,
        "messages": _messages(text, history),
        "temperature": 0.35,
        "stream": False,
    }
    data = _http_json(
        f"{cfg.openai_base_url}/chat/completions",
        payload,
        {"Authorization": f"Bearer {cfg.openai_api_key}"},
        cfg.brain_timeout,
    )
    return _chat_completion_content(data)


def call_ollama(text: str, history: list[dict], cfg: Config) -> str:
    payload = {"model": cfg.ollama_model, "messages": _messages(text, history), "stream": False}
    data = _http_json(f"{cfg.ollama_base_url}/api/chat", payload, {}, cfg.brain_timeout)
    try:
        return data["message"]["content"] or ""
    except (KeyError, TypeError) as exc:
        raise BrainError("unexpected Ollama response shape") from exc


def demo_reply(text: str, cfg: Config) -> tuple[str, list[dict]]:
    actions = detect_intent(text, cfg)
    if actions:
        return _clip(describe_action(actions[0]), 600), actions
    low = text.lower().strip()
    if re.search(r"\b(hello|hi|hey|good morning|good evening)\b", low):
        return "Hello! R is online. Say “open YouTube”, ask for system status, or tap the microphone.", []
    if re.search(r"\b(what can you do|help|capabilities|commands)\b", low):
        return "I can chat, listen to your voice, open sites and apps, check battery or system status, set volume, and show every guarded command in the terminal panel.", []
    if re.search(r"\b(thank|thanks)\b", low):
        return "You're welcome. I'm right here whenever you need me.", []
    if re.search(r"\b(joke|funny)\b", low):
        return "Why did the ROG Ally X bring a charger to the party? Because it wanted to be the life of the battery.", []
    if re.search(r"\b(who are you|your name)\b", low):
        return "I'm R, your local ROG Ally X assistant. My brain is connected through Arena, and my system actions are guarded.", []
    return (
        "I heard you. This is the offline demo brain, so add an Arena API key in .env for full AI replies. I can still open YouTube, check system status, and run guarded terminal reports.",
        [],
    )


def parse_brain_output(content: str) -> tuple[str, list[dict]]:
    """Accept strict JSON, fenced JSON, JSON with trailing text, or plain text."""
    cleaned = (content or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    decoder = json.JSONDecoder()
    parsed = None
    for candidate in (cleaned, cleaned[cleaned.find("{") :] if "{" in cleaned else ""):
        if not candidate:
            continue
        try:
            parsed, _ = decoder.raw_decode(candidate)
            break
        except (json.JSONDecodeError, ValueError):
            continue
    if isinstance(parsed, dict):
        reply = parsed.get("reply") or parsed.get("text") or parsed.get("message") or ""
        actions = parsed.get("actions") if isinstance(parsed.get("actions"), list) else []
        if isinstance(reply, str) and reply.strip():
            return _clip(reply, 1500), [item for item in actions if isinstance(item, dict)]
    plain = re.sub(r"^```(?:json)?\s*|\s*```$", "", (content or "").strip(), flags=re.I)
    return _clip(plain or "I'm here, but the AI brain returned an empty reply.", 1500), []


def friendly_error(exc: Exception, cfg: Config) -> str:
    detail = str(exc)
    if cfg.provider == "arena" and ("403" in detail or "organization_client_restricted" in detail):
        return (
            "Arena rejected this key (403). Free-router keys can be restricted to Claude Code; "
            "create a key in a workspace with API access or choose a model enabled for your key. "
            "Using the offline demo brain for now."
        )
    if cfg.provider == "arena":
        return f"Arena brain unavailable ({_clip(detail, 180)}). Check ARENA_API_KEY, ARENA_MODEL and your connection. Using the offline demo brain."
    if cfg.provider == "ollama":
        return f"Local Ollama is unavailable ({_clip(detail, 180)}). Start Ollama and pull {cfg.ollama_model}. Using the offline demo brain."
    return f"AI brain unavailable ({_clip(detail, 180)}). Using the offline demo brain."


def think(text: str, history: list[dict] | None, cfg: Config) -> BrainResult:
    text = (text or "").strip()
    if not text:
        return BrainResult("I didn't catch that. Try again?", provider=cfg.provider, model=cfg.model_name)
    history = history or []

    if cfg.provider == "demo":
        reply, actions = demo_reply(text, cfg)
        return BrainResult(reply, actions, "demo", cfg.model_name, True, "Demo brain active. Set AI_PROVIDER=arena and add ARENA_API_KEY in .env for full AI replies.", True)

    if cfg.provider == "arena" and not cfg.arena_api_key:
        reply, actions = demo_reply(text, cfg)
        return BrainResult(reply, actions, "demo", cfg.model_name, False, "No Arena API key found. Add ARENA_API_KEY to .env, then restart the service. Demo brain is active.", True)
    if cfg.provider == "openai" and not cfg.openai_api_key:
        reply, actions = demo_reply(text, cfg)
        return BrainResult(reply, actions, "demo", cfg.model_name, False, "No OPENAI_API_KEY found. Demo brain is active.", True)

    try:
        if cfg.provider == "arena":
            content = call_arena(text, history, cfg)
        elif cfg.provider == "openai":
            content = call_openai(text, history, cfg)
        elif cfg.provider == "ollama":
            content = call_ollama(text, history, cfg)
        else:
            content = ""
        reply, brain_actions = parse_brain_output(content)
        # Local intent is merged by the server; keep the brain result clean here.
        return BrainResult(reply, brain_actions, cfg.provider, cfg.model_name, True, "", False)
    except BrainError as exc:
        reply, actions = demo_reply(text, cfg)
        return BrainResult(reply, actions, "demo", cfg.model_name, False, friendly_error(exc, cfg), True)
