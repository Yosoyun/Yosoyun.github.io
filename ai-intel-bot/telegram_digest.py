#!/usr/bin/env python3
"""Build and send a concise AI intelligence digest to Telegram."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config" / "sources.json"
CHANNEL_CONFIG_DIR = BASE_DIR / "config" / "channels"
DEFAULT_ENV = BASE_DIR / ".env"
DEFAULT_STATE = BASE_DIR / "state" / "seen.json"
IST = ZoneInfo("Asia/Kolkata")
USER_AGENT = "VanindraAIDigestBot/1.0 (+https://telegram.org/)"
TELEGRAM_LIMIT = 4096


@dataclass(frozen=True)
class Entry:
    title: str
    link: str
    source: str
    category: str
    summary: str
    published: datetime | None
    score: float
    matched: tuple[str, ...]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    decoded = html.unescape(without_tags)
    return re.sub(r"\s+", " ", decoded).strip()


def norm_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node: ET.Element, names: tuple[str, ...]) -> str:
    wanted = {name.lower() for name in names}
    for child in list(node):
        if norm_tag(child.tag) in wanted:
            return "".join(child.itertext()).strip()
    return ""


def atom_link(node: ET.Element) -> str:
    for child in list(node):
        if norm_tag(child.tag) == "link":
            href = child.attrib.get("href", "").strip()
            if href:
                return href
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""


def parse_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fetch_url(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as exc:
        curl = shutil.which("curl")
        if not curl:
            raise
        result = subprocess.run(
            [
                curl,
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--max-time",
                str(timeout),
                "--user-agent",
                USER_AGENT,
                url,
            ],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"{exc}; curl fallback failed: {detail}") from exc
        return result.stdout


def canonical_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query_pairs = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    cleaned = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query=urllib.parse.urlencode(query_pairs),
        fragment="",
    )
    return urllib.parse.urlunsplit(cleaned).rstrip("/")


def fingerprint(title: str, link: str) -> str:
    if link:
        return canonical_url(link)
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def keyword_hits(text: str, keywords: dict[str, list[str]]) -> dict[str, list[str]]:
    haystack = text.lower()
    hits: dict[str, list[str]] = {}
    for group, terms in keywords.items():
        matches = []
        for term in terms:
            if term.lower() in haystack:
                matches.append(term)
        hits[group] = matches
    return hits


def digest_meta(config: dict[str, object]) -> dict[str, object]:
    raw = config.get("digest", {})
    if not isinstance(raw, dict):
        raw = {}
    return raw


def keyword_weights(config: dict[str, object]) -> dict[str, float]:
    raw = config.get("keyword_weights", {})
    weights = {
        "must_know": 2.2,
        "research": 1.6,
        "business": 1.9,
        "markets": 1.9,
        "macro": 1.7,
        "risk": 1.7,
        "technical": 1.5,
        "strategy": 1.6,
        "negative": -3.5,
    }
    if isinstance(raw, dict):
        for key, value in raw.items():
            try:
                weights[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
    return weights


def score_entry(
    title: str,
    summary: str,
    source_weight: float,
    source_category: str,
    published: datetime | None,
    keywords: dict[str, list[str]],
    weights: dict[str, float],
) -> tuple[float, tuple[str, ...]]:
    text = f"{title} {summary}"
    hits = keyword_hits(text, keywords)
    score = source_weight
    for group, matches in hits.items():
        if not matches:
            continue
        score += weights.get(group, 1.3) * len(matches)

    if source_category in {"frontier", "research", "math", "quantum"}:
        score += 1.5
    elif source_category in {
        "business",
        "infrastructure",
        "markets",
        "equities",
        "macro",
        "geopolitics",
        "policy",
        "mega-cap",
    }:
        score += 1.0

    if published:
        age_hours = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
        if age_hours <= 12:
            score += 3.0
        elif age_hours <= 36:
            score += 2.0
        elif age_hours <= 96:
            score += 0.7
        elif age_hours > 336:
            score -= 1.5

    matched_terms = []
    for group, matches in hits.items():
        if weights.get(group, 1.3) <= 0:
            continue
        matched_terms.extend(matches[:4])
    return score, tuple(matched_terms)


def parse_feed(
    feed: dict[str, object],
    keywords: dict[str, list[str]],
    weights: dict[str, float],
    timeout: int,
) -> list[Entry]:
    content = fetch_url(str(feed["url"]), timeout)
    root = ET.fromstring(content)
    category = str(feed.get("category", "general"))
    source = str(feed.get("name", feed.get("url", "Unknown Source")))
    weight = float(feed.get("weight", 1))

    items = [node for node in root.iter() if norm_tag(node.tag) == "item"]
    if not items:
        items = [node for node in root.iter() if norm_tag(node.tag) == "entry"]

    entries: list[Entry] = []
    for item in items:
        title = strip_html(child_text(item, ("title",)))
        link = child_text(item, ("link",)) or atom_link(item) or child_text(item, ("guid", "id"))
        summary = strip_html(child_text(item, ("description", "summary", "content", "encoded")))
        published = parse_datetime(
            child_text(item, ("pubDate", "published", "updated", "dc:date", "date"))
        )
        if not title:
            continue
        score, matched = score_entry(title, summary, weight, category, published, keywords, weights)
        entries.append(
            Entry(
                title=title,
                link=link,
                source=source,
                category=category,
                summary=summary,
                published=published,
                score=score,
                matched=matched,
            )
        )
    return entries


def reason_for(entry: Entry) -> str:
    text = f"{entry.title} {entry.summary}".lower()
    if entry.category in {"markets", "equities", "rates", "commodities", "earnings"}:
        return "market signal for capital flows, risk appetite, rates, or earnings."
    if entry.category in {"world", "geopolitics", "policy", "macro"}:
        return "global risk signal for policy, conflict, trade, or macro direction."
    if entry.category in {"math", "qfinance", "research", "technical"}:
        return "research signal for models, mathematics, quantitative methods, or technical capability."
    if entry.category in {"quantum", "deeptech", "science"}:
        return "deep-tech signal for quantum capability, hardware, physics, or frontier science."
    if entry.category in {"mega-cap", "infrastructure", "trillion", "business"} or any(
        term in text for term in ("billion", "trillion", "funding", "gpu", "cloud", "regulation", "valuation")
    ):
        return "strategic capital signal for trillion-dollar markets, infrastructure, or market structure."
    if any(
        term in text for term in ("benchmark", "reasoning", "inference", "training", "agent", "llm")
    ):
        return "technical signal for models, agents, or AI capability."
    if entry.category == "frontier":
        return "frontier-lab signal worth tracking before it becomes mainstream."
    return "high-signal item based on source quality, recency, and keyword match."


def confidence_for(entry: Entry, config: dict[str, object]) -> str:
    high_sources = digest_meta(config).get("high_confidence_sources", [])
    if isinstance(high_sources, list) and entry.source in {str(source) for source in high_sources}:
        return "high"
    if entry.score >= 13:
        return "high"
    if entry.score >= 10:
        return "medium-high"
    return "medium"


def unique_entries(entries: list[Entry]) -> list[Entry]:
    seen: set[str] = set()
    unique: list[Entry] = []
    for entry in sorted(entries, key=lambda item: item.score, reverse=True):
        key = fingerprint(entry.title, entry.link)
        title_key = re.sub(r"[^a-z0-9]+", " ", entry.title.lower()).strip()
        if key in seen or title_key in seen:
            continue
        seen.add(key)
        seen.add(title_key)
        unique.append(entry)
    return unique


def source_capped_entries(entries: list[Entry], limit: int, per_source: int) -> list[Entry]:
    counts: dict[str, int] = {}
    chosen: list[Entry] = []
    overflow: list[Entry] = []
    for entry in entries:
        count = counts.get(entry.source, 0)
        if count < per_source:
            chosen.append(entry)
            counts[entry.source] = count + 1
        else:
            overflow.append(entry)
        if len(chosen) >= limit:
            return chosen
    return (chosen + overflow)[:limit]


def section_entries(
    entries: list[Entry],
    categories: set[str],
    limit: int,
    exclude: set[str],
) -> list[Entry]:
    chosen: list[Entry] = []
    for entry in entries:
        key = fingerprint(entry.title, entry.link)
        if key in exclude:
            continue
        if entry.category in categories:
            chosen.append(entry)
            exclude.add(key)
        if len(chosen) >= limit:
            break
    return chosen


def link_for(entry: Entry) -> str:
    title = html.escape(textwrap.shorten(entry.title, width=115, placeholder="..."))
    if entry.link:
        return f'<a href="{html.escape(entry.link, quote=True)}">{title}</a>'
    return title


def bullet(entry: Entry) -> str:
    return f"• {link_for(entry)} <i>({html.escape(entry.source)})</i>"


def numbered(entry: Entry, index: int, config: dict[str, object]) -> str:
    matched = f" Signals: {html.escape(', '.join(entry.matched[:3]))}." if entry.matched else ""
    return (
        f"{index}. {link_for(entry)}\n"
        f"   Why: {html.escape(reason_for(entry))} Confidence: {confidence_for(entry, config)}.{matched}"
    )


def build_digest(entries: list[Entry], skipped_count: int, max_items: int, config: dict[str, object]) -> str:
    now = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    meta = digest_meta(config)
    title = str(meta.get("title", "AI Intelligence Digest"))
    empty = str(
        meta.get(
            "empty",
            "No fresh high-signal items were found in the configured feeds. That is useful too: the right move is not to force-feed noise.",
        )
    )
    ranked = unique_entries(entries)[:50]
    if not ranked:
        return (
            f"<b>{html.escape(title)}</b>\n"
            f"<code>{html.escape(now)}</code>\n\n"
            f"{html.escape(empty)}"
        )

    used: set[str] = set()
    per_source = int(meta.get("per_source", 2))
    must = source_capped_entries(ranked, min(6, max_items), per_source=per_source)
    used.update(fingerprint(entry.title, entry.link) for entry in must)

    lines = [
        f"<b>{html.escape(title)}</b>",
        f"<code>{html.escape(now)}</code>",
        "",
        "<b>Executive Brief</b>",
    ]
    for entry in must[:5]:
        lines.append(bullet(entry))

    lines.extend(["", "<b>Must-Know</b>"])
    for index, entry in enumerate(must, start=1):
        lines.append(numbered(entry, index, config))

    raw_sections = meta.get("sections", [])
    if not isinstance(raw_sections, list) or not raw_sections:
        raw_sections = [
            {"label": "Research / Technical", "categories": ["research", "technical", "frontier"]},
            {"label": "Business / Macro", "categories": ["business", "infrastructure"]},
        ]
    for raw_section in raw_sections:
        if not isinstance(raw_section, dict):
            continue
        label = str(raw_section.get("label", "Signals"))
        categories = raw_section.get("categories", [])
        if not isinstance(categories, list):
            continue
        selected = section_entries(ranked, {str(category) for category in categories}, 3, used)
        if selected:
            lines.extend(["", f"<b>{html.escape(label)}</b>"])
            for entry in selected:
                lines.append(bullet(entry))

    watchlist = [entry for entry in ranked if fingerprint(entry.title, entry.link) not in used][:3]
    if watchlist:
        lines.extend(["", "<b>Watchlist</b>"])
        for entry in watchlist:
            lines.append(bullet(entry))

    noise = str(
        meta.get(
            "noise",
            "RSS/API-friendly sources only. Skipped duplicates, low-signal items, and older feed entries.",
        )
    )
    lines.extend(
        [
            "",
            "<b>Noise Filter</b>",
            f"Skipped {skipped_count} duplicate, low-signal, or older feed items. {html.escape(noise)}",
        ]
    )
    return "\n".join(lines)


def chunk_message(message: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in message.splitlines():
        next_size = size + len(line) + 1
        if current and next_size > TELEGRAM_LIMIT - 250:
            chunks.append("\n".join(current))
            current = []
            size = 0
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def send_telegram(message: str, token: str, chat_id: str, timeout: int) -> None:
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in chunk_message(message):
        body = json.dumps(
            {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
        ).encode("utf-8")
        payload = post_json(endpoint, body, timeout)
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API rejected message: {payload}")


def post_json(endpoint: str, body: bytes, timeout: int) -> dict[str, object]:
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        curl = shutil.which("curl")
        if not curl:
            raise
        result = subprocess.run(
            [
                curl,
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--max-time",
                str(timeout),
                "--user-agent",
                USER_AGENT,
                "--header",
                "Content-Type: application/json",
                "--request",
                "POST",
                "--data-binary",
                "@-",
                endpoint,
            ],
            input=body,
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"{exc}; curl fallback failed: {detail}") from exc
        return json.loads(result.stdout.decode("utf-8"))


def collect_entries(config: dict[str, object], timeout: int) -> tuple[list[Entry], list[str]]:
    keywords = config.get("keywords", {})
    if not isinstance(keywords, dict):
        keywords = {}
    normalized_keywords = {
        str(key): [str(term) for term in value]
        for key, value in keywords.items()
        if isinstance(value, list)
    }
    weights = keyword_weights(config)
    entries: list[Entry] = []
    failures: list[str] = []
    for feed in config.get("feeds", []):
        if not isinstance(feed, dict):
            continue
        try:
            entries.extend(parse_feed(feed, normalized_keywords, weights, timeout))
        except Exception as exc:
            failures.append(f"{feed.get('name', feed.get('url', 'unknown'))}: {exc}")
    return entries, failures


def is_fresh(entry: Entry, hours: float) -> bool:
    if hours <= 0 or entry.published is None:
        return True
    age_hours = (datetime.now(timezone.utc) - entry.published).total_seconds() / 3600
    return age_hours <= hours


def channel_config_path(channel: str) -> Path:
    safe_channel = re.sub(r"[^a-zA-Z0-9_-]+", "", channel.strip())
    if not safe_channel:
        return DEFAULT_CONFIG
    return CHANNEL_CONFIG_DIR / f"{safe_channel}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a curated intelligence digest to Telegram.")
    parser.add_argument("--channel", help="Named channel config from ai-intel-bot/config/channels.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--max-items", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--fresh-hours",
        type=float,
        default=0,
        help="Only include dated feed items published within this many hours.",
    )
    parser.add_argument("--include-seen", action="store_true")
    parser.add_argument("--test", action="store_true", help="Send a short Telegram connectivity test.")
    args = parser.parse_args()

    channel = (args.channel or "").strip()
    config_path = args.config or channel_config_path(channel)
    state_path = args.state or (
        BASE_DIR / "state" / f"{re.sub(r'[^a-zA-Z0-9_-]+', '', channel)}-seen.json"
        if channel
        else DEFAULT_STATE
    )

    load_env_file(args.env_file)
    dry_run = args.dry_run or os.environ.get("AI_DIGEST_DRY_RUN") == "1"
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if args.test:
        message = "<b>Telegram Intelligence Network</b>\nTelegram bot connection works."
        if dry_run:
            print(message)
            return 0
        if not token or not chat_id:
            print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.", file=sys.stderr)
            return 2
        send_telegram(message, token, chat_id, args.timeout)
        print("Telegram test message sent.")
        return 0

    config = load_json(config_path, {"feeds": [], "keywords": {}})
    if not isinstance(config, dict):
        print(f"Invalid config: {config_path}", file=sys.stderr)
        return 2

    all_entries, failures = collect_entries(config, args.timeout)
    seen = load_json(state_path, {})
    if not isinstance(seen, dict):
        seen = {}
    current_seen = set(seen.keys())

    fresh_entries: list[Entry] = []
    skipped = 0
    for entry in all_entries:
        key = fingerprint(entry.title, entry.link)
        if not is_fresh(entry, args.fresh_hours):
            skipped += 1
            continue
        if entry.score < 4:
            skipped += 1
            continue
        if not args.include_seen and key in current_seen:
            skipped += 1
            continue
        fresh_entries.append(entry)

    digest = build_digest(fresh_entries, skipped, args.max_items, config)
    if failures:
        failure_note = "\n".join(f"• {html.escape(item)}" for item in failures[:5])
        digest += f"\n\n<b>Source Notes</b>\n{failure_note}"

    if dry_run:
        print(digest)
    else:
        if not token or not chat_id:
            print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.", file=sys.stderr)
            return 2
        send_telegram(digest, token, chat_id, args.timeout)

    if not dry_run:
        now = datetime.now(timezone.utc).isoformat()
        for entry in fresh_entries:
            seen[fingerprint(entry.title, entry.link)] = {
                "title": entry.title,
                "source": entry.source,
                "sent_at": now,
            }
        save_json(state_path, seen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
