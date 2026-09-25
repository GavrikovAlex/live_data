"""Report how old the committed anonymized sample is.

The snapshot date is the commit date of ``data/sample.json``, because the sample
itself must stay a plain list of rows without any metadata field. Git is the
authoritative source; the newest ``published_at`` and the file mtime are used as
fallbacks when the file is used outside a git checkout.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE = PROJECT_ROOT / "data" / "sample.json"
DEFAULT_MAX_AGE_DAYS = 7


def _git_commit_date(sample_path: Path) -> str | None:
    """Return the commit date of the sample file as an ISO date."""
    try:
        completed = subprocess.run(
            [
                "git",
                "log",
                "-1",
                "--format=%cI",
                "--",
                str(sample_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    raw = completed.stdout.strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).astimezone(timezone.utc).date().isoformat()
    except ValueError:
        return None


def _newest_published_at(rows: list[dict[str, Any]]) -> str | None:
    """Return the newest publication date found in the sample rows."""
    dates = sorted(str(row["published_at"]) for row in rows if row.get("published_at"))
    return dates[-1] if dates else None


def data_as_of(sample_path: Path = DEFAULT_SAMPLE) -> str | None:
    """Resolve the snapshot date from git, then row dates, then the file mtime."""
    if not sample_path.exists():
        return None
    commit_date = _git_commit_date(sample_path)
    if commit_date is not None:
        return commit_date
    try:
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = []
    if isinstance(payload, list):
        published = _newest_published_at(payload)
        if published is not None:
            return published[:10]
    mtime = datetime.fromtimestamp(sample_path.stat().st_mtime, tz=timezone.utc)
    return mtime.date().isoformat()


def age_days(as_of: str | None, today: date | None = None) -> int | None:
    """Return how many days passed since the snapshot date."""
    if not as_of:
        return None
    try:
        snapshot = date.fromisoformat(as_of)
    except ValueError:
        return None
    return ((today or datetime.now(timezone.utc).date()) - snapshot).days


def describe(sample_path: Path = DEFAULT_SAMPLE, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> str:
    """Return a one-line human-readable freshness report."""
    as_of = data_as_of(sample_path)
    days = age_days(as_of)
    if as_of is None or days is None:
        return "data_as_of=unknown age=unknown status=unknown"
    status = "fresh" if days <= max_age_days else "stale"
    return f"data_as_of={as_of} age_days={days} max_age_days={max_age_days} status={status}"


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the freshness report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument(
        "--github-output",
        type=Path,
        default=None,
        help="append data_as_of and age_days to this GITHUB_OUTPUT file",
    )
    parser.add_argument(
        "--fail-if-stale",
        action="store_true",
        help="exit with code 1 when the snapshot is older than the limit",
    )
    return parser.parse_args()


def main() -> int:
    """Print the freshness report and optionally export it to GitHub Actions."""
    args = parse_args()
    as_of = data_as_of(args.sample)
    days = age_days(as_of)
    report = describe(args.sample, args.max_age_days)
    print(report)

    if args.github_output is not None:
        lines = [
            f"data_as_of={as_of or ''}",
            f"data_age_days={'' if days is None else days}",
        ]
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    if days is None:
        print("WARNING: could not determine the snapshot date")
        return 1 if args.fail_if_stale else 0
    if days > args.max_age_days:
        print(
            f"WARNING: sample is {days} days old (limit {args.max_age_days}). "
            "Refresh it manually: python scraper/collect_ids.py && "
            "python scraper/parse_detail.py && python src/build_dashboard.py"
        )
        return 1 if args.fail_if_stale else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
