# TrendMe

Поиск **зарождающихся научно-технологических сигналов** по свободному запросу на русском или английском.

Карточка выдачи — одна недавняя научная работа или препринт с артефактом (прототип, устройство, архитектура), а не обзор поля и не кластер «все статьи про ИИ». Патент и Wikipedia — **факторы**, не единица результата. ML отмечает слабый сигнал и объясняет признаки; сильные/зрелые наблюдения в выдачу не попадают. «Высокая уверенность» — относительный топ текущего прогона (до 25%, не больше 4 карточек), не абсолютный порог 75% логистической регрессии.

Живой стенд: [http://64.188.60.125](http://64.188.60.125)

## Состав

| Сервис | Роль |
|---|---|
| `frontend` | Next.js, клиент к API |
| `backend` | Django 6 + DRF: оркестрация, фильтры, карточки |
| `celery` | Параллельный сбор источников, финализация |
| `ml` | FastAPI + sklearn: `/predict`, без поиска |
| `db` | PostgreSQL 17 |
| `redis` | Брокер Celery |
| `nginx` | Порт 80: UI, `/api/`, `/admin/`, `/ml/` |

Источники ядра: OpenAlex, arXiv, Crossref, Europe PMC. Поддержка: Google Patents (fallback Europe PMC PAT), Wikipedia EN/RU.

Русский запрос сначала идёт через словарь терминов, иначе через Wikipedia langlinks (запасной перевод). arXiv получает только латинский запрос. Неуспех одного источника не валит прогон: статус `partial`, список в `errors`.

## Требования

- Docker и Docker Compose
- Свободный порт 80
- На машине ~2 ГБ RAM нужен swap ~1 ГБ: Next.js-сборка и Celery иначе получают OOM 137. Compose уже ставит gunicorn **1 worker** и Celery `--pool=solo`.

## Запуск

```bash
git clone https://github.com/AbdunazarovHikmatullo/Trendme.git
cd Trendme
cp .env.example .env
docker compose up -d --build
```

Миграции выполняются при старте `backend` (`entrypoint.sh`). UI: `http://localhost`. API: `http://localhost/api/searches/`.

Полезные команды:

```bash
docker compose ps
docker compose logs -f celery backend
docker compose exec backend python manage.py test pipeline parser --verbosity=1
docker compose restart nginx   # после recreate backend, иначе возможен 502 из-за старого DNS
```

Остановка: `docker compose down`. Данные Postgres в volume `postgres_data`.

### Переменные (`.env`)

См. `.env.example`. Для своего домена добавьте хост в `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`.

`ML_SERVICE_URL` внутри сети Compose по умолчанию `http://ml:8001`.

### Только backend без UI (разработка)

```bash
cd trendme
python -m venv .venv
.venv/bin/pip install -r requirements.txt
USE_SQLITE=1 .venv/bin/python manage.py migrate
USE_SQLITE=1 .venv/bin/python manage.py runserver
```

Нужны Redis, Celery worker и ML (`cd ML && uvicorn main:app --port 8001`), иначе поиск не завершится. Для полного контура используйте Compose.

ML отдельно: `GET http://localhost/ml/health`, OpenAPI `GET http://localhost/ml/docs`.

## Публичный API

Префикс `/api/` проксируется на Django. Тело JSON, кодировка UTF-8.

### `POST /api/searches/`

Создаёт прогон и ставит Celery-задачу. Ответ **202**.

| Поле | Тип | |
|---|---|---|
| `query` | string | 2–300 символов, RU или EN |
| `industry` | string, необязательно | фильтр отрасли кандидатов |

Значения `industry`: `industrial_ai`, `robotics`, `infrastructure`, `fintech`, `ai_security`, `edge`, `semiconductor`, `energy`, `health`, `other`.

```bash
curl -sS -X POST http://localhost/api/searches/ \
  -H "Content-Type: application/json" \
  -d '{"query":"нейроморфные процессоры"}'
```

```json
{
  "id": "uuid",
  "query": "нейроморфные процессоры",
  "industry_filter": "",
  "status": "queued",
  "processed_sources": 0,
  "candidates_count": 0,
  "weak_signals_count": 0,
  "high_confidence_count": 0,
  "errors": [],
  "created_at": "...",
  "started_at": null,
  "completed_at": null,
  "candidates": []
}
```

Опрашивайте `GET` до терминального статуса.

### `GET /api/searches/{id}/`

Статус прогона и карточки.

| `status` | |
|---|---|
| `queued` | создан |
| `fetching` | сбор источников |
| `analyzing` | фильтры и ML |
| `completed` | готово, `errors` пуст |
| `partial` | готово, часть источников недоступна |
| `failed` | конвейер упал |

Необязательный query-параметр `?category=<industry>` оставляет в `candidates` только эту отрасль.

Карточка кандидата: `id`, `title`, `description`, `potential_benefit`, `case_example`, `confidence`, `is_weak_signal`, `is_high_confidence`, `explanation`, `factors[]`, `industry`, `industry_label`, `sources[]`.

Источник: `title`, `url`, `provider`, `source_name`, `source_type` (`academic` / `preprint` / `patent` / `encyclopedia`), `role` (`core` / `patent` / `encyclopedia`), `published_date`, `language`, `trust`, `trust_level`.

```bash
curl -sS "http://localhost/api/searches/<uuid>/"
```

Типичное ожидание: 30–90 с на прогон (шесть внешних API + ML).

### `GET /api/searches/`

Последние 20 прогонов, новые сверху. `?category=<industry>` — только прогоны, у которых есть кандидат этой отрасли.

### Пример сессии

```bash
curl -sS -X POST http://localhost/api/searches/ \
  -H "Content-Type: application/json" \
  -d '{"query":"artificial intelligence"}'
```

В ответе возьмите `id` и опрашивайте, пока `status` не станет `completed`, `partial` или `failed` (обычно 30–90 с):

```bash
curl -sS http://localhost/api/searches/<id>/
```

### Ошибки API

- `400` — невалидный `query` / `industry`
- `404` — нет прогона с таким id
- в `errors[]` строки вида `wikipedia: HTTP Error 429…`, `openalex: …`, `ML: …`, `no_projects_after_filters: sources=N relevant=… core=…`

## ML (внутренний)

Клиенту ходить в ML не нужно. Через nginx: `GET /ml/health`, `GET /ml/docs`, `POST /ml/predict`. Обучение: `POST /ml/train` и `python train.py` в каталоге `ML/` — см. [ML/README.md](ML/README.md).

## Тесты

```bash
docker compose exec backend python manage.py test pipeline parser
docker compose exec ml python -m unittest discover -s tests -v
```

## Выкладка на сервер

1. Закоммитить и `git push origin main`
2. На сервере: `git pull` → `docker compose up -d --build` нужных сервисов
3. После recreate `backend` — `docker compose restart nginx`

Сборку `frontend` лучше не совмещать с тяжёлым пайплайном на 2 ГБ RAM.

## Каталоги

```
frontend/   UI
trendme/    Django, Celery, парсеры
ML/         классификатор слабого сигнала
nginx/      reverse proxy
```
