# live_data

AI-агентные исследования на живых данных.
Проекты на живых данных с автообновлением через GitHub Actions: парсер + дашборд + автоматический деплой.

## Проекты

### [Аналитика квартир Москвы](./projects/apartments-moscow/)

Аналитика вторичного рынка квартир Москвы по открытым страницам Restate: 11 округов, 1–3-комнатные
квартиры, фильтры и относительный score выгодности в браузере.

- [Открыть дашборд](https://GavrikovAlex.github.io/live_data/projects/apartments-moscow/dashboard.html)
- [Открыть исходники проекта](./projects/apartments-moscow/)
- **Источник:** [restate.ru](https://www.restate.ru)
- **Обновление:** раз в день через GitHub Actions

## Как это устроено

Каждый проект живёт в `projects/<название>/`:
- `scraper/` — сбор данных
- `data/` — локальные JSON-файлы и обезличенный sample
- `src/` — обработка и сборка дашборда
- `dashboard.html` — итоговый файл для GitHub Pages

GitHub Actions запускает парсер по расписанию, обновляет данные и коммитит свежий дашборд обратно в репозиторий.

## Стек

Python 3.11 · pandas · Plotly · GitHub Actions · GitHub Pages

## Лицензия

MIT
