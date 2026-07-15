"""Extract structured intent from free-form user idea text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.services.genre_resolver import infer_genre_from_idea, infer_mood_from_idea, resolve_genre

_RAP_GENRES = {"hip-hop", "hip hop", "trap", "drill"}

_GENRE_KEYWORDS: list[tuple[str, str]] = [
    ("рэп", "Реп"),
    ("реп", "Реп"),
    ("рэпчик", "Реп"),
    ("rap", "Реп"),
    ("хип-хоп", "Хип-хоп"),
    ("хип хоп", "Хип-хоп"),
    ("hip-hop", "Хип-хоп"),
    ("hip hop", "Хип-хоп"),
    ("трэп", "Трэп"),
    ("trap", "Трэп"),
    ("дрилл", "Дрилл"),
    ("drill", "Дрилл"),
    ("поп", "Поп"),
    ("pop", "Поп"),
    ("рок", "Рок"),
    ("rock", "Рок"),
    ("баллад", "Баллада"),
    ("ballad", "Баллада"),
    ("электрон", "Электронная"),
    ("electronic", "Электронная"),
    ("edm", "Электронная"),
    ("ло-фай", "Ло-фай"),
    ("lo-fi", "Ло-фай"),
    ("lofi", "Ло-фай"),
    ("джаз", "Джаз"),
    ("jazz", "Джаз"),
    ("металл", "Металл"),
    ("metal", "Металл"),
    ("кантри", "Кантри"),
    ("country", "Кантри"),
    ("р-н-б", "Р-н-б"),
    ("r&b", "Р-н-б"),
    ("шансон", "Шансон"),
]

_MOOD_KEYWORDS: list[tuple[str, str]] = [
    ("о любви", "romantic"),
    ("про любовь", "romantic"),
    ("любовн", "romantic"),
    ("романт", "romantic"),
    ("груст", "melancholy"),
    ("печал", "melancholy"),
    ("тоск", "melancholy"),
    ("радост", "uplifting"),
    ("весёл", "uplifting"),
    ("весел", "uplifting"),
    ("энерг", "uplifting"),
    ("мрач", "dark"),
    ("агресс", "dark"),
    ("спокой", "calm"),
    ("ностальг", "nostalgic"),
    ("эпич", "adventurous"),
    ("эпическ", "adventurous"),
    ("epic", "adventurous"),
    ("triumphant", "adventurous"),
    ("stadium", "adventurous"),
    ("anthem", "adventurous"),
    ("patriotic", "adventurous"),
]

_ARTIST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:стил[еья]|звучани[ея])\s+"
        r"(?:как\s+у\s+)?([A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\s\-\.]{1,40})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:как\s+у|в\s+духе|похож[еа]\s+на|в\s+стиле)\s+"
        r"([A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\s\-\.]{1,40})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:привёл\s+в\s+пример|пример[у]?|музыкант[а]?|групп[аы]|артист[а]?)\s+"
        r"([A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\s\-\.]{1,40})",
        re.IGNORECASE,
    ),
]

_GENRE_INLINE = re.compile(
    r"жанр[еа]?\s+([A-Za-zА-Яа-яЁё\-]+)",
    re.IGNORECASE,
)

_BACKING_MARKERS = (
    "подпевк",
    "подпек",  # опечатка «подпеках» без «в»
    "бэк-вокал",
    "бэк вокал",
    "бэков",
    "бек-вокал",  # без ъ
    "бек вокал",
    "бек вокал",
    "backing vocal",
    "backing vocals",
    "гармони",
    "хор на припев",
)

_STOP_WORDS = frozenset(
    {
        "песня",
        "песню",
        "трек",
        "композици",
        "музык",
        "звучан",
        "стиль",
        "стиле",
        "жанре",
        "жанр",
        "про",
        "о",
        "на",
        "с",
        "и",
        "в",
        "как",
        "у",
        "the",
        "a",
        "an",
    }
)


@dataclass
class ParsedIdea:
    genre: str = ""
    artist_ref: str = ""
    mood: str = ""
    vocal_hint: str = ""  # lead: male | female | duet | auto
    backing_vocal: bool = False
    backing_vocal_gender: str = ""  # f | m | ""
    female_lead_explicit: bool = False
    male_lead_explicit: bool = False
    # True если в тексте явно «жанр реп» / «жанр: rock» — важнее чипа UI
    genre_inline_lock: bool = False
    locked_fields: list[str] = field(default_factory=list)

    @property
    def has_locked_genre(self) -> bool:
        return bool(self.genre.strip())

    @property
    def has_locked_artist(self) -> bool:
        return bool(self.artist_ref.strip())


def _clean_artist_name(raw: str) -> str:
    name = raw.strip().strip("«»\"'.,")
    name = re.sub(
        r"\s+(про|о|на|с|и|жанр|стиль|песня|трек).*$",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()
    if len(name) < 2:
        return ""
    lower = name.lower()
    if any(lower.startswith(w) or lower == w for w in _STOP_WORDS):
        return ""
    return name[:60]


def _find_genre_keyword(text: str) -> tuple[str, bool]:
    """Возвращает (жанр_UI, inline_lock). inline_lock = явное «жанр …» в тексте."""
    lower = text.lower()
    inline = _GENRE_INLINE.search(text)
    if inline:
        token = inline.group(1).strip().lower()
        for keyword, genre_ui in _GENRE_KEYWORDS:
            if token == keyword or token.startswith(keyword):
                return genre_ui, True
        resolved, _ = resolve_genre(token, text)
        if resolved:
            # resolve может вернуть English — нормализуем если есть в UI map
            for key, val in (
                ("hip-hop", "Реп"),
                ("hip hop", "Реп"),
                ("pop", "Поп"),
                ("rock", "Рок"),
            ):
                if resolved.lower() == key:
                    return val, True
            return resolved, True

    best_pos = len(lower) + 1
    best_genre = ""
    for keyword, genre_ui in _GENRE_KEYWORDS:
        pos = lower.find(keyword)
        if pos != -1 and pos < best_pos:
            best_pos = pos
            best_genre = genre_ui
    return best_genre, False


def _find_mood(text: str) -> str:
    lower = text.lower()
    for keyword, mood in _MOOD_KEYWORDS:
        if keyword in lower:
            return mood
    return ""


def _find_artist(text: str) -> str:
    for pattern in _ARTIST_PATTERNS:
        match = pattern.search(text)
        if match:
            name = _clean_artist_name(match.group(1))
            if name:
                return name
    return ""


def _is_backing_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 30) : min(len(text), end + 40)].lower()
    return any(marker in window for marker in _BACKING_MARKERS)


def _detect_vocals(text: str) -> tuple[str, bool, str, bool, bool]:
    """Returns lead hint, backing, backing gender, female_lead_explicit, male_lead_explicit."""
    lower = text.lower()
    backing = any(marker in lower for marker in _BACKING_MARKERS)

    backing_gender = ""
    if backing:
        if re.search(
            r"женск\w*.*(?:подпев|бэк|бек)|female.*backing|backing.*female",
            lower,
        ):
            backing_gender = "f"
        elif re.search(
            r"мужск\w*.*(?:подпев|бэк|бек)|male.*backing|backing.*male",
            lower,
        ):
            backing_gender = "m"

    female_lead = False
    male_lead = False
    lead_hint = ""

    for match in re.finditer(
        r"(женск\w*|female)\s+(?:голос|вокал|исполн)",
        lower,
    ):
        if not _is_backing_context(text, match.start(), match.end()):
            female_lead = True
            lead_hint = "female"
            break

    for match in re.finditer(
        r"(мужск\w*|male)\s+(?:голос|вокал|исполн)",
        lower,
    ):
        if not _is_backing_context(text, match.start(), match.end()):
            male_lead = True
            lead_hint = "male"
            break

    if re.search(r"женск\w*\s+голос\s+на\s+подпевк", lower):
        backing = True
        backing_gender = backing_gender or "f"
        if not female_lead:
            lead_hint = ""

    if re.search(r"дуэт|duet", lower):
        lead_hint = "duet"

    return lead_hint, backing, backing_gender, female_lead, male_lead


def parse_idea(idea: str) -> ParsedIdea:
    text = (idea or "").strip()
    if not text:
        return ParsedIdea()

    result = ParsedIdea()
    locked: list[str] = []

    genre, genre_inline = _find_genre_keyword(text)
    result.genre_inline_lock = genre_inline
    if not genre:
        genre_en, _ = infer_genre_from_idea(text)
        lower = text.lower()
        if any(k in lower for k in ("рэп", "реп", "rap", "хип-хоп", "хип хоп", "hip-hop", "hip hop")):
            genre = "Реп"
        elif genre_en and genre_en.lower() != "pop":
            # Любой распознанный жанр (Rock, Jazz, Metal…) — не только реп
            genre = genre_en
    if genre:
        result.genre = genre
        locked.append("genre")

    artist = _find_artist(text)
    if artist:
        result.artist_ref = artist
        locked.append("artist")

    mood = _find_mood(text)
    if mood:
        result.mood = mood
        locked.append("mood")
    elif not mood:
        inferred_mood = infer_mood_from_idea(text)
        if inferred_mood != "uplifting":
            result.mood = inferred_mood
            locked.append("mood")

    (
        lead_hint,
        backing,
        backing_gender,
        female_lead,
        male_lead,
    ) = _detect_vocals(text)
    if lead_hint:
        result.vocal_hint = lead_hint
        locked.append("vocal")
    if backing:
        result.backing_vocal = True
        locked.append("backing")
    if backing_gender:
        result.backing_vocal_gender = backing_gender
    result.female_lead_explicit = female_lead
    result.male_lead_explicit = male_lead

    result.locked_fields = locked
    return result


def is_rap_genre(genre_ui: str, genre_en: str = "") -> bool:
    combined = f"{genre_ui} {genre_en}".lower()
    return any(
        token in combined
        for token in ("реп", "рэп", "rap", "hip-hop", "hip hop", "трэп", "trap", "дрилл", "drill")
    )


def apply_rap_lead_default(
    vocal_hint: str,
    *,
    genre_ui: str,
    genre_en: str,
    female_lead_explicit: bool,
) -> str:
    if vocal_hint and vocal_hint != "auto":
        return vocal_hint
    if female_lead_explicit:
        return "female"
    if is_rap_genre(genre_ui, genre_en):
        return "male"
    return vocal_hint or "auto"


def _genres_conflict(ui_genre: str, idea_genre: str) -> bool:
    """True если UI и идея указывают разные жанры (Поп vs Реп/Рок/Джаз…)."""
    if not ui_genre.strip() or not idea_genre.strip():
        return False
    ui_en, _ = resolve_genre(ui_genre, "")
    idea_en, _ = resolve_genre(idea_genre, "")
    return ui_en.lower() != idea_en.lower()


def _is_sticky_default_pop(ui_genre: str) -> bool:
    """Дефолт студии selectedGenre=Поп — не должен затирать жанр из текста идеи."""
    g = ui_genre.strip().lower()
    return g in {"поп", "pop", "modern pop"}


def merge_parsed_with_request(
    parsed: ParsedIdea,
    *,
    genre: str = "",
    mood: str = "",
    artist_ref: str = "",
    vocal_hint: str = "",
    backing_vocal: bool = False,
) -> tuple[str, str, str, str, bool, str, ParsedIdea]:
    """Слияние UI и текста идеи (универсально для любого жанра).

    Приоритет жанра:
    1) Явное «жанр …» в идее (genre_inline_lock) — важнее чипа UI.
    2) Жанр из ключевых слов идеи (рок/джаз/реп/…) — важнее *дефолтного* Поп UI
       (липкий selectedGenre=Поп не должен ломать описание пользователя).
    3) Явный чип UI (не дефолт-поп, или совпадает с идеей) — для Расширенного режима.
    4) Иначе — жанр из идеи / пусто.
    """
    ui_genre = genre.strip()
    idea_genre = parsed.genre.strip()

    if idea_genre and ui_genre and _genres_conflict(ui_genre, idea_genre):
        if parsed.genre_inline_lock or _is_sticky_default_pop(ui_genre):
            effective_genre = idea_genre
        else:
            # Пользователь явно выбрал другой чип (Рок, Джаз…) — чип важнее
            effective_genre = ui_genre
    elif ui_genre:
        effective_genre = ui_genre
    else:
        effective_genre = idea_genre

    effective_artist = artist_ref.strip() if artist_ref.strip() else parsed.artist_ref
    effective_mood = mood.strip() if mood.strip() else parsed.mood
    effective_vocal = (
        vocal_hint.strip()
        if vocal_hint.strip() and vocal_hint.strip() != "auto"
        else (parsed.vocal_hint or vocal_hint.strip())
    )
    effective_backing = backing_vocal or parsed.backing_vocal
    backing_gender = parsed.backing_vocal_gender

    if effective_genre:
        parsed.genre = effective_genre
        if "genre" not in parsed.locked_fields:
            parsed.locked_fields.append("genre")
    if artist_ref.strip():
        parsed.artist_ref = effective_artist
        if "artist" not in parsed.locked_fields:
            parsed.locked_fields.append("artist")
    if mood.strip():
        parsed.mood = effective_mood
        if "mood" not in parsed.locked_fields:
            parsed.locked_fields.append("mood")

    genre_en = ""
    if effective_genre:
        genre_en, _ = resolve_genre(effective_genre, "")

    effective_vocal = apply_rap_lead_default(
        effective_vocal,
        genre_ui=effective_genre,
        genre_en=genre_en,
        female_lead_explicit=parsed.female_lead_explicit,
    )

    return (
        effective_genre,
        effective_mood,
        effective_artist,
        effective_vocal,
        effective_backing,
        backing_gender,
        parsed,
    )