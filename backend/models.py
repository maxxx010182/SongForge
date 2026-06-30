from typing import Any, Optional

from pydantic import BaseModel, Field


class ProduceRequest(BaseModel):
    idea: str
    artist_ref: str = ""
    instrumental: bool = False
    vocal_hint: str = ""


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
        "low quality, noise, distortion, clipping, bad mixing, "
        "monotone, mumbling, spoken word"
    )
    style_weight: float = 0.85
    weirdness_constraint: float = 0.20
    audio_weight: float = 0.70
    instrumental: bool = False
    channel: str = "auto"
    model_version: str = "V5_5"
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


class TrackVariant(BaseModel):
    id: str = ""
    audio_url: str
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


class CreateSongRequest(BaseModel):
    idea: str
    artist_ref: str = ""
    instrumental: bool = False
    vocal_hint: str = ""


class CreateSongResponse(BaseModel):
    success: bool
    production_id: str
    task_id: str = ""
    plan: ProductionPlan
    title: str
    lyrics: str
    style: str
    message: str = ""


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
    artist_ref: str = ""
    vocal: str = "auto"
    backing: bool = False


class MusicRequest(BaseModel):
    lyrics: str
    style: str
    vocal: str = "auto"
    idea: str = ""
    title: str = ""
    plan: Optional[dict[str, Any]] = None