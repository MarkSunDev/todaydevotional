# -*- coding: utf-8 -*-
"""
Spanish devotional scraper for ministerioreforma.com.

Examples:
  python scraper_es.py --limit 20
  python scraper_es.py --start 20250101 --end 20251231
"""

from __future__ import annotations

import argparse
import re
import time
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper_common import (
    HEADERS,
    add_common_arguments,
    finalize_records,
    node_to_text,
    resolve_selection,
    save_records,
    split_lines,
)


BASE_URL = "https://ministerioreforma.com/cadadia/"
REQUEST_DELAY = 0.3

ES_MONTHS = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}
ES_MONTHS_REVERSE = {value: key for key, value in ES_MONTHS.items()}


def format_es_date(value: date) -> str:
    return f"{value.day} de {ES_MONTHS[value.month]} del {value.year}"


def parse_es_display_date(text: str) -> date:
    match = re.search(r"(\d{1,2}) de ([a-záéíóú]+) del (\d{4})", text.lower())
    if not match:
        raise ValueError(f"Could not parse ES date from: {text}")
    return date(int(match.group(3)), ES_MONTHS_REVERSE[match.group(2)], int(match.group(1)))


def split_es_verse(text: str) -> tuple[str, str]:
    value = re.sub(r"\s+", " ", (text or "").strip())
    ref_match = re.search(
        r"([1-3]?\s?[A-Za-zÁÉÍÓÚáéíóúÑñ]+(?:\s+[A-Za-zÁÉÍÓÚáéíóúÑñ]+)*\s+\d+:\d+(?:-\d+)?)\s*$",
        value,
    )
    if ref_match:
        reference = ref_match.group(1).strip()
        quote = value[: ref_match.start()].strip().strip('“”" .')
        return quote, reference
    return value, ""


def fetch_page(session: requests.Session, url: str) -> tuple[dict, str | None]:
    response = session.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    title = node_to_text(soup.select_one("#titulo"))
    verse_line = node_to_text(soup.select_one("#versiculo"))
    quote, reference = split_es_verse(verse_line)
    record_date = parse_es_display_date(node_to_text(soup.select_one(".colunas")))

    bio_lines = split_lines(node_to_text(soup.select_one("#bio")))
    author_name = bio_lines[0] if bio_lines else ""
    introduce = "\n".join(bio_lines[1:]).strip() if len(bio_lines) > 1 else ""

    avatar_node = soup.select_one("#autor img")
    avatar = urljoin(url, avatar_node["src"]) if avatar_node and avatar_node.get("src") else ""

    prev_anchor = soup.find("a", href=re.compile(r"dir=menos"))
    previous_link = urljoin(url, prev_anchor["href"]) if prev_anchor and prev_anchor.get("href") else None

    record = {
        "date_o": format_es_date(record_date),
        "date": record_date.strftime("%m%d"),
        "reference": reference,
        "ari": node_to_text(soup.select_one("#texto-biblico")),
        "title": title,
        "inspiration": node_to_text(soup.select_one("#novocorpo")),
        "prayer": node_to_text(soup.select_one("#ora")),
        "quote": quote,
        "author": {
            "name": author_name,
            "avatar": avatar,
        },
        "introduce": introduce,
        "original_link": url,
        "audio": "",
        "id": 0,
        "_date": record_date,
    }
    return record, previous_link


def scrape(selection: dict) -> list[dict]:
    session = requests.Session()
    records_desc = []
    start_url = f"{BASE_URL}?data={selection['today'].isoformat()}"
    if selection["mode"] == "range":
        start_url = f"{BASE_URL}?data={selection['end'].isoformat()}"

    url = start_url
    while url:
        print(f"[*] ES fetch {url}")
        record, previous_link = fetch_page(session, url)
        record_date = record.pop("_date")

        if selection["mode"] == "latest":
            if record_date <= selection["today"]:
                records_desc.append(record)
                if len(records_desc) >= selection["limit"]:
                    break
        else:
            if record_date < selection["start"]:
                break
            if selection["start"] <= record_date <= selection["end"]:
                records_desc.append(record)

        url = previous_link
        time.sleep(REQUEST_DELAY)

    return finalize_records(records_desc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Spanish devotional scraper")
    add_common_arguments(parser, "es")
    args = parser.parse_args()
    selection = resolve_selection(args, parser)
    records = scrape(selection)
    save_records(records, args.output)


if __name__ == "__main__":
    main()
