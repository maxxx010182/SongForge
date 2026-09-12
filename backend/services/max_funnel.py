"""Тексты и разбор ответов воронки MAX по сценарию копирайтера (v2)."""

from __future__ import annotations

import re

from backend.services.messenger_service import (
    BIZ_GOAL_LABELS,
    BIZ_TONE_LABELS,
    OCCASION_LABELS,
    SOUND_LABELS,
    THEME_LABELS,
    VOICE_LABELS,
    WHOM_LABELS,
)

GATE_TEXT = (
    "Есть то, что вслух не говорится — но можно спеть.\n"
    "Расскажи в двух словах, кому и о чём — и услышишь, как это звучит, уже сегодня.\n\n"
    "Продолжая, вы соглашаетесь с соглашением и политикой. "
    "Иногда будем писать по делу в этот чат."
)
GATE_RETURN_TEXT = GATE_TEXT
WHOM_TEXT = "Для кого рождается песня?"
WHOM_RETRY = "Точнее не скажу — выбери, кому, или напиши прямо здесь 🙂"
WHOM_WRITE_PROMPT = "Напиши, кому — имя или как зовёте."
OCCASION_TEXT = "А повод какой?"
THEME_TEXT = "Тогда это про тебя. Что сейчас важнее всего почувствовать в песне?"
DETAIL_GIFT = (
    "Одна деталь — и песня оживёт. Может, фраза, которую {whom} всегда говорит? "
    "Привычка? Момент, который запомнился?"
)
DETAIL_WAIT = "Напиши её сюда — как есть, без красоты."
UNSAID_TEXT = "Что стоит в горле, но так и не сказалось? Не нужно красиво — можно просто как есть."
UNSAID_WAIT = "Пиши как есть. Это останется между нами и песней."
DETAIL_JUST = "Была сцена или момент, который стоит вшить в текст?"
SOUND_TEXT = "А как должно звучать?"
VOICE_TEXT = "Чей голос споёт это?"
VOICE_RETRY_TEXT = "Голос лучше ткнуть — так первая проба звучит вернее."
FAQ_TEXT = (
    "Первая проба бесплатна. Сколько нот — увидишь в студии, после того как услышишь.\n"
    "Сначала соберём, кому песня."
)
GREET_STAY_TEXT = "Тут. Можно ткнуть кнопку или написать своими словами."
STOP_TEXT = "Ок, молчу. Если передумаете — напишите сюда. Документы: support@sozdaipesnu.ru"
RESUME_TEXT = "Снова на связи. Соберём новую?"
LATER_TEXT = "Можно без имени. Ткни, кому песня — или напиши сам."
BIZ_SWITCH_TEXT = "А, это по делу — тоже к нам, только вопросы будут другие 🙂"
BIZ_GOAL_TEXT = "Для чего нужна песня?"
BIZ_DETAIL_TEXT = "В двух словах — о чём бренд/повод/ролик? Что должно считываться с первых секунд?"
BIZ_TONE_TEXT = "Какой тон нужен?"
STUDIO_FOOTER = "Первая проба бесплатна — два варианта, минут пять."

DETAIL_MAX = 500
WHOM_MAX = 40
OCCASION_MAX = 80
SOUND_MAX = 80

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
    "моей маме": "маме",
    "папе": "папе",
    "папа": "папе",
    "моему папе": "папе",
    "половинке": "половинке",
    "моей половинке": "половинке",
    "жене": "жене",
    "мужу": "мужу",
    "ей": "половинке",
    "ему": "половинке",
    "дружбану": "дружбану",
    "другу": "дружбану",
    "подругане": "подругане",
    "подруге": "подругане",
    "бабушке": "бабушке",
    "дедушке": "дедушке",
    "сыну": "сыну",
    "дочери": "дочери",
    "сестре": "сестре",
    "брату": "брату",
}
OCCASION_ALIASES = {
    "др": "birthday",
    "день рождения": "birthday",
    "годовщина": "anniversary",
    "свадьба": "anniversary",
    "свадьбу": "anniversary",
    "просто так": "just",
    "без повода": "just",
    "праздник": "holiday",
    "скоро праздник": "holiday",
    "8 марта": "holiday",
    "новый год": "holiday",
    "не могу сказать": "unsaid",
    "не выговаривается": "unsaid",
    "вслух": "unsaid",
}
SOUND_ALIASES = {
    "тепло": "warm",
    "тепло и близко": "warm",
    "нежно": "soft",
    "драйв": "drive",
    "погромче": "drive",
    "с улыбкой": "smile",
    "гимн": "anthem",
    "как гимн": "anthem",
}
VOICE_ALIASES = {
    "женский": "female",
    "девушка": "female",
    "female": "female",
    "мужской": "male",
    "парень": "male",
    "male": "male",
    "дуэт": "duet",
    "вдвоём": "duet",
    "на твоё усмотрение": "auto",
    "на усмотрение": "auto",
    "всё равно": "auto",
    "все равно": "auto",
}
BIZ_MARKERS = (
    "реклам",
    "бренд",
    "джингл",
    "корпоратив",
    "саундтрек",
    "ролик",
    "видео для",
    "компания",
    "бизнес",
)

_WHOM_FIND = re.compile(
    r"\b(маме|мама|папе|папа|жене|мужу|бабушке|дедушке|сыну|дочери|"
    r"сестре|брату|подруге|другу|половинке|дружбану|подругане)\b",
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


def looks_business(raw: str) -> bool:
    key = _norm(raw)
    if not key:
        return False
    return any(word in key for word in BIZ_MARKERS)


def is_just_plot(whom: str, segment: str = "") -> bool:
    if (segment or "") == "just":
        return True
    return _norm(whom) in {"", "конкретно никому", "никому", "не указан"}


def whom_display(whom: str) -> str:
    label = (whom or "").strip()
    if not label:
        return "тебя"
    return label


def detail_gift_text(whom: str) -> str:
    addr = whom_display(whom)
    if addr == "тебя":
        addr = "этот человек"
    return DETAIL_GIFT.format(whom=addr)


def parse_whom(raw: str) -> tuple[str | None, str, str]:
    """(whom, leftover, plot). plot=just|gift. None whom + gift = invalid."""
    text = (raw or "").strip()
    if not text or is_skip(text):
        return None, "", "gift"
    key = _norm(text)
    if key in FILLER_WORDS:
        return None, "", "gift"
    if key in {"nobody", "никому", "конкретно никому", "никому конкретно"}:
        return "", "", "just"
    if key in WHOM_LABELS:
        return WHOM_LABELS[key], "", "gift"
    if key in WHOM_ALIASES:
        return WHOM_ALIASES[key], "", "gift"
    if key.startswith("для "):
        return parse_whom(text[4:].strip())
    if len(text) > WHOM_MAX:
        match = _WHOM_FIND.search(text)
        if match:
            found, leftover, plot = parse_whom(match.group(1))
            extra = (text[: match.start()] + text[match.end() :]).strip(" ,.;")
            return found, extra[:DETAIL_MAX], plot
        return None, "", "gift"
    if len(text) < 2:
        return None, "", "gift"
    return text[:WHOM_MAX], "", "gift"


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


def parse_theme(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    key = _norm(text)
    if key in THEME_LABELS:
        return THEME_LABELS[key]
    for label in THEME_LABELS.values():
        if key == _norm(label) or _norm(label) in key:
            return label
    if is_skip(text):
        return THEME_LABELS["dunno"]
    if key in FILLER_WORDS:
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
    text = (raw or "").strip()
    if not text or is_skip(text):
        return ""
    return text[:DETAIL_MAX]


def occasion_key_of(label: str) -> str:
    want = _norm(label)
    for key, value in OCCASION_LABELS.items():
        if _norm(value) == want:
            return key
    return ""


def theme_key_of(label: str) -> str:
    want = _norm(label)
    for key, value in THEME_LABELS.items():
        if _norm(value) == want:
            return key
    return ""


def studio_mirror(
    *,
    whom: str,
    occasion: str,
    detail: str,
    sound: str,
    voice: str,
    plot: str = "gift",
) -> str:
    bits = []
    if plot == "just" or not (whom or "").strip():
        bits.append("это про тебя самого")
        if occasion:
            bits.append(occasion)
    else:
        bits.append(whom)
        if occasion:
            bits.append(occasion)
    if sound:
        bits.append(sound)
    voice_bit = _voice_for_mirror(voice)
    if voice_bit:
        bits.append(voice_bit)
    head = "Держу: " + ", ".join(bits)
    if detail:
        head += f" — и «{detail}»"
    head += "."
    return head + "\n" + STUDIO_FOOTER


def _voice_for_mirror(voice: str) -> str:
    key = _norm(voice)
    if key == "дуэт":
        return "дуэт"
    if key in {"женский", "мужской"}:
        return f"{key} голос"
    return ""


def biz_studio_mirror(goal: str, detail: str, tone: str) -> str:
    parts = [p for p in (goal, detail, tone) if p]
    hold = ", ".join(parts) if parts else "идею"
    return f"Собрал: {hold}. Первая проба бесплатна — послушаешь и решишь."
