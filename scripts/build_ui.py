#!/usr/bin/env python3
"""Inline CSS, JS and the avatar into one standalone static/index.html.

The generated page works in the Arena file viewer (which has no network) and
from the local Python server. Edit files under ui/, then rerun this script.
"""
from __future__ import annotations

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "ui" / "index.template.html"
CSS = ROOT / "ui" / "styles.css"
JS = ROOT / "ui" / "app.js"
AVATAR = ROOT / "assets" / "avatar.png"
OUTPUT = ROOT / "static" / "index.html"


def build() -> Path:
    template = TEMPLATE.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8").replace("</style", "<\\/style")
    js = JS.read_text(encoding="utf-8").replace("</script", "<\\/script")
    data_uri = "data:image/png;base64," + base64.b64encode(AVATAR.read_bytes()).decode("ascii")
    html = template
    html = html.replace("__AVATAR_DATA_URI__", data_uri)
    html = html.replace("/*__INLINE_CSS__*/", css)
    html = html.replace("/*__INLINE_JS__*/", js)
    if "__AVATAR_DATA_URI__" in html or "__INLINE_" in html:
        raise RuntimeError("One or more UI placeholders were not replaced")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"Built {path} ({path.stat().st_size:,} bytes)")
