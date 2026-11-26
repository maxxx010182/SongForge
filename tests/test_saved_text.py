"""Повтор кнопки текста показывает уже сохранённый текст и не зовёт Кие."""

import json
import uuid
from pathlib import Path

from backend.database.db import get_connection, init_db, utc_now
from backend.models import ProductionPlan
from backend.services.ai_producer import AiProducer


def _insert(user_id: str, production_id: str, idea: str, *, task_id: str = "") -> None:
    plan = ProductionPlan(own_voice_id="secret-voice")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at, trial_generations_used)
            VALUES (?, ?, ?, 1, ?, 1)
            """,
            (user_id, f"{user_id}@example.com", user_id[:12], utc_now()),
        )
        conn.execute(
            """
            INSERT INTO generations (
                id, created_at, idea, optimized_idea, title, lyrics, style,
                plan_json, status, task_id, user_id
            ) VALUES (?, ?, ?, ?, 'Песня', ?, 'pop', ?, 'planned', ?, ?)
            """,
            (
                production_id,
                utc_now(),
                idea,
                idea,
                "куплет уже написан " * 20,
                json.dumps(plan.model_dump()),
                task_id,
                user_id,
            ),
        )


def _cleanup(user_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM generations WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def test_saved_text_is_shown_without_kie():
    init_db()
    user_id = str(uuid.uuid4())
    production_id = str(uuid.uuid4())
    idea = "весёлая песня ко дню рождения"
    _insert(user_id, production_id, idea)
    producer = AiProducer()
    producer.set_actor(user_id=user_id)
    producer._builder.build = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Кие звать не нужно")
    )
    try:
        saved = producer.produce(idea, reuse_saved=True)
        assert saved.reused is True
        assert saved.production_id == production_id
        assert "уже написан" in saved.lyrics
        assert saved.plan.own_voice_id == ""

        spaced = producer.produce("  весёлая   песня ко дню рождения  ", reuse_saved=True)
        assert spaced.production_id == production_id
    finally:
        producer.clear_actor()
        _cleanup(user_id)


def test_other_idea_started_song_and_forced_write_do_not_reuse():
    init_db()
    user_id = str(uuid.uuid4())
    other_user = str(uuid.uuid4())
    idea = "тихая песня про дорогу"
    _insert(user_id, str(uuid.uuid4()), idea, task_id="already-started")
    _insert(other_user, str(uuid.uuid4()), idea)
    producer = AiProducer()
    calls = {"n": 0}

    def _called(*args, **kwargs):
        calls["n"] += 1
        raise ValueError("новая запись")

    producer._builder.build = _called
    producer.set_actor(user_id=user_id)
    try:
        for attempt in (
            {"idea": idea, "reuse_saved": True},
            {"idea": "совсем другая песня", "reuse_saved": True},
            {"idea": idea, "reuse_saved": False},
        ):
            try:
                producer.produce(attempt["idea"], reuse_saved=attempt["reuse_saved"])
            except ValueError as exc:
                assert str(exc) == "новая запись"
            except AssertionError:
                raise
        assert calls["n"] == 3
    finally:
        producer.clear_actor()
        _cleanup(user_id)
        _cleanup(other_user)


def test_page_asks_to_reuse_only_when_the_text_is_hidden():
    page = Path("index.html").read_text(encoding="utf-8")
    assert "if(!visibleSongText())textPayload.reuse_saved=true" in page
    assert "Текст уже был готов. Показываю его. Кие снова не вызываю." in page
