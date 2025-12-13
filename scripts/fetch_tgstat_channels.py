#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
import yaml

TAG_URL_TEMPLATE = "https://tgstat.com/ru/tag/{tag}"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.9",
}


def fetch_tag_page(tag: str) -> str:
    url = TAG_URL_TEMPLATE.format(tag=tag)
    req = Request(url, headers=DEFAULT_HEADERS)
    try:
        with urlopen(req, timeout=30) as resp:
            encoding = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(encoding, errors="ignore")
    except HTTPError as exc:
        raise RuntimeError(f"TGStat responded with HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to load {url}: {exc}") from exc


def extract_telegram_url(source_url: str) -> str | None:
    source_url = (source_url or "").strip()
    if not source_url:
        return None

    if "t.me/" in source_url:
        suffix = source_url.split("t.me/", 1)[1].lstrip("/")
        return f"https://t.me/{suffix}"

    match = re.search(r"/@([^/?#]+)", source_url)
    if match:
        username = match.group(1).lstrip("+")
        if username:
            return f"https://t.me/{username}"

    return None


def normalize_image_url(url: str | None) -> str:
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    return url


def parse_channels(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.peer-item-box")

    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for card in cards:
        anchor = card.select_one("a.text-body")
        if not anchor:
            continue
        title_node = anchor.select_one("div.font-16.text-dark")
        if not title_node:
            continue
        title = title_node.get_text(strip=True)

        href = anchor.get("href", "")
        tg_url = extract_telegram_url(href)
        if not tg_url or tg_url.lower() in seen:
            continue

        desc_node = anchor.select_one("div.font-14")
        description = desc_node.get_text(" ", strip=True) if desc_node else ""

        img_node = card.select_one("img")
        image_url = normalize_image_url(img_node.get("src") if img_node else "")

        seen.add(tg_url.lower())
        results.append(
            {
                "title": title,
                "url": tg_url,
                "description": description,
                "image": image_url,
            }
        )

    return results


def dump_yaml(channels: Iterable[dict[str, str]], output_path: Path) -> None:
    data = {"channels": list(channels)}
    text = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )
    output_path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch all channels from tgstat.ru for a specific tag into YAML."
    )
    parser.add_argument("--tag", default="pro1C", help="TGStat tag slug (default: pro1C)")
    parser.add_argument(
        "--output",
        default="channels.yaml",
        help="Path to the YAML file to overwrite (default: channels.yaml)",
    )
    args = parser.parse_args()

    try:
        html = fetch_tag_page(args.tag)
        channels = parse_channels(html)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc

    if not channels:
        print("No channels were parsed from TGStat.", file=sys.stderr)
        raise SystemExit(2)

    output_path = Path(args.output)
    dump_yaml(channels, output_path)
    print(f"Saved {len(channels)} channels to {output_path}")


if __name__ == "__main__":
    main()
