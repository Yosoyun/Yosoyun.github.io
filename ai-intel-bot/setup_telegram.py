#!/usr/bin/env python3
"""Interactive setup for the Telegram AI digest bot."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

from mobile_link import write_page
from telegram_digest import BASE_DIR, DEFAULT_ENV, fetch_url, post_json


def telegram_json(token: str, method: str, timeout: int) -> dict[str, object]:
    payload = fetch_url(f"https://api.telegram.org/bot{token}/{method}", timeout)
    data = json.loads(payload.decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data


def open_file(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)


def open_url(url: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", url], check=False)


def get_bot_info(token: str, timeout: int) -> tuple[str, str]:
    data = telegram_json(token, "getMe", timeout)
    result = data.get("result", {})
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected getMe response: {data}")
    username = str(result.get("username", "")).strip()
    first_name = str(result.get("first_name", "")).strip()
    if not username:
        raise RuntimeError("Telegram did not return a bot username.")
    return username, first_name


def latest_private_chat_id(token: str, timeout: int) -> str:
    data = telegram_json(token, "getUpdates", timeout)
    updates = data.get("result", [])
    if not isinstance(updates, list):
        return ""
    for update in reversed(updates):
        if not isinstance(update, dict):
            continue
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict):
            continue
        chat_id = chat.get("id")
        if chat_id is not None:
            return str(chat_id)
    return ""


def write_env(path: Path, token: str, chat_id: str, username: str) -> None:
    path.write_text(
        "\n".join(
            [
                f"TELEGRAM_BOT_TOKEN={token}",
                f"TELEGRAM_CHAT_ID={chat_id}",
                f"TELEGRAM_BOT_USERNAME={username}",
                "AI_DIGEST_DRY_RUN=0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def send_setup_message(token: str, chat_id: str, timeout: int) -> None:
    body = json.dumps(
        {
            "chat_id": chat_id,
            "text": "AI Intelligence Digest is connected. Next message can be the real digest.",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    payload = post_json(f"https://api.telegram.org/bot{token}/sendMessage", body, timeout)
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram rejected setup message: {payload}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up Telegram credentials for the AI digest bot.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--open-botfather", action="store_true")
    args = parser.parse_args()

    if args.open_botfather:
        open_url("https://t.me/BotFather")

    print("\nTelegram AI Digest setup")
    print("1. In Telegram, create a bot with @BotFather.")
    print("2. Copy the token BotFather gives you.")
    print("3. Paste it here. The token is saved only to ai-intel-bot/.env on this Mac.\n")

    token = getpass.getpass("Paste TELEGRAM_BOT_TOKEN: ").strip()
    if not token:
        print("No token entered.", file=sys.stderr)
        return 2

    try:
        username, first_name = get_bot_info(token, args.timeout)
    except Exception as exc:
        print(f"Token validation failed: {exc}", file=sys.stderr)
        return 2

    mobile_page = BASE_DIR / "open-on-mobile.html"
    bot_link = write_page(username, mobile_page)
    print(f"\nValidated bot: {first_name or username} (@{username})")
    print(f"Opening QR page: {mobile_page}")
    print(f"Telegram link: {bot_link}")
    open_file(mobile_page)

    print("\nOn your phone: scan the QR code, open Telegram, and tap Start.")
    print("Waiting for the first message from your phone...")

    chat_id = ""
    deadline = time.time() + 180
    while time.time() < deadline:
        try:
            chat_id = latest_private_chat_id(token, args.timeout)
        except urllib.error.URLError:
            chat_id = ""
        if chat_id:
            break
        time.sleep(4)

    if not chat_id:
        print("I could not detect a Telegram chat yet. Tap Start in the bot chat and run this setup again.", file=sys.stderr)
        return 2

    write_env(args.env_file, token, chat_id, username)
    send_setup_message(token, chat_id, args.timeout)
    print(f"\nConnected. Chat ID: {chat_id}")
    print(f"Credentials saved to: {args.env_file}")
    print("Setup test message sent to Telegram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
