from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import requests
import random
import time
import os
import uvicorn

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

YANDEX_API_KEY   = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "b1gto6f1fi6j2dpfdlhd")
APIPASS_API_KEY  = os.getenv("APIPASS_API_KEY", "")
APIPASS_BASE     = "https://api.apipass.dev/api/v1/jobs"


def yandex_gpt(system_prompt: str, user_text: str, max_tokens: int = 400, temperature: float = 0.7) -> str:
    """Универсальный вызов YandexGPT"""
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {"temperature": temperature, "maxTokens": max_tokens},
        "messages": [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": user_text}
        ]
    }
    response = requests.post(url, headers=headers, json=body, timeout=30)
    response.raise_for_status()
    return response.json()["result"]["alternatives"][0]["message"]["text"].strip()


def clean_text(text: str) -> str:
    """Убираем markdown-обёртки"""
    text = text.strip()
    for marker in ["```python", "```json", "```"]:
        if text.startswith(marker):
            text = text[len(marker):]
        if text.endswith(marker):
            text = text[:-len(marker)]
    return text.strip()


# ============================================================
# ШАГ 1: ГЕНЕРАЦИЯ ТЕКСТА ПЕСНИ
# ============================================================
class LyricsRequest(BaseModel):
    prompt: str
    genre: str
    mood: str
    vocal: str = "auto"


@app.post("/api/generate-lyrics")
async def generate_lyrics_endpoint(req: LyricsRequest):
    try:
        system_prompt = (
            f"Ты поэт-песенник. Напиши текст песни на русском языке в жанре {req.genre}, "
            f"настроение: {req.mood}. Тема песни: {req.prompt}. "
            f"Структура: [Verse 1], [Chorus], [Verse 2], [Chorus], [Outro]. "
            f"Выведи только сам текст песни со структурными тегами, без пояснений, "
            f"без markdown, без блоков кода, без тройных кавычек."
        )
        lyrics = yandex_gpt(system_prompt, req.prompt, max_tokens=600)
        lyrics = clean_text(lyrics)
        return {"success": True, "lyrics": lyrics}
    except Exception as e:
        print("Ошибка генерации текста:", e)
        fallback = (
            f"[Verse 1]\n{req.prompt}\n\n"
            f"[Chorus]\nЭто твоя песня\nТвой момент настал\n\n"
            f"[Outro]\nНавсегда."
        )
        return {"success": False, "lyrics": fallback}


# ============================================================
# ШАГ 2: ГЕНЕРАЦИЯ КАЧЕСТВЕННОГО STYLE ПРОМТА
# ============================================================
class StyleRequest(BaseModel):
    genre: str        # английский жанр
    mood: str         # английское настроение
    artist_ref: str = ""  # референс исполнителя (необязательно)
    vocal: str = "auto"
    backing: bool = False


@app.post("/api/generate-style")
async def generate_style_endpoint(req: StyleRequest):
    """Генерируем качественный style prompt через YandexGPT"""
    try:
        artist_part = ""
        if req.artist_ref.strip():
            artist_part = f"Пользователь хочет звучание похожее на исполнителя/группу: '{req.artist_ref}'. "

        system_prompt = (
            "Ты эксперт по музыкальному производству и звукорежиссуре. "
            "Составь детальный style prompt для AI музыкального генератора Suno на английском языке. "
            "Опиши: темп (BPM), тональность, инструменты, тембр вокала, характер аранжировки, "
            "производственные приёмы, динамику, атмосферу. "
            "ВАЖНО: НЕ упоминай имена артистов, групп или исполнителей — только музыкальные характеристики. "
            "Ответ должен быть одной строкой через запятую, максимум 180 символов, только на английском."
        )
        user_text = (
            f"Жанр: {req.genre}. Настроение: {req.mood}. {artist_part}"
            f"Вокал: {req.vocal}."
        )
        style = yandex_gpt(system_prompt, user_text, max_tokens=200, temperature=0.6)
        style = clean_text(style)

        # Добавляем бэк-вокал и дуэт если нужно
        if req.backing:
            style += ", with backing vocals, harmonies"
        if req.vocal == "duet":
            style += ", male and female duet vocals"

        # Ограничиваем длину
        if len(style) > 950:
            style = style[:950]

        return {"success": True, "style": style}
    except Exception as e:
        print("Ошибка генерации style:", e)
        # Фоллбэк — простой промт
        style = f"{req.genre}, {req.mood}"
        if req.backing:
            style += ", with backing vocals, harmonies"
        if req.vocal == "duet":
            style += ", male and female duet vocals"
        return {"success": False, "style": style}


# ============================================================
# ШАГ 3: ГЕНЕРАЦИЯ МУЗЫКИ через APIPASS / Suno V5_5
# ============================================================
class MusicRequest(BaseModel):
    lyrics: str
    style: str        # готовый style prompt (сформированный на фронте или через /api/generate-style)
    vocal: str = "auto"
    idea: str = ""    # идея пользователя для title


def get_vocal_gender(vocal: str):
    if vocal == "male":
        return "m"
    elif vocal == "female":
        return "f"
    return None


def start_apipass_generation(lyrics: str, style: str, vocal: str, idea: str = ""):
    lyrics = clean_text(lyrics)

    headers = {
        "Authorization": f"Bearer {APIPASS_API_KEY}",
        "Content-Type": "application/json"
    }

    title = idea[:75].strip() if idea else "My Song"

    input_data = {
        "model_version": "V5_5",
        "customMode": True,
        "instrumental": False,
        "prompt": lyrics,
        "style": style,
        "title": title,
        "negativeTags": "low quality, distorted, noise, spoken word, mumbling",
    }

    vocal_gender = get_vocal_gender(vocal)
    if vocal_gender:
        input_data["vocalGender"] = vocal_gender

    payload = {
        "model": "suno/generate",
        "input": input_data,
        "channel": "auto"
    }

    print(f"APIPASS запрос: style='{style[:80]}...', vocal={vocal_gender}, lyrics_len={len(lyrics)}")

    try:
        resp = requests.post(
            f"{APIPASS_BASE}/createTask",
            headers=headers,
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"APIPASS ответ: {data}")
        task_id = data.get("data", {}).get("taskId")
        print(f"APIPASS задача создана: {task_id}")
        return task_id
    except Exception as e:
        print(f"Ошибка запуска APIPASS: {e}")
        try:
            print(f"Ответ сервера: {e.response.text}")
        except Exception:
            pass
        return None


def poll_apipass_result(task_id: str, max_wait: int = 360):
    if not task_id:
        return None, None

    headers = {"Authorization": f"Bearer {APIPASS_API_KEY}"}
    waited = 0

    while waited < max_wait:
        time.sleep(10)
        waited += 10
        try:
            resp = requests.get(
                f"{APIPASS_BASE}/recordInfo",
                headers=headers,
                params={"taskId": task_id},
                timeout=20
            )
            data = resp.json()
            inner = data.get("data", {})
            state = inner.get("state", "").lower()
            print(f"APIPASS [{task_id[:8]}] state={state} (прошло {waited}с)")

            if state == "success":
                result = inner.get("resultJson", {}) or {}
                songs = result.get("data", [])
                if isinstance(songs, list) and len(songs) >= 2:
                    url_a = songs[0].get("audio_url")
                    url_b = songs[1].get("audio_url")
                    dur_a = songs[0].get("duration", 0)
                    dur_b = songs[1].get("duration", 0)
                    print(f"APIPASS готово: {url_a} ({dur_a}s), {url_b} ({dur_b}s)")
                    return url_a, url_b
                elif isinstance(songs, list) and len(songs) == 1:
                    url = songs[0].get("audio_url")
                    return url, url
                return None, None

            if state == "fail":
                fail_code = inner.get("failCode", "")
                fail_msg = inner.get("failMsg", "")
                print(f"APIPASS FAIL: {fail_code} — {fail_msg}")
                return None, None

        except Exception as e:
            print(f"Ошибка опроса APIPASS: {e}")

    print(f"APIPASS timeout для {task_id} после {max_wait}с")
    return None, None


@app.post("/api/generate-music")
async def generate_music_endpoint(req: MusicRequest):
    task_id = start_apipass_generation(req.lyrics, req.style, req.vocal, idea=req.idea)
    url_a, url_b = poll_apipass_result(task_id)

    fallback_used = False
    if not url_a:
        url_a = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3"
        fallback_used = True
    if not url_b:
        url_b = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3"
        fallback_used = True

    return {
        "success": not fallback_used,
        "track_id": random.randint(1000, 9999),
        "music_url": url_a,
        "music_url_b": url_b
    }


@app.get("/")
async def get_index():
    return FileResponse("index.html")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
