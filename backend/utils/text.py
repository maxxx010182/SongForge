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