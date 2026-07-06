import uuid

from backend.logger import log
from backend.models import CreateSongResponse, ProduceResponse, ProductionPlan
from backend.services.music_provider_service import MusicProviderService
from backend.services.cabinet_service import CabinetService
from backend.services.history import HistoryService
from backend.services.prompt_builder import PromptBuilder
from backend.services.plan_overrides import apply_user_to_plan
from backend.services.yandex_client import YandexClient
from backend.utils.text import lyrics_look_lazy


class AiProducer:
    PRODUCER_MESSAGE = (
        "AI-продюсер анализирует идею и подбирает оптимальные параметры генерации..."
    )

    def __init__(self) -> None:
        yandex = YandexClient()
        self._builder = PromptBuilder(yandex)
        self._music = MusicProviderService()
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
        lyrics_engine: str = "classic",
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
            lyrics_engine=lyrics_engine,
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
            user_id=getattr(self, "_current_user_id", None),
            guest_id=getattr(self, "_current_guest_id", None),
        )

        if not instrumental:
            log.info(
                "Production lyrics: id=%s len=%s lazy=%s preview=%r",
                production_id,
                len(lyrics),
                lyrics_look_lazy(lyrics, idea),
                lyrics[:160],
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

    def resolve_production_for_repeat(self, production_id: str) -> str:
        """Новая генерация — новый production_id, если предыдущая уже в фонотеке."""
        if not production_id:
            return production_id
        row = self._history.get_by_id(production_id)
        if not row:
            return production_id
        cabinet = CabinetService()
        repeat = (
            (row.get("status") or "").lower() == "success"
            or int(row.get("purchased") or 0)
            or int(row.get("note_charged") or 0)
            or cabinet.library_entry_count(production_id) > 0
        )
        if not repeat:
            return production_id

        import json

        new_id = str(uuid.uuid4())
        plan = ProductionPlan.model_validate(json.loads(row["plan_json"] or "{}"))
        self._history.save_production(
            production_id=new_id,
            idea=row.get("idea") or "",
            optimized_idea=row.get("optimized_idea") or "",
            plan=plan,
            title=row.get("title") or "",
            lyrics=row.get("lyrics") or "",
            style=row.get("style") or "",
            user_id=row.get("user_id"),
            guest_id=row.get("guest_id"),
        )
        log.info(
            "Repeat music start: forked production %s -> %s",
            production_id,
            new_id,
        )
        return new_id

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
            if lyrics.strip() or style.strip() or idea.strip():
                plan = self._builder.build_plan(
                    idea or title or "My Song",
                    genre=genre,
                    mood=mood,
                    artist_ref=artist_ref,
                    vocal_hint=vocal_hint,
                    backing_vocal=backing_vocal,
                )
            else:
                raise ValueError("Не найден план продакшена")

        if genre.strip() or mood.strip() or vocal_hint.strip() or backing_vocal:
            plan = apply_user_to_plan(
                plan,
                genre=genre,
                mood=mood,
                vocal_hint=vocal_hint,
                backing_vocal=backing_vocal,
            )

        task_ref = self._music.create_task(
            lyrics=lyrics,
            style=style,
            title=title,
            plan=plan,
        )
        self._history.attach_task(
            production_id=production_id,
            task_id=task_ref.task_id,
            idea=idea,
            title=title,
            lyrics=lyrics,
            style=style,
            plan=plan,
            user_id=getattr(self, "_current_user_id", None),
            guest_id=getattr(self, "_current_guest_id", None),
            music_provider=task_ref.provider,
        )
        return task_ref.task_id

    def set_actor(self, *, user_id: str | None = None, guest_id: str | None = None) -> None:
        self._current_user_id = user_id
        self._current_guest_id = guest_id

    def clear_actor(self) -> None:
        self._current_user_id = None
        self._current_guest_id = None

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
        lyrics_engine: str = "classic",
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
            lyrics_engine=lyrics_engine,
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