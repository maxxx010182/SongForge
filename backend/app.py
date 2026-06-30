from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.logger import log
from backend.models import (
    ConsultantRequest,
    ConsultantResponse,
    CreateSongRequest,
    CreateSongResponse,
    LyricsRequest,
    MusicRequest,
    MusicStartRequest,
    MusicStatusResponse,
    ProduceRequest,
    ProduceResponse,
    StyleRequest,
)
from backend.services.ai_producer import AiProducer
from backend.services.apipass_client import ApiPassClient
from backend.services.consultant import ConsultantService
from backend.services.history import HistoryService
from backend.services.prompt_builder import PromptBuilder
from backend.services.yandex_client import YandexClient
from backend.settings import ROOT_DIR
from backend.utils.text import clean_text, truncate

producer = AiProducer()
apipass = ApiPassClient()
history = HistoryService()
consultant = ConsultantService()
yandex = YandexClient()
prompt_builder = PromptBuilder(yandex)

app = FastAPI(title="SongForge", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def get_index():
    return FileResponse(ROOT_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "SongForge", "version": "2.0.0"}


@app.post("/api/produce", response_model=ProduceResponse)
async def produce_song(req: ProduceRequest):
    try:
        return producer.produce(
            req.idea,
            genre=req.genre,
            mood=req.mood,
            artist_ref=req.artist_ref,
            instrumental=req.instrumental,
            vocal_hint=req.vocal_hint,
            backing_vocal=req.backing_vocal,
            style_mode=req.style_mode,
            custom_description=req.custom_description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("produce failed")
        raise HTTPException(status_code=500, detail="AI-продюсер временно недоступен") from exc


@app.post("/api/create-song", response_model=CreateSongResponse)
async def create_song(req: CreateSongRequest):
    try:
        return producer.create_song(
            req.idea,
            genre=req.genre,
            mood=req.mood,
            artist_ref=req.artist_ref,
            instrumental=req.instrumental,
            vocal_hint=req.vocal_hint,
            backing_vocal=req.backing_vocal,
            style_mode=req.style_mode,
            custom_description=req.custom_description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("create-song failed")
        raise HTTPException(status_code=500, detail="Не удалось запустить создание песни") from exc


@app.post("/api/music/start")
async def start_music(req: MusicStartRequest):
    try:
        task_id = producer.start_music(
            production_id=req.production_id,
            lyrics=req.lyrics,
            style=req.style,
            title=req.title,
            plan=req.plan,
            idea=req.idea,
        )
        return {"success": True, "task_id": task_id, "production_id": req.production_id}
    except Exception as exc:
        log.exception("music start failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/music/status/{task_id}", response_model=MusicStatusResponse)
async def music_status(task_id: str):
    try:
        status = apipass.get_status(task_id)
        state = status["state"]
        tracks = status["tracks"]
        production = history.get_by_task(task_id) or {}
        production_id = production.get("id", "")

        if state == "success" and tracks:
            history.update_task_result(task_id=task_id, status="success", tracks=tracks)
            return MusicStatusResponse(
                success=True,
                task_id=task_id,
                state=state,
                progress_hint=status["progress_hint"],
                tracks=tracks,
                production_id=production_id,
            )

        if state in {"fail", "failed"}:
            history.update_task_result(
                task_id=task_id,
                status="failed",
                tracks=[],
                fail_code=status.get("fail_code", ""),
                fail_msg=status.get("fail_msg", ""),
            )
            return MusicStatusResponse(
                success=False,
                task_id=task_id,
                state="failed",
                progress_hint=status["progress_hint"],
                fail_code=status.get("fail_code", ""),
                fail_msg=status.get("fail_msg", "") or "Suno не смогла создать трек",
                production_id=production_id,
            )

        return MusicStatusResponse(
            success=False,
            task_id=task_id,
            state=state,
            progress_hint=status["progress_hint"],
            production_id=production_id,
        )
    except Exception as exc:
        log.exception("music status failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/consultant/chat", response_model=ConsultantResponse)
async def consultant_chat(req: ConsultantRequest):
    try:
        reply = consultant.reply(req.message, req.context)
        return ConsultantResponse(success=True, reply=reply)
    except Exception as exc:
        log.exception("consultant failed")
        return ConsultantResponse(
            success=False,
            reply="Сейчас не могу ответить. Попробуйте переформулировать вопрос.",
        )


@app.post("/api/generate-lyrics")
async def generate_lyrics_endpoint(req: LyricsRequest):
    plan = prompt_builder._fallback_plan(req.prompt, vocal_hint=req.vocal)
    plan.genre = req.genre
    plan.mood = req.mood
    plan.vocal = req.vocal
    try:
        lyrics = prompt_builder.generate_lyrics(req.prompt, plan)
        return {"success": True, "lyrics": lyrics}
    except Exception as exc:
        log.exception("legacy lyrics failed")
        return {"success": False, "lyrics": prompt_builder._fallback_lyrics(req.prompt)}


@app.post("/api/generate-style")
async def generate_style_endpoint(req: StyleRequest):
    custom_mode = req.style_mode == "custom" and req.custom_description.strip()
    if custom_mode:
        plan = prompt_builder.build_plan(
            req.custom_description,
            vocal_hint=req.vocal,
            style_mode="custom",
            custom_description=req.custom_description,
        )
    else:
        plan = prompt_builder._fallback_plan("", vocal_hint=req.vocal)
        plan.genre = req.genre
        plan.mood = req.mood
        plan.vocal = req.vocal
    try:
        style = prompt_builder.build_style_via_ai(
            plan,
            artist_ref=req.artist_ref,
            style_mode=req.style_mode,
            custom_description=req.custom_description,
        )
        if req.backing:
            style += ", with backing vocals, harmonies"
        if req.vocal == "duet":
            style += ", male and female duet vocals"
        return {"success": True, "style": truncate(style, 950)}
    except Exception as exc:
        log.exception("legacy style failed")
        style = f"{req.genre}, {req.mood}"
        return {"success": False, "style": style}


@app.post("/api/generate-music")
async def generate_music_endpoint(req: MusicRequest):
    """Legacy endpoint: returns task_id immediately for polling."""
    from backend.models import ProductionPlan

    plan_data = req.plan or {}
    if plan_data:
        plan = ProductionPlan.model_validate(plan_data)
    else:
        plan = prompt_builder._fallback_plan(req.idea, vocal_hint=req.vocal)

    title = req.title or truncate(req.idea or "My Song", 75)
    try:
        task_id = apipass.create_task(
            lyrics=req.lyrics,
            style=req.style,
            title=title,
            plan=plan,
        )
        return {
            "success": True,
            "task_id": task_id,
            "message": "Используйте GET /api/music/status/{task_id} для проверки статуса",
        }
    except Exception as exc:
        log.exception("legacy generate-music failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc