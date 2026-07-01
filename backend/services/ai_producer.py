import uuid

from backend.logger import log
from backend.models import CreateSongResponse, ProduceResponse, ProductionPlan
from backend.services.apipass_client import ApiPassClient
from backend.services.history import HistoryService
from backend.services.prompt_builder import PromptBuilder
from backend.services.plan_overrides import apply_user_to_plan
from backend.services.yandex_client import YandexClient


class AiProducer:
    PRODUCER_MESSAGE = (
        "AI-продюсер анализирует идею и подбирает оптимальные параметры генерации..."
    )

    def __init__(self) -> None:
        yandex = YandexClient()
        self._builder = PromptBuilder(yandex)
        self._apipass = ApiPassClient()
        self._history = HistoryService()

    def produce(
        self,
        idea: str,
        *,
        genre: str = "",
        mood: str = "",
        artist_ref: str = "",
        instrumental: bool = False,
        vocal_hint: str = "",
        backing_vocal: bool = False,
        style_mode: str = "presets",
        custom_description: str = "",
    ) -> ProduceResponse:
        idea = idea.strip()
        custom_mode = style_mode == "custom" and custom_description.strip()
        if not idea and not custom_mode:
            raise ValueError("Идея песни не может быть пустой")
        if custom_mode and not idea:
            idea = custom_description.strip()

        plan, payload = self._builder.build(
            idea,
            genre=genre,
            mood=mood,
            artist_ref=artist_ref,
            instrumental=instrumental,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
            style_mode=style_mode,
            custom_description=custom_description,
        )
        plan.optimized_idea = idea

        title = payload.title
        lyrics = payload.lyrics
        style = payload.style

        production_id = str(uuid.uuid4())
        self._history.save_production(
            production_id=production_id,
            idea=idea,
            optimized_idea=idea,
            plan=plan,
            title=title,
            lyrics=lyrics,
            style=style,
        )

        log.info("Production ready: %s | %s | instrumental=%s", production_id, title, instrumental)
        return ProduceResponse(
            success=True,
            production_id=production_id,
            plan=plan,
            title=title,
            lyrics=lyrics,
            style=style,
            message=self.PRODUCER_MESSAGE,
        )

    def start_music(
        self,
        *,
        production_id: str,
        lyrics: str,
        style: str,
        title: str,
        plan: ProductionPlan | None = None,
        idea: str = "",
        genre: str = "",
        mood: str = "",
        artist_ref: str = "",
        vocal_hint: str = "",
        backing_vocal: bool = False,
    ) -> str:
        if plan is None and production_id:
            stored = self._history.get_production(production_id)
            if stored:
                plan = ProductionPlan.model_validate(stored["plan"])
                lyrics = lyrics or stored["lyrics"]
                style = style or stored["style"]
                title = title or stored["title"]
                idea = idea or stored.get("idea", "")

        if plan is None:
            raise ValueError("Не найден план продакшена")

        if genre.strip() or mood.strip() or vocal_hint.strip() or backing_vocal:
            plan = apply_user_to_plan(
                plan,
                genre=genre,
                mood=mood,
                vocal_hint=vocal_hint,
                backing_vocal=backing_vocal,
            )

        task_id = self._apipass.create_task(
            lyrics=lyrics,
            style=style,
            title=title,
            plan=plan,
        )
        self._history.attach_task(
            production_id=production_id,
            task_id=task_id,
            idea=idea,
            title=title,
            lyrics=lyrics,
            style=style,
            plan=plan,
        )
        return task_id

    def create_song(
        self,
        idea: str,
        *,
        genre: str = "",
        mood: str = "",
        artist_ref: str = "",
        instrumental: bool = False,
        vocal_hint: str = "",
        backing_vocal: bool = False,
        style_mode: str = "presets",
        custom_description: str = "",
    ) -> CreateSongResponse:
        produced = self.produce(
            idea,
            genre=genre,
            mood=mood,
            artist_ref=artist_ref,
            instrumental=instrumental,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
            style_mode=style_mode,
            custom_description=custom_description,
        )
        task_id = self.start_music(
            production_id=produced.production_id,
            lyrics=produced.lyrics,
            style=produced.style,
            title=produced.title,
            plan=produced.plan,
            idea=idea,
            genre=genre,
            mood=mood,
            artist_ref=artist_ref,
            vocal_hint=vocal_hint,
            backing_vocal=backing_vocal,
        )
        return CreateSongResponse(
            success=True,
            production_id=produced.production_id,
            task_id=task_id,
            plan=produced.plan,
            title=produced.title,
            lyrics=produced.lyrics,
            style=produced.style,
            message=produced.message,
        )