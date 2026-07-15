import json
import re


def clean_text(text: str) -> str:
    text = text.strip()
    for marker in ("```python", "```json", "```"):
        if text.startswith(marker):
            text = text[len(marker):]
        if text.endswith(marker):
            text = text[:-len(marker)]
    return text.strip()


def extract_json(text: str) -> dict:
    text = clean_text(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("JSON not found in model response")
        return json.loads(match.group(0))


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


_RUSSIAN_VOCAL_MARKERS = (
    "russian vocal",
    "sung in russian",
    "russian lyrics",
    "singing in russian",
)


_STRUCTURE_TAGS = (
    "[verse",
    "[chorus",
    "[bridge",
    "[outro",
    "[pre-chorus",
    "[intro",
    "[final chorus",
    "[куплет",
    "[припев",
    "[бридж",
    "[аутро",
)

_SHORT_SONG_MARKERS = (
    "детск",
    "kids",
    "children",
    "сказк",
    "колыбел",
    "lullaby",
    "для малыш",
    "для ребён",
    "для ребен",
)


def _normalize_phrase(text: str) -> str:
    lowered = re.sub(r"[^\wа-яё\s]", " ", text.lower(), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", lowered).strip()


def _lyric_body_lines(lyrics: str) -> list[str]:
    lines: list[str] = []
    for raw in lyrics.splitlines():
        line = raw.strip()
        if not line or line.startswith("["):
            continue
        lines.append(line)
    return lines


def idea_allows_short_song(idea: str) -> bool:
    """Детские/колыбельные — короче; остальные целимся в ~4 минуты."""
    blob = (idea or "").lower()
    return any(m in blob for m in _SHORT_SONG_MARKERS)


def lyrics_look_incomplete(lyrics: str, idea: str = "") -> bool:
    """True: слишком короткий текст или нет полноценной формы песни (~4 мин)."""
    text = clean_text(lyrics)
    if not text:
        return True
    lower = text.lower()
    short_ok = idea_allows_short_song(idea)
    min_len = 700 if short_ok else 1400
    if len(text) < min_len:
        return True
    if "[verse" not in lower or "[chorus" not in lower:
        return True
    if short_ok:
        return False
    verse_n = lower.count("[verse")
    chorus_n = lower.count("[chorus") + lower.count("[final chorus")
    has_bridge = "[bridge" in lower
    # Полная форма: 2 куплета + повтор припева, либо куплет+bridge+2 chorus
    if verse_n < 2 and not has_bridge:
        return True
    if chorus_n < 2 and not has_bridge:
        return True
    body = _lyric_body_lines(text)
    if len(body) < 16:
        return True
    return False


def lyrics_look_lazy(lyrics: str, idea: str) -> bool:
    """True when lyrics look like a copied user description, not a real song."""
    text = clean_text(lyrics)
    if not text:
        return True
    if len(text) < 80:
        return True
    lower = text.lower()
    if not any(tag in lower for tag in _STRUCTURE_TAGS):
        return True

    idea_norm = _normalize_phrase(idea)
    # Целый бриф вставлен в текст — явный «что вижу то пою»
    if len(idea_norm) >= 16 and idea_norm in _normalize_phrase(text):
        return True

    idea_words = [w for w in re.findall(r"[а-яёa-z]{3,}", idea_norm, re.IGNORECASE)]
    # Слова из брифа (имена, места) в песне — нормально.
    # Lazy только если почти весь бриф «протащен» и текст всё ещё короткий/плоский.
    if len(idea_words) >= 4 and len(text) < 500:
        matched = sum(1 for w in idea_words if w in lower)
        if matched / len(idea_words) >= 0.85:
            return True

    body_lines = _lyric_body_lines(text)
    if body_lines:
        first_line_norm = _normalize_phrase(body_lines[0])
        if len(idea_norm) >= 12 and (
            idea_norm in first_line_norm or first_line_norm in idea_norm
        ):
            return True
        if len(idea_words) >= 3:
            first_words = re.findall(r"[а-яёa-z]{3,}", first_line_norm, re.IGNORECASE)
            if first_words and len(first_line_norm) >= 20:
                overlap = sum(1 for w in idea_words if w in first_words)
                if overlap / len(idea_words) >= 0.7:
                    return True

    return False


_EXPLICIT_LYRICS_LANG = (
    (r"(?:на|in)\s+английск|по-английски|english\s+lyrics|song\s+in\s+english|lyrics\s+in\s+english", "en", "английском"),
    (r"(?:на|in)\s+арабск|по-арабски|arabic\s+lyrics|song\s+in\s+arabic", "ar", "арабском"),
    (r"(?:на|in)\s+испанск|spanish\s+lyrics|song\s+in\s+spanish", "es", "испанском"),
    (r"(?:на|in)\s+французск|french\s+lyrics|song\s+in\s+french", "fr", "французском"),
    (r"(?:на|in)\s+немецк|german\s+lyrics|song\s+in\s+german", "de", "немецком"),
    (r"(?:на|in)\s+китайск|chinese\s+lyrics|song\s+in\s+chinese", "zh", "китайском"),
    (r"(?:на|in)\s+турецк|turkish\s+lyrics|song\s+in\s+turkish", "tr", "турецком"),
)


def resolve_lyrics_language(idea: str) -> tuple[str, str, bool]:
    """
    Язык текста песни из идеи пользователя.
    Возвращает (код, подпись для промпта, is_default_ru).
    По умолчанию — русский, если пользователь явно не попросил другой язык.
    """
    text = (idea or "").lower()
    for pattern, code, label in _EXPLICIT_LYRICS_LANG:
        if re.search(pattern, text, re.IGNORECASE):
            return code, label, False
    return "ru", "русском", True


def idea_looks_russian(text: str) -> bool:
    """True when lyrics should be Russian (default or Russian prompt)."""
    code, _, _ = resolve_lyrics_language(text)
    if code != "ru":
        return False
    if not text.strip():
        return True
    cyrillic = len(re.findall(r"[а-яё]", text.lower()))
    latin = len(re.findall(r"[a-z]", text.lower()))
    if cyrillic == 0 and latin > 0:
        return False
    return cyrillic >= latin or cyrillic >= 8


def lyrics_language_instruction(idea: str) -> str:
    """Строка для промпта: на каком языке писать строки песни."""
    code, label, is_default = resolve_lyrics_language(idea)
    if code == "ru":
        return (
            "ОБЯЗАТЕЛЬНО: все строки песни (куплеты, припев, бридж, финал) только на русском. "
            "Структурные теги [Verse 1], [Chorus], [Bridge], [Outro] — на английском (требование Suno)."
        )
    return (
        f"ОБЯЗАТЕЛЬНО: пользователь просит текст на {label} языке — все строки песни только на нём. "
        "Структурные теги [Verse 1], [Chorus], [Bridge], [Outro] — на английском (требование Suno)."
        + (" Это явный запрос, не переводить на русский." if not is_default else "")
    )


def lyrics_look_english(lyrics: str) -> bool:
    """True when lyric lines are mostly English, not Russian."""
    body = _lyric_body_lines(lyrics)
    if not body:
        return False
    joined = " ".join(body)
    cyrillic = len(re.findall(r"[а-яё]", joined.lower()))
    latin_words = re.findall(r"\b[a-z]{2,}\b", joined.lower())
    if not latin_words:
        return False
    if cyrillic >= len(latin_words) * 3:
        return False
    if len(latin_words) >= 6 and cyrillic < 12:
        return True
    latin_chars = len(re.findall(r"[a-z]", joined.lower()))
    return latin_chars > cyrillic * 2


def scrub_idea_echo_from_lyrics(lyrics: str, idea: str) -> str:
    """Remove lines that repeat the user's prompt verbatim."""
    if not lyrics.strip() or not idea.strip():
        return lyrics

    idea_norm = _normalize_phrase(idea)
    idea_words = [w for w in re.findall(r"[а-яёa-z]{3,}", idea_norm, re.IGNORECASE)]
    kept: list[str] = []

    for raw in lyrics.splitlines():
        line = raw.strip()
        if not line:
            kept.append(raw)
            continue
        if line.startswith("["):
            kept.append(raw)
            continue

        line_norm = _normalize_phrase(line)
        if len(idea_norm) >= 12 and (
            idea_norm in line_norm or line_norm in idea_norm
        ):
            continue
        if len(idea_words) >= 2:
            line_words = re.findall(r"[а-яёa-z]{3,}", line_norm, re.IGNORECASE)
            if line_words:
                overlap = sum(1 for w in idea_words if w in line_words)
                if overlap / len(idea_words) >= 0.65:
                    continue
        kept.append(raw)

    cleaned = "\n".join(kept).strip()
    if len(_lyric_body_lines(cleaned)) >= 4:
        return cleaned
    return lyrics


def ensure_russian_vocal_style(style: str) -> str:
    """Prefix English style with Russian vocal directive for Suno custom mode."""
    cleaned = style.strip()
    if not cleaned:
        return "sung in Russian, native Russian vocals, clear Russian pronunciation"
    lower = cleaned.lower()
    if any(marker in lower for marker in _RUSSIAN_VOCAL_MARKERS):
        return cleaned
    return (
        "sung in Russian, native Russian vocals, clear Russian pronunciation, "
        + cleaned
    )