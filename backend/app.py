from fastapi import Cookie, Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.logger import log
from backend.models import (
    ConsultantRequest,
    ConsultantResponse,
    CreateSongRequest,
    CreateSongResponse,
    EmailAuthRequest,
    EmailVerifyRequest,
    HistoryItem,
    HistoryPreviewResponse,
    LibraryItem,
    LyricsRequest,
    MeResponse,
    MusicRequest,
    MusicStartRequest,
    MusicStatusResponse,
    ProduceRequest,
    ProduceResponse,
    PurchaseResponse,
    DevTopupRequest,
    DevTopupResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    StyleRequest,
    TelegramAuthRequest,
    UserInfo,
)
from backend.services.ai_producer import AiProducer
from backend.services.apipass_client import ApiPassClient
from backend.services.auth_service import AuthService
from backend.services.cabinet_service import CabinetService
from backend.services.consultant import ConsultantService
from backend.services.guest_service import GuestService
from backend.services.history import HistoryService
from backend.services.profile_service import ProfileService
from backend.services.prompt_builder import PromptBuilder
from backend.services.yandex_client import YandexClient
from backend.settings import DEV_TOPUP_ENABLED, GUEST_GENERATION_LIMIT, ROOT_DIR, UPLOADS_DIR
from backend.utils.text import clean_text, truncate

producer = AiProducer()
apipass = ApiPassClient()
history = HistoryService()
consultant = ConsultantService()
yandex = YandexClient()
prompt_builder = PromptBuilder(yandex)
guest_service = GuestService()
auth_service = AuthService()
cabinet = CabinetService()
profile_service = ProfileService()

app = FastAPI(title="SongForge", version="2.2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


def _session_cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "max_age": 60 * 60 * 24 * 30,
        "path": "/",
    }


def _guest_cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "max_age": 60 * 60 * 24 * 365,
        "path": "/",
    }


def get_guest_id(
    response: Response,
    sf_guest_id: str | None = Cookie(default=None),
) -> str:
    guest_id = sf_guest_id or guest_service.new_guest_id()
    if not sf_guest_id:
        response.set_cookie(GuestService.COOKIE_NAME, guest_id, **_guest_cookie_kwargs())
    guest_service.touch(guest_id)
    return guest_id


def get_optional_user(
    sf_session: str | None = Cookie(default=None),
) -> dict | None:
    return auth_service.get_user_by_session(sf_session)


def _user_info(user: dict) -> UserInfo:
    return UserInfo(
        id=user["id"],
        email=user.get("email"),
        display_name=user.get("display_name") or "",
        balance=int(user.get("balance") or 0),
        avatar_url=user.get("avatar_url"),
    )


@app.get("/")
async def get_index():
    return FileResponse(ROOT_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "SongForge", "version": "2.2.1"}


@app.get("/api/me", response_model=MeResponse)
async def get_me(
    guest_id: str = Depends(get_guest_id),
    user: dict | None = Depends(get_optional_user),
):
    remaining = guest_service.remaining(guest_id) if not user else GUEST_GENERATION_LIMIT
    return MeResponse(
        logged_in=bool(user),
        user=_user_info(user) if user else None,
        guest_remaining=remaining,
        guest_limit=GUEST_GENERATION_LIMIT,
    )


@app.get("/api/history", response_model=list[HistoryItem])
async def get_history(user: dict | None = Depends(get_optional_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    return cabinet.list_history(user["id"])


@app.get("/api/history/{generation_id}/preview", response_model=HistoryPreviewResponse)
async def get_history_preview(
    generation_id: str,
    variant: str = "a",
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    try:
        return cabinet.get_history_preview(
            user_id=user["id"],
            generation_id=generation_id,
            variant=variant,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/library", response_model=list[LibraryItem])
async def get_library(user: dict | None = Depends(get_optional_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    return cabinet.list_library(user["id"])


@app.post("/api/auth/email/request")
async def auth_email_request(req: EmailAuthRequest):
    try:
        code = auth_service.request_email_code(req.email)
        log.info("Email auth code for %s: %s", req.email, code)
        return {
            "success": True,
            "message": "Код отправлен на email",
            "dev_code": code,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/email/verify")
async def auth_email_verify(
    req: EmailVerifyRequest,
    response: Response,
    guest_id: str = Depends(get_guest_id),
):
    try:
        user, token = auth_service.verify_email_code(req.email, req.code)
        cabinet.link_guest_generations(guest_id=guest_id, user_id=user["id"])
        response.set_cookie(AuthService.COOKIE_NAME, token, **_session_cookie_kwargs())
        return {"success": True, "user": _user_info(user).model_dump()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/telegram")
async def auth_telegram(
    req: TelegramAuthRequest,
    response: Response,
    guest_id: str = Depends(get_guest_id),
):
    try:
        user, token = auth_service.login_telegram(
            telegram_id=req.id,
            first_name=req.first_name,
            username=req.username,
        )
        cabinet.link_guest_generations(guest_id=guest_id, user_id=user["id"])
        response.set_cookie(AuthService.COOKIE_NAME, token, **_session_cookie_kwargs())
        return {"success": True, "user": _user_info(user).model_dump()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/profile", response_model=ProfileUpdateResponse)
async def update_profile(
    req: ProfileUpdateRequest,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    try:
        updated = profile_service.update_display_name(
            user_id=user["id"],
            display_name=req.display_name,
        )
        return ProfileUpdateResponse(success=True, user=_user_info(updated))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/profile/avatar", response_model=ProfileUpdateResponse)
async def upload_profile_avatar(
    file: UploadFile = File(...),
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    content = await file.read()
    try:
        updated = profile_service.save_avatar(
            user_id=user["id"],
            content=content,
            filename=file.filename or "",
            content_type=file.content_type or "",
        )
        return ProfileUpdateResponse(success=True, user=_user_info(updated))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/logout")
async def auth_logout(
    response: Response,
    sf_session: str | None = Cookie(default=None),
):
    if sf_session:
        auth_service.logout(sf_session)
    response.delete_cookie(AuthService.COOKIE_NAME, path="/")
    return {"success": True}


@app.post("/api/purchase/{generation_id}", response_model=PurchaseResponse)
async def purchase_generation(
    generation_id: str,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    try:
        return cabinet.purchase_generation(
            user_id=user["id"],
            generation_id=generation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/dev/topup", response_model=DevTopupResponse)
async def dev_topup(
    req: DevTopupRequest,
    user: dict | None = Depends(get_optional_user),
):
    """Тестовое пополнение баланса (скрытая кнопка в UI)."""
    if not DEV_TOPUP_ENABLED:
        raise HTTPException(status_code=403, detail="Тестовое пополнение отключено")
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Войдите в аккаунт — ноты хранятся на сервере",
        )
    amount = max(1, min(int(req.amount), 100))
    balance = cabinet.add_balance(user["id"], amount)
    log.info("Dev topup: user=%s +%s → balance=%s", user["id"], amount, balance)
    return DevTopupResponse(
        success=True,
        balance=balance,
        message=f"Баланс пополнен на {amount} нот",
    )


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
async def create_song(
    req: CreateSongRequest,
    guest_id: str = Depends(get_guest_id),
    user: dict | None = Depends(get_optional_user),
):
    if not user and not guest_service.can_generate(guest_id):
        raise HTTPException(
            status_code=403,
            detail="Бесплатная генерация использована. Войдите в аккаунт, чтобы продолжить.",
        )

    try:
        producer.set_actor(
            user_id=user["id"] if user else None,
            guest_id=None if user else guest_id,
        )
        result = producer.create_song(
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
        if not user:
            guest_service.consume_generation(guest_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("create-song failed")
        raise HTTPException(status_code=500, detail="Не удалось запустить создание песни") from exc
    finally:
        producer.clear_actor()


@app.post("/api/music/start")
async def start_music(
    req: MusicStartRequest,
    guest_id: str = Depends(get_guest_id),
    user: dict | None = Depends(get_optional_user),
):
    if not user and not guest_service.can_generate(guest_id):
        raise HTTPException(
            status_code=403,
            detail="Бесплатная генерация использована. Войдите в аккаунт, чтобы продолжить.",
        )

    try:
        producer.set_actor(
            user_id=user["id"] if user else None,
            guest_id=None if user else guest_id,
        )
        task_id = producer.start_music(
            production_id=req.production_id,
            lyrics=req.lyrics,
            style=req.style,
            title=req.title,
            plan=req.plan,
            idea=req.idea,
            genre=req.genre,
            mood=req.mood,
            artist_ref=req.artist_ref,
            vocal_hint=req.vocal_hint,
            backing_vocal=req.backing_vocal,
        )
        if not user:
            guest_service.consume_generation(guest_id)
        return {"success": True, "task_id": task_id, "production_id": req.production_id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("music start failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        producer.clear_actor()


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
                fail_msg=status.get("fail_msg", "") or "Не удалось создать трек",
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