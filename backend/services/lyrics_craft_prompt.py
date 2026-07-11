"""Общие промпты и цепочки моделей для генерации текстов песен (YandexGPT)."""

from __future__ import annotations

# Резервная цепочка: Pro (креатив) → Pro (строже) → Lite (запасная модель).
# При сбое всех попыток — template-fallback в prompt_builder / classic pipeline.
LYRICS_MODEL_ATTEMPTS: tuple[tuple[str, float, str], ...] = (
    ("yandexgpt", 0.78, ""),
    ("yandexgpt", 0.62, "retry"),
    ("yandexgpt-lite", 0.70, "lite-retry"),
)

UNIFIED_MODEL_ATTEMPTS: tuple[tuple[str, float, str], ...] = (
    ("yandexgpt", 0.76, ""),
    ("yandexgpt", 0.58, "retry"),
    ("yandexgpt-lite", 0.65, "lite-retry"),
)

# Один удачный кейс владельца — stadium/pop-rock anthem. Не шаблон для всех жанров.
_STADIUM_ANTHEM_EXAMPLE = (
    "ПРИМЕР (только для stadium / гимн / концерт — не копируй тему и не применяй ко всем жанрам):\n"
    "[Intro - crowd chanting rhythmically]\n"
    "Ту-мень! Ту-мень!\n\n"
    "[Verse 1 - gritty rap-sung delivery]\n"
    "...\n\n"
    "[Chorus - huge stadium singalong, female vocals doubling melody]\n"
    "..."
)

_SUNO_SCREENPLAY_FORMAT = (
    "ФОРМАТ SUNO STUDIO: поле lyrics — сценарий под КОНКРЕТНЫЙ жанр и запрос пользователя.\n"
    "Приём (инструмент, не один стиль на все песни):\n"
    "1. Заголовок секции на английском + подсказка исполнения через дефис — "
    "подбирай под жанр/настроение из запроса, не копируй один шаблон.\n"
    "2. Отдельные строки-режиссура — только если уместны теме "
    "(не вставляй crowd/stadium в балладу, джаз или лирическую песню).\n"
    "3. Ad-libs в () — по жанру: rap (эй), pop (о-о-о), ballad (мм) или без них.\n"
    "4. Строки песни — на языке запроса; рифма и ритм под жанр.\n"
    "5. Структура гибкая: минимум [Verse 1] и [Chorus]; "
    "[Pre-Chorus], [Bridge], [Outro] — если логичны для жанра. "
    "Припев дословно одинаков при повторе.\n"
    "6. Конкретика из идеи: имена, места, даты, детали — вплетай, когда они есть в запросе.\n\n"
    "ПОДСКАЗКИ ПО ЖАНРУ (выбери подходящие, остальное не используй):\n"
    "- Баллада / акустика: [Verse 1 - soft intimate vocal], [Piano and strings], "
    "[Chorus - emotional belt]; без толпы.\n"
    "- Pop / dance: [Verse 1 - bright melodic delivery], [Pre-Chorus - building], "
    "[Chorus - catchy hook, layered vocals].\n"
    "- Rap / hip-hop: [Verse 1 - rhythmic rap flow], [Chorus - sung hook]; ad-libs уместны.\n"
    "- Rock / anthem: [Verse 1 - gritty delivery], [Final Chorus - explosive full band].\n"
    "- Stadium / гимн / концерт (только если в идее или жанре): crowd, singalong, buildup.\n"
    "- Electronic: [Drop], [Build-up], [Breakdown] — вместо куплетов при необходимости.\n"
    "- Детская / простая: короче, без сложной режиссуры.\n\n"
    f"{_STADIUM_ANTHEM_EXAMPLE}"
)

_CREATIVE_CRAFT = (
    "ПЕРЕД ТЕКСТОМ (внутренне, не выводи отдельно):\n"
    "1. Прочитай идею, жанр, настроение, энергию — выбери тон и режиссуру под НИХ.\n"
    "2. Хук припева и title — из смысла запроса, не из чужого примера.\n"
    "3. Якоря из идеи (места, имена, факты) — используй, если пользователь их дал; "
    "если идея абстрактная — образы и ситуации, не выдуманный «гимн городу».\n"
    "4. Драматургия под жанр: спокойная песня может быть ровной; "
    "энергичная — с нарастанием; не делай всё стадионным финалом.\n"
    "5. [Verse 2] — новый ракурс; [Bridge] — только если уместен.\n\n"
    "ЗАПРЕЩЕНО:\n"
    "- Один стиль на все запросы (толпа, rap-sung, stadium — только где уместно).\n"
    "- Плоские стихи без delivery-тегов у секций.\n"
    "- Пустые штампы: «ты моя судьба», «до конца дней», «ты моя звезда».\n"
    "- Банальные метафоры: мосты-крылья, реки-вены.\n"
    "- Копировать пример Тюмень по смыслу.\n"
    "- Имена реальных исполнителей и групп."
)

SCREENPLAY_RETRY_HINT = (
    "\n\nКРИТИЧНО: Suno screenplay под ЭТОТ жанр и идею. "
    "Delivery-теги у секций — но без чужого шаблона (crowd только если уместно). "
    "Конкретика из запроса пользователя."
)


def lyrics_screenplay_user_hint(
    *,
    genre: str,
    subgenre: str,
    mood: str,
    energy: str,
    idea: str,
    backing_vocal: bool,
) -> str:
    """Одна строка в user prompt — подсказка режиссуры под контекст, не универсальный стадион."""
    blob = f"{idea} {genre} {subgenre} {mood}".lower()
    energy_l = (energy or "").lower()

    if any(
        t in blob
        for t in (
            "стадион",
            "stadium",
            "гимн",
            "anthem",
            "концерт",
            "arena",
            "толпа",
            "live",
            "хор",
        )
    ):
        return (
            "Режиссура lyrics: stadium / anthem — crowd, singalong, buildup к финалу "
            "допустимы, если логичны теме."
        )

    if any(t in blob for t in ("баллад", "ballad", "акуст", "acoustic", "лирич", "jazz", "джаз")):
        return (
            "Режиссура lyrics: спокойная/лирическая — intimate vocal, мягкие секции; "
            "без crowd и stadium."
        )

    if any(t in blob for t in ("rap", "хип", "hip-hop", "hip hop", "trap", "drill")):
        return (
            "Режиссура lyrics: rap / hip-hop — rhythmic flow в куплетах, sung hook в припеве; "
            "ad-libs по месту, без стадионного хора если не просили."
        )

    if any(t in blob for t in ("electro", "edm", "house", "techno", "dance", "тrance")):
        return (
            "Режиссура lyrics: electronic — build-up / drop / breakdown уместнее стадионных тегов."
        )

    if any(t in blob for t in ("детск", "kids", "children", "сказк", "колыбел", "lullaby")):
        return "Режиссура lyrics: простая, короткие секции, без тяжёлой продакшн-режиссуры."

    if energy_l in ("low", "низк", "medium", "средн") or any(
        t in blob for t in ("груст", "sad", "melanch", "спокой", "calm", "chill", "lofi")
    ):
        return (
            "Режиссура lyrics: низкая/средняя энергия — без crowd и финального «взрыва», "
            "если пользователь явно не просил концерт."
        )

    if backing_vocal:
        return (
            "Режиссура lyrics: подпевки — отметь [Backing vocals] / harmonized chorus где уместно."
        )

    return (
        "Режиссура lyrics: подбери delivery-теги и структуру под жанр и настроение из запроса; "
        "не используй стадионный шаблон без необходимости."
    )


CLASSIC_LYRICS_SYSTEM = (
    "Ты — сонграйтер и режиссёр вокала для Suno V5.5 custom mode.\n"
    f"{_SUNO_SCREENPLAY_FORMAT}\n\n"
    f"{_CREATIVE_CRAFT}\n\n"
    "ФОРМАТ ОТВЕТА: только текст lyrics, без markdown и пояснений."
)

CLASSIC_LYRICS_RETRY_HINT = SCREENPLAY_RETRY_HINT

UNIFIED_PACKAGE_SYSTEM = (
    "Ты — сонграйтер и саунд-продюсер для SongForge "
    "(custom vocal: отдельно lyrics, title и style для Suno V5.5).\n"
    f"{_SUNO_SCREENPLAY_FORMAT}\n\n"
    f"{_CREATIVE_CRAFT}\n\n"
    "ФОРМАТ: верни ТОЛЬКО валидный JSON-объект, без markdown до или после.\n"
    "Поля (без лишних):\n"
    '- "title": короткое название на языке запроса, до 80 символов; '
    "хук припева, не сценическая ремарка.\n"
    '- "lyrics": Suno screenplay до 3000 символов; delivery-теги под жанр запроса; '
    "строки — на языке запроса; припев дословно одинаков при повторе.\n"
    '- "style_prompt": одна строка на английском, СТРОГО до 200 символов; '
    "6–10 тегов; genre → mood → instruments → vocals → production; "
    "обязательно sung in Russian, native Russian vocals; без имён артистов.\n"
    "negativeTags, vocalGender и веса Suno задаёт сервер — не включай в JSON."
)

UNIFIED_SCREENPLAY_RETRY_HINT = SCREENPLAY_RETRY_HINT