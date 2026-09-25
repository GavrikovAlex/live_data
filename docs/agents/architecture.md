# Архитектура репозитория

## Поток данных

Источник → scraper/parse.py → data/raw.json
data/raw.json → src/transform.py → data/clean.json
data/clean.json → src/build_dashboard.py → dashboard.html
dashboard.html → GitHub Actions → GitHub Pages

## Слои

- scraper/ — только сбор. Не знает о визуализации.
- src/transform.py — только очистка.
- src/build_dashboard.py — только визуализация.
- .github/workflows/ — запуск по cron.

## Почему так

Разделение слоёв позволяет менять источник данных без переписывания дашборда, тестировать парсер отдельно и запускать нужный этап при отладке.
