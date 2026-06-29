# APIPASS_API.md

# APIPASS API Reference

## Назначение

Данный документ содержит только ту часть документации APIPass, которая используется в проекте SongForge.

Используется как основная техническая документация проекта.

---

# Основная модель

```text
Model

suno/generate
```

---

# Endpoint

Создание задачи

```
POST /api/v1/jobs/createTask
```

Получение результата

```
GET /api/v1/jobs/recordInfo
```

---

# Основная идея

SongForge никогда не использует минимальный набор параметров.

Цель проекта —

использовать максимум возможностей Suno V5.5.

---

# Поддерживаемые версии

Приоритет:

1.

V5_5

(основная модель)

2.

V5

3.

V4_5PLUS

4.

V4_5ALL

5.

V4_5

6.

V4

---

# Channel

По умолчанию

```
auto
```

Использовать автоматически.

При необходимости дать пользователю возможность выбрать

* auto
* starter
* standard
* official

---

# Custom Mode

Всегда использовать

```
customMode = true
```

если пользователь не выбрал простой режим.

Это позволяет использовать:

✔ Style

✔ Title

✔ VocalGender

✔ NegativeTags

✔ StyleWeight

✔ WeirdnessConstraint

✔ AudioWeight

---

# Instrumental

Поддерживать два режима

```
true
```

Инструментал

```
false
```

Песня

---

# Prompt

Максимальная длина

5000 символов

Prompt должен генерироваться автоматически AI Prompt Builder.

---

# Style

Обязательно использовать.

Style должен состоять из:

жанра

настроения

темпа

энергии

инструментов

референсов

структуры

характера вокала

атмосферы

---

Пример

```
Epic Cinematic Trailer, Hybrid Orchestra, Female Vocal, Emotional, Powerful, Modern Film Score, Huge Choir, Wide Stereo, High Energy
```

---

# Title

Всегда автоматически генерировать название песни,

если пользователь его не указал.

---

# Vocal Gender

Поддерживать

Male

Female

Auto

---

# Negative Tags

Использовать максимально активно.

Например

```
Low quality

Noise

Distortion

Clipping

Heavy Metal

Screaming

Out of Tune

Bad Mixing

Monotone

Radio Compression
```

---

# Style Weight

Диапазон

0.00 — 1.00

Рекомендуемое значение

```
0.85
```

---

# Weirdness Constraint

Диапазон

0.00 — 1.00

По умолчанию

```
0.20
```

При экспериментальных генерациях

```
0.60
```

---

# Audio Weight

Диапазон

0.00 — 1.00

По умолчанию

```
0.70
```

---

# Ответ API

SongForge должен ожидать

```
taskId
```

После чего переходить к постоянному опросу статуса.

---

# Статусы

queue

↓

generating

↓

success

или

failed

---

# После success

Получить

```
resultJson.data[]
```

Каждый элемент содержит

id

audio_url

image_url

duration

---

# Что необходимо сохранять

SongForge должен сохранять

Task ID

Prompt

Style

Title

Negative Tags

Model Version

Дата генерации

Audio URL

Image URL

Duration

---

# Возможности SongForge

SongForge должен поддерживать абсолютно все параметры APIPass,

даже если они ещё не отображаются в интерфейсе.

При появлении новых параметров API

архитектура должна позволять быстро их добавить.

---

# Правило проекта

При обновлении документации APIPass

в первую очередь обновляется данный документ,

после чего вносятся изменения в код.
