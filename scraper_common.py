# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).parent
RESOURCE_DIR = BASE_DIR / "resource"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def parse_cli_date(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def add_common_arguments(parser: argparse.ArgumentParser, language: str) -> None:
    parser.add_argument("--limit", type=int, default=None, help="Download latest N records")
    parser.add_argument("--start", type=str, default=None, help="Start date in YYYYMMDD")
    parser.add_argument("--end", type=str, default=None, help="End date in YYYYMMDD")
    parser.add_argument(
        "--today",
        type=str,
        default=date.today().strftime("%Y%m%d"),
        help="Reference date for latest mode in YYYYMMDD",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RESOURCE_DIR / f"daily_devotion_{language}.json",
        help="Output JSON path",
    )


def resolve_selection(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    use_limit = args.limit is not None
    use_range = args.start is not None or args.end is not None

    if use_limit and use_range:
        parser.error("Use either --limit or --start/--end, not both.")
    if not use_limit and not use_range:
        parser.error("Use --limit N or --start YYYYMMDD --end YYYYMMDD.")

    today = parse_cli_date(args.today)

    if use_limit:
        if args.limit <= 0:
            parser.error("--limit must be greater than 0.")
        return {"mode": "latest", "limit": args.limit, "today": today}

    if not args.start or not args.end:
        parser.error("Date-range mode requires both --start and --end.")

    start = parse_cli_date(args.start)
    end = parse_cli_date(args.end)
    if start > end:
        parser.error("--start must be earlier than or equal to --end.")

    return {"mode": "range", "start": start, "end": end, "today": today}


def finalize_records(records_desc: Iterable[dict]) -> list[dict]:
    newest_first = list(records_desc)
    ordered = []
    for idx, record in enumerate(reversed(newest_first), start=1):
        record["id"] = idx
        ordered.append(record)
    ordered.sort(key=lambda item: item["id"], reverse=True)
    return ordered


def save_records(records: list[dict], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)
    print(f"[OK] Saved {len(records)} records -> {output_file}")


def as_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    paragraphs = [
        p.get_text(" ", strip=True)
        for p in soup.find_all("p")
        if p.get_text(" ", strip=True)
    ]
    if paragraphs:
        return "\n\n".join(paragraphs)
    return soup.get_text("\n", strip=True)


def node_to_text(node) -> str:
    if node is None:
        return ""
    paragraphs = [
        p.get_text(" ", strip=True)
        for p in node.find_all("p")
        if p.get_text(" ", strip=True)
    ]
    if paragraphs:
        return "\n\n".join(paragraphs)
    return node.get_text("\n", strip=True)
