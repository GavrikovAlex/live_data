"""Parse public Restate detail pages into an anonymized local dataset."""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger("apartments.parse_detail")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "ids.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "listings.json"
DEFAULT_SAMPLE_OUTPUT = PROJECT_ROOT / "data" / "sample.json"
BASE_URL = "https://www.restate.ru"
MAX_PRICE = 100_000_000
DEFAULT_DELAY = 2.0
DEFAULT_SAMPLE_SIZE = 50
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
FLOOR_RE = re.compile(r"(\d+)\s+из\s+(\d+)", re.IGNORECASE)
MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


class RateLimiter:
    """Delay detail-page requests by at least the configured interval."""

    def __init__(self, delay: float = DEFAULT_DELAY) -> None:
        self.delay = max(0.0, delay)
        self.last_request_at = 0.0

    def wait(self) -> None:
        """Sleep until the next request is allowed."""
        elapsed = time.monotonic() - self.last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request_at = time.monotonic()


def normalize_text(value: str) -> str:
    """Collapse whitespace and normalize common punctuation."""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def parse_number(value: Any, multiplier: float = 1.0) -> float | None:
    """Parse a localized number from HTML text or a JSON value."""
    if value is None:
        return None
    text = normalize_text(str(value)).casefold()
    if "млн" in text:
        multiplier *= 1_000_000
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    match = NUMBER_RE.search(text)
    if match is None:
        return None
    number = match.group(0).replace(" ", "").replace(",", ".")
    try:
        return float(number) * multiplier
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    """Parse an integer value, returning None for missing or invalid data."""
    number = parse_number(value)
    if number is None:
        return None
    return int(round(number))


def clean_metro(value: str | None) -> str | None:
    """Reduce a metro label to the station name only."""
    if not value:
        return None
    cleaned = re.sub(r"\([^)]*\)", " ", value)
    cleaned = cleaned.split(",", 1)[0]
    cleaned = re.sub(r"^метро\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = normalize_text(cleaned)
    return cleaned or None


def labeled_values(soup: BeautifulSoup, selector: str) -> dict[str, str]:
    """Collect label/value pairs from compact detail-page elements."""
    values: dict[str, str] = {}
    for element in soup.select(selector):
        label_element = element.select_one(".obj-params__label")
        value_element = element.select_one(".obj-params__value")
        if label_element is not None and value_element is not None:
            label = normalize_text(label_element.get_text(" ", strip=True)).casefold()
            value = normalize_text(value_element.get_text(" ", strip=True))
            if label and value:
                values[label] = value
            continue
        text = normalize_text(element.get_text(" ", strip=True))
        if not text:
            continue
        match = re.match(r"([^:]+):\s*(.*)$", text)
        if match is not None:
            label = normalize_text(match.group(1)).casefold()
            value = normalize_text(match.group(2))
        else:
            direct_parts = [
                normalize_text(part.get_text(" ", strip=True))
                for part in element.find_all(recursive=False)
                if normalize_text(part.get_text(" ", strip=True))
            ]
            if len(direct_parts) >= 2:
                label = direct_parts[0].casefold()
                value = " ".join(direct_parts[1:])
            else:
                label_match = re.match(
                    r"(.+?(?:комнат|этаж|площадь|кухня|жилая|общая))\s+(.+)",
                    text,
                    re.IGNORECASE,
                )
                if label_match is None:
                    continue
                label = normalize_text(label_match.group(1)).casefold()
                value = normalize_text(label_match.group(2))
        if label and value:
            values[label] = value
    return values


def value_for_labels(values: dict[str, str], labels: Iterable[str]) -> str | None:
    """Return the first value whose label contains one of the requested terms."""
    for label, value in values.items():
        if any(term in label for term in labels):
            return value
    return None


def extract_specs(soup: BeautifulSoup) -> dict[str, int | float | None]:
    """Extract room count, areas, and floor values from detail labels."""
    values = labeled_values(
        soup,
        "li.base-specs__list-item, .obj-params__param, .obj-params__item",
    )
    rooms_value = value_for_labels(values, ("количество комнат", "комнат"))
    total_value = value_for_labels(values, ("общая площадь", "общая"))
    if total_value is None:
        total_value = value_for_labels(values, ("площадь",))
    living_value = value_for_labels(values, ("жилая площадь", "жилая"))
    kitchen_value = value_for_labels(values, ("кухня",))
    floor_text = " ".join(values.values())
    floor_match = FLOOR_RE.search(floor_text)
    if floor_match is not None:
        floor = int(floor_match.group(1))
        floors_total = int(floor_match.group(2))
    else:
        floor = None
        floors_total = None
        for label, value in values.items():
            if label.startswith("этажей"):
                floors_total = parse_int(value)
            elif label.startswith("этаж") and floor is None:
                floor = parse_int(value)
    return {
        "rooms": parse_int(rooms_value),
        "area_total": parse_number(total_value),
        "area_living": parse_number(living_value),
        "area_kitchen": parse_number(kitchen_value),
        "floor": floor,
        "floors_total": floors_total,
    }


def extract_meta_text(soup: BeautifulSoup) -> str:
    """Collect title and metadata used only for local filtering."""
    values: list[str] = []
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    values.append(title)
    for selector in (
        'meta[property="og:title"]',
        'meta[name="description"]',
        'meta[property="og:description"]',
    ):
        element = soup.select_one(selector)
        if element is not None:
            values.append(str(element.get("content", "")))
    return normalize_text(" ".join(values)).casefold()


def extract_breadcrumbs(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Return visible breadcrumb labels and their paths without storing them."""
    result: list[tuple[str, str]] = []
    selectors = (
        ".breadcrumbs a",
        ".base-breadcrumbs a",
        '[itemprop="itemListElement"] a',
    )
    seen: set[tuple[str, str]] = set()
    for selector in selectors:
        for link in soup.select(selector):
            label = normalize_text(link.get_text(" ", strip=True))
            href = str(link.get("href", ""))
            if not label or not href or (label, href) in seen:
                continue
            seen.add((label, href))
            result.append((label, href))
    return result


def extract_location(soup: BeautifulSoup, current_url: str) -> dict[str, str | None]:
    """Extract only broad Moscow geography fields from existing links."""
    location: dict[str, str | None] = {
        "city": "Москва",
        "okrug": None,
        "district": None,
        "metro": None,
    }
    for label, href in extract_breadcrumbs(soup):
        path = urlparse(href).path
        label_folded = label.casefold()
        if "/metro/" in path or "метро" in label_folded:
            location["metro"] = label
        elif "/area/moscow/" in path and label_folded not in {"москва", "объявления"}:
            location["okrug"] = label
        elif "/dist/" in path or "район" in label_folded:
            location["district"] = label
    if location["metro"] is None and "/metro/moscow/" in urlparse(current_url).path:
        location["metro"] = None
    return location


def extract_published_at(soup: BeautifulSoup) -> str | None:
    """Parse the publication date from the public ad-parameters block."""
    element = soup.select_one(".base__ad-params")
    if element is None:
        return None
    text = normalize_text(element.get_text(" ", strip=True))
    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if iso_match:
        return iso_match.group(0)
    month_match = re.search(r"\b(\d{1,2})\s+([а-яё]+)\s+(\d{4})\b", text.casefold())
    if month_match is not None:
        day, month_name, year = month_match.groups()
        month = MONTHS.get(month_name)
        if month is not None:
            try:
                return date(int(year), month, int(day)).isoformat()
            except ValueError:
                return None
    numeric_dates = re.findall(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", text)
    if not numeric_dates:
        return None
    day, month, year = numeric_dates[-1]
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def is_moscow(soup: BeautifulSoup, current_url: str, meta_text: str) -> bool:
    """Check that the page is a Moscow listing without using a broad body match."""
    breadcrumb_text = " ".join(label for label, _ in extract_breadcrumbs(soup)).casefold()
    path = urlparse(current_url).path.casefold()
    return "moscow" in path or "москв" in meta_text or "москв" in breadcrumb_text


def is_secondary(meta_text: str) -> bool:
    """Check the required secondary-market marker in title or metadata."""
    return "вторич" in meta_text


def is_apartment(meta_text: str) -> bool:
    """Check that title or metadata describes an apartment."""
    return "квартир" in meta_text


def parse_detail(html: str, current_url: str, listing_id: int | None = None) -> dict[str, Any]:
    """Parse one public detail page into a minimal, non-identifying record."""
    soup = BeautifulSoup(html, "html.parser")
    meta_text = extract_meta_text(soup)
    price_element = soup.select_one(".price-line__price")
    price_meter_element = soup.select_one(".price-line__price-meter")
    metro_element = soup.select_one(".base__metro-list")
    location = extract_location(soup, current_url)
    specs = extract_specs(soup)
    record: dict[str, Any] = {
        "id": listing_id,
        "city": location["city"],
        "price": parse_number(price_element.get_text(" ", strip=True) if price_element else None),
        "price_per_m2": parse_number(
            price_meter_element.get_text(" ", strip=True) if price_meter_element else None
        ),
        "rooms": specs["rooms"],
        "area_total": specs["area_total"],
        "area_living": specs["area_living"],
        "area_kitchen": specs["area_kitchen"],
        "floor": specs["floor"],
        "floors_total": specs["floors_total"],
        "metro": clean_metro(
            metro_element.get_text(" ", strip=True) if metro_element else location["metro"]
        ),
        "okrug": location["okrug"],
        "district": location["district"],
        "published_at": extract_published_at(soup),
        "is_secondary": is_secondary(meta_text),
        "is_apartment": is_apartment(meta_text),
        "is_moscow": is_moscow(soup, current_url, meta_text),
    }
    return record


def rejection_reason(record: dict[str, Any], max_price: int = MAX_PRICE) -> str | None:
    """Return the name of the first failed filter, or None when the record passes."""
    if not record.get("is_secondary"):
        return "not_secondary"
    if not record.get("is_apartment"):
        return "not_apartment"
    if not record.get("is_moscow"):
        return "not_moscow"
    price = record.get("price")
    if price is None:
        return "no_price"
    if float(price) > max_price:
        return "price_above_limit"
    return None


def passes_filters(record: dict[str, Any], max_price: int = MAX_PRICE) -> bool:
    """Apply the project-wide secondary, apartment, Moscow, and price filters."""
    return rejection_reason(record, max_price) is None


def make_session() -> requests.Session:
    """Create a browser-like session for public detail requests."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
        }
    )
    return session


def read_ids(input_path: Path) -> list[int]:
    """Read numeric IDs from the local collection output."""
    if not input_path.exists():
        LOGGER.warning("ID file does not exist: %s", input_path)
        return []
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("ids", payload.get("records", []))
    ids: list[int] = []
    for item in payload:
        raw_id = item.get("id") if isinstance(item, dict) else item
        if isinstance(raw_id, bool):
            continue
        try:
            listing_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if listing_id > 0:
            ids.append(listing_id)
    return list(dict.fromkeys(ids))


def fetch_detail(
    session: requests.Session,
    limiter: RateLimiter,
    listing_id: int,
) -> dict[str, Any] | None:
    """Fetch and parse one canonical www detail page."""
    current_url = f"{BASE_URL}/base/{listing_id}.html"
    limiter.wait()
    try:
        response = session.get(current_url, timeout=30)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = response.apparent_encoding
        return parse_detail(response.text, current_url, listing_id)
    except requests.RequestException as exc:
        LOGGER.warning("Detail request failed for ID %d: %s", listing_id, exc)
        return None


def anonymize_records(
    records: list[dict[str, Any]],
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Create a random sample without IDs, listing links, addresses, or contacts."""
    if not records:
        return []
    rng = random.Random(seed)
    selected = records if len(records) < sample_size else rng.sample(records, sample_size)
    allowed_fields = (
        "city",
        "price",
        "price_per_m2",
        "rooms",
        "area_total",
        "area_living",
        "area_kitchen",
        "floor",
        "floors_total",
        "metro",
        "okrug",
        "district",
        "published_at",
    )
    result: list[dict[str, Any]] = []
    for index, record in enumerate(selected, start=1):
        item = {"sample_index": index}
        for field in allowed_fields:
            value = record.get(field)
            item[field] = value if value not in ("", None) else None
        result.append(item)
    return result


def load_existing_sample(path: Path) -> list[dict[str, Any]]:
    """Load the committed sample when a live run has too few records."""
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def write_json(payload: Any, output_path: Path) -> None:
    """Write UTF-8 JSON with stable indentation."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line options for detail parsing."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-output", type=Path, default=DEFAULT_SAMPLE_OUTPUT)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--max-listings", type=int, default=None)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    """Run detail parsing and refresh the local anonymized sample."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    ids = read_ids(args.input)
    if args.max_listings is not None:
        ids = ids[: max(0, args.max_listings)]
    session = make_session()
    limiter = RateLimiter(args.delay)
    records: list[dict[str, Any]] = []
    rejections: Counter[str] = Counter()
    for index, listing_id in enumerate(ids, start=1):
        LOGGER.info("Parsing %d/%d", index, len(ids))
        record = fetch_detail(session, limiter, listing_id)
        if record is None:
            rejections["request_failed"] += 1
            continue
        reason = rejection_reason(record)
        if reason is None:
            records.append(record)
        else:
            rejections[reason] += 1

    write_json(records, args.output)
    existing_sample = load_existing_sample(args.sample_output)
    if len(records) >= args.sample_size:
        sample = anonymize_records(records, args.sample_size, args.seed)
    elif len(existing_sample) >= args.sample_size:
        sample = existing_sample
    else:
        sample = anonymize_records(records, args.sample_size, args.seed)
    write_json(sample, args.sample_output)
    LOGGER.info("Saved %d listings and %d sample rows", len(records), len(sample))
    if rejections:
        LOGGER.info("Rejected: %s", ", ".join(f"{k}={v}" for k, v in rejections.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
