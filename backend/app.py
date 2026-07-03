import requests
from fastapi import Cookie, Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.logger import log
from backend.models import (
    ConsultantRequest,
    ConsultantResponse,
    CreatePaymentOrderRequest,
    CreateSongRequest,
    CreateSongResponse,
    DevTopupRequest,
    DevTopupResponse,
    EmailAuthRequest,
    EmailVerifyRequest,
    FullAudioResponse,
    HistoryItem,
    HistoryPreviewResponse,
    LibraryItem,
    LyricsRequest,
    MeResponse,
    MusicRequest,
    MusicStartRequest,
    MusicStatusResponse,
    PaymentOrderResponse,
    PaymentOrderStatusResponse,
    PaymentPackage,
    ProduceRequest,
    ProduceResponse,
    PurchaseResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    StyleRequest,
    TelegramAuthRequest,
    TrackVariant,
    UserInfo,
)
from backend.services.ai_producer import AiProducer
from backend.services.apipass_client import ApiPassClient
from backend.services.audio_access_service import AudioAccessService
from backend.services.auth_service import AuthService
from backend.services.cabinet_service import CabinetService
from backend.services.consultant import ConsultantService
from backend.services.generation_quota_service import GenerationQuotaService
from backend.services.guest_service import GuestService
from backend.services.history import HistoryService
from backend.services.payment_service import PaymentService
from backend.services.profile_service import ProfileService
from backend.services.prompt_builder import PromptBuilder
from backend.services.yandex_client import YandexClient
from backend.settings import (
    AUTH_DEV_CODE_ENABLED,
    SMTP_HOST,
    DEV_TOPUP_ENABLED,
    GUEST_GENERATION_LIMIT,
    LEGACY_API_ENABLED,
    PAYMENT_PROVIDER,
    ROOT_DIR,
    TELEGRAM_AUTH_ENABLED,
    UPLOADS_DIR,
)
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
generation_quota = GenerationQuotaService()
audio_access = AudioAccessService()
payment_service = PaymentService()

app = FastAPI(title="SongForge", version="2.4.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR = ROOT_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


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


def _begin_generation(
    *,
    user: dict | None,
    guest_id: str,
    production_id: str | None = None,
) -> tuple[str, int | None]:
    mode = generation_quota.resolve_mode(user=user, guest_id=guest_id)
    balance = generation_quota.consume_on_start(
        mode=mode,
        user=user,
        guest_id=guest_id,
        production_id=production_id,
    )
    if mode == "paid" and production_id:
        generation_quota.mark_note_charged(production_id)
    return mode, balance


def _generation_error_message(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.Timeout):
        return (
            "Студия не дождалась ответа от сервиса создания музыки. "
            "Попробуйте ещё раз через минуту."
        )
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Нет связи с сервисом создания музыки. Попробуйте позже."
    return "Не удалось создать песню. Попробуйте ещё раз."


def _refund_generation_start(
    *,
    mode: str,
    user: dict | None,
    guest_id: str,
    paid_user_id: str | None,
) -> None:
    if mode == "trial":
        generation_quota.refund_trial_start(user=user, guest_id=guest_id)
    elif paid_user_id:
        generation_quota.refund_paid_start(user_id=paid_user_id)


def _generation_flags(production_id: str) -> tuple[bool, bool]:
    row = history.get_by_id(production_id) if production_id else None
    if not row:
        return False, False
    return bool(row.get("purchased")), bool(row.get("note_charged"))


@app.get("/")
async def get_index():
    return FileResponse(ROOT_DIR / "index.html")


@app.get("/SongForgeLogo.png")
async def get_logo():
    path = ROOT_DIR / "SongForgeLogo.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Logo not found")
    return FileResponse(path, media_type="image/png")


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "SongForge", "version": "2.4.2"}


@app.get("/api/me", response_model=MeResponse)
async def get_me(
    guest_id: str = Depends(get_guest_id),
    user: dict | None = Depends(get_optional_user),
):
    if user:
        remaining = generation_quota.user_trial_remaining(user["id"])
    else:
        remaining = guest_service.remaining(guest_id)
    return MeResponse(
        logged_in=bool(user),
        user=_user_info(user) if user else None,
        guest_remaining=remaining,
        guest_limit=GUEST_GENERATION_LIMIT,
        dev_tools=DEV_TOPUP_ENABLED,
        payment_provider=PAYMENT_PROVIDER,
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


def _expose_email_auth_code() -> bool:
    """Пока SMTP не настроен — код только на экране, не в письме."""
    return AUTH_DEV_CODE_ENABLED or not SMTP_HOST


@app.post("/api/auth/email/request")
async def auth_email_request(req: EmailAuthRequest):
    try:
        code = auth_service.request_email_code(req.email)
        expose_code = _expose_email_auth_code()
        if expose_code:
            log.info("Email auth code for %s: %s", req.email, code)
        payload: dict = {"success": True}
        if expose_code:
            payload["dev_code"] = code
            payload["message"] = "Код показан на экране (почта пока не подключена)"
        else:
            payload["message"] = "Код отправлен на email"
        return payload
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
        generation_quota.sync_guest_trial_on_login(
            guest_id=guest_id, user_id=user["id"]
        )
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
    if not TELEGRAM_AUTH_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Вход через Telegram скоро будет доступен",
        )
    try:
        user, token = auth_service.login_telegram(
            telegram_id=req.id,
            first_name=req.first_name,
            username=req.username,
        )
        cabinet.link_guest_generations(guest_id=guest_id, user_id=user["id"])
        generation_quota.sync_guest_trial_on_login(
            guest_id=guest_id, user_id=user["id"]
        )
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


@app.get("/api/payment/packages", response_model=list[PaymentPackage])
async def list_payment_packages():
    return payment_service.list_packages()


@app.post("/api/payment/create-order", response_model=PaymentOrderResponse)
async def create_payment_order(
    req: CreatePaymentOrderRequest,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    try:
        order = payment_service.create_order(
            user_id=user["id"],
            package_id=req.package_id,
        )
        return PaymentOrderResponse(
            order_id=order["order_id"],
            status=order["status"],
            package=PaymentPackage.model_validate(order["package"]),
            payment_url=order.get("payment_url"),
            provider=order.get("provider", PAYMENT_PROVIDER),
            message=order.get("message", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/payment/orders/{order_id}", response_model=PaymentOrderStatusResponse)
async def get_payment_order(
    order_id: str,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    try:
        order = payment_service.get_order(user_id=user["id"], order_id=order_id)
        from backend.database.db import get_connection

        with get_connection() as conn:
            balance_row = conn.execute(
                "SELECT balance FROM users WHERE id = ?",
                (user["id"],),
            ).fetchone()
        balance = int(balance_row["balance"]) if balance_row else 0
        return PaymentOrderStatusResponse(
            order_id=order["order_id"],
            status=order["status"],
            package=(
                PaymentPackage.model_validate(order["package"])
                if order.get("package")
                else None
            ),
            notes_amount=order.get("notes_amount", 0),
            price_rub=order.get("price_rub", 0),
            provider=order.get("provider", ""),
            paid_at=order.get("paid_at"),
            balance=balance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/payment/webhook/{provider}")
async def payment_webhook(provider: str, payload: dict):
    try:
        result = payment_service.handle_webhook(provider, payload)
        if not result:
            return {"ok": True, "status": "ignored"}
        return {"ok": True, "status": "paid", **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/audio/preview/{production_id}/{variant}")
async def stream_audio_preview(
    production_id: str,
    variant: int,
    guest_id: str = Depends(get_guest_id),
    user: dict | None = Depends(get_optional_user),
):
    row = audio_access.get_generation_row(production_id)
    if not row:
        raise HTTPException(status_code=404, detail="Генерация не найдена")
    audio_access.assert_access(
        row,
        user_id=user["id"] if user else None,
        guest_id=guest_id,
    )
    if row["purchased"]:
        raise HTTPException(status_code=400, detail="Трек уже куплен — откройте фонотеку")
    source = audio_access.resolve_source_url(row, variant)
    return audio_access.stream_preview(source)


@app.get("/api/audio/full/{production_id}/{variant}", response_model=FullAudioResponse)
async def get_full_audio_url(
    production_id: str,
    variant: int,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    row = audio_access.get_generation_row(production_id)
    if not row:
        raise HTTPException(status_code=404, detail="Генерация не найдена")
    audio_access.assert_access(row, user_id=user["id"], guest_id=None)
    if not row["purchased"]:
        raise HTTPException(status_code=403, detail="Сначала купите трек")
    source = audio_access.resolve_source_url(row, variant)
    return FullAudioResponse(
        audio_url=source,
        title=row["title"] or "Без названия",
    )


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
async def produce_song(
    req: ProduceRequest,
    guest_id: str = Depends(get_guest_id),
):
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
    mode = ""
    paid_user_id: str | None = None
    balance: int | None = None
    try:
        mode, balance = _begin_generation(user=user, guest_id=guest_id)
        if user and mode == "paid":
            paid_user_id = user["id"]
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

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
        if mode == "paid" and result.production_id:
            generation_quota.mark_note_charged(result.production_id)
        result.balance = balance
        result.generation_mode = mode
        return result
    except ValueError as exc:
        _refund_generation_start(
            mode=mode, user=user, guest_id=guest_id, paid_user_id=paid_user_id
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _refund_generation_start(
            mode=mode, user=user, guest_id=guest_id, paid_user_id=paid_user_id
        )
        log.exception("create-song failed")
        raise HTTPException(
            status_code=500,
            detail=_generation_error_message(exc),
        ) from exc
    finally:
        producer.clear_actor()


@app.post("/api/music/start")
async def start_music(
    req: MusicStartRequest,
    guest_id: str = Depends(get_guest_id),
    user: dict | None = Depends(get_optional_user),
):
    mode = ""
    paid_user_id: str | None = None
    balance: int | None = None
    try:
        mode, balance = _begin_generation(
            user=user,
            guest_id=guest_id,
            production_id=req.production_id or None,
        )
        if user and mode == "paid":
            paid_user_id = user["id"]
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

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
        return {
            "success": True,
            "task_id": task_id,
            "production_id": req.production_id,
            "balance": balance,
            "generation_mode": mode,
        }
    except ValueError as exc:
        _refund_generation_start(
            mode=mode, user=user, guest_id=guest_id, paid_user_id=paid_user_id
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _refund_generation_start(
            mode=mode, user=user, guest_id=guest_id, paid_user_id=paid_user_id
        )
        log.exception("music start failed")
        raise HTTPException(
            status_code=500,
            detail=_generation_error_message(exc),
        ) from exc
    finally:
        producer.clear_actor()


def _tracks_from_db_row(row) -> list[dict]:
    tracks: list[dict] = []
    pairs = [
        ("music_url_a", "image_url_a", "duration_a"),
        ("music_url_b", "image_url_b", "duration_b"),
    ]
    for idx, (url_key, image_key, duration_key) in enumerate(pairs):
        url = row[url_key] if row[url_key] else ""
        if not url:
            continue
        tracks.append(
            {
                "id": str(idx),
                "audio_url": url,
                "image_url": row[image_key] or "",
                "duration": float(row[duration_key] or 0),
            }
        )
    return tracks


def _music_status_from_db(
    *,
    task_id: str,
    row,
    production_id: str,
) -> MusicStatusResponse | None:
    if not row or row["status"] != "success":
        return None
    if not (row["music_url_a"] or row["music_url_b"]):
        return None
    purchased, prepaid = _generation_flags(production_id)
    safe_tracks = _sanitize_status_tracks(
        _tracks_from_db_row(row),
        production_id=production_id,
        purchased=purchased,
        prepaid=prepaid,
    )
    if not safe_tracks:
        return None
    return MusicStatusResponse(
        success=True,
        task_id=task_id,
        state="success",
        progress_hint="Готово!",
        tracks=safe_tracks,
        production_id=production_id,
        purchased=purchased,
        prepaid=prepaid,
    )


def _sanitize_status_tracks(
    tracks: list[dict],
    *,
    production_id: str,
    purchased: bool,
    prepaid: bool,
) -> list[dict]:
    cleaned = audio_access.sanitize_tracks(
        tracks,
        production_id=production_id,
        purchased=purchased,
        prepaid=prepaid,
    )
    return [TrackVariant.model_validate(item) for item in cleaned]


@app.get("/api/music/status/{task_id}", response_model=MusicStatusResponse)
async def music_status(
    task_id: str,
    guest_id: str = Depends(get_guest_id),
    user: dict | None = Depends(get_optional_user),
):
    try:
        production = history.get_by_task(task_id) or {}
        production_id = production.get("id", "")
        row = None
        if production_id:
            row = audio_access.get_generation_row(production_id)
            audio_access.assert_access(
                row,
                user_id=user["id"] if user else None,
                guest_id=guest_id,
            )
            cached = _music_status_from_db(
                task_id=task_id,
                row=row,
                production_id=production_id,
            )
            if cached:
                return cached

        status = apipass.get_status(task_id)
        state = status["state"]
        tracks = status["tracks"]

        if state == "success" and tracks:
            history.update_task_result(task_id=task_id, status="success", tracks=tracks)
            if production_id:
                cabinet.complete_prepaid_generation(production_id)
            purchased, prepaid = _generation_flags(production_id)
            safe_tracks = _sanitize_status_tracks(
                tracks,
                production_id=production_id,
                purchased=purchased,
                prepaid=prepaid,
            )
            return MusicStatusResponse(
                success=True,
                task_id=task_id,
                state=state,
                progress_hint=status["progress_hint"],
                tracks=safe_tracks,
                production_id=production_id,
                purchased=purchased,
                prepaid=prepaid,
            )

        if state in {"fail", "failed"}:
            history.update_task_result(
                task_id=task_id,
                status="failed",
                tracks=[],
                fail_code=status.get("fail_code", ""),
                fail_msg=status.get("fail_msg", ""),
            )
            if production_id:
                generation_quota.refund_if_charged(
                    production_id=production_id,
                    user_id=production.get("user_id"),
                )
                generation_quota.refund_trial_on_failed(production_id=production_id)
            purchased, prepaid = _generation_flags(production_id)
            return MusicStatusResponse(
                success=False,
                task_id=task_id,
                state="failed",
                progress_hint=status["progress_hint"],
                fail_code=status.get("fail_code", ""),
                fail_msg=status.get("fail_msg", "") or "Не удалось создать трек",
                production_id=production_id,
                purchased=purchased,
                prepaid=prepaid,
            )

        return MusicStatusResponse(
            success=False,
            task_id=task_id,
            state=state,
            progress_hint=status["progress_hint"],
            production_id=production_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("music status failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/consultant/chat", response_model=ConsultantResponse)
async def consultant_chat(
    req: ConsultantRequest,
    guest_id: str = Depends(get_guest_id),
):
    if not LEGACY_API_ENABLED:
        return ConsultantResponse(
            success=False,
            reply="Консультант временно недоступен.",
        )
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
async def generate_lyrics_endpoint(
    req: LyricsRequest,
    guest_id: str = Depends(get_guest_id),
):
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
async def generate_style_endpoint(
    req: StyleRequest,
    guest_id: str = Depends(get_guest_id),
):
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
async def generate_music_endpoint(
    req: MusicRequest,
    guest_id: str = Depends(get_guest_id),
):
    """Legacy endpoint: returns task_id immediately for polling."""
    if not LEGACY_API_ENABLED:
        raise HTTPException(status_code=410, detail="Endpoint отключён")
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