# Разработка и эксплуатация SongForge

> Внутренний документ. Не подключать к AI-помощнику на сайте.

---

## Статус документа

Полное содержание — по плану в `docs/DOCUMENTATION_PLAN.md`.

### Быстрые ссылки

| Задача | Где смотреть |
|--------|----------------|
| Деплой на VPS | `COMMANDS.txt`, `scripts/update-now.sh` |
| Архитектура | `docs/ARCHITECTURE.md` |
| ApiPass / Suno | `docs/APIPASS_API.md` |
| Переменные окружения | `.env.example` |
| Smoke-тесты | `pytest tests/test_smoke.py` |
| Backlog | `docs/NOTES_NEXT.md`, `SONGFORGE-КОНТЕКСТ.txt` |

### Сервер (текущий)

- VPS: `195.19.20.245`, порт `8000`
- Процесс: **PM2** (`pm2 restart songforge`), не systemd
- Health: `GET /api/health` → `version`

---

_Собрать единый пошаговый гайд «перенос на новый сервер» — в следующих итерациях._