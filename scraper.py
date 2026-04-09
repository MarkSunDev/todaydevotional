# -*- coding: utf-8 -*-
"""
todaydevotional.com scraper
Uses the Algolia search API to enumerate articles, then fetches each page for full content.

Usage:
  python scraper.py scrape           # Scrape new articles (incremental)
  python scraper.py scrape --dry-run # List new links only (no fetching)
  python scraper.py fix-audio        # Add audio field by date (fast, no network)
  python scraper.py fix-avatars      # Fix broken avatar URLs (slow, re-fetches pages)
  python scraper.py list-algolia     # Dump Algolia metadata only (no page fetching)

JSON structure per record:
{
    "date_o": "December 31, 2022",
    "date": "1231",
    "reference": "Isaiah 65:17, 25",
    "ari": "Isaiah 65:17-25",
    "title": "What's Ahead?",
    "inspiration": "...",
    "prayer": "...",
    "quote": "...",
    "author": {"name": "...", "avatar": "https://sp-today-webassets..."},
    "introduce": "...",
    "original_link": "https://todaydevotional.com/devotions/...",
    "audio": "https://todaydevotional.com/audio/podcast/YYYY-MM-DD/website.mp3",
    "id": 459
}
"""

import json
import time
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Run: pip install requests beautifulsoup4")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "https://todaydevotional.com"
OUTPUT_FILE = Path(__file__).parent / "daily_devotion_en.json"
RESOURCE_DIR = Path(__file__).parent / "resource"

# Algolia credentials (public search-only key, extracted from page JS)
ALGOLIA_APP_ID   = "0CNYOKKCC8"
ALGOLIA_API_KEY  = "50680178cc2373f106dfd9f37c1be8d6"
ALGOLIA_INDEX    = "today"
ALGOLIA_QUERY_URL  = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
ALGOLIA_BROWSE_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/browse"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

ALGOLIA_HEADERS = {
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "X-Algolia-API-Key": ALGOLIA_API_KEY,
    "Content-Type": "application/json",
}

REQUEST_DELAY = 1.2   # seconds between page requests
MAX_RETRIES = 3
ALGOLIA_PAGE_SIZE = 1000  # max hits per Algolia request


# ---------------------------------------------------------------------------
# Algolia helpers
# ---------------------------------------------------------------------------

def algolia_get_all_devotions() -> list:
    """
    Fetch ALL devotion article metadata from Algolia using the Browse API
    (cursor-based, no 1000-hit limit unlike the query API).
    Returns list sorted by dateTimestamp descending (newest first).
    """
    all_hits = []
    cursor = None
    page_num = 0

    RETRIEVE_ATTRS = [
        "url", "uri", "title", "authors",
        "dateFormatted", "dateTimestamp",
        "scriptureReadingReference", "scriptureQuoteReference",
        "objectID",
    ]

    print("[*] Fetching article list from Algolia (Browse API)...")
    while True:
        page_num += 1
        if cursor:
            # Continue from cursor
            payload = {"cursor": cursor}
        else:
            # First request
            payload = {
                "query": "",
                "hitsPerPage": 1000,
                "filters": "section:Devotions",
                "attributesToRetrieve": RETRIEVE_ATTRS,
            }

        resp = requests.post(
            ALGOLIA_BROWSE_URL, headers=ALGOLIA_HEADERS, json=payload, timeout=20
        )
        resp.raise_for_status()
        data = resp.json()

        hits = data.get("hits", [])
        all_hits.extend(hits)
        cursor = data.get("cursor")

        total = data.get("nbHits", "?")
        print(f"  Page {page_num} — {len(all_hits)}/{total} fetched", end="\r")

        if not cursor:
            break  # No more pages

    print()  # newline after \r
    # Sort newest first
    all_hits.sort(key=lambda h: h.get("dateTimestamp", 0), reverse=True)
    print(f"[+] Total devotion articles: {len(all_hits)}")
    return all_hits


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def get_page(url: str, session: requests.Session):
    """Fetch URL with retry, return BeautifulSoup or None."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            print(f"  [!] Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(3)
    return None


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def parse_date(date_str: str):
    """Return (date_o, date_mmdd) e.g. ('December 31, 2022', '1231')."""
    date_str = date_str.strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d %Y"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Remove leading zero from day in MMDD
            mmdd = dt.strftime("%m%d")
            return date_str, mmdd
        except ValueError:
            continue
    return date_str, ""


def audio_url_from_date(date_o: str) -> str:
    """Derive audio podcast URL from date string (no network needed)."""
    for fmt in ["%B %d, %Y", "%b %d, %Y"]:
        try:
            dt = datetime.strptime(date_o.strip(), fmt)
            return f"{BASE_URL}/audio/podcast/{dt.strftime('%Y-%m-%d')}/website.mp3"
        except ValueError:
            continue
    return ""


def extract_audio_from_html(html_text: str) -> str:
    """Find the audio MP3 URL in raw HTML."""
    match = re.search(
        r'https://todaydevotional\.com/audio/podcast/\d{4}-\d{2}-\d{2}/website\.mp3',
        html_text
    )
    if match:
        return match.group(0)
    m2 = re.search(r'<source[^>]+src="([^"]*\.mp3)"', html_text)
    if m2:
        src = m2.group(1)
        return src if src.startswith("http") else f"{BASE_URL}{src}"
    return ""


def extract_avatar_from_img(img_tag) -> str:
    """
    Extract avatar URL from <img> tag.
    New CDN: sp-today-webassets.todaydevotional.com
    Uses data-srcset (lazy-load attribute in raw HTML), prefers 400w entry.
    """
    if img_tag is None:
        return ""
    # IMPORTANT: use data-srcset (raw HTML), not srcset (which is a placeholder SVG)
    srcset = img_tag.get("data-srcset", "") or img_tag.get("srcset", "")
    if srcset and "sp-today-webassets" in srcset:
        parts = [p.strip() for p in srcset.split(",") if p.strip()]
        # Prefer 400w
        for part in parts:
            tokens = part.split()
            if len(tokens) >= 2 and tokens[1] == "400w":
                return tokens[0].replace("&amp;", "&")
        # Fallback: first valid entry
        if parts:
            return parts[0].split()[0].replace("&amp;", "&")
    src = img_tag.get("src", "")
    return src.replace("&amp;", "&") if (src and "sp-today-webassets" in src) else ""


def parse_text_block(el) -> str:
    """Extract clean text, joining <p> tags with double newlines."""
    if el is None:
        return ""
    paragraphs = el.find_all("p")
    if paragraphs:
        return "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
    return el.get_text(separator="\n", strip=True)


# ---------------------------------------------------------------------------
# Page parser
# ---------------------------------------------------------------------------

def parse_devotion_page(url: str, session: requests.Session,
                        algolia_meta: dict = None) -> dict | None:
    """
    Parse a single devotion article page.
    algolia_meta: optional pre-fetched metadata from Algolia to fill missing fields.
    """
    soup = get_page(url, session)
    if soup is None:
        return None

    html = str(soup)
    meta = algolia_meta or {}
    record: dict = {"original_link": url, "id": 0}

    # --- title ---
    h1 = soup.find("h1")
    record["title"] = h1.get_text(strip=True) if h1 else meta.get("title", "")

    # --- date ---
    # Prefer Algolia's dateFormatted (reliable)
    date_str = meta.get("dateFormatted", "")
    if not date_str:
        # !dateActions class holds "December 31, 2020"
        date_el = soup.find(class_="!dateActions")
        if date_el:
            date_str = date_el.get_text(strip=True)
    if not date_str:
        # Derive from audio URL in page
        m = re.search(r"/audio/podcast/(\d{4}-\d{2}-\d{2})/", html)
        if m:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d")
            date_str = dt.strftime("%B %d, %Y").replace(" 0", " ")

    record["date_o"], record["date"] = parse_date(date_str)

    # --- audio ---
    record["audio"] = extract_audio_from_html(html)
    if not record["audio"] and record["date_o"]:
        record["audio"] = audio_url_from_date(record["date_o"])

    # --- scripture references ---
    # ari = full reading passage; reference = short key verse
    # Algolia provides: scriptureReadingReference (=ari), scriptureQuoteReference (=reference)
    record["ari"] = meta.get("scriptureReadingReference", "")
    record["reference"] = meta.get("scriptureQuoteReference", "")
    if not record["ari"]:
        reading_el = soup.find(class_="scriptureReading")
        if reading_el:
            txt = reading_el.get_text(strip=True)
            record["ari"] = re.sub(r"^Scripture\s+Reading\s*[—\-–]\s*", "", txt).strip()
    if not record["ari"]:
        record["ari"] = record["reference"]

    # --- inspiration ---
    # Body uses Alpine.js x-data="textMagnifier('devotionBody')"
    body_div = soup.find(attrs={"x-data": "textMagnifier('devotionBody')"})
    all_paras = body_div.find_all("p") if body_div else []
    record["inspiration"] = "\n\n".join(
        p.get_text(strip=True) for p in all_paras if p.get_text(strip=True)
    )

    # --- quote and prayer ---
    # Both use class="scriptureQuote":
    #   scriptureQuote[0] = quote (a Bible verse)
    #   scriptureQuote[1] = prayer (ends with Amen)
    sq_els = soup.find_all(class_="scriptureQuote")
    record["quote"] = sq_els[0].get_text(strip=True) if len(sq_els) > 0 else ""
    record["prayer"] = sq_els[1].get_text(strip=True) if len(sq_els) > 1 else ""

    # --- author name + bio ---
    # The author section has structure:
    #   "About the author —" heading
    #   <a href="/authors/..."> [avatar img] </a>
    #   <div> author name (h2/h3/strong/span) </div>
    #   <p> author bio </p>
    #
    # Strategy: find the "About the author" container, then walk its children.

    # Prefer Algolia authors list (most reliable)
    authors = meta.get("authors", [])
    author_name = authors[0] if authors else ""
    introduce = ""
    avatar_url = ""

    # Find author section via the /authors/ link
    author_link = soup.find("a", href=re.compile(r"/authors/"))
    if author_link:
        # Walk up to find the container that holds name + bio
        container = author_link.parent
        for _ in range(6):
            container = container.parent
            texts = [t.strip() for t in container.stripped_strings]
            # The container with bio has >100 chars of text
            full_text = " ".join(texts)
            if len(full_text) > 100:
                # Extract name: first meaningful text after "About the author"
                if not author_name:
                    # Skip "About the author" header text
                    for txt in texts:
                        if txt and "about the author" not in txt.lower() and "—" not in txt and len(txt) > 3:
                            author_name = txt
                            break
                # Extract bio: the longest paragraph-like text
                paras = container.find_all("p")
                if paras:
                    introduce = max((p.get_text(strip=True) for p in paras), key=len, default="")
                if introduce:
                    break

        # Avatar: img with data-srcset inside the author link
        img_tag = author_link.find("img", attrs={"data-srcset": True})
        if not img_tag:
            img_tag = author_link.find("img")
        avatar_url = extract_avatar_from_img(img_tag)

    # Final fallback for author name from Algolia
    author_name = re.sub(r"^by\s+", "", author_name, flags=re.I).strip()

    record["author"] = {"name": author_name, "avatar": avatar_url}
    record["introduce"] = introduce

    return record


# ---------------------------------------------------------------------------
# Data I/O
# ---------------------------------------------------------------------------

def load_existing(output_file: Path = None):
    """Load JSON, return (data_list, existing_links_set, max_id)."""
    path = output_file or OUTPUT_FILE
    if not path.exists():
        return [], set(), 0
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    existing_links = {d["original_link"] for d in data}
    max_id = max((d.get("id", 0) for d in data), default=0)
    return data, existing_links, max_id


def save_data(data: list, output_file: Path = None) -> None:
    """Save sorted by id descending (newest first)."""
    path = output_file or OUTPUT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    data_sorted = sorted(data, key=lambda x: x.get("id", 0), reverse=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data_sorted, f, ensure_ascii=False, indent=2)
    print(f"[OK] Saved {len(data_sorted)} records -> {path}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_scrape(dry_run: bool = False, year: int = None,
               output_file: Path = None, limit: int = None) -> None:
    """
    Scrape new articles using Algolia for enumeration + HTML for full content.
    year: filter to a specific year (optional)
    output_file: save path (default: daily_devotion_en.json)
    limit: max number of articles to scrape (optional)
    """
    out = output_file or OUTPUT_FILE
    print("=" * 60)
    print("todaydevotional.com scraper")
    print("=" * 60)

    existing_data, existing_links, max_id = load_existing(out)
    print(f"[*] Existing records: {len(existing_data)}, max ID: {max_id}")

    # Get all articles from Algolia
    all_algolia = algolia_get_all_devotions()

    # Filter to new ones only
    new_items = [
        h for h in all_algolia
        if h.get("url") and h["url"] not in existing_links
    ]

    # Optional year filter
    if year:
        new_items = [
            h for h in new_items
            if h.get("dateFormatted", "").endswith(str(year))
        ]
        print(f"[*] Filtered to year {year}: {len(new_items)} articles")

    # Optional limit
    if limit and limit > 0:
        new_items = new_items[:limit]
        print(f"[*] Limited to first {limit} articles")

    print(f"\n[*] New articles to scrape: {len(new_items)}")

    if not new_items:
        print("[*] Nothing new, exiting")
        return

    if dry_run:
        print("\n[DRY RUN] New article URLs:")
        for h in new_items:
            print(f"  {h.get('dateFormatted', '?'):>22}  {h['url']}")
        return

    new_records = []
    session = requests.Session()
    current_id = max_id + 1

    for i, algolia_hit in enumerate(new_items, 1):
        url = algolia_hit["url"]
        print(f"\n[{i}/{len(new_items)}] {url}")
        time.sleep(REQUEST_DELAY)

        record = parse_devotion_page(url, session, algolia_meta=algolia_hit)
        if record is None:
            print("  [!] Skip (fetch/parse failed)")
            continue

        record["id"] = current_id
        current_id += 1
        print(f"  title  : {record.get('title', '?')}")
        print(f"  date   : {record.get('date_o', '?')}")
        print(f"  audio  : {record.get('audio') or '-'}")
        print(f"  author : {record.get('author', {}).get('name', '?')}")
        new_records.append(record)

        if i % 20 == 0:
            save_data(existing_data + new_records, out)

    save_data(existing_data + new_records, out)
    print(f"\n[OK] Done. Added {len(new_records)} new records.")


def cmd_fix_audio() -> None:
    """Add 'audio' field to records missing it, derived from date_o. No network needed."""
    data, _, _ = load_existing()
    fixed = 0
    for record in data:
        if record.get("audio"):
            continue
        url = audio_url_from_date(record.get("date_o", ""))
        if url:
            record["audio"] = url
            fixed += 1
            print(f"  [+] {record.get('date_o')} -> {url}")
    save_data(data)
    print(f"[OK] Added audio URL to {fixed} records")


def cmd_fix_avatars() -> None:
    """
    Fix broken avatar URLs by re-fetching each article page.
    Old (broken): today-webassets.imgix.net
    New (working): sp-today-webassets.todaydevotional.com
    """
    data, _, _ = load_existing()
    session = requests.Session()
    fixed = 0
    total = len(data)
    needs_fix = [r for r in data if "imgix.net" in r.get("author", {}).get("avatar", "")
                 or not r.get("author", {}).get("avatar", "")]

    print(f"[*] Records needing avatar fix: {len(needs_fix)}/{total}")

    for i, record in enumerate(needs_fix, 1):
        link = record.get("original_link", "")
        old_avatar = record.get("author", {}).get("avatar", "")
        print(f"[{i}/{len(needs_fix)}] {link}")
        time.sleep(REQUEST_DELAY)

        soup = get_page(link, session)
        if soup is None:
            print("  [!] Fetch failed, skipping")
            continue

        author_link = soup.find("a", href=re.compile(r"/authors/"))
        img_tag = None
        if author_link:
            img_tag = author_link.find("img", attrs={"data-srcset": True})
            if not img_tag:
                img_tag = author_link.find("img")
        if not img_tag:
            img_tag = soup.find("img", attrs={"data-srcset": re.compile(r"sp-today-webassets")})

        new_avatar = extract_avatar_from_img(img_tag)
        if new_avatar and new_avatar != old_avatar:
            record["author"]["avatar"] = new_avatar
            fixed += 1
            print(f"  [+] {new_avatar[:90]}")
        else:
            print(f"  [-] No new avatar found")

        if i % 20 == 0:
            save_data(data)

    save_data(data)
    print(f"[OK] Fixed {fixed} avatar URLs")


def cmd_list_algolia(year: int = None) -> None:
    """Print all Algolia-enumerated articles without fetching pages."""
    hits = algolia_get_all_devotions()
    if year:
        hits = [h for h in hits if h.get("dateFormatted", "").endswith(str(year))]
    for h in hits:
        print(f"{h.get('dateFormatted', '?'):>22}  {h.get('url', '?')}")
    print(f"\nTotal: {len(hits)}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="todaydevotional.com scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py scrape                    Scrape all new articles
  python scraper.py scrape --dry-run          List new articles only
  python scraper.py scrape --year 2023        Scrape only 2023 articles
  python scraper.py fix-audio                 Add audio field by date (fast)
  python scraper.py fix-avatars               Fix broken avatar URLs (slow)
  python scraper.py list-algolia              Show all Algolia article URLs
  python scraper.py list-algolia --year 2024  Show 2024 articles
        """
    )
    sub = parser.add_subparsers(dest="command")

    p_scrape = sub.add_parser("scrape", help="Scrape new articles (incremental)")
    p_scrape.add_argument("--dry-run", action="store_true")
    p_scrape.add_argument("--year", type=int, default=None, help="Filter to a specific year")
    p_scrape.add_argument("--limit", type=int, default=None, help="Max articles to scrape")
    p_scrape.add_argument("--output", type=str, default=None,
                          help="Output JSON file path (default: daily_devotion_en.json)")

    sub.add_parser("fix-audio", help="Add audio field by date (fast, no network)")
    sub.add_parser("fix-avatars", help="Fix broken avatar URLs (slow)")

    p_list = sub.add_parser("list-algolia", help="List all articles from Algolia")
    p_list.add_argument("--year", type=int, default=None)

    args = parser.parse_args()

    if args.command == "scrape":
        out = Path(args.output) if getattr(args, "output", None) else None
        cmd_scrape(dry_run=args.dry_run, year=args.year,
                   output_file=out, limit=getattr(args, "limit", None))
    elif args.command == "fix-audio":
        cmd_fix_audio()
    elif args.command == "fix-avatars":
        cmd_fix_avatars()
    elif args.command == "list-algolia":
        cmd_list_algolia(year=args.year)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
