#!/usr/bin/env python3
"""Optional offline speech-to-text adapter using faster-whisper.

The browser records a 16-bit PCM WAV and POSTs it to /api/transcribe. This
script is called with a fixed argv list; it never evaluates user text.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import wave
from pathlib import Path

INSTALL_HINT = (
    "faster-whisper is not installed for this Python interpreter. Create a venv, "
    "run `pip install faster-whisper`, then set WHISPER_PYTHON to its python binary in .env."
)


def fail(message: str, hint: str = "") -> int:
    print(json.dumps({"error": message, "hint": hint}, ensure_ascii=False))
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", help="Path to a 16-bit PCM WAV file")
    parser.add_argument("--model", default=os.environ.get("WHISPER_MODEL", "small.en"))
    parser.add_argument("--language", default=os.environ.get("WHISPER_LANGUAGE", "en"))
    parser.add_argument("--beam-size", type=int, default=int(os.environ.get("WHISPER_BEAM_SIZE", "5")))
    parser.add_argument("--device", default=os.environ.get("WHISPER_DEVICE", "cpu"))
    parser.add_argument("--compute-type", default=os.environ.get("WHISPER_COMPUTE_TYPE", "int8"))
    args = parser.parse_args()

    path = Path(args.audio)
    if not path.is_file():
        return fail(f"Audio file not found: {path}")
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getsampwidth() != 2:
                return fail("Expected 16-bit PCM WAV audio", "The browser encoder should produce 16-bit PCM.")
    except (wave.Error, OSError) as exc:
        return fail(f"Invalid WAV audio: {exc}")

    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        return fail(INSTALL_HINT, INSTALL_HINT)

    try:
        model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
        language = None if args.language in {"auto", ""} else args.language
        segments, info = model.transcribe(
            str(path),
            language=language,
            beam_size=args.beam_size,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
    except Exception as exc:  # model download / runtime errors should be readable in the UI
        return fail(f"Whisper could not transcribe audio: {exc}", "Check the model name, disk space and WHISPER_* settings.")

    print(json.dumps({"text": text, "language": getattr(info, "language", args.language), "model": args.model}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
