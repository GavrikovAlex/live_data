"""Clean and normalize apartment listing records for analysis."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE = PROJECT_ROOT / "data" / "sample.json"
DEFAULT_LISTINGS = PROJECT_ROOT / "data" / "listings.json"
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


def parse_number(value: Any) -> float | None:
    """Convert localized numeric text to a float."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).replace("\xa0", " ")
    multiplier = 1_000_000 if "млн" in text.casefold() else 1
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    match = NUMBER_RE.search(text)
    if match is None:
        return None
    try:
        return float(match.group(0).replace(",", ".")) * multiplier
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    """Convert numeric text to an integer."""
    number = parse_number(value)
    return None if number is None else int(round(number))


def load_records(input_path: Path | None = None) -> list[dict[str, Any]]:
    """Load local listings, falling back to the committed anonymized sample."""
    if input_path is None:
        input_path = DEFAULT_LISTINGS if DEFAULT_LISTINGS.exists() else DEFAULT_SAMPLE
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("listings", payload.get("records", []))
    return payload if isinstance(payload, list) else []


def transform_records(
    records: Iterable[dict[str, Any]],
    reference_time: datetime | None = None,
) -> pd.DataFrame:
    """Return a clean DataFrame with numeric prices, areas, floors, and age."""
    rows: list[dict[str, Any]] = []
    reference_time = reference_time or datetime.now(timezone.utc)
    for record in records:
        price = parse_number(record.get("price"))
        area_total = parse_number(record.get("area_total"))
        price_per_m2 = parse_number(record.get("price_per_m2"))
        if price_per_m2 is None and price is not None and area_total:
            price_per_m2 = price / area_total
        published_at = record.get("published_at")
        age_days: int | None = None
        if published_at:
            parsed_date = pd.to_datetime(published_at, errors="coerce")
            if pd.notna(parsed_date):
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.tz_localize("UTC")
                else:
                    parsed_date = parsed_date.tz_convert("UTC")
                age_days = max(0, (reference_time - parsed_date.to_pydatetime()).days)
        rows.append(
            {
                "price": price,
                "price_per_m2": price_per_m2,
                "rooms": parse_int(record.get("rooms")),
                "area_total": area_total,
                "area_living": parse_number(record.get("area_living")),
                "area_kitchen": parse_number(record.get("area_kitchen")),
                "floor": parse_int(record.get("floor")),
                "floors_total": parse_int(record.get("floors_total")),
                "metro": record.get("metro") or "Не указан",
                "okrug": record.get("okrug") or "Не указан",
                "district": record.get("district") or "Не указан",
                "published_at": published_at,
                "listing_age_days": age_days,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
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
                "listing_age_days",
            ]
        )
    numeric_columns = [
        "price",
        "price_per_m2",
        "rooms",
        "area_total",
        "area_living",
        "area_kitchen",
        "floor",
        "floors_total",
        "listing_age_days",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["price", "area_total"]).reset_index(drop=True)


def load_dataframe(input_path: Path | None = None) -> pd.DataFrame:
    """Load and transform a local JSON dataset."""
    return transform_records(load_records(input_path))


def parse_args() -> argparse.Namespace:
    """Parse local transformation options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    """Print a compact local transformation summary."""
    args = parse_args()
    frame = load_dataframe(args.input)
    print(f"rows={len(frame)}")
    if not frame.empty:
        print(f"median_price={frame['price'].median():.0f}")
        print(f"median_price_per_m2={frame['price_per_m2'].median():.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
