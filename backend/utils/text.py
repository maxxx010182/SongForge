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