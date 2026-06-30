from backend.models import ProductionPlan
from backend.services.yandex_client import YandexClient
from backend.utils.text import clean_text, extract_json, truncate


class PromptBuilder:
    PLAN_SYSTEM = (
        "Ты AI Prompt Builder для музыкального сервиса SongForge и Suno V5.5. "
        "Проанализируй идею пользователя и верни ТОЛЬКО валидный JSON без markdown. "
        "Поля: genre, subgenre, mood, bpm (число), energy (low|medium|high), "
        "instruments (массив строк на английском), atmosphere, production_style, "
        "vocal (male|female|duet|auto), vocal_description, structure, negative_tags, "
        "style_weight (0.0-1.0), weirdness_constraint (0.0-1.0), audio_weight (0.0-1.0), "
        "explanation_ru (1-2 предложения на русском — почему выбраны эти параметры). "
        "Не упоминай имена артистов. Делай коммерчески сильные решения."
    )

    LYRICS_SYSTEM = (
        "Ты поэт-песенник и музыкальный продюсер. "
        "Напиши текст песни на русском языке со структурными тегами "
        "[Verse 1], [Chorus], [Verse 2], [Chorus], [Bridge], [Chorus], [Outro]. "
        "Только текст песни, без пояснений и markdown."
    )

    def __init__(self, yandex: YandexClient) -> None:
        self._yandex = yandex

    def build_plan(
        self,
        idea: str,
        *,
        artist_ref: str = "",
        instrumental: bool = False,
        vocal_hint: str = "",
    ) -> ProductionPlan:
        hints = []
        if artist_ref.strip():
            hints.append(
                f"Референс звучания (без имён в треке): {artist_ref.strip()}"
            )
        if vocal_hint.strip():
            hints.append(f"Пожелание по вокалу: {vocal_hint.strip()}")
        if instrumental:
            hints.append("Нужен инструментальный трек без вокала.")

        user_text = idea
        if hints:
            user_text += "\n\n" + "\n".join(hints)

        try:
            raw = self._yandex.complete(
                self.PLAN_SYSTEM,
                user_text,
                max_tokens=700,
                temperature=0.55,
            )
            data = extract_json(raw)
            plan = ProductionPlan.model_validate(data)
            plan.instrumental = instrumental
            plan.optimized_idea = idea
            return self._normalize_plan(plan)
        except Exception:
            return self._fallback_plan(idea, instrumental=instrumental, vocal_hint=vocal_hint)

    def generate_lyrics(self, idea: str, plan: ProductionPlan) -> str:
        user_text = (
            f"Идея: {idea}\n"
            f"Жанр: {plan.genre} / {plan.subgenre}\n"
            f"Настроение: {plan.mood}\n"
            f"Энергия: {plan.energy}\n"
            f"BPM: {plan.bpm}\n"
            f"Вокал: {plan.vocal} — {plan.vocal_description}\n"
            f"Атмосфера: {plan.atmosphere}\n"
            f"Структура: {plan.structure}"
        )
        if plan.instrumental:
            return "[Instrumental]\n"

        try:
            lyrics = self._yandex.complete(
                self.LYRICS_SYSTEM,
                user_text,
                max_tokens=700,
                temperature=0.75,
            )
            return clean_text(lyrics)
        except Exception:
            return self._fallback_lyrics(idea)

    def build_style(self, plan: ProductionPlan) -> str:
        instruments = ", ".join(plan.instruments)
        parts = [
            f"{plan.genre} {plan.subgenre}",
            f"{plan.mood} mood",
            f"{plan.bpm} BPM",
            f"{plan.energy} energy",
            instruments,
            plan.vocal_description,
            plan.production_style,
            plan.atmosphere,
            "crystal clear mix",
            "commercial production",
        ]
        if plan.vocal == "duet":
            parts.append("male and female duet vocals")
        style = ", ".join(p for p in parts if p)
        return truncate(style, 950)

    def build_style_via_ai(self, plan: ProductionPlan, artist_ref: str = "") -> str:
        artist_part = ""
        if artist_ref.strip():
            artist_part = (
                f"Референс (без имён артистов в ответе): {artist_ref.strip()}. "
            )

        system_prompt = (
            "Ты эксперт по музыкальному продакшену для Suno V5.5. "
            "Собери профессиональный style prompt на английском: жанр, поджанр, "
            "настроение, BPM, энергия, инструменты, вокал, продакшн, атмосфера, микс. "
            "Одна строка через запятую, без имён артистов, максимум 900 символов."
        )
        user_text = (
            f"{artist_part}"
            f"Genre: {plan.genre}, Subgenre: {plan.subgenre}, Mood: {plan.mood}, "
            f"BPM: {plan.bpm}, Energy: {plan.energy}, Vocal: {plan.vocal}, "
            f"Instruments: {', '.join(plan.instruments)}, "
            f"Production: {plan.production_style}, Atmosphere: {plan.atmosphere}"
        )
        try:
            style = self._yandex.complete(
                system_prompt,
                user_text,
                max_tokens=250,
                temperature=0.55,
            )
            style = clean_text(style)
            if style:
                return truncate(style, 950)
        except Exception:
            pass
        return self.build_style(plan)

    @staticmethod
    def _normalize_plan(plan: ProductionPlan) -> ProductionPlan:
        plan.bpm = max(60, min(int(plan.bpm or 120), 200))
        plan.style_weight = max(0.0, min(float(plan.style_weight), 1.0))
        plan.weirdness_constraint = max(0.0, min(float(plan.weirdness_constraint), 1.0))
        plan.audio_weight = max(0.0, min(float(plan.audio_weight), 1.0))
        if plan.vocal not in {"male", "female", "duet", "auto"}:
            plan.vocal = "auto"
        if not plan.instruments:
            plan.instruments = ["synth", "drums", "bass"]
        return plan

    @staticmethod
    def _fallback_plan(
        idea: str,
        *,
        instrumental: bool = False,
        vocal_hint: str = "",
    ) -> ProductionPlan:
        vocal = vocal_hint if vocal_hint in {"male", "female", "duet", "auto"} else "auto"
        return ProductionPlan(
            genre="Pop",
            subgenre="Modern Pop",
            mood="uplifting",
            bpm=120,
            energy="medium",
            instruments=["synth", "drums", "bass", "electric guitar"],
            atmosphere="modern emotional atmosphere",
            production_style="radio-ready polished mix",
            vocal=vocal,
            vocal_description="expressive modern vocals",
            explanation_ru="Подобрали универсальный поп-стиль под вашу идею.",
            instrumental=instrumental,
            optimized_idea=idea,
        )

    @staticmethod
    def _fallback_lyrics(idea: str) -> str:
        snippet = truncate(idea, 80)
        return (
            f"[Verse 1]\n{snippet}\nМузыка ведёт меня вперёд\n\n"
            f"[Chorus]\nЭто моя песня, мой огонь\n"
            f"Звучит внутри и снаружи\n\n"
            f"[Verse 2]\nКаждый бит — как новый день\n"
            f"Я иду туда, где слышен свет\n\n"
            f"[Chorus]\nЭто моя песня, мой огонь\n"
            f"Звучит внутри и снаружи\n\n"
            f"[Outro]\nНавсегда."
        )