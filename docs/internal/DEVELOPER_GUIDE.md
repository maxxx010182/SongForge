# SongForge — разработка, деплой, новый сервер

> Внутренний документ. **Не** подключать к AI-помощнику на сайте.  
> Версия продукта: **2.11.30**  
> Дата: 15.07.2026

---

## 1. Стек и репозиторий

| | |
|--|--|
| Backend | Python 3.11+, FastAPI, Uvicorn, SQLite |
| Frontend | `index.html` (+ `admin.html`) |
| Музыка | ApiPass / sunoapi.org (Suno V5.5) |
| Тексты | YandexGPT |
| Очередь | Redis + worker (опционально) |
| Оплата | GetPlatinum |
| Репо | GitHub `maxxx010182/SongForge`, ветка `main` |

Рабочая папка на проде: `~/SongForge` (VPS `195.19.20.245`).

---

## 2. Локальный запуск

```bash
git clone <repo> SongForge
cd SongForge
python -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполнить ключи
python app.py
```

- Сайт: http://127.0.0.1:8000/  
- Health: `/api/health` → `"version":"2.11.30"`  
- Тесты: `pytest tests/ -q`

**Важно:** `data/`, `.env` — не в git. Версия в `backend/app.py` = истина.

---

## 3. Обновление прода (обычный путь)

Владелец копирует из **`COMMANDS.txt`** (корень, латиница):

```text
ssh root@195.19.20.245
cd ~/SongForge
curl -fsSL "https://raw.githubusercontent.com/maxxx010182/SongForge/main/scripts/update-now.sh?$(date +%s)" | bash
curl -s https://sozdaipesnu.ru/api/health
```

Ожидание: `=== Готово! vX.Y.Z ===` и health с той же версией.

Если update-now падает → `docs/instrukcii/DEPLOY-SEYCHAS.txt`.

Правило разработки: **правки локально → commit → push → на сервере только update-now**.

---

## 4. Новый сервер с нуля

Полный чеклист: **`docs/instrukcii/FULL-DEPLOY-FROM-SCRATCH.txt`**.

Кратко:

1. Ubuntu/Debian VPS, SSH, firewall (22, 80, 443).  
2. Python 3.11+, nginx, certbot, redis, sqlite3, pm2 (node).  
3. Клон репо → venv → `.env` из `.env.example`.  
4. `data/songforge.db` создаётся при старте.  
5. nginx → proxy на `127.0.0.1:8000`, `X-Real-IP $remote_addr`.  
6. pm2: web + worker.  
7. DNS A на IP, HTTPS.  
8. `SITE_URL=https://домен`, ключи GP/SMTP/Suno/Yandex.  
9. Webhook GP: `https://домен/api/payment/webhook/getplatinum`.  
10. Cron: `backup-db.sh`, `health-watch.sh`.  
11. Smoke: health, вход, песня, оплата.

---

## 5. `.env` (критичное)

См. `.env.example`. Минимум прода:

| Переменная | |
|------------|--|
| `SITE_URL` | https://sozdaipesnu.ru |
| `YANDEX_API_KEY`, `YANDEX_FOLDER_ID` | тексты |
| `APIPASS_API_KEY` и/или `SUNOAPI_ORG_API_KEY` | музыка |
| `MUSIC_PROVIDER` | `fallback_suno` / `apipass` / … |
| `PAYMENT_PROVIDER=getplatinum` | |
| `GETPLATINUM_*` | account, key, prefix, vat |
| `SMTP_*` | email-вход |
| `ADMIN_BOOTSTRAP_EMAILS` | админка |
| `AUTH_DEV_CODE_ENABLED=false` | прод |
| `REDIS_*` | очередь |

Бета-лимиты (defaults в `settings.py`): concurrent 6/2, trial 8 IP/day.

После смены `.env`: `pm2 restart songforge --update-env` (и worker).

---

## 6. Администрирование (ежедневно / еженедельно)

| Задача | Как |
|--------|-----|
| Версия | `curl -s https://sozdaipesnu.ru/api/health` |
| Процессы | `pm2 status` |
| Логи | `pm2 logs songforge --lines 80 --nostream` |
| Ноты не пришли | `docs/instrukcii/GETPLATINUM-NOTY-RUNBOOK.txt` |
| Бэкап БД | `scripts/backup-db.sh` (+ cron) |
| Health-watch | `scripts/health-watch.sh` (+ cron) |
| Диск | `df -h` — свободно > 1,5 ГБ |
| Credits Suno | ЛК sunoapi / ApiPass |
| Админка | `/admin` — см. `ADMIN_GUIDE.md` |

---

## 7. Структура кода (куда смотреть)

```
backend/app.py              # API, версия
backend/services/           # payment, music, lyrics, quota, rate_limit, beta_guards
backend/settings.py         # env
index.html                  # UI
scripts/update-now.sh       # деплой
scripts/backup-db.sh
COMMANDS.txt                # команды для владельца
SONGFORGE-КОНТЕКСТ.txt      # handoff ассистенту
docs/NOTES_NEXT.md          # backlog
```

---

## 8. Версионирование

Каждый значимый релиз:

1. `backend/app.py` (FastAPI version + health)  
2. `scripts/deploy-vps.sh`, `deploy-local.sh`  
3. `README.md`, `COMMANDS.txt`, `SONGFORGE-КОНТЕКСТ` блок СЕЙЧАС, `AGENTS.md`  
4. commit + push → update-now  

---

## 9. Связанные инструкции

| Файл | |
|------|--|
| `docs/instrukcii/INDEX.txt` | оглавление |
| `docs/instrukcii/FULL-DEPLOY-FROM-SCRATCH.txt` | новый VPS |
| `docs/instrukcii/GETPLATINUM-NOTY-RUNBOOK.txt` | оплата/ноты |
| `docs/instrukcii/SMTP-DIAGNOSTIKA.txt` | почта |
| `docs/instrukcii/VK-ENV-SEYCHAS.txt` | VK |
| `docs/biznes/ЭКОНОМИКА.txt` | деньги, промо |
| `docs/internal/ADMIN_GUIDE.md` | админка |
| `docs/public/USER_GUIDE.md` | пользователи |
