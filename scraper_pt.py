# -*- coding: utf-8 -*-
"""
Portuguese devotional scraper for presentediario.transmundial.org.br.

Examples:
  python scraper_pt.py --limit 20
  python scraper_pt.py --start 20250101 --end 20251231
"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime

import requests

from scraper_common import (
    HEADERS,
    add_common_arguments,
    as_text,
    finalize_records,
    html_to_text,
    resolve_selection,
    save_records,
)


BASE_URL = "https://presentediario.transmundial.org.br/"
FIRST_YEAR = 1998

PT_MONTHS = {
    1: "janeiro",
    2: "fevereiro",
    3: "março",
    4: "abril",
    5: "maio",
    6: "junho",
    7: "julho",
    8: "agosto",
    9: "setembro",
    10: "outubro",
    11: "novembro",
    12: "dezembro",
}


def format_pt_date(value: date) -> str:
    return f"{value.day} de {PT_MONTHS[value.month]} de {value.year}"


def split_key_verse(text: str) -> tuple[str, str]:
    value = re.sub(r"\s+", " ", as_text(text))
    match = re.match(r"^(.*)\(([^()]+)\)\.?\s*$", value)
    if not match:
        return value, ""
    return match.group(1).strip(), match.group(2).strip().rstrip(".")


def fetch_year(session: requests.Session, year: int) -> list[dict]:
    url = f"{BASE_URL}js/{year}.json"
    response = session.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.json()


def build_record(item: dict) -> dict:
    published = datetime.strptime(item["publishedAt"], "%Y-%m-%d").date()
    quote, reference = split_key_verse(item.get("keyVerse", ""))
    reading_reference = as_text(item.get("reference", ""))
    if not reference:
        reference = reading_reference

    return {
        "date_o": format_pt_date(published),
        "date": published.strftime("%m%d"),
        "reference": reference,
        "ari": reading_reference,
        "title": as_text(item.get("title", "")),
        "inspiration": html_to_text(as_text(item.get("content", ""))),
        "prayer": "",
        "quote": quote,
        "author": {
            "name": as_text(item.get("author", "")),
            "avatar": "",
        },
        "introduce": "",
        "original_link": f"{BASE_URL}js/{published.year}.json#{item['publishedAt']}",
        "audio": as_text(item.get("audioUrl", "")),
        "id": 0,
        "_date": published,
    }


def scrape(selection: dict) -> list[dict]:
    session = requests.Session()
    records_desc = []

    if selection["mode"] == "latest":
        years = range(selection["today"].year, FIRST_YEAR - 1, -1)
    else:
        years = range(selection["end"].year, selection["start"].year - 1, -1)

    for year in years:
        print(f"[*] PT fetch year {year}")
        items = fetch_year(session, year)
        items.sort(key=lambda item: item.get("publishedAt", ""), reverse=True)
        for item in items:
            record = build_record(item)
            published = record.pop("_date")

            if selection["mode"] == "latest":
                if published <= selection["today"]:
                    records_desc.append(record)
                    if len(records_desc) >= selection["limit"]:
                        return finalize_records(records_desc)
            else:
                if selection["start"] <= published <= selection["end"]:
                    records_desc.append(record)

    return finalize_records(records_desc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Portuguese devotional scraper")
    add_common_arguments(parser, "pt")
    args = parser.parse_args()
    selection = resolve_selection(args, parser)
    records = scrape(selection)
    save_records(records, args.output)


if __name__ == "__main__":
    main()
