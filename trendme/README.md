# TrendMe orchestration

Django принимает запрос, крутит Celery, пишет источники в PostgreSQL и вызывает изолированный ML. Интерфейс — в `frontend/`. Запуск всего стека и контракт HTTP — в [корневом README](../README.md).

Локально только API + SQLite:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
USE_SQLITE=1 .venv/bin/python manage.py migrate
USE_SQLITE=1 .venv/bin/python manage.py runserver
```

Тесты: `USE_SQLITE=1 python manage.py test pipeline parser`.
