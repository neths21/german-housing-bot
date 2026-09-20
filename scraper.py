"""Munich WG room watcher: scrape WG-Gesucht and push new listings to Telegram."""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.wg-gesucht.de"
SEEN_FILE = Path(__file__).parent / "seen_listings.json"
MIN_PRICE = 0
MAX_PRICE = 700
# U6 stations (Garching -> Klinikum Grosshadern) plus the districts around the
# line, since WG-Gesucht cards show districts/streets rather than stations.
# Listings matching any of these get a "Near U6" tag; nothing is filtered out.
U6_KEYWORDS = [
    "garching", "forschungszentrum", "hochbruck", "frottmaning", "kieferngarten",
    "freimann", "studentenstadt", "alte heide", "nordfriedhof", "dietlindenstrasse",
    "munchner freiheit", "giselastrasse", "universitat", "odeonsplatz",
    "marienplatz", "sendlinger tor", "goetheplatz", "poccistrasse", "harras",
    "implerstrasse", "partnachplatz", "westpark", "holzapfelkreuth",
    "haderner stern", "grosshadern", "hadern", "klinikum",
    "schwabing", "maxvorstadt", "milbertshofen", "altstadt", "lehel",
    "ludwigsvorstadt", "isarvorstadt", "glockenbach", "sendling", "laim",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def require_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"ERROR: environment variable {name} is missing or empty.")
    return value


def fetch_html(url):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def parse_price(text):
    """Extract the euro amount from text like '650 €' or '650,-€'."""
    match = re.search(r"(\d[\d.]*)\s*(?:,\s*-|,\d{1,2})?\s*€", text)
    if not match:
        return None
    return int(match.group(1).replace(".", ""))


def normalize(text):
    text = text.casefold()
    for src, dst in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        text = text.replace(src, dst)
    return text


def u6_matches(text):
    haystack = normalize(text)
    return [k for k in U6_KEYWORDS if re.search(rf"\b{re.escape(k)}", haystack)]


def parse_listings(html):
    # NOTE: WG-Gesucht's HTML may drift over time. If the bot stops finding
    # listings, inspect a listing card in your browser's dev tools and adjust
    # the selectors below.
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(
        'div[class*="wgg_card"][data-id], div[class*="offer_list_item"][data-id]'
    )

    listings = []
    seen_ids = set()
    for card in cards:
        listing_id = card.get("data-id", "").strip()
        if not listing_id or listing_id in seen_ids:
            continue

        link = card.select_one(
            "h2 a[href], h3 a[href], a.detailansicht[href], a[href*='.html']"
        )
        if not link:
            continue
        title = " ".join(link.get_text().split()) or (link.get("title") or "").replace(
            "Anzeige ansehen:", ""
        ).strip()
        url = link["href"]
        if url.startswith("/"):
            url = BASE_URL + url

        price_el = card.select_one("[class*='price'], b")
        price = parse_price(price_el.get_text(" ")) if price_el else None
        if price is None:
            price = parse_price(card.get_text(" "))

        district = ""
        details = card.select_one(".col-xs-11 span, [class*='location']")
        if details:
            text = " ".join(details.get_text().split())
            # Typically "WG 12 m² | München Maxvorstadt | Straße"
            parts = [p.strip() for p in text.split("|")]
            district = parts[1] if len(parts) > 1 else text

        seen_ids.add(listing_id)
        listings.append(
            {
                "id": listing_id,
                "title": title,
                "price": price,
                "district": district,
                "url": url,
                "u6": u6_matches(" ".join(card.get_text(" ").split())),
            }
        )
    return listings


def load_seen():
    if not SEEN_FILE.exists():
        return []
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def save_seen(ids):
    SEEN_FILE.write_text(json.dumps(ids, indent=2) + "\n", encoding="utf-8")


def send_telegram(token, chat_id, listing):
    tag = f"[Near U6: {', '.join(listing['u6'][:3])}]\n" if listing["u6"] else ""
    text = (
        f"{tag}{listing['title']}\n"
        f"Price: {listing['price']} EUR\n"
        f"District: {listing['district'] or 'n/a'}\n"
        f"{listing['url']}"
    )
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    response.raise_for_status()


def main():
    # WG_SEARCH_URL may hold several search URLs separated by whitespace/newlines.
    search_urls = require_env("WG_SEARCH_URL").split()
    token = require_env("TELEGRAM_BOT_TOKEN")
    chat_id = require_env("TELEGRAM_CHAT_ID")

    listings = []
    found_ids = set()
    failures = 0
    for i, search_url in enumerate(search_urls):
        if i:
            time.sleep(3)
        try:
            page = parse_listings(fetch_html(search_url))
        except requests.RequestException as exc:
            failures += 1
            print(f"WARNING: search {i + 1} failed to load: {type(exc).__name__}")
            continue
        for listing in page:
            if listing["id"] not in found_ids:
                found_ids.add(listing["id"])
                listings.append(listing)
    if failures == len(search_urls):
        sys.exit("ERROR: all search URLs failed to load.")

    in_budget = [
        l for l in listings if l["price"] is not None and MIN_PRICE <= l["price"] <= MAX_PRICE
    ]

    seen = load_seen()
    seen_set = set(seen)
    new = [l for l in in_budget if l["id"] not in seen_set]

    notified = 0
    for listing in new:
        try:
            send_telegram(token, chat_id, listing)
        except requests.RequestException as exc:
            # Do not mark as seen, so it is retried on the next run.
            # Avoid printing the exception: it can contain the bot token in the URL.
            print(f"WARNING: failed to send listing {listing['id']}: {type(exc).__name__}")
            continue
        seen.append(listing["id"])
        notified += 1

    if notified:
        save_seen(seen)

    print(f"Found {len(listings)} listings, {len(in_budget)} in budget, {notified} new")


if __name__ == "__main__":
    main()
