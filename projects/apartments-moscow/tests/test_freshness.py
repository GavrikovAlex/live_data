"""Offline tests for the data freshness report."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from src import freshness


SAMPLE = [
    {"published_at": "2026-09-20"},
    {"published_at": "2026-09-25"},
]


class FreshnessTests(unittest.TestCase):
    """Cover snapshot date resolution and the staleness report."""

    def setUp(self) -> None:
        """Create a temporary sample file for each test."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.sample = self.tmp / "sample.json"
        self.sample.write_text(json.dumps(SAMPLE), encoding="utf-8")

    def test_age_days_counts_whole_days(self) -> None:
        self.assertEqual(freshness.age_days("2026-09-25", date(2026, 10, 1)), 6)

    def test_age_days_handles_missing_value(self) -> None:
        self.assertIsNone(freshness.age_days(None))
        self.assertIsNone(freshness.age_days("not-a-date"))

    def test_data_as_of_prefers_git_commit_date(self) -> None:
        with mock.patch.object(freshness, "_git_commit_date", return_value="2026-09-24"):
            self.assertEqual(freshness.data_as_of(self.sample), "2026-09-24")

    def test_data_as_of_falls_back_to_newest_row(self) -> None:
        with mock.patch.object(freshness, "_git_commit_date", return_value=None):
            self.assertEqual(freshness.data_as_of(self.sample), "2026-09-25")

    def test_describe_marks_old_sample_as_stale(self) -> None:
        with mock.patch.object(freshness, "data_as_of", return_value="2026-01-01"):
            report = freshness.describe(self.sample, max_age_days=7)
        self.assertIn("status=stale", report)
        self.assertIn("data_as_of=2026-01-01", report)

    def test_describe_marks_recent_sample_as_fresh(self) -> None:
        with mock.patch.object(freshness, "data_as_of", return_value="2026-09-25"):
            report = freshness.describe(self.sample, max_age_days=7)
        self.assertIn("status=fresh", report)


if __name__ == "__main__":
    unittest.main()
