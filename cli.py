#!/usr/bin/env python3
"""Terminal-only client for R.

Useful over SSH or when you want the assistant's reply and guarded command
output directly in a terminal instead of the web UI.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace

import actions
import brain
from settings import Config

CYAN = "\033[96m"
GREEN = "\033[92m"
AMBER = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_terminal(entries: list[dict], color: bool) -> None:
    for entry in entries:
        prefix = GREEN if entry.get("ok", True) else RED
        if color:
            print(f"{prefix}❯ {entry.get('command', '')}{RESET}")
        else:
            print(f"❯ {entry.get('command', '')}")
        if entry.get("note"):
            print(f"  {DIM if color else ''}{entry['note']}{RESET if color else ''}")
        if entry.get("stdout"):
            print(entry["stdout"])
        if entry.get("stderr"):
            print(entry["stderr"], file=sys.stderr)


def answer(text: str, history: list[dict], cfg: Config, dry_run: bool, color: bool) -> tuple[str, list[dict]]:
    result = brain.think(text, history, cfg)
    final_actions = actions.merge_actions(result.actions, actions.detect_intent(text, cfg), cfg)
    terminal = [
        {
            "command": f'$ r.brain --ask "{text[:60]}"',
            "ok": True,
            "stdout": result.reply,
            "note": f"provider={result.provider} • model={result.model}",
        }
    ]
    terminal.extend(actions.execute_actions(final_actions, cfg, dry_run=dry_run))
    if result.warning:
        print(f"{AMBER if color else ''}⚠ {result.warning}{RESET if color else ''}")
    print(f"{CYAN if color else ''}R@arena:~${RESET if color else ''} {result.reply}")
    print_terminal(terminal, color)
    return result.reply, terminal


def main() -> int:
    base = Config.load()
    parser = argparse.ArgumentParser(description="R assistant terminal client")
    parser.add_argument("prompt", nargs="*", help="One-shot prompt; omit for an interactive REPL")
    parser.add_argument("--dry-run", action="store_true", help="Simulate system actions")
    parser.add_argument("--demo", action="store_true", help="Force the offline demo brain")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    args = parser.parse_args()
    cfg = replace(base, provider="demo") if args.demo else base
    dry_run = True if args.dry_run else cfg.dry_run
    color = sys.stdout.isatty() and not args.no_color
    history: list[dict] = []

    print(f"{CYAN if color else ''}R • ROG Ally X Assistant / Bazzite / guarded terminal{RESET if color else ''}")
    print(f"Brain: {cfg.provider}/{cfg.model_name} • dry-run: {'on' if dry_run else 'off'} • type 'exit' to quit\n")

    if args.prompt:
        reply, _ = answer(" ".join(args.prompt), history, cfg, dry_run, color)
        return 0 if reply else 1

    while True:
        try:
            text = input(f"{GREEN if color else ''}you@ally-x:~${RESET if color else ''} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() in {"exit", "quit", "bye"}:
            break
        if not text:
            continue
        reply, _ = answer(text, history, cfg, dry_run, color)
        history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": reply}])
        history = history[-12:]
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
