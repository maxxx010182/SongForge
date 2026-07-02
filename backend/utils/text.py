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
    "[куплет",
    "[припев",
    "[бридж",
    "[аутро",
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
    if len(idea_norm) >= 16 and idea_norm in _normalize_phrase(text):
        return True

    idea_words = [w for w in re.findall(r"[а-яёa-z]{3,}", idea_norm, re.IGNORECASE)]
    if len(idea_words) >= 2:
        matched = sum(1 for w in idea_words if w in lower)
        if matched / len(idea_words) >= 0.5:
            return True

    body_lines = _lyric_body_lines(text)
    if body_lines:
        first_line_norm = _normalize_phrase(body_lines[0])
        if len(idea_norm) >= 12 and (
            idea_norm in first_line_norm or first_line_norm in idea_norm
        ):
            return True
        if len(idea_words) >= 2:
            first_words = re.findall(r"[а-яёa-z]{3,}", first_line_norm, re.IGNORECASE)
            if first_words:
                overlap = sum(1 for w in idea_words if w in first_words)
                if overlap / len(idea_words) >= 0.6:
                    return True

    return False


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