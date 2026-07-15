# SongForge — администрирование

> Внутренний документ. Не для AI-помощника на сайте.  
> Шпаргалка входа: `docs/instrukcii/ADMIN-VHOD.txt`  
> Версия: **2.11.30** (15.07.2026)

---

## 1. Вход в `/admin`

1. На сайте войти email из `ADMIN_BOOTSTRAP_EMAILS` (в `~/SongForge/.env`).  
2. После смены `.env`: `pm2 restart songforge --update-env`.  
3. Открыть **https://sozdaipesnu.ru/admin** (та же сессия браузера).  
4. Опционально: `ADMIN_IP_ALLOWLIST` — только эти IP.

Роли:

| Роль | |
|------|--|
| `super_admin` | всё |
| `support` | пользователи, ±ноты (лимит) |
| `readonly` | просмотр |

---

## 2. Вкладки админки

| Вкладка | Действия |
|---------|----------|
| **Обзор** | Сводка, зависшие генерации (>10 мин), алерты |
| **Генерации** | Список, статус, task_id |
| **Пользователи** | Поиск, **± ноты** (обязательна причина) |
| **Команда** | Роли (super_admin) |
| **Журнал** | Кто что менял |
| **Витрина / showcase** | Персоны, лайки, комментарии (если есть) |

**Начисление нот вручную** — только поддержка (ошибка оплаты, компенсация).  
Не заменяет промокод GetPlatinum для скидок тестерам.

---

## 3. Типовые сценарии

### 3.1. Оплатил — нот нет

1. `docs/instrukcii/GETPLATINUM-NOTY-RUNBOOK.txt`  
2. `COMMANDS.txt` — sqlite order + `mark_paid`  
3. Логи: `pm2 logs songforge | grep -i getplatinum`

### 3.2. Зависшая генерация

```text
cd ~/SongForge
./venv/bin/python scripts/check_task.py last
# при необходимости --fix (осторожно, см. скрипт)
```

Или `scripts/recover_orphan_task.py` по task_id.

### 3.3. Выдать ноты тестеру (без промо)

Админка → Пользователи → ± ноты → причина `бета / компенсация`.  
Учитывайте себестоимость ~12–25 ₽/ноту (см. экономику).

### 3.4. Скидка тестерам (предпочтительно)

Промокод **в ЛК GetPlatinum** → пользователь вводит на **форме GP**.  
Сколько % можно — `docs/biznes/ЭКОНОМИКА.txt` §11 и Excel лист **Промо**.

---

## 4. Еженедельный чеклист

- [ ] `curl -s https://sozdaipesnu.ru/api/health` — version OK  
- [ ] `pm2 status` — songforge + worker online  
- [ ] Credits sunoapi / ApiPass  
- [ ] Yandex Cloud баланс  
- [ ] `df -h` > 1,5 ГБ свободно  
- [ ] Есть свежий бэкап в `~/backups/songforge/`  
- [ ] Зависшие генерации в /admin  

---

## 5. Cron (обязательно на проде)

```text
15 3 * * * /root/SongForge/scripts/backup-db.sh >> /var/log/songforge-backup.log 2>&1
*/5 * * * * /root/SongForge/scripts/health-watch.sh >> /var/log/songforge-health.log 2>&1
```

Ручной бэкап: `cd ~/SongForge && ./scripts/backup-db.sh`

---

## 6. Безопасность

- `AUTH_DEV_CODE_ENABLED=false` на проде  
- Не светить API-ключи в чатах/тикетах  
- Webhook GP: только с verify (checksum / order+IP)  
- Rate limit + concurrent уже в коде (2.11.28+)  

---

## 7. Ссылки

| | |
|--|--|
| Команды | `COMMANDS.txt` |
| Деплой / новый сервер | `docs/internal/DEVELOPER_GUIDE.md`, `FULL-DEPLOY-FROM-SCRATCH.txt` |
| Экономика / промо | `docs/biznes/ЭКОНОМИКА.txt`, `ЭКОНОМИКА.xlsx` |
| Пользователи | `docs/public/USER_GUIDE.md` |
