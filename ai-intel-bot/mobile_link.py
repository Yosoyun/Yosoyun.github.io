#!/usr/bin/env python3
"""Create a mobile-friendly Telegram bot link page with a QR code."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import urllib.parse
from pathlib import Path

from telegram_digest import BASE_DIR, DEFAULT_ENV, fetch_url, load_env_file


DEFAULT_OUTPUT = BASE_DIR / "open-on-mobile.html"


def clean_username(username: str) -> str:
    username = username.strip().removeprefix("@")
    if username and not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        raise ValueError("Telegram bot username should be 5-32 letters, numbers, or underscores.")
    return username


def username_from_token(token: str, timeout: int) -> str:
    if not token:
        return ""
    payload = fetch_url(f"https://api.telegram.org/bot{token}/getMe", timeout)
    data = json.loads(payload.decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Telegram getMe failed: {data}")
    return clean_username(str(data.get("result", {}).get("username", "")))


def write_page(bot_username: str, output: Path) -> str:
    bot_link = f"https://t.me/{bot_username}"
    qr_src = "https://api.qrserver.com/v1/create-qr-code/?" + urllib.parse.urlencode(
        {"size": "360x360", "margin": "18", "data": bot_link}
    )
    output.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Open AI Digest Bot</title>
  <style>
    :root {{ color-scheme: light dark; font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f6f7f9; color: #111827; }}
    main {{ width: min(92vw, 480px); text-align: center; padding: 32px 20px; }}
    h1 {{ font-size: 28px; margin: 0 0 10px; letter-spacing: 0; }}
    p {{ margin: 0 0 20px; color: #4b5563; line-height: 1.5; }}
    img {{ width: min(78vw, 360px); height: auto; background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; }}
    a.button {{ display: inline-flex; align-items: center; justify-content: center; min-height: 48px; padding: 0 20px; margin: 22px 0 12px; border-radius: 8px; background: #229ed9; color: white; text-decoration: none; font-weight: 700; }}
    code {{ display: block; overflow-wrap: anywhere; color: #374151; }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #0f172a; color: #f8fafc; }}
      p, code {{ color: #cbd5e1; }}
      img {{ border-color: #334155; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>AI Digest Bot</h1>
    <p>Scan this QR code from your phone, or open the link below. In Telegram, tap <strong>Start</strong>.</p>
    <img src="{html.escape(qr_src, quote=True)}" alt="QR code for {html.escape(bot_link, quote=True)}">
    <div><a class="button" href="{html.escape(bot_link, quote=True)}">Open in Telegram</a></div>
    <code>{html.escape(bot_link)}</code>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    return bot_link


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an open-on-mobile page for your Telegram bot.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--username", help="Bot username from BotFather, without @.")
    args = parser.parse_args()

    load_env_file(args.env_file)
    username = clean_username(args.username or os.environ.get("TELEGRAM_BOT_USERNAME", ""))
    if not username:
        username = username_from_token(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), args.timeout)
    if not username:
        raise SystemExit(
            "Missing bot username. Add TELEGRAM_BOT_USERNAME to ai-intel-bot/.env, "
            "or add TELEGRAM_BOT_TOKEN so the script can discover it."
        )

    bot_link = write_page(username, args.output)
    print(f"Telegram bot link: {bot_link}")
    print(f"Mobile page: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
