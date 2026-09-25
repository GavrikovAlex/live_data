"""Calculate apartment market metrics and value scores."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _mean(series: pd.Series) -> float | None:
    """Return a JSON-safe mean for a numeric series."""
    value = pd.to_numeric(series, errors="coerce").mean()
    return None if pd.isna(value) else float(value)


def _median(series: pd.Series) -> float | None:
    """Return a JSON-safe median for a numeric series."""
    value = pd.to_numeric(series, errors="coerce").median()
    return None if pd.isna(value) else float(value)


def add_value_score(frame: pd.DataFrame) -> pd.DataFrame:
    """Add a metro-relative value score in percent to the DataFrame."""
    result = frame.copy()
    if result.empty or "price_per_m2" not in result:
        result["value_score"] = pd.Series(dtype="float64")
        return result
    result["price_per_m2"] = pd.to_numeric(result["price_per_m2"], errors="coerce")
    reference = result.groupby("metro", dropna=False)["price_per_m2"].transform("mean")
    overall_reference = result["price_per_m2"].mean()
    reference = reference.fillna(overall_reference)
    result["value_score"] = ((reference - result["price_per_m2"]) / reference) * 100
    result.loc[result["value_score"].abs() < 0.005, "value_score"] = 0.0
    return result


def calculate_metrics(frame: pd.DataFrame) -> dict[str, float | int | None]:
    """Calculate the six headline cards used by the dashboard."""
    if frame.empty:
        return {
            "count": 0,
            "avg_price": None,
            "median_price": None,
            "avg_floor": None,
            "avg_area": None,
            "avg_price_per_m2": None,
        }
    return {
        "count": int(len(frame)),
        "avg_price": _mean(frame["price"]),
        "median_price": _median(frame["price"]),
        "avg_floor": _mean(frame["floor"]),
        "avg_area": _mean(frame["area_total"]),
        "avg_price_per_m2": _mean(frame["price_per_m2"]),
    }


def _top_metro(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Aggregate the ten most expensive metro stations by average price."""
    if frame.empty:
        return []
    grouped = (
        frame.assign(metro=frame["metro"].fillna("Не указан"))
        .groupby("metro", as_index=False)
        .agg(avg_price=("price", "mean"), count=("price", "size"))
        .sort_values(["avg_price", "metro"], ascending=[False, True])
        .head(10)
    )
    return [
        {
            "metro": str(row.metro),
            "avg_price": float(row.avg_price),
            "count": int(row.count),
        }
        for row in grouped.itertuples()
    ]


def _monthly_prices(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Aggregate average prices by publication month."""
    if frame.empty or "published_at" not in frame:
        return []
    dates = pd.to_datetime(frame["published_at"], errors="coerce")
    working = frame.assign(month=dates.dt.strftime("%Y-%m"))
    grouped = (
        working.dropna(subset=["month"])
        .groupby("month", as_index=False)
        .agg(avg_price=("price", "mean"), count=("price", "size"))
        .sort_values("month")
    )
    return [
        {"month": str(row.month), "avg_price": float(row.avg_price), "count": int(row.count)}
        for row in grouped.itertuples()
    ]


def _room_distribution(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Aggregate listing counts by room count."""
    if frame.empty or "rooms" not in frame:
        return []
    rooms = pd.to_numeric(frame["rooms"], errors="coerce")
    counts = rooms.dropna().astype(int).value_counts().sort_index()
    return [{"rooms": int(room), "count": int(count)} for room, count in counts.items()]


def prepare_dashboard_data(frame: pd.DataFrame) -> dict[str, Any]:
    """Prepare headline metrics, scores, and chart-ready aggregates."""
    scored = add_value_score(frame)
    return {
        "metrics": calculate_metrics(scored),
        "top_metro": _top_metro(scored),
        "monthly": _monthly_prices(scored),
        "rooms": _room_distribution(scored),
    }
