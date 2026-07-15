"""Общие промпты и цепочки моделей для генерации текстов песен (YandexGPT).

Цель: полная песня ~4 минуты под Suno V5.5 custom mode —
качественная структура и сонграйтинг, не «что вижу — то пою».
"""

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
    "ПРИМЕР ФОРМАТА (только stadium / гимн / концерт — не копируй тему и не применяй ко всем жанрам):\n"
    "[Intro - soft crowd bed]\n"
    "...\n\n"
    "[Verse 1 - gritty rap-sung delivery]\n"
    "...\n\n"
    "[Pre-Chorus - building]\n"
    "...\n\n"
    "[Chorus - huge stadium singalong]\n"
    "...\n\n"
    "[Verse 2 - new angle, same energy]\n"
    "...\n\n"
    "[Chorus]\n"
    "...\n\n"
    "[Bridge - strip-back then lift]\n"
    "...\n\n"
    "[Final Chorus - full band + ad-libs]\n"
    "...\n\n"
    "[Outro]\n"
    "..."
)

_FULL_SONG_STRUCTURE = (
    "ДЛИНА И СТРУКТУРА (Suno V5.5, цель ~4 минуты звучания):\n"
    "• Обычная песня: lyrics 2000–4500 символов (не короче ~1800, кроме явной детской/колыбельной).\n"
    "• Обязательные секции (теги на английском):\n"
    "  [Intro] (коротко, 2–4 строки или режиссура) — по желанию, но желательно;\n"
    "  [Verse 1 - …delivery…] — 6–10 строк, сцена/конфликт;\n"
    "  [Pre-Chorus - …] — 2–4 строки, подъём к хуку;\n"
    "  [Chorus - …] — 4–8 строк, яркий запоминающийся хук; при повторе ДОСЛОВНО тот же текст;\n"
    "  [Verse 2 - …] — 6–10 строк, НОВЫЙ ракурс (не копия Verse 1);\n"
    "  [Pre-Chorus] + [Chorus] — повтор;\n"
    "  [Bridge - …] — 4–8 строк, сдвиг эмоции/образа;\n"
    "  [Final Chorus - …] — тот же хук + усиление (ad-libs в () по жанру);\n"
    "  [Outro] — 2–6 строк, закрытие.\n"
    "• Electronic: можно [Build-up]/[Drop]/[Breakdown] вместо части куплетов, "
    "но сохрани объём и повторяемый хук/вокальную тему.\n"
    "• Детская / колыбельная: короче (900–1800 символов), проще лексика, "
    "но всё равно Verse + Chorus + повтор + Outro.\n"
)

_BRIEF_NOT_LYRICS = (
    "ИДЕЯ ПОЛЬЗОВАТЕЛЯ = БРИФ, НЕ ГОТОВЫЙ ТЕКСТ ПЕСНИ.\n"
    "ЗАПРЕЩЕНО «что вижу — то пою»:\n"
    "- Пересказывать описание построчно / списком фактов.\n"
    "- Вставлять целые фразы брифа как строки куплета.\n"
    "- Писать прозой «песня про …», «эта песня рассказывает …».\n"
    "- Плоский отчёт: «я родился / живу / люблю» без образов и рифмы.\n"
    "НУЖНО:\n"
    "- Превратить бриф в песню: сюжет, эмоция, хук, развитие, рифма и ритм под жанр.\n"
    "- Имена, места, даты, детали из брифа — вплетать естественно (1–3 якоря на куплет), "
    "не перечислять как анкету.\n"
    "- Припев: 1 короткая идея-хук (фраза, которую хочется подпевать), не пересказ всего брифа.\n"
    "- Куплеты: сцены и детали; припев: обобщение чувства.\n"
    "- Рифма/ассонанс по возможности; строки удобные для пения (не канцелярит).\n"
)

_SUNO_SCREENPLAY_FORMAT = (
    "ФОРМАТ SUNO STUDIO (custom mode): поле lyrics — screenplay под жанр и бриф.\n"
    "1. Заголовок секции на английском + delivery через дефис — под жанр/настроение, "
    "не один шаблон на все песни.\n"
    "2. Отдельные строки-режиссура (crowd, piano, drop) — только если уместны теме "
    "(не stadium в балладе).\n"
    "3. Ad-libs в () — по жанру: rap (эй), pop (о-о-о), ballad (мм) или без.\n"
    "4. Поющиеся строки — на языке брифа; структурные теги — на английском.\n"
    "5. Припев при каждом [Chorus]/[Final Chorus] — один и тот же текст хука.\n"
    "6. Delivery-теги у КАЖДОЙ вокальной секции ([Verse 1 - soft intimate vocal], …).\n\n"
    f"{_FULL_SONG_STRUCTURE}\n"
    "ПОДСКАЗКИ ПО ЖАНРУ (выбери подходящие, остальное не используй):\n"
    "- Баллада / акустика: intimate vocal, piano/strings; без crowd.\n"
    "- Pop / dance: bright melodic delivery, building pre, catchy layered chorus.\n"
    "- Rap / hip-hop: rhythmic flow в куплетах, sung hook в припеве; ad-libs по месту.\n"
    "- Rock / anthem: gritty delivery, Final Chorus — full band.\n"
    "- Stadium / гимн / концерт (только если в идее): crowd, singalong, buildup.\n"
    "- Electronic: build-up / drop / breakdown + вокальный хук.\n"
    "- Детская: проще слова, короче, тёплый тон.\n\n"
    f"{_STADIUM_ANTHEM_EXAMPLE}"
)

_CREATIVE_CRAFT = (
    "ПЕРЕД ТЕКСТОМ (внутренне, не выводи отдельно):\n"
    "1. Бриф → 1 эмоция + 1 конфликт/желание + 1 хук-фраза припева.\n"
    "2. 2–3 якоря из брифа (имя/место/деталь) — распредели по куплетам, не в каждую строку.\n"
    "3. Драматургия: Verse 1 завязка → Chorus тезис → Verse 2 развитие → Bridge поворот → Final.\n"
    "4. Тон и delivery — строго под жанр и энергию, не «стадион по умолчанию».\n\n"
    f"{_BRIEF_NOT_LYRICS}\n"
    "ЗАПРЕЩЕНО:\n"
    "- Один стиль на все запросы (толпа, rap-sung, stadium — только где уместно).\n"
    "- Плоские стихи без delivery-тегов у секций.\n"
    "- Пустые штампы: «ты моя судьба», «до конца дней», «ты моя звезда», «в сердце навсегда».\n"
    "- Банальные метафоры: мосты-крылья, реки-вены, огонь-страсть без свежего образа.\n"
    "- Копировать пример Тюмень / stadium по смыслу.\n"
    "- Имена реальных исполнителей и групп.\n"
    "- Коротыш «Verse + Chorus + конец» без Verse 2 / Bridge / повторов (кроме детской)."
)

SCREENPLAY_RETRY_HINT = (
    "\n\nКРИТИЧНО ПЕРЕПИСАТЬ:\n"
    "1) Полная структура ~4 мин (Intro? V1 → Pre → Chorus → V2 → Pre → Chorus → Bridge → Final Chorus → Outro).\n"
    "2) 2000+ символов (если не детская).\n"
    "3) НЕ пересказывать бриф — песня с хуком, рифмой, новым Verse 2, дословный повтор припева.\n"
    "4) Delivery-теги у секций; crowd/stadium только если уместно.\n"
    "5) Конкретика из запроса — якорями, не списком."
)

UNIFIED_SCREENPLAY_RETRY_HINT = SCREENPLAY_RETRY_HINT
CLASSIC_LYRICS_RETRY_HINT = SCREENPLAY_RETRY_HINT


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
            "допустимы, если логичны теме. Полная длина ~4 мин."
        )

    if any(t in blob for t in ("баллад", "ballad", "акуст", "acoustic", "лирич", "jazz", "джаз")):
        return (
            "Режиссура lyrics: спокойная/лирическая — intimate vocal, мягкие секции; "
            "без crowd и stadium. Всё равно полная форма (V1–V2–Bridge–Final), ~4 мин."
        )

    if any(t in blob for t in ("rap", "хип", "hip-hop", "hip hop", "trap", "drill")):
        return (
            "Режиссура lyrics: rap / hip-hop — rhythmic flow в куплетах, sung hook в припеве; "
            "ad-libs по месту; два полноценных куплета + bridge; ~4 мин."
        )

    if any(t in blob for t in ("electro", "edm", "house", "techno", "dance", "trance")):
        return (
            "Режиссура lyrics: electronic — build-up / drop / breakdown + вокальный хук; "
            "достаточный объём текста под ~4 мин."
        )

    if any(t in blob for t in ("детск", "kids", "children", "сказк", "колыбел", "lullaby")):
        return (
            "Режиссура lyrics: детская/простая — понятные слова, короче обычной, "
            "но с припевом и повтором; без тяжёлой stadium-режиссуры."
        )

    if energy_l in ("low", "низк", "medium", "средн") or any(
        t in blob for t in ("груст", "sad", "melanch", "спокой", "calm", "chill", "lofi")
    ):
        return (
            "Режиссура lyrics: низкая/средняя энергия — без crowd и финального «взрыва», "
            "если пользователь явно не просил концерт. Форма полная, ~4 мин."
        )

    if backing_vocal:
        return (
            "Режиссура lyrics: подпевки — [Backing vocals] / harmonized chorus где уместно; "
            "полная форма ~4 мин."
        )

    return (
        "Режиссура lyrics: delivery-теги и структура под жанр и настроение; "
        "полная форма ~4 мин; не стадионный шаблон без необходимости; "
        "бриф → песня, не пересказ."
    )


CLASSIC_LYRICS_SYSTEM = (
    "Ты — сонграйтер и режиссёр вокала для Suno V5.5 custom mode.\n"
    "Модель всегда V5_5 — пиши screenplay под неё.\n"
    f"{_FULL_SONG_STRUCTURE}\n"
    f"{_SUNO_SCREENPLAY_FORMAT}\n\n"
    f"{_CREATIVE_CRAFT}\n\n"
    "ФОРМАТ ОТВЕТА: только текст lyrics, без markdown и пояснений."
)

UNIFIED_PACKAGE_SYSTEM = (
    "Ты — сонграйтер и саунд-продюсер для SongForge "
    "(custom vocal: lyrics + title + style для Suno V5.5).\n"
    "Модель всегда V5_5.\n"
    f"{_SUNO_SCREENPLAY_FORMAT}\n\n"
    f"{_CREATIVE_CRAFT}\n\n"
    "ФОРМАТ: верни ТОЛЬКО валидный JSON-объект, без markdown до или после.\n"
    "Поля (без лишних):\n"
    '- "title": короткое название на языке запроса, до 80 символов; '
    "хук/суть песни, не сценическая ремарка и не весь бриф.\n"
    '- "lyrics": полный Suno screenplay; цель 2000–4500 символов (~4 мин); '
    "delivery-теги; строки на языке запроса; припев дословно одинаков; "
    "НЕ пересказ брифа.\n"
    '- "style_prompt": одна строка на английском, СТРОГО до 200 символов; '
    "6–10 тегов; СНАЧАЛА точный genre/subgenre из анализа "
    "(не подменяй на Modern Pop, если жанр другой: Jazz, Rock, Hip-Hop, Ballad, "
    "Electronic, Metal, R&B, Folk, Chanson…); "
    "genre → mood → instruments → vocals → production; "
    "обязательно sung in Russian, native Russian vocals "
    "(если язык песни не русский — укажи язык вокала по брифу); без имён артистов.\n"
    "negativeTags, vocalGender и веса Suno задаёт сервер — не включай в JSON."
)
