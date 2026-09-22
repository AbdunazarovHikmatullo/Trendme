# TrendMe orchestration service

Django-сервис принимает свободный технологический запрос, управляет Celery-конвейером, хранит доказательства в PostgreSQL и передаёт нормализованные кандидаты в ML-сервис. Он не обучает модель и не отображает интерфейс.

## Конвейер

1. `POST /api/searches/` создаёт запуск в статусе `queued`.
2. Celery параллельно получает документы из OpenAlex и arXiv.
3. Каждый документ сохраняется с названием, URL, датой, языком, типом и уровнем доверенности.
4. Callback дедуплицирует совпадающие названия, рассчитывает факторы кандидата и вызывает `ML_SERVICE_URL/predict`.
5. `GET /api/searches/{id}/` возвращает статус, статистику, кандидатов, объяснение модели и источники.

Неуспешный источник не отменяет запуск: он фиксируется в `errors`, а поиск завершается `partial`.

## Локальный запуск

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
USE_SQLITE=1 .venv/bin/python manage.py migrate
USE_SQLITE=1 .venv/bin/python manage.py runserver
```

Для полноценного запуска используйте Docker Compose из корня проекта: PostgreSQL и Redis уже определены там. Переменная `ML_SERVICE_URL` по умолчанию указывает на `http://ml:8001`.

## Пример

```bash
curl -X POST http://localhost/api/searches/ \
  -H 'Content-Type: application/json' \
  -d '{"query":"перспективные решения в финтехе"}'
```

Ответ содержит `id`. Опрос `GET /api/searches/{id}/` выполняется до статуса `completed`, `partial` или `failed`.
