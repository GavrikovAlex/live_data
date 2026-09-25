"""Collect listing IDs from allowed Restate catalog pages."""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger("apartments.collect_ids")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "ids.json"
BASE_URL = "https://www.restate.ru"
# Этот скрипт предназначен только для локального сбора разрешённых страниц.
# Все каталоги по умолчанию — district-срезы «вторичного рынка» внутри Moscow.
ROOM_SLUGS = (
    "prodazha_odnokomnatnyh_kvartir_na_vtorichnom_rynke",
    "prodazha_dvuhkomnatnyh_kvartir_na_vtorichnom_rynke",
    "prodazha_trekhkomnatnyh_kvartir_na_vtorichnom_rynke",
)
MOSCOW_AREA_IDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
DEFAULT_CATALOG_URLS = tuple(
    f"{BASE_URL}/area/moscow/{area_id}/{slug}"
    for slug in ROOM_SLUGS
    for area_id in MOSCOW_AREA_IDS
)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
LISTING_PATH_RE = re.compile(r"^/base/(\d+)\.html$")
NUMERIC_ID_RE = re.compile(r"^\d+$")
DEFAULT_DELAY = 2.0
DEFAULT_MAX_PAGES = 2


class RateLimiter:
    """Delay requests to the public site by at least the configured interval."""

    def __init__(self, delay: float = DEFAULT_DELAY) -> None:
        self.delay = max(0.0, delay)
        self.last_request_at = 0.0

    def wait(self) -> None:
        """Sleep until the next request is allowed."""
        elapsed = time.monotonic() - self.last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request_at = time.monotonic()


def make_session() -> requests.Session:
    """Create a browser-like session for public catalog requests."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
        }
    )
    return session


def page_url(base_url: str, page: int) -> str:
    """Build a catalog URL for a one-based page number."""
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["o"] = "0"
    query["page"] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def listing_url(listing_id: int) -> str:
    """Return the canonical detail URL for a numeric listing ID."""
    return f"{BASE_URL}/base/{listing_id}.html"


def extract_listing_ids(soup: BeautifulSoup, current_url: str) -> list[dict[str, object]]:
    """Extract unique numeric IDs and canonical detail links from catalog cards."""
    cards = soup.select("div.search-list__list > div.sri[data-id]")
    if not cards:
        cards = soup.select("div.sri[data-id]")

    found: dict[int, dict[str, object]] = {}
    for card in cards:
        raw_id = str(card.get("data-id", "")).strip()
        if not NUMERIC_ID_RE.fullmatch(raw_id):
            continue
        listing_id = int(raw_id)
        link = card.select_one(
            'a.sri__slider[href*="/base/"], a.sri__common-link[href*="/base/"]'
        )
        if link is None:
            link = card.select_one('a[href*="/base/"]')
        href = str(link.get("href", "")) if link is not None else ""
        absolute_href = urljoin(current_url, href) if href else listing_url(listing_id)
        path = urlparse(absolute_href).path
        path_match = LISTING_PATH_RE.match(path)
        if path_match is None or int(path_match.group(1)) != listing_id:
            absolute_href = listing_url(listing_id)
        found[listing_id] = {"id": listing_id, "url": absolute_href}

    return list(found.values())


def extract_last_page(soup: BeautifulSoup, current_url: str) -> int:
    """Find the largest page number linked from the current catalog page."""
    current_path = urlparse(current_url).path
    last_page = 1
    for link in soup.select("a[href]"):
        target = urlparse(urljoin(current_url, str(link.get("href", ""))))
        if target.path != current_path:
            continue
        page_values = parse_qs(target.query).get("page", [])
        for value in page_values:
            if value.isdigit():
                last_page = max(last_page, int(value))
    return last_page


def fetch_catalog_page(
    session: requests.Session,
    limiter: RateLimiter,
    url: str,
) -> BeautifulSoup:
    """Fetch and parse one public catalog page."""
    limiter.wait()
    response = session.get(url, timeout=30)
    response.raise_for_status()
    if not response.encoding:
        response.encoding = response.apparent_encoding
    return BeautifulSoup(response.text, "html.parser")


def collect_catalog(
    session: requests.Session,
    limiter: RateLimiter,
    catalog_url: str,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[dict[str, object]]:
    """Collect IDs from one catalog until its last linked page is reached."""
    collected: list[dict[str, object]] = []
    seen_ids: set[int] = set()
    last_page = 1
    for page_number in range(1, max_pages + 1):
        current_url = page_url(catalog_url, page_number)
        try:
            soup = fetch_catalog_page(session, limiter, current_url)
        except requests.RequestException as exc:
            LOGGER.warning("Catalog request failed: %s (%s)", current_url, exc)
            break

        page_records = extract_listing_ids(soup, current_url)
        LOGGER.info("Page %d: %d listing cards", page_number, len(page_records))
        for record in page_records:
            listing_id = int(record["id"])
            if listing_id not in seen_ids:
                seen_ids.add(listing_id)
                collected.append(record)

        if page_number == 1:
            last_page = extract_last_page(soup, current_url)
        if page_number >= last_page or not page_records:
            break

    LOGGER.info("Catalog total: %d unique IDs (last linked page %d)", len(collected), last_page)
    return collected


def interleave_records(groups: list[list[dict[str, object]]]) -> list[dict[str, object]]:
    """Merge per-catalog records round-robin, keeping the first occurrence."""
    merged: list[dict[str, object]] = []
    seen_ids: set[int] = set()
    depth = max((len(group) for group in groups), default=0)
    for index in range(depth):
        for group in groups:
            if index >= len(group):
                continue
            record = group[index]
            listing_id = int(record["id"])
            if listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)
            merged.append(record)
    return merged


def collect_ids(
    catalog_urls: list[str] | tuple[str, ...] = DEFAULT_CATALOG_URLS,
    delay: float = DEFAULT_DELAY,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[dict[str, object]]:
    """Collect and deduplicate IDs from several allowed Restate catalogs.

    Catalogs are interleaved round-robin so that any prefix of the result stays
    balanced across districts instead of exhausting the first catalog first.
    """
    session = make_session()
    limiter = RateLimiter(delay)
    per_catalog: list[list[dict[str, object]]] = []
    for catalog_url in catalog_urls:
        if not catalog_url.startswith(f"{BASE_URL}/"):
            raise ValueError(f"Catalog URL is outside the allowed host: {catalog_url}")
        LOGGER.info("Collecting %s", catalog_url)
        per_catalog.append(collect_catalog(session, limiter, catalog_url, max_pages))

    return interleave_records(per_catalog)


def write_ids(records: list[dict[str, object]], output_path: Path) -> None:
    """Write collected IDs as UTF-8 JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line options for local collection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--catalog", action="append", dest="catalog_urls")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    return parser.parse_args()


def main() -> int:
    """Run the local ID collection command."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    catalogs = tuple(args.catalog_urls or DEFAULT_CATALOG_URLS)
    records = collect_ids(catalogs, delay=args.delay, max_pages=args.max_pages)
    write_ids(records, args.output)
    LOGGER.info("Saved %d unique IDs to %s", len(records), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
