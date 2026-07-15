# SongForge (СоздайСвоюПесню)

AI-платформа для создания песен: Suno через ApiPass, тексты через YandexGPT.

**Текущая версия:** 2.11.30

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

**Команды сервера** — один файл в корне: `COMMANDS.txt` (латиница, копировать по строке).

**Пошаговые инструкции** — папка `docs/instrukcii/` (оглавление: `INDEX.txt`).

После обновления:

```bash
curl http://127.0.0.1:8000/api/health
```

## Документация проекта

| Файл | Назначение |
|------|------------|
| `COMMANDS.txt` | Команды SSH/деплой/pm2 (латиница) |
| `docs/instrukcii/INDEX.txt` | Оглавление всех инструкций |
| `SONGFORGE-КОНТЕКСТ.txt` | Статус, планы, тексты UI |
| `docs/NOTES_NEXT.md` | Технический backlog |
| `docs/ARCHITECTURE.md` | Архитектура |
| `AGENTS.md` | Правила для ассистента Cursor |

## Структура

```
SongForge/
  COMMANDS.txt           ← команды сервера
  SONGFORGE-КОНТЕКСТ.txt
  backend/               ← API
  index.html             ← фронт
  scripts/               ← деплой, утилиты
  docs/
    instrukcii/          ← инструкции (.txt)
    biznes/              ← PDF, docx
    NOTES_NEXT.md
```
