# -*- coding: utf-8 -*-
"""
English devotional scraper for todaydevotional.com.

Examples:
  python scraper_en.py --limit 20
  python scraper_en.py --start 20250101 --end 20251231
"""

from __future__ import annotations

import argparse
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scraper_common import (
    HEADERS,
    add_common_arguments,
    finalize_records,
    node_to_text,
    resolve_selection,
    save_records,
)


BASE_URL = "https://todaydevotional.com"
ALGOLIA_APP_ID = "0CNYOKKCC8"
ALGOLIA_API_KEY = "50680178cc2373f106dfd9f37c1be8d6"
ALGOLIA_INDEX = "today"
ALGOLIA_BROWSE_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/browse"

ALGOLIA_HEADERS = {
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "X-Algolia-API-Key": ALGOLIA_API_KEY,
    "Content-Type": "application/json",
}

REQUEST_DELAY = 1.0
MAX_RETRIES = 3


def parse_display_date(date_str: str) -> tuple[str, str]:
    date_str = date_str.strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d %Y"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            return date_str, dt.strftime("%m%d")
        except ValueError:
            continue
    return date_str, ""


def parse_algolia_date(date_str: str):
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d %Y"]:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def audio_url_from_date(date_o: str) -> str:
    for fmt in ["%B %d, %Y", "%b %d, %Y"]:
        try:
            dt = datetime.strptime(date_o.strip(), fmt)
            return f"{BASE_URL}/audio/podcast/{dt.strftime('%Y-%m-%d')}/website.mp3"
        except ValueError:
            continue
    return ""


def extract_audio_from_html(html_text: str) -> str:
    match = re.search(
        r'https://todaydevotional\.com/audio/podcast/\d{4}-\d{2}-\d{2}/website\.mp3',
        html_text,
    )
    if match:
        return match.group(0)
    fallback = re.search(r'<source[^>]+src="([^"]*\.mp3)"', html_text)
    if fallback:
        src = fallback.group(1)
        return src if src.startswith("http") else f"{BASE_URL}{src}"
    return ""


def extract_avatar_from_img(img_tag) -> str:
    if img_tag is None:
        return ""
    srcset = img_tag.get("data-srcset", "") or img_tag.get("srcset", "")
    if srcset and "sp-today-webassets" in srcset:
        parts = [part.strip() for part in srcset.split(",") if part.strip()]
        for part in parts:
            tokens = part.split()
            if len(tokens) >= 2 and tokens[1] == "400w":
                return tokens[0].replace("&amp;", "&")
        if parts:
            return parts[0].split()[0].replace("&amp;", "&")
    src = img_tag.get("src", "")
    return src.replace("&amp;", "&") if (src and "sp-today-webassets" in src) else ""


def algolia_get_all_devotions() -> list[dict]:
    all_hits = []
    cursor = None

    payload = {
        "query": "",
        "hitsPerPage": 1000,
        "filters": "section:Devotions",
        "attributesToRetrieve": [
            "url",
            "title",
            "authors",
            "dateFormatted",
            "dateTimestamp",
            "scriptureReadingReference",
            "scriptureQuoteReference",
        ],
    }

    while True:
        body = {"cursor": cursor} if cursor else payload
        response = requests.post(ALGOLIA_BROWSE_URL, headers=ALGOLIA_HEADERS, json=body, timeout=20)
        response.raise_for_status()
        data = response.json()
        all_hits.extend(data.get("hits", []))
        cursor = data.get("cursor")
        if not cursor:
            break

    all_hits.sort(key=lambda hit: hit.get("dateTimestamp", 0), reverse=True)
    return all_hits


def get_page(url: str, session: requests.Session):
    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2)
    raise RuntimeError("Unreachable")


def parse_devotion_page(url: str, session: requests.Session, algolia_meta: dict) -> dict:
    soup = get_page(url, session)
    html = str(soup)

    record = {"original_link": url, "id": 0}

    h1 = soup.find("h1")
    record["title"] = h1.get_text(strip=True) if h1 else algolia_meta.get("title", "")

    date_str = algolia_meta.get("dateFormatted", "")
    if not date_str:
        date_el = soup.find(class_="!dateActions")
        if date_el:
            date_str = date_el.get_text(strip=True)
    if not date_str:
        match = re.search(r"/audio/podcast/(\d{4}-\d{2}-\d{2})/", html)
        if match:
            dt = datetime.strptime(match.group(1), "%Y-%m-%d")
            date_str = dt.strftime("%B %d, %Y").replace(" 0", " ")

    record["date_o"], record["date"] = parse_display_date(date_str)
    record["audio"] = extract_audio_from_html(html) or audio_url_from_date(record["date_o"])

    record["ari"] = algolia_meta.get("scriptureReadingReference", "") or ""
    record["reference"] = algolia_meta.get("scriptureQuoteReference", "") or ""
    if not record["ari"]:
        reading_el = soup.find(class_="scriptureReading")
        if reading_el:
            text = reading_el.get_text(strip=True)
            record["ari"] = re.sub(r"^Scripture\s+Reading\s*[—\-–]\s*", "", text).strip()
    if not record["ari"]:
        record["ari"] = record["reference"]

    body_div = soup.find(attrs={"x-data": "textMagnifier('devotionBody')"})
    body_paragraphs = body_div.find_all("p") if body_div else []
    record["inspiration"] = "\n\n".join(
        p.get_text(strip=True) for p in body_paragraphs if p.get_text(strip=True)
    )

    scripture_quotes = soup.find_all(class_="scriptureQuote")
    record["quote"] = scripture_quotes[0].get_text(strip=True) if len(scripture_quotes) > 0 else ""
    record["prayer"] = scripture_quotes[1].get_text(strip=True) if len(scripture_quotes) > 1 else ""

    authors = algolia_meta.get("authors", [])
    author_name = authors[0] if authors else ""
    introduce = ""
    avatar = ""

    author_link = soup.find("a", href=re.compile(r"/authors/"))
    if author_link:
        container = author_link.parent
        for _ in range(6):
            container = container.parent
            texts = [text.strip() for text in container.stripped_strings]
            if len(" ".join(texts)) > 100:
                if not author_name:
                    for text in texts:
                        if (
                            text
                            and "about the author" not in text.lower()
                            and "—" not in text
                            and len(text) > 3
                        ):
                            author_name = text
                            break
                paragraphs = container.find_all("p")
                if paragraphs:
                    introduce = max((p.get_text(strip=True) for p in paragraphs), key=len, default="")
                if introduce:
                    break
        img_tag = author_link.find("img", attrs={"data-srcset": True}) or author_link.find("img")
        avatar = extract_avatar_from_img(img_tag)

    record["author"] = {
        "name": re.sub(r"^by\s+", "", author_name, flags=re.I).strip(),
        "avatar": avatar,
    }
    record["introduce"] = introduce
    return record


def select_hits(selection: dict) -> list[dict]:
    hits = algolia_get_all_devotions()

    filtered = []
    for hit in hits:
        hit_date = parse_algolia_date(hit.get("dateFormatted", ""))
        if hit_date is None:
            continue
        if selection["mode"] == "latest":
            if hit_date <= selection["today"]:
                filtered.append(hit)
        else:
            if selection["start"] <= hit_date <= selection["end"]:
                filtered.append(hit)

    if selection["mode"] == "latest":
        return filtered[: selection["limit"]]
    return filtered


def scrape(selection: dict) -> list[dict]:
    selected_hits = select_hits(selection)
    session = requests.Session()
    records_desc = []

    for index, hit in enumerate(selected_hits, start=1):
        url = hit["url"]
        print(f"[{index}/{len(selected_hits)}] {url}")
        record = parse_devotion_page(url, session, hit)
        records_desc.append(record)
        time.sleep(REQUEST_DELAY)

    return finalize_records(records_desc)


def main() -> None:
    parser = argparse.ArgumentParser(description="English devotional scraper")
    add_common_arguments(parser, "en")
    args = parser.parse_args()
    selection = resolve_selection(args, parser)
    records = scrape(selection)
    save_records(records, args.output)


if __name__ == "__main__":
    main()
