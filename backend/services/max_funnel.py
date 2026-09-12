"""Тексты и разбор ответов воронки MAX: кнопки + свои слова, мусор в бриф не кладём."""

from __future__ import annotations

import re

from backend.services.messenger_service import (
    OCCASION_LABELS,
    SOUND_LABELS,
    VOICE_LABELS,
    WHOM_LABELS,
)

GATE_TEXT = (
    "Есть вещи, которые вслух не выходят. Их можно спеть.\n\n"
    "Первая проба бесплатно — два варианта, минут пять.\n\n"
    "«Поехали» — соглашение и политика, как на сайте. Редкие сообщения сюда. "
    "Стоп — напишите «стоп»."
)
GATE_RETURN_TEXT = (
    "Есть вещи, которые вслух не выходят. Их можно спеть.\n\n"
    "Соберём новую. Первая проба бесплатно — два варианта, минут пять.\n\n"
    "Стоп — напишите «стоп»."
)
WHOM_TEXT = "Для кого сейчас первая песня?"
OCCASION_TEXT = "Это к дате — или просто от сердца?"
SOUND_TEXT = "Как это должно звучать в наушниках?"
VOICE_TEXT = "Кто поёт?"
VOICE_RETRY_TEXT = "Голос лучше ткнуть — так первая проба звучит вернее."
FAQ_TEXT = (
    "Первая проба бесплатно. Сколько нот — в студии, после того как услышите.\n"
    "Сначала соберём, кому песня."
)
GREET_STAY_TEXT = "Тут. Можно ткнуть кнопку или написать своими словами."
STOP_TEXT = (
    "Ок, молчу. Если передумаете — напишите сюда. "
    "Документы и данные: support@sozdaipesnu.ru"
)
RESUME_TEXT = "Снова на связи. Соберём новую?"
LATER_TEXT = "Без имени тоже можно. Ткните, кому песня — слова потом допишем."
STUDIO_FOOTER = (
    "Открою студию — два варианта, минут пять. Первая проба бесплатно."
)

DETAIL_MAX = 500
WHOM_MAX = 40
OCCASION_MAX = 80
SOUND_MAX = 80

FILLER_WORDS = {
    "ок",
    "окей",
    "ok",
    "okay",
    "хорошо",
    "угу",
    "ага",
    "да",
    "нет",
    "эм",
    "хм",
}
SKIP_WORDS = {
    "не знаю",
    "хз",
    "любой",
    "любая",
    "как скажешь",
    "пропусти",
    "пока без",
    "пока без этого",
    "без этого",
    "неважно",
    "не важно",
    "как хочешь",
    "без разницы",
    "все равно",
    "всё равно",
    "skip",
    "later",
}
PRICE_MARKERS = (
    "сколько",
    "цена",
    "цену",
    "платно",
    "бесплатн",
    "стоит",
    "стоимост",
    "ноты",
    "руб",
    "₽",
    "оплат",
)
WHOM_ALIASES = {
    "маме": "маме",
    "мама": "маме",
    "мамы": "маме",
    "маму": "маме",
    "для мамы": "маме",
    "папе": "папе",
    "папа": "папе",
    "папы": "папе",
    "отцу": "папе",
    "батя": "папе",
    "для папы": "папе",
    "ей": "ей",
    "любимой": "любимой",
    "жене": "жене",
    "девушке": "ей",
    "супруге": "жене",
    "ему": "ему",
    "любимому": "любимому",
    "мужу": "мужу",
    "парню": "ему",
    "другу": "другу",
    "подруге": "подруге",
    "другу/подруге": "другу",
    "себе": "себе",
    "мне": "себе",
    "для себя": "себе",
    "бабушке": "бабушке",
    "дедушке": "дедушке",
    "сыну": "сыну",
    "дочери": "дочери",
    "сестре": "сестре",
    "брату": "брату",
    "коллеге": "коллеге",
}
OCCASION_ALIASES = {
    "др": "birthday",
    "д.р": "birthday",
    "д.р.": "birthday",
    "день рождения": "birthday",
    "день рожденья": "birthday",
    "годовщина": "anniversary",
    "годовщину": "anniversary",
    "свадьба": "anniversary",
    "свадьбу": "anniversary",
    "свадьбы": "anniversary",
    "просто так": "just",
    "просто": "just",
    "от сердца": "just",
    "без повода": "just",
    "праздник": "holiday",
    "скоро праздник": "holiday",
    "8 марта": "holiday",
    "новый год": "holiday",
    "нг": "holiday",
    "23 февраля": "holiday",
    "14 февраля": "holiday",
    "не могу вслух": "unsaid",
    "хочу сказать": "unsaid",
    "хочу сказать и не могу вслух": "unsaid",
}
SOUND_ALIASES = {
    "тепло": "warm",
    "тепло и близко": "warm",
    "близко": "warm",
    "нежно": "soft",
    "нежность": "soft",
    "драйв": "drive",
    "погромче": "drive",
    "энергичн": "drive",
    "с улыбкой": "smile",
    "улыбк": "smile",
    "юмор": "smile",
    "гимн": "anthem",
    "как гимн": "anthem",
}
VOICE_ALIASES = {
    "женский": "female",
    "женски": "female",
    "девушка": "female",
    "девушк": "female",
    "female": "female",
    "мужской": "male",
    "мужски": "male",
    "парень": "male",
    "male": "male",
    "решите сами": "auto",
    "на усмотрение": "auto",
    "сам": "auto",
    "сама": "auto",
    "как скажешь": "auto",
}
SELF_DETAIL_LABELS = {
    "chapter": "новая глава",
    "anger": "злость",
    "high": "кайф",
    "nostalgia": "ностальгия",
    "own": "просто хочу свою песню",
}

_WHOM_FIND = re.compile(
    r"\b(маме|мама|мамы|папе|папа|отцу|жене|мужу|бабушке|дедушке|"
    r"сыну|дочери|сестре|брату|подруге|другу|себе|любимой|любимому|"
    r"девушке|парню|коллеге)\b",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower()).strip(" .!?,;:")


def is_skip(text: str) -> bool:
    return _norm(text) in SKIP_WORDS


def is_price_question(text: str) -> bool:
    low = _norm(text)
    if not low:
        return False
    if "?" in (text or "") and any(m in low for m in PRICE_MARKERS):
        return True
    return any(m in low for m in PRICE_MARKERS) and len(low) < 80


def is_self(whom: str) -> bool:
    key = _norm(whom)
    return key in {"себе", "мне", "для себя"}


def whom_reaction(whom: str) -> str:
    if is_self(whom):
        return "Себе. Тогда без открытки — свой трек."
    label = (whom or "").strip()
    if not label:
        return ""
    return f"{label[0].upper() + label[1:]}. Хороший жест."


def detail_text(whom: str) -> str:
    if is_self(whom):
        return "Для себя — что сейчас внутри? Можно одной сценой."
    hints = {
        "маме": "Для мамы: как встречает из школы, её фраза, свет на кухне.",
        "папе": "Для папы: его привычка, как встречает, что всегда говорит.",
        "ей": "Как познакомились, её привычка, ваше место.",
        "ему": "Как познакомились, его привычка, ваше место.",
        "любимой": "Как познакомились, её привычка, ваше место.",
        "любимому": "Как познакомились, его привычка, ваше место.",
        "жене": "Как познакомились, её привычка, ваше место.",
        "мужу": "Как познакомились, его привычка, ваше место.",
        "другу": "Общая история, кличка, случай, который только вы двое помните.",
        "подруге": "Общая история, кличка, случай, который только вы двое помните.",
    }
    extra = hints.get(_norm(whom), "Любая живая штука: фраза, привычка, случай.")
    return (
        "Имя и одна штука, которую знает только тот, кто дарит. "
        "С этого начинается припев.\n\n"
        f"{extra} Можно одной строкой."
    )


def parse_whom(raw: str) -> tuple[str | None, str]:
    """Возвращает (whom, leftover_detail). None — не сохранять."""
    text = (raw or "").strip()
    if not text or is_skip(text):
        return None, ""
    key = _norm(text)
    if key in FILLER_WORDS:
        return None, ""
    if key in WHOM_LABELS:
        return WHOM_LABELS[key], ""
    if key in WHOM_ALIASES:
        return WHOM_ALIASES[key], ""
    if key.startswith("для "):
        inner, extra = parse_whom(text[4:].strip())
        return inner, extra
    if len(text) > WHOM_MAX:
        match = _WHOM_FIND.search(text)
        if match:
            found, _ = parse_whom(match.group(1))
            leftover = (text[: match.start()] + text[match.end() :]).strip(" ,.;")
            leftover = leftover[:DETAIL_MAX]
            return found, leftover
        return None, ""
    if len(text) < 2:
        return None, ""
    return text[:WHOM_MAX], ""


def parse_occasion(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    if is_skip(text):
        return OCCASION_LABELS["just"]
    key = _norm(text)
    if key in FILLER_WORDS:
        return None
    if key in OCCASION_LABELS:
        return OCCASION_LABELS[key]
    if key in OCCASION_ALIASES:
        return OCCASION_LABELS[OCCASION_ALIASES[key]]
    for alias, mapped in OCCASION_ALIASES.items():
        if alias in key:
            return OCCASION_LABELS[mapped]
    if len(text) < 2 or len(text) > OCCASION_MAX:
        return None
    return text[:OCCASION_MAX]


def parse_sound(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text or is_skip(text):
        return None
    key = _norm(text)
    if key in FILLER_WORDS:
        return None
    if key in SOUND_LABELS:
        return SOUND_LABELS[key]
    for alias, mapped in SOUND_ALIASES.items():
        if alias == key or (len(alias) > 4 and alias in key):
            return SOUND_LABELS[mapped]
    if len(text) < 2 or len(text) > SOUND_MAX:
        return None
    return text[:SOUND_MAX]


def parse_voice(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    if is_skip(text):
        return VOICE_LABELS["auto"]
    key = _norm(text)
    if key in VOICE_LABELS:
        return VOICE_LABELS[key]
    for alias, mapped in VOICE_ALIASES.items():
        if key == alias or key.startswith(alias):
            return VOICE_LABELS[mapped]
    return None


def parse_detail(raw: str) -> str | None:
    """None = пропуск (пусто). Строка — сохранить."""
    text = (raw or "").strip()
    if not text or is_skip(text):
        return ""
    return text[:DETAIL_MAX]


def parse_self_detail(raw: str) -> str | None:
    key = _norm(raw)
    if key in SELF_DETAIL_LABELS:
        return SELF_DETAIL_LABELS[key]
    if key in {v: k for k, v in SELF_DETAIL_LABELS.items()}:
        return key
    for label in SELF_DETAIL_LABELS.values():
        if key == label:
            return label
    return parse_detail(raw)


def studio_mirror(
    *,
    whom: str,
    occasion: str,
    detail: str,
    sound: str,
    voice: str,
) -> str:
    lines = ["Собрал черновик:", ""]
    head = (whom or "песня").strip()
    if occasion:
        head = f"{head[0].upper() + head[1:]}. {occasion[0].upper() + occasion[1:]}."
    else:
        head = f"{head[0].upper() + head[1:]}."
    lines.append(head)
    if detail:
        lines.append(f"Деталь: {detail}")
    sound_bits = [part for part in (sound, _voice_for_mirror(voice)) if part]
    if sound_bits:
        lines.append("Звучание: " + ", ".join(sound_bits) + ".")
    lines.extend(["", STUDIO_FOOTER])
    return "\n".join(lines)


def _voice_for_mirror(voice: str) -> str:
    key = _norm(voice)
    if key in {"женский", "мужской"}:
        return f"{key} голос"
    return ""


def occasion_key_of(label: str) -> str:
    want = _norm(label)
    for key, value in OCCASION_LABELS.items():
        if _norm(value) == want:
            return key
    return ""
