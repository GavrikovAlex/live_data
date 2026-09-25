"""Offline tests for the public listing parsers and filters."""

from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from scraper.collect_ids import (
    collect_ids,
    extract_last_page,
    extract_listing_ids,
    interleave_records,
    page_url,
)
from scraper.parse_detail import (
    anonymize_records,
    parse_detail,
    parse_number,
    passes_filters,
    rejection_reason,
)


DETAIL_HTML = """
<html>
<head>
  <title>Продажа вторичной 2-комнатной квартиры в Москве</title>
  <meta name="description" content="Вторичная квартира в Москве, продажа">
</head>
<body>
  <div class="price-line__price">12 500 000 ₽</div>
  <div class="price-line__price-meter">230 627 ₽/м²</div>
  <ul>
    <li class="base-specs__list-item">Комнат: 2</li>
    <li class="base-specs__list-item">Этаж: 3 из 23</li>
  </ul>
  <div class="obj-params__param">Общая площадь: 54,2 м²</div>
  <div class="obj-params__param">Жилая площадь: 31,5 м²</div>
  <div class="obj-params__param">Кухня: 8,4 м²</div>
  <div class="base__metro-list">Кожуховская</div>
  <div class="breadcrumbs">
    <a href="/area/moscow/9/prodazha_odnokomnatnoy_kvartiry">ЮВАО</a>
    <a href="/metro/moscow/47/prodazha_odnokomnatnoy_kvartiry">Метро Кожуховская</a>
  </div>
  <div class="base__ad-params">Опубликовано 5 сентября 2026</div>
  <div class="contact-phone">+7 999 000-00-00</div>
</body>
</html>
"""

MODERN_DETAIL_HTML = """
<html>
<head>
  <title>Продажа 34 кв. м. 1-комнатной квартиры у метро Кожуховская Москва</title>
  <meta name="description" content="Вторичная квартира в Москве у метро Кожуховская">
</head>
<body>
  <div class="price-line__price">17 816 800 Р</div>
  <ul class="base-specs__list">
    <li class="base-specs__list-item"><span>Количество комнат для продажи/аренды</span><span>1</span></li>
    <li class="base-specs__list-item"><span>Этаж</span><span>57</span></li>
    <li class="base-specs__list-item"><span>Площадь жилая</span><span>16.30 кв. м</span></li>
  </ul>
  <ul class="base__obj-params obj-params">
    <li class="obj-params__item"><p class="obj-params__value">34.00 м<sup>2</sup></p><p class="obj-params__label">Общая</p></li>
    <li class="obj-params__item"><p class="obj-params__value">16.30 м<sup>2</sup></p><p class="obj-params__label">Жилая</p></li>
    <li class="obj-params__item"><p class="obj-params__value">10.20 м<sup>2</sup></p><p class="obj-params__label">Кухня</p></li>
    <li class="obj-params__item"><p class="obj-params__value">57 из 69</p><p class="obj-params__label">Этаж</p></li>
  </ul>
  <div class="base__metro-list">Кожуховская (700 м), 10 мин пешком</div>
  <div class="breadcrumbs">
    <a href="/area/moscow/9/prodazha_odnokomnatnoy_kvartiry">ЮВАО</a>
    <a href="/metro/moscow/47/prodazha_odnokomnatnoy_kvartiry">Метро Кожуховская</a>
  </div>
  <div class="base__ad-params">27 с 18.12.2025, обновлён 24.03.2026</div>
</body>
</html>
"""

SPLIT_SPECS_HTML = """
<html>
<head>
  <title>Продажа вторичной 3-комнатной квартиры в Москве</title>
  <meta name="description" content="Вторичная квартира в Москве">
</head>
<body>
  <div class="price-line__price">18 000 000 Р</div>
  <ul>
    <li class="base-specs__list-item"><span>Количество комнат для продажи/аренды</span><span>3</span></li>
    <li class="base-specs__list-item"><span>Этаж</span><span>5</span></li>
    <li class="base-specs__list-item"><span>Этажей всего</span><span>9</span></li>
  </ul>
  <ul class="obj-params">
    <li class="obj-params__item"><p class="obj-params__value">74.00 м<sup>2</sup></p><p class="obj-params__label">Общая</p></li>
  </ul>
  <div class="base__ad-params">Опубликовано 3 марта 2026</div>
</body>
</html>
"""

CATALOG_HTML = """
<div class="search-list__list">
  <div class="sri" data-id="123">
    <a class="sri__slider" href="/base/123.html">one</a>
  </div>
  <div class="sri" data-id="456">
    <a class="sri__common-link" href="/base/456.html">two</a>
  </div>
</div>
<div class="pagination">
  <a href="?o=0&amp;page=1">1</a>
  <a href="?o=0&amp;page=3">3</a>
</div>
"""


class ParserTests(unittest.TestCase):
    def test_parse_detail_extracts_allowed_fields(self) -> None:
        record = parse_detail(DETAIL_HTML, "https://www.restate.ru/base/123.html", 123)
        self.assertEqual(record["price"], 12_500_000)
        self.assertEqual(record["price_per_m2"], 230_627)
        self.assertEqual(record["rooms"], 2)
        self.assertEqual(record["area_total"], 54.2)
        self.assertEqual(record["area_living"], 31.5)
        self.assertEqual(record["area_kitchen"], 8.4)
        self.assertEqual(record["floor"], 3)
        self.assertEqual(record["floors_total"], 23)
        self.assertEqual(record["okrug"], "ЮВАО")
        self.assertEqual(record["metro"], "Кожуховская")
        self.assertEqual(record["published_at"], "2026-09-05")
        self.assertTrue(passes_filters(record))

    def test_parse_detail_supports_current_object_params_layout(self) -> None:
        record = parse_detail(
            MODERN_DETAIL_HTML,
            "https://www.restate.ru/base/1441963412.html",
            1441963412,
        )
        self.assertEqual(record["rooms"], 1)
        self.assertEqual(record["area_total"], 34.0)
        self.assertEqual(record["area_living"], 16.3)
        self.assertEqual(record["area_kitchen"], 10.2)
        self.assertEqual(record["floor"], 57)
        self.assertEqual(record["floors_total"], 69)
        self.assertEqual(record["metro"], "Кожуховская")
        self.assertEqual(record["published_at"], "2026-03-24")
        self.assertTrue(passes_filters(record))

    def test_parse_detail_handles_split_floor_labels(self) -> None:
        record = parse_detail(
            SPLIT_SPECS_HTML,
            "https://www.restate.ru/base/555.html",
            555,
        )
        self.assertEqual(record["rooms"], 3)
        self.assertEqual(record["area_total"], 74.0)
        self.assertEqual(record["floor"], 5)
        self.assertEqual(record["floors_total"], 9)
        self.assertEqual(record["published_at"], "2026-03-03")

    def test_rejection_reason_reports_first_failed_filter(self) -> None:
        record = parse_detail(DETAIL_HTML, "https://www.restate.ru/base/123.html", 123)
        self.assertIsNone(rejection_reason(record))
        self.assertEqual(rejection_reason({**record, "is_secondary": False}), "not_secondary")
        self.assertEqual(rejection_reason({**record, "price": 150_000_000}), "price_above_limit")
        self.assertEqual(rejection_reason({**record, "price": None}), "no_price")

    def test_anonymized_sample_excludes_identifiers(self) -> None:
        record = parse_detail(DETAIL_HTML, "https://www.restate.ru/base/123.html", 123)
        sample = anonymize_records([record], sample_size=1, seed=1)
        self.assertEqual(len(sample), 1)
        self.assertNotIn("id", sample[0])
        self.assertNotIn("url", sample[0])
        self.assertNotIn("contact_phone", sample[0])
        self.assertEqual(sample[0]["sample_index"], 1)

    def test_collect_ids_rejects_hosts_outside_allowlist(self) -> None:
        for url in (
            "https://msk.restate.ru/dist/moscow/176/prodazha_kvuhk_na_vtorichnom_rynke",
            "https://www.restate.ru.evil.example/area/moscow/1/prodazha_kvartir",
            "https://example.com/area/moscow/1/prodazha_kvartir",
        ):
            with self.assertRaises(ValueError):
                collect_ids((url,))

    def test_interleave_keeps_prefix_balanced_and_deduplicates(self) -> None:
        first = [{"id": 1}, {"id": 2}, {"id": 3}]
        second = [{"id": 4}, {"id": 1}]
        merged = interleave_records([first, second])
        self.assertEqual([record["id"] for record in merged], [1, 4, 2, 3])

    def test_number_parser_handles_grouped_rubles(self) -> None:
        self.assertEqual(parse_number("10 000 000 ₽"), 10_000_000)
        self.assertEqual(parse_number("38,5 м²"), 38.5)

    def test_catalog_extraction_and_pagination(self) -> None:
        soup = BeautifulSoup(CATALOG_HTML, "html.parser")
        records = extract_listing_ids(soup, "https://www.restate.ru/area/moscow/9/test")
        self.assertEqual([record["id"] for record in records], [123, 456])
        self.assertEqual(extract_last_page(soup, "https://www.restate.ru/area/moscow/9/test"), 3)
        self.assertEqual(
            page_url("https://www.restate.ru/area/moscow/9/test", 2),
            "https://www.restate.ru/area/moscow/9/test?o=0&page=2",
        )


if __name__ == "__main__":
    unittest.main()
