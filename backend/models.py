from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.settings import (
    DEFAULT_AUDIO_WEIGHT,
    DEFAULT_CHANNEL,
    DEFAULT_MODEL_VERSION,
    DEFAULT_STYLE_WEIGHT,
    DEFAULT_WEIRDNESS,
)


class ProduceRequest(BaseModel):
    idea: str
    genre: str = ""
    mood: str = ""
    artist_ref: str = ""
    instrumental: bool = False
    vocal_hint: str = ""
    backing_vocal: bool = False
    style_mode: str = "presets"
    custom_description: str = ""
    lyrics_engine: str = "classic"


class MusicAnalysis(BaseModel):
    genre: str = "Pop"
    subgenre: str = "Modern Pop"
    mood: str = "uplifting"
    bpm: int = 120
    energy: str = "medium"
    instruments: list[str] = Field(default_factory=lambda: ["synth", "drums", "bass"])
    atmosphere: str = "modern"
    vocal: str = "auto"
    vocal_description: str = "expressive vocals"
    production_style: str = "radio-ready mix"
    commercial_intent: str = "commercial"
    structure: str = "verse-chorus-verse-chorus-outro"
    instrumental: bool = False
    idea: str = ""


class SunoPromptPayload(BaseModel):
    title: str = ""
    lyrics: str = ""
    style: str = ""
    vocal_gender: str = Field(default="", alias="vocalGender")
    negative_tags: str = Field(default="", alias="negativeTags")
    style_weight: float = Field(default=DEFAULT_STYLE_WEIGHT, alias="styleWeight")
    weirdness_constraint: float = Field(default=DEFAULT_WEIRDNESS, alias="weirdnessConstraint")
    audio_weight: float = Field(default=DEFAULT_AUDIO_WEIGHT, alias="audioWeight")

    model_config = {"populate_by_name": True}


class ProductionPlan(BaseModel):
    genre: str = "Pop"
    subgenre: str = "Modern Pop"
    mood: str = "uplifting"
    bpm: int = 120
    energy: str = "medium"
    instruments: list[str] = Field(default_factory=lambda: ["synth", "drums", "bass"])
    atmosphere: str = "modern"
    production_style: str = "radio-ready mix"
    vocal: str = "auto"
    vocal_description: str = "expressive vocals"
    structure: str = "verse-chorus-verse-chorus-outro"
    negative_tags: str = (
        "unwanted noise, distortion, clipping, screaming, off-key vocals, "
        "poor mix, muddy sound, low quality, chaotic arrangement"
    )
    style_weight: float = DEFAULT_STYLE_WEIGHT
    weirdness_constraint: float = DEFAULT_WEIRDNESS
    audio_weight: float = DEFAULT_AUDIO_WEIGHT
    vocal_gender: str = ""
    instrumental: bool = False
    channel: str = DEFAULT_CHANNEL
    model_version: str = DEFAULT_MODEL_VERSION
    explanation_ru: str = ""
    optimized_idea: str = ""


class ProduceResponse(BaseModel):
    success: bool
    production_id: str
    plan: ProductionPlan
    title: str
    lyrics: str
    style: str
    message: str = ""


class MusicStartRequest(BaseModel):
    production_id: str = ""
    lyrics: str
    style: str
    title: str
    plan: Optional[ProductionPlan] = None
    idea: str = ""
    genre: str = ""
    mood: str = ""
    artist_ref: str = ""
    vocal_hint: str = ""
    backing_vocal: bool = False


class TrackVariant(BaseModel):
    id: str = ""
    audio_url: str = ""
    preview_url: str = ""
    image_url: str = ""
    duration: float = 0


class MusicStatusResponse(BaseModel):
    success: bool
    task_id: str
    state: str
    progress_hint: str = ""
    tracks: list[TrackVariant] = Field(default_factory=list)
    fail_code: str = ""
    fail_msg: str = ""
    production_id: str = ""
    purchased: bool = False
    prepaid: bool = False


class CreateSongRequest(BaseModel):
    idea: str
    genre: str = ""
    mood: str = ""
    artist_ref: str = ""
    instrumental: bool = False
    vocal_hint: str = ""
    backing_vocal: bool = False
    style_mode: str = "presets"
    custom_description: str = ""
    lyrics_engine: str = "classic"


class CreateSongResponse(BaseModel):
    success: bool
    production_id: str
    task_id: str = ""
    plan: ProductionPlan
    title: str
    lyrics: str
    style: str
    message: str = ""
    balance: int | None = None
    generation_mode: str = ""


class ConsultantRequest(BaseModel):
    message: str
    context: str = ""


class ConsultantResponse(BaseModel):
    success: bool
    reply: str


class LyricsRequest(BaseModel):
    prompt: str
    genre: str
    mood: str
    vocal: str = "auto"


class StyleRequest(BaseModel):
    genre: str
    mood: str
    idea: str = ""
    artist_ref: str = ""
    vocal: str = "auto"
    backing: bool = False
    style_mode: str = "presets"
    custom_description: str = ""


class MusicRequest(BaseModel):
    lyrics: str
    style: str
    vocal: str = "auto"
    idea: str = ""
    title: str = ""
    plan: Optional[dict[str, Any]] = None


class EmailAuthRequest(BaseModel):
    email: str


class EmailVerifyRequest(BaseModel):
    email: str
    code: str


class TelegramAuthRequest(BaseModel):
    id: str
    first_name: str = ""
    username: str = ""


class UserInfo(BaseModel):
    id: str
    email: str | None = None
    display_name: str = ""
    balance: int = 0
    avatar_url: str | None = None
    nickname_confirmed: bool = False
    theme: str = "burgundy"


class PublicTrackResponse(BaseModel):
    id: str
    title: str = ""
    author_name: str = "Аноним"
    image_url: str = ""
    listen_url: str = ""
    likes: int = 0
    share_url: str = ""


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    theme: str | None = None


class ProfileUpdateResponse(BaseModel):
    success: bool
    user: UserInfo


class MeResponse(BaseModel):
    logged_in: bool
    user: UserInfo | None = None
    guest_remaining: int = 0
    guest_limit: int = 1
    payment_provider: str = "stub"


class HistoryItem(BaseModel):
    id: str
    title: str
    status: str
    created_at: str
    genre: str = ""
    purchased: bool = False
    has_preview_a: bool = False
    has_preview_b: bool = False
    image_url_a: str | None = None
    image_url_b: str | None = None


class HistoryPreviewResponse(BaseModel):
    preview_url: str
    preview_limit_sec: int = 30
    title: str = ""
    image_url: str | None = None


class LibraryItem(BaseModel):
    id: str
    generation_id: str
    title: str
    variant: str = ""
    audio_url: str
    image_url: str = ""
    duration: float = 0
    lyrics: str = ""
    genre: str = ""
    purchased_at: str = ""
    published_at: str | None = None
    likes: int = 0


class ExploreItem(BaseModel):
    id: str
    title: str
    genre: str = ""
    image_url: str = ""
    duration: float = 0
    likes: int = 0
    published_at: str = ""
    author_name: str = "Аноним"
    author_avatar_url: str | None = None
    listen_url: str = ""
    liked_by_me: bool = False
    comment_count: int = 0


class TrackCommentItem(BaseModel):
    id: str
    text: str
    author_name: str = "Аноним"
    created_at: str = ""


class TrackCommentCreateRequest(BaseModel):
    text: str


class TrackCommentsResponse(BaseModel):
    items: list[TrackCommentItem] = Field(default_factory=list)
    total: int = 0


class LikeResponse(BaseModel):
    success: bool
    likes: int = 0
    liked: bool = True
    already_liked: bool = False
    message: str = ""


class PublishResponse(BaseModel):
    success: bool
    published_at: str | None = None
    message: str = ""


class PurchaseResponse(BaseModel):
    success: bool
    generation_id: str
    library_ids: list[str] = Field(default_factory=list)
    balance: int = 0


class PaymentPackage(BaseModel):
    id: str
    notes: int
    price_rub: int
    label: str = ""
    discount: str = ""


class CreatePaymentOrderRequest(BaseModel):
    package_id: str


class PaymentOrderResponse(BaseModel):
    order_id: str
    status: str
    package: PaymentPackage
    payment_url: str | None = None
    provider: str = "stub"
    message: str = ""


class PaymentOrderStatusResponse(BaseModel):
    order_id: str
    status: str
    package: PaymentPackage | None = None
    notes_amount: int = 0
    price_rub: int = 0
    provider: str = ""
    paid_at: str | None = None
    balance: int | None = None


class FullAudioResponse(BaseModel):
    audio_url: str
    title: str = ""


class AdminMeResponse(BaseModel):
    role: str
    permissions: list[str]
    email: str | None = None
    display_name: str = ""


class AdminDashboardResponse(BaseModel):
    users_total: int = 0
    users_week: int = 0
    generations_24h: dict = {}
    generations_stuck: int = 0
    generations_active: int = 0
    orders_paid_24h: dict = {}
    tracks_published: int = 0
    alerts: list[dict] = []


class AdminBalanceAdjustRequest(BaseModel):
    delta: int
    reason: str


class AdminGrantRequest(BaseModel):
    email: str
    role: str = "support"


class AdminCreatePersonasRequest(BaseModel):
    names: list[str] = Field(default_factory=list)
    count: int = 20


class AdminSeedLikesRequest(BaseModel):
    count: int = 10


class AdminSeedCommentRequest(BaseModel):
    persona_id: str
    text: str
    created_at: str = ""


class AdminUpdateTrackTitleRequest(BaseModel):
    title: str


class AdminUpdateAuthorNameRequest(BaseModel):
    display_name: str


class AdminBoostTrackRequest(BaseModel):
    likes: int = 12
    comments: int = 3