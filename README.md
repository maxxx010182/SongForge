# SongForge (СоздайСвоюПесню)

AI-платформа для создания песен: Suno через ApiPass, тексты через YandexGPT.

**Текущая версия:** 2.5.0

## Стек

- **Backend:** Python, FastAPI, Uvicorn, SQLite
- **Frontend:** `index.html` (одностраничное приложение)
- **Музыка:** ApiPass / Suno V5.5
- **Тексты:** YandexGPT

## Быстрый старт (локально)

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux

pip install -r requirements.txt
copy .env.example .env         # заполните APIPASS_API_KEY и YANDEX_API_KEY
python app.py
```

Сайт: http://127.0.0.1:8000/  
API-документация: http://127.0.0.1:8000/docs

## Деплой на VPS

Команды — в `DEPLOY-NOW.txt` (или ярлык **ОТКРЫТЬ-ДЕПЛОЙ** на рабочем столе).

После обновления проверьте:

```bash
curl http://127.0.0.1:8000/api/health
```

## Документация проекта

| Файл | Назначение |
|------|------------|
| `SONGFORGE-КОНТЕКСТ.txt` | Статус, планы, тексты UI |
| `docs/NOTES_NEXT.md` | Технический backlog |
| `docs/ARCHITECTURE.md` | Архитектура |
| `docs/TODO.md` | Долгосрочный roadmap |
| `COMMANDS.txt` | Команды сервера (латиница) |

## Структура

```
backend/
  app.py              # API (эндпоинты)
  settings.py         # переменные окружения
  models.py           # Pydantic-схемы
  services/           # бизнес-логика
  database/           # SQLite
index.html            # UI
scripts/              # деплой, диагностика
data/                 # БД и загрузки (не в git)
```

## Тесты (smoke)

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Переменные окружения

Шаблон: `.env.example`