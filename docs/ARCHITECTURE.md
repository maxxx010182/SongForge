\# ARCHITECTURE.md



\# SongForge Architecture



Версия: 1.0



\---



\# Общая идея



SongForge — это AI-платформа для создания музыки через Suno V5.5.



Основная задача проекта — не просто отправлять запросы в Suno, а автоматически превращать идеи пользователя в профессиональные музыкальные композиции.



SongForge является интеллектуальной надстройкой над API Suno (через APIPass).



\---



\# Общая схема



```text

Пользователь



↓



Frontend



↓



Prompt Builder



↓



AI Prompt Optimizer



↓



APIPass API



↓



Suno V5.5



↓



SongForge Player



↓



Пользователь

```



\---



\# Архитектура проекта



```text

SongForge/



app.py



index.html



requirements.txt



.env



PROJECT\_CONTEXT.md



DEVELOPER\_RULES.md



TODO.md



CHANGELOG.md



ARCHITECTURE.md



APIPASS\_API.md



SUNO\_PROMPT\_GUIDE.md

```



\---



\# Будущая структура



```text

SongForge/



backend/



frontend/



prompts/



history/



templates/



static/



config/



logs/



docs/

```



\---



\# Backend



Основной язык



Python



Framework



FastAPI



Server



Uvicorn



\---



\# Основные модули



\## app.py



Главный сервер проекта.



Отвечает за:



\* API

\* генерацию

\* получение статуса

\* выдачу результата



\---



\## prompt\_builder.py



Создание профессионального Prompt.



Получает пользовательский текст.



Возвращает готовый Prompt для Suno.



\---



\## ai\_optimizer.py



Использует LLM для улучшения Prompt.



Получает:



идею пользователя



↓



создаёт профессиональный Prompt



↓



возвращает результат.



\---



\## suno\_api.py



Полностью инкапсулирует работу с APIPass.



Внутри находятся



createTask()



recordInfo()



download()



\---



\## history.py



Работа с историей генераций.



\---



\## settings.py



Все настройки проекта.



\---



\## logger.py



Логирование.



\---



\# Frontend



Главный файл



index.html



\---



Будущая структура



```text

frontend/



index.html



style.css



app.js



player.js



wizard.js



history.js

```



\---



\# Prompt Pipeline



Пользователь



↓



Идея



↓



Prompt Builder



↓



AI Optimizer



↓



Style Generator



↓



Negative Tags Generator



↓



Title Generator



↓



APIPass



↓



Suno



\---



\# Prompt Builder



Отвечает за



жанр



↓



поджанр



↓



темп



↓



энергию



↓



голос



↓



инструменты



↓



стиль



↓



референсы



↓



Negative Tags



↓



финальный Prompt



\---



\# Music Wizard



Будущий модуль.



Работает пошагово.



Вместо написания Prompt пользователь отвечает на вопросы.



После каждого ответа SongForge постепенно строит идеальный Prompt.



\---



\# AI Prompt Optimizer



Отдельный интеллект.



Его задача —



улучшить пользовательскую идею.



Например



Пользователь



```text

Хочу красивую песню про космос.

```



↓



SongForge



↓



создаёт профессиональный Prompt



↓



отправляет в Suno.



\---



\# Player



Будущий функционал



✔ красивый аудиоплеер



✔ waveform



✔ скачать MP3



✔ скачать обложку



✔ повтор



✔ громкость



✔ очередь



\---



\# История



Каждая генерация должна сохранять



TaskID



Дата



Prompt



Style



Title



Model



Audio



Cover



Duration



Статус



\---



\# Настройки пользователя



Будущие настройки



Тема



Язык



Версия Suno



Любимый жанр



Любимый голос



Любимый стиль



Настройки Prompt Builder



\---



\# Масштабируемость



Архитектура должна позволять без переписывания проекта добавить:



новые модели



новые API



новые AI



новые генераторы



новые режимы



\---



\# Главный принцип



Любая новая функция должна быть отдельным модулем.



Минимум зависимости.



Максимум читаемости.



Максимум повторного использования.



\---



\# Цель архитектуры



SongForge должен постепенно превратиться из клиента Suno в полноценную интеллектуальную музыкальную платформу, где пользователь взаимодействует не с API, а с AI-помощником, который самостоятельно принимает технические решения и обеспечивает максимально качественный результат.



