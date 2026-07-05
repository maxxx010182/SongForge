import requests
from fastapi import Cookie, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.database.db import get_connection
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
    ExploreItem,
    LikeResponse,
    HistoryPreviewResponse,
    LibraryItem,
    PublishResponse,
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
    PublicTrackResponse,
    StyleRequest,
    AdminBalanceAdjustRequest,
    AdminDashboardResponse,
    AdminGrantRequest,
    AdminCreatePersonasRequest,
    AdminSeedLikesRequest,
    AdminSeedCommentRequest,
    AdminUpdateTrackTitleRequest,
    AdminUpdateAuthorNameRequest,
    AdminBoostTrackRequest,
    AdminMeResponse,
    TelegramAuthRequest,
    TrackCommentCreateRequest,
    TrackCommentsResponse,
    TrackCommentItem,
    TrackVariant,
    UserInfo,
)
from backend.services.admin_service import AdminService
from backend.services.showcase_admin_service import ShowcaseAdminService
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
from backend.services.profile_service import DisplayNameTakenError, ProfileService
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
    SITE_URL,
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
admin_service = AdminService()
showcase_admin = ShowcaseAdminService()

app = FastAPI(title="SongForge", version="2.9.27")

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


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


async def require_admin_user(
    request: Request,
    user: dict | None = Depends(get_optional_user),
) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт на сайте")
    ip = _client_ip(request)
    try:
        admin = admin_service.resolve_admin(user, ip=ip)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not admin:
        from backend.settings import ADMIN_BOOTSTRAP_EMAILS

        email = (user.get("email") or "").strip().lower()
        if not ADMIN_BOOTSTRAP_EMAILS:
            detail = (
                "Нет прав администратора: на сервере пустой ADMIN_BOOTSTRAP_EMAILS "
                f"в ~/SongForge/.env (вы вошли как {email}). "
                "Добавьте email в .env и выполните: pm2 restart songforge"
            )
        elif email not in ADMIN_BOOTSTRAP_EMAILS:
            detail = (
                f"Нет прав администратора: вы вошли как {email}, "
                "но этого адреса нет в ADMIN_BOOTSTRAP_EMAILS на сервере. "
                "Исправьте .env и: pm2 restart songforge"
            )
        else:
            detail = (
                f"Нет прав администратора (вход: {email}). "
                "Email в .env указан — перезапустите приложение: pm2 restart songforge"
            )
        raise HTTPException(status_code=403, detail=detail)
    return {
        **user,
        "admin_id": admin["id"],
        "admin_role": admin["role"],
    }


def _user_info(user: dict) -> UserInfo:
    from backend.services.profile_service import DEFAULT_THEME, VALID_THEMES

    theme = (user.get("theme") or DEFAULT_THEME).strip().lower()
    if theme not in VALID_THEMES:
        theme = DEFAULT_THEME
    return UserInfo(
        id=user["id"],
        email=user.get("email"),
        display_name=user.get("display_name") or "",
        balance=int(user.get("balance") or 0),
        avatar_url=user.get("avatar_url"),
        nickname_confirmed=bool(int(user.get("nickname_confirmed") or 0)),
        theme=theme,
    )


def _public_track_payload(library_id: str, row) -> PublicTrackResponse:
    author = cabinet.resolve_public_author_name(row)
    title = (row["title"] or "").strip() or "Без названия"
    return PublicTrackResponse(
        id=library_id,
        title=title,
        author_name=author,
        image_url=row["image_url"] or "",
        listen_url=f"/api/explore/{library_id}/listen",
        likes=int(row["likes"] or 0),
        share_url=f"{SITE_URL}/t/{library_id}",
    )


def _assert_can_generate(*, user: dict | None, guest_id: str) -> None:
    """Проверка права на генерацию без списания нот (текст / produce)."""
    generation_quota.resolve_mode(user=user, guest_id=guest_id)


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


def _generation_flags_after_success(production_id: str) -> tuple[bool, bool]:
    """После успешной музыки: prepaid → фонотека без повторного списания."""
    if production_id:
        cabinet.complete_prepaid_generation(production_id)
    return _generation_flags(production_id)


@app.get("/")
async def get_index():
    return FileResponse(ROOT_DIR / "index.html")


@app.get("/admin")
async def get_admin_page():
    """Отдельная админ-панель. Не ссылаемся с главной — URL только для команды."""
    path = ROOT_DIR / "admin.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)


@app.get("/t/{library_id}")
async def track_share_short_link(library_id: str):
    """Короткая ссылка для шаринга — как YouTube / Instagram."""
    row = cabinet.get_published_library_item(library_id)
    if not row:
        raise HTTPException(status_code=404, detail="Трек не найден или снят с публикации")
    return RedirectResponse(url=f"/?track={library_id}", status_code=302)


@app.get("/SongForgeLogo.png")
async def get_logo():
    path = ROOT_DIR / "SongForgeLogo.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Logo not found")
    return FileResponse(path, media_type="image/png")


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "SongForge", "version": "2.9.27"}


@app.get("/api/admin/me", response_model=AdminMeResponse)
async def admin_me(admin_user: dict = Depends(require_admin_user)):
    role = admin_user["admin_role"]
    return AdminMeResponse(
        role=role,
        permissions=admin_service.list_permissions(role),
        email=admin_user.get("email"),
        display_name=admin_user.get("display_name") or "",
    )


@app.get("/api/admin/dashboard", response_model=AdminDashboardResponse)
async def admin_dashboard(admin_user: dict = Depends(require_admin_user)):
    try:
        admin_service.assert_permission(admin_user["admin_role"], "dashboard:read")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return AdminDashboardResponse(**admin_service.get_dashboard())


@app.get("/api/admin/generations")
async def admin_list_generations(
    status: str | None = None,
    limit: int = 50,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        admin_service.assert_permission(admin_user["admin_role"], "generations:read")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return admin_service.list_generations(status=status, limit=limit)


@app.get("/api/admin/users/search")
async def admin_search_users(
    q: str,
    limit: int = 30,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        admin_service.assert_permission(admin_user["admin_role"], "users:read")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return admin_service.search_users(q=q, limit=limit)


@app.post("/api/admin/users/{user_id}/balance")
async def admin_adjust_balance(
    user_id: str,
    req: AdminBalanceAdjustRequest,
    request: Request,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        result = admin_service.adjust_balance(
            admin_id=admin_user["admin_id"],
            admin_role=admin_user["admin_role"],
            target_user_id=user_id,
            delta=int(req.delta),
            reason=req.reason,
            ip=_client_ip(request),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


@app.get("/api/admin/admins")
async def admin_list_admins(admin_user: dict = Depends(require_admin_user)):
    try:
        return admin_service.list_admins(admin_role=admin_user["admin_role"])
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/api/admin/admins/grant")
async def admin_grant_role(
    req: AdminGrantRequest,
    request: Request,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        return admin_service.grant_admin(
            admin_id=admin_user["admin_id"],
            admin_role=admin_user["admin_role"],
            target_email=req.email,
            role=req.role,
            ip=_client_ip(request),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/admin/audit")
async def admin_audit_log(
    limit: int = 100,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        return admin_service.list_audit(admin_role=admin_user["admin_role"], limit=limit)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _assert_showcase_permission(admin_user: dict) -> None:
    admin_service.assert_permission(admin_user["admin_role"], "showcase:write")


def _log_showcase_action(
    *,
    admin_user: dict,
    request: Request,
    action: str,
    target_id: str | None = None,
    target_type: str = "library",
    details: dict | None = None,
) -> None:
    admin_service.log_action(
        admin_id=admin_user["admin_id"],
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip=_client_ip(request),
    )


@app.get("/api/admin/showcase/personas")
async def admin_list_personas(
    limit: int = 100,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        _assert_showcase_permission(admin_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    personas = showcase_admin.list_personas(limit=limit)
    return {"items": personas, "total": showcase_admin.persona_count()}


@app.post("/api/admin/showcase/personas")
async def admin_create_personas(
    req: AdminCreatePersonasRequest,
    request: Request,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        _assert_showcase_permission(admin_user)
        created = showcase_admin.create_personas(names=req.names, count=req.count)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log_showcase_action(
        admin_user=admin_user,
        request=request,
        action="showcase.personas_create",
        target_type="showcase",
        details={"created": len(created), "total": showcase_admin.persona_count()},
    )
    return {"success": True, "created": created, "total": showcase_admin.persona_count()}


@app.get("/api/admin/showcase/tracks")
async def admin_list_showcase_tracks(
    limit: int = 50,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        _assert_showcase_permission(admin_user)
        items = showcase_admin.list_showcase_tracks(
            admin_user_id=admin_user["id"],
            admin_role=admin_user["admin_role"],
            limit=limit,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"items": items}


@app.post("/api/admin/showcase/tracks/{library_id}/boost")
async def admin_boost_track(
    library_id: str,
    req: AdminBoostTrackRequest,
    request: Request,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        _assert_showcase_permission(admin_user)
        result = showcase_admin.boost_track(
            admin_user_id=admin_user["id"],
            admin_role=admin_user["admin_role"],
            library_id=library_id,
            likes=req.likes,
            comments=req.comments,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log_showcase_action(
        admin_user=admin_user,
        request=request,
        action="showcase.boost",
        target_id=library_id,
        details={
            "likes_added": result["likes_added"],
            "comments_added": result["comments_added"],
        },
    )
    return result


@app.post("/api/admin/showcase/tracks/{library_id}/likes")
async def admin_seed_likes(
    library_id: str,
    req: AdminSeedLikesRequest,
    request: Request,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        _assert_showcase_permission(admin_user)
        result = showcase_admin.add_seed_likes(
            admin_user_id=admin_user["id"],
            admin_role=admin_user["admin_role"],
            library_id=library_id,
            count=req.count,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log_showcase_action(
        admin_user=admin_user,
        request=request,
        action="showcase.likes",
        target_id=library_id,
        details={"added": result["added"], "likes": result["likes"]},
    )
    return result


@app.post("/api/admin/showcase/tracks/{library_id}/comments")
async def admin_seed_comment(
    library_id: str,
    req: AdminSeedCommentRequest,
    request: Request,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        _assert_showcase_permission(admin_user)
        result = showcase_admin.add_seed_comment(
            admin_user_id=admin_user["id"],
            admin_role=admin_user["admin_role"],
            library_id=library_id,
            persona_id=req.persona_id,
            text=req.text,
            created_at=req.created_at or None,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log_showcase_action(
        admin_user=admin_user,
        request=request,
        action="showcase.comment",
        target_id=library_id,
        details={"persona_id": req.persona_id, "text": req.text[:120]},
    )
    return result


@app.patch("/api/admin/showcase/tracks/{library_id}/title")
async def admin_update_track_title(
    library_id: str,
    req: AdminUpdateTrackTitleRequest,
    request: Request,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        _assert_showcase_permission(admin_user)
        result = showcase_admin.update_track_title(
            admin_user_id=admin_user["id"],
            admin_role=admin_user["admin_role"],
            library_id=library_id,
            title=req.title,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log_showcase_action(
        admin_user=admin_user,
        request=request,
        action="showcase.title",
        target_id=library_id,
        details={"title": result["title"]},
    )
    return result


@app.patch("/api/admin/showcase/tracks/{library_id}/author")
async def admin_update_track_author(
    library_id: str,
    req: AdminUpdateAuthorNameRequest,
    request: Request,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        _assert_showcase_permission(admin_user)
        result = showcase_admin.update_author_display_name(
            admin_user_id=admin_user["id"],
            admin_role=admin_user["admin_role"],
            library_id=library_id,
            display_name=req.display_name,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log_showcase_action(
        admin_user=admin_user,
        request=request,
        action="showcase.author",
        target_id=library_id,
        details={"display_name": result["display_name"]},
    )
    return result


@app.delete("/api/admin/showcase/tracks/{library_id}/seed")
async def admin_clear_seed_engagement(
    library_id: str,
    request: Request,
    admin_user: dict = Depends(require_admin_user),
):
    try:
        _assert_showcase_permission(admin_user)
        result = showcase_admin.clear_seed_engagement(
            admin_user_id=admin_user["id"],
            admin_role=admin_user["admin_role"],
            library_id=library_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log_showcase_action(
        admin_user=admin_user,
        request=request,
        action="showcase.clear_seed",
        target_id=library_id,
        details={
            "likes_removed": result["likes_removed"],
            "comments_removed": result["comments_removed"],
        },
    )
    return result


@app.get("/api/me", response_model=MeResponse)
async def get_me(
    guest_id: str = Depends(get_guest_id),
    user: dict | None = Depends(get_optional_user),
):
    if user:
        remaining = generation_quota.user_trial_remaining(user["id"])
    else:
        remaining = 0
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


@app.post("/api/library/{library_id}/publish", response_model=PublishResponse)
async def publish_library_track(
    library_id: str,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    try:
        return cabinet.publish_library_track(user_id=user["id"], library_id=library_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/library/{library_id}/unpublish", response_model=PublishResponse)
async def unpublish_library_track(
    library_id: str,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    try:
        return cabinet.unpublish_library_track(user_id=user["id"], library_id=library_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/library/{library_id}/listen")
async def listen_library_track(
    library_id: str,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    row = cabinet.get_library_item(user_id=user["id"], library_id=library_id)
    if not row:
        raise HTTPException(status_code=404, detail="Трек не найден в фонотеке")
    if not row["audio_url"]:
        raise HTTPException(status_code=404, detail="Аудио не найдено")
    return audio_access.stream_playback(
        row["audio_url"],
        range_header=request.headers.get("range"),
    )


@app.delete("/api/library/{library_id}")
async def delete_library_track(
    library_id: str,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    try:
        cabinet.delete_library_track(user_id=user["id"], library_id=library_id)
        return {"success": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/explore", response_model=list[ExploreItem])
async def get_explore(
    limit: int = 50,
    user: dict | None = Depends(get_optional_user),
):
    user_id = user["id"] if user else None
    return cabinet.list_explore(limit=limit, user_id=user_id)


@app.post("/api/explore/{library_id}/like", response_model=LikeResponse)
async def like_explore_track(
    library_id: str,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Лайки могут ставить только зарегистрированные пользователи",
        )
    try:
        return cabinet.like_published_track(user_id=user["id"], library_id=library_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/explore/{library_id}/like", response_model=LikeResponse)
async def unlike_explore_track(
    library_id: str,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Лайки могут ставить только зарегистрированные пользователи",
        )
    try:
        return cabinet.unlike_published_track(user_id=user["id"], library_id=library_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/explore/{library_id}/comments", response_model=TrackCommentsResponse)
async def get_track_comments(library_id: str, limit: int = 50):
    try:
        return cabinet.list_track_comments(library_id=library_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/explore/{library_id}/comments", response_model=TrackCommentItem)
async def post_track_comment(
    library_id: str,
    req: TrackCommentCreateRequest,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Комментарии могут оставлять только зарегистрированные пользователи",
        )
    try:
        return cabinet.add_track_comment(
            user_id=user["id"],
            library_id=library_id,
            text=req.text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/explore/{library_id}/public", response_model=PublicTrackResponse)
async def get_public_track(library_id: str):
    row = cabinet.get_published_library_item(library_id)
    if not row:
        raise HTTPException(status_code=404, detail="Трек не найден или снят с публикации")
    return _public_track_payload(library_id, row)


@app.get("/api/explore/{library_id}/listen")
async def listen_explore_track(library_id: str, request: Request):
    row = cabinet.get_published_library_item(library_id)
    if not row:
        raise HTTPException(status_code=404, detail="Публичный трек не найден")
    if not row["audio_url"]:
        raise HTTPException(status_code=404, detail="Аудио не найдено")
    return audio_access.stream_playback(
        row["audio_url"],
        range_header=request.headers.get("range"),
    )


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


@app.get("/api/profile/nickname-available")
async def check_nickname_available(
    display_name: str,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    try:
        available = profile_service.is_nickname_available(
            user_id=user["id"],
            display_name=display_name,
        )
        return {"available": available}
    except ValueError as exc:
        return {"available": False, "reason": str(exc)}


@app.patch("/api/profile", response_model=ProfileUpdateResponse)
async def update_profile(
    req: ProfileUpdateRequest,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    if req.display_name is None and req.theme is None:
        raise HTTPException(status_code=400, detail="Укажите, что изменить")
    try:
        updated = profile_service.get_user(user["id"])
        if not updated:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        if req.display_name is not None:
            updated = profile_service.update_display_name(
                user_id=user["id"],
                display_name=req.display_name,
            )
        if req.theme is not None:
            updated = profile_service.update_theme(
                user_id=user["id"],
                theme=req.theme,
            )
        return ProfileUpdateResponse(success=True, user=_user_info(updated))
    except DisplayNameTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    guest_id: str = Depends(get_guest_id),
    user: dict | None = Depends(get_optional_user),
):
    if user:
        guest_service.mark_exhausted(guest_id)
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


@app.get("/api/audio/download/library/{library_id}")
async def download_library_audio(
    library_id: str,
    user: dict | None = Depends(get_optional_user),
):
    if not user:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    row = cabinet.get_library_item(user_id=user["id"], library_id=library_id)
    if not row:
        raise HTTPException(status_code=404, detail="Трек не найден в фонотеке")
    if not row["audio_url"]:
        raise HTTPException(status_code=404, detail="Аудио не найдено")
    log.info("Download proxy: user=%s library=%s", user["id"], library_id)
    return audio_access.stream_download(
        row["audio_url"],
        title=row["title"] or "Без названия",
    )


@app.get("/api/audio/download/{production_id}/{variant}")
async def download_full_audio(
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
    lib_title = row["title"] or "Без названия"
    if variant == 1:
        lib_title = f"{lib_title} (вариант B)"
    elif row["music_url_b"]:
        lib_title = f"{lib_title} (вариант A)"
    log.info("Download proxy: user=%s gen=%s", user["id"], production_id)
    return audio_access.stream_download(source, title=lib_title)


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
    user: dict | None = Depends(get_optional_user),
):
    try:
        _assert_can_generate(user=user, guest_id=guest_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
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
            lyrics_engine=req.lyrics_engine,
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
            lyrics_engine=req.lyrics_engine,
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
        if mode == "paid" and req.production_id:
            generation_quota.mark_note_charged(req.production_id)
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
    purchased, prepaid = _generation_flags_after_success(production_id)
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
            purchased, prepaid = _generation_flags_after_success(production_id)
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
    user: dict | None = Depends(get_optional_user),
):
    try:
        _assert_can_generate(user=user, guest_id=guest_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        plan = prompt_builder.build_plan(
            req.prompt,
            genre=req.genre,
            mood=req.mood,
            vocal_hint=req.vocal,
        )
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
    idea = (req.idea or req.custom_description or "Song").strip()
    try:
        plan = prompt_builder.build_plan(
            idea,
            genre=req.genre,
            mood=req.mood,
            artist_ref=req.artist_ref,
            vocal_hint=req.vocal,
            backing_vocal=req.backing,
            style_mode=req.style_mode,
            custom_description=req.custom_description,
        )
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
        from backend.services.genre_resolver import resolve_genre

        genre_en, _ = resolve_genre(req.genre, idea)
        style = f"{genre_en}, {req.mood}"
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