import uuid

from backend.logger import log
from backend.models import CreateSongResponse, ProduceResponse, ProductionPlan
from backend.services.ai_optimizer import AiOptimizer
from backend.services.apipass_client import ApiPassClient
from backend.services.history import HistoryService
from backend.services.prompt_builder import PromptBuilder
from backend.services.title_generator import TitleGenerator
from backend.services.yandex_client import YandexClient


class AiProducer:
    def __init__(self) -> None:
        yandex = YandexClient()
        self._optimizer = AiOptimizer(yandex)
        self._builder = PromptBuilder(yandex)
        self._titles = TitleGenerator(yandex)
        self._apipass = ApiPassClient()
        self._history = HistoryService()

    def produce(
        self,
        idea: str,
        *,
        artist_ref: str = "",
        instrumental: bool = False,
        vocal_hint: str = "",
    ) -> ProduceResponse:
        idea = idea.strip()
        if not idea:
            raise ValueError("Идея песни не может быть пустой")

        optimized = self._optimizer.optimize(idea)
        plan = self._builder.build_plan(
            optimized,
            artist_ref=artist_ref,
            instrumental=instrumental,
            vocal_hint=vocal_hint,
        )
        plan.optimized_idea = optimized

        title = self._titles.generate(optimized, plan)
        lyrics = self._builder.generate_lyrics(optimized, plan)
        style = self._builder.build_style_via_ai(plan, artist_ref=artist_ref)

        production_id = str(uuid.uuid4())
        self._history.save_production(
            production_id=production_id,
            idea=idea,
            optimized_idea=optimized,
            plan=plan,
            title=title,
            lyrics=lyrics,
            style=style,
        )

        log.info("Production ready: %s | %s", production_id, title)
        return ProduceResponse(
            success=True,
            production_id=production_id,
            plan=plan,
            title=title,
            lyrics=lyrics,
            style=style,
            message=plan.explanation_ru or "AI-продюсер подобрал параметры для вашей песни.",
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
        artist_ref: str = "",
        instrumental: bool = False,
        vocal_hint: str = "",
    ) -> CreateSongResponse:
        produced = self.produce(
            idea,
            artist_ref=artist_ref,
            instrumental=instrumental,
            vocal_hint=vocal_hint,
        )
        task_id = self.start_music(
            production_id=produced.production_id,
            lyrics=produced.lyrics,
            style=produced.style,
            title=produced.title,
            plan=produced.plan,
            idea=idea,
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