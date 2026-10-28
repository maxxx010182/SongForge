"""Unit tests for unclaimed generations showcase and 90-second preview limit."""

import uuid
from datetime import datetime, timedelta, timezone

from backend.database.db import get_connection, init_db
from backend.services.cabinet_service import CabinetService
from backend.services.showcase_admin_service import (
    ShowcaseAdminService,
    unclaimed_notice_message,
)
from backend.settings import PREVIEW_LIMIT_SEC, PREVIEW_MAX_BYTES


def test_preview_limit_setting():
    assert PREVIEW_LIMIT_SEC == 90
    # 128 кбит/с × 90 с = 1 440 000 байт. Меньше — отрывок оборвётся раньше плеера.
    assert PREVIEW_MAX_BYTES >= (128_000 // 8) * PREVIEW_LIMIT_SEC


def test_cabinet_history_preview_reports_90s():
    init_db()
    cab = CabinetService()
    uid = uuid.uuid4().hex[:8]
    user_id = f"user-{uid}"
    gen_id = f"gen-{uid}"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at)
            VALUES (?, ?, ?, 0, '2026-07-01T10:00:00')
            """,
            (user_id, f"test-{uid}@preview.local", f"Тестер-{uid}"),
        )
        conn.execute(
            """
            INSERT INTO generations (
                id, user_id, title, status, music_url_a, music_url_b,
                created_at, purchased
            ) VALUES (?, ?, 'Песня на 60 сек', 'success', 'https://cdn.example/a.mp3', 'https://cdn.example/b.mp3', '2026-07-01T10:00:00', 0)
            """,
            (gen_id, user_id),
        )

    res = cab.get_history_preview(user_id=user_id, generation_id=gen_id, variant="a")
    assert res["preview_limit_sec"] == 90
    assert "/api/audio/preview/" in res["preview_url"]


def test_list_and_publish_unclaimed_generations():
    init_db()
    svc = ShowcaseAdminService()
    uid = uuid.uuid4().hex[:8]
    admin_id = f"admin-{uid}"

    # Older than 14 days — moderation queue.
    past_time = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
    # Still inside the 14 days — the user can buy it.
    recent_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

    old_gen_id = f"gen-old-{uid}"
    recent_gen_id = f"gen-rec-{uid}"
    purchased_gen_id = f"gen-pur-{uid}"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at)
            VALUES (?, ?, ?, 0, '2026-07-01T10:00:00')
            """,
            (admin_id, f"admin-{uid}@showcase.local", f"Админ-{uid}"),
        )
        # 1. Eligible unclaimed generation (15 days, unpurchased, success)
        conn.execute(
            """
            INSERT INTO generations (
                id, user_id, title, style, lyrics, status, music_url_a, music_url_b,
                created_at, purchased
            ) VALUES (?, ?, 'Забытый рок-хит', 'Рок', 'Текст куплета', 'success',
                     'https://cdn.example/rock_a.mp3', 'https://cdn.example/rock_b.mp3', ?, 0)
            """,
            (old_gen_id, admin_id, past_time),
        )
        # 2. Ineligible recent generation (10 days)
        conn.execute(
            """
            INSERT INTO generations (
                id, user_id, title, status, music_url_a, created_at, purchased
            ) VALUES (?, ?, 'Свежий трек', 'success', 'https://cdn.example/fresh.mp3', ?, 0)
            """,
            (recent_gen_id, admin_id, recent_time),
        )
        # 3. Ineligible purchased generation
        conn.execute(
            """
            INSERT INTO generations (
                id, user_id, title, status, music_url_a, created_at, purchased
            ) VALUES (?, ?, 'Купленный трек', 'success', 'https://cdn.example/pur.mp3', ?, 1)
            """,
            (purchased_gen_id, admin_id, past_time),
        )

    # Verify listing
    unclaimed = svc.list_unclaimed_generations(hours=48, limit=50)
    found_ids = [u["id"] for u in unclaimed]
    assert old_gen_id in found_ids
    assert recent_gen_id not in found_ids
    assert purchased_gen_id not in found_ids

    # Find the specific item
    target = next(u for u in unclaimed if u["id"] == old_gen_id)
    assert target["title"] == "Забытый рок-хит"
    assert target["has_a"] is True
    assert target["has_b"] is True
    assert "/api/audio/preview/" in target["preview_url_a"]
    assert target["already_published"] is False

    # Publish variant A under custom author
    pub = svc.publish_unclaimed_generation(
        admin_user_id=admin_id,
        admin_role="admin",
        generation_id=old_gen_id,
        variant="A",
        author_name="Студия SongForge",
        title="Забытый рок-хит (Релиз)",
    )
    assert pub["success"] is True
    assert pub["variant"] == "A"
    assert pub["author_name"] == "Студия SongForge"

    # Now verify it shows up in explore / showcase
    cab = CabinetService()
    explore = cab.list_explore(limit=20)
    explore_ids = [e["id"] for e in explore]
    assert pub["library_id"] in explore_ids
    exp_item = next(e for e in explore if e["id"] == pub["library_id"])
    assert exp_item["title"] == "Забытый рок-хит (Релиз)"
    assert exp_item["author_name"] == "Студия SongForge"

    # Publishing does not mark the demo as bought. After 14 days the user cannot buy it.
    with get_connection() as conn:
        g = conn.execute(
            "SELECT purchased FROM generations WHERE id = ?", (old_gen_id,)
        ).fetchone()
        assert g["purchased"] == 0
    try:
        CabinetService().purchase_generation(user_id=admin_id, generation_id=old_gen_id)
        raise AssertionError("покупка после 14 дней должна быть закрыта")
    except ValueError as exc:
        assert "Срок выкупа прошёл" in str(exc)

    try:
        svc.publish_unclaimed_generation(
            admin_user_id=admin_id,
            admin_role="admin",
            generation_id=recent_gen_id,
            variant="A",
        )
        raise AssertionError("раньше 14 дней публиковать нельзя")
    except ValueError as exc:
        assert "14 дней" in str(exc)


def test_delete_expired_demo_keeps_paid_song(monkeypatch):
    from backend.services.storage_service import StorageService

    monkeypatch.setattr(StorageService, "enabled", lambda self: False)
    init_db()
    svc = ShowcaseAdminService()
    cab = CabinetService()
    uid = uuid.uuid4().hex[:8]
    user_id = f"user-{uid}"
    old_id = f"gen-del-{uid}"
    young_id = f"gen-young-{uid}"
    fresh_id = f"gen-fresh-{uid}"
    paid_id = f"gen-paid-{uid}"
    old_time = (datetime.now(timezone.utc) - timedelta(days=16)).isoformat()
    young_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, balance, created_at)
            VALUES (?, ?, ?, 1, '2026-07-01T10:00:00')
            """,
            (user_id, f"demo-{uid}@claim.local", f"Слушатель-{uid}"),
        )
        conn.execute(
            """
            INSERT INTO generations (
                id, user_id, title, idea, status, music_url_a,
                created_at, purchased
            ) VALUES (?, ?, 'Тихая песня', 'секретный сюжет про маму', 'success',
                     'https://cdn.example/quiet.mp3', ?, 0)
            """,
            (old_id, user_id, old_time),
        )
        conn.execute(
            """
            INSERT INTO generations (
                id, user_id, title, status, music_url_a, created_at, purchased
            ) VALUES (?, ?, 'Свежая песня', 'success', 'https://cdn.example/young.mp3', ?, 0)
            """,
            (young_id, user_id, young_time),
        )
        conn.execute(
            """
            INSERT INTO generations (
                id, user_id, title, status, music_url_a, created_at, purchased
            ) VALUES (?, ?, 'Ещё рано', 'success', 'https://cdn.example/fresh.mp3', ?, 0)
            """,
            (fresh_id, user_id, young_time),
        )
        conn.execute(
            """
            INSERT INTO generations (
                id, user_id, title, status, music_url_a, created_at, purchased
            ) VALUES (?, ?, 'Уже куплена', 'success', 'https://cdn.example/paid.mp3', ?, 1)
            """,
            (paid_id, user_id, old_time),
        )
        conn.execute(
            """
            INSERT INTO messenger_followups (
                id, contact_id, user_id, generation_id, kind, due_at, created_at
            ) VALUES (?, 'contact-x', ?, ?, 'keep_d14', ?, ?)
            """,
            (f"fu-{uid}", user_id, old_id, old_time, old_time),
        )

    notice = unclaimed_notice_message("Тихая песня")
    assert "Тихая песня" in notice
    assert "не выкуплена 14 дней" in notice
    assert "секретный сюжет" not in notice
    queued = svc.list_unclaimed_generations(limit=100)
    assert old_id in [item["id"] for item in queued]
    assert "секретный сюжет" not in " ".join(
        item["message"] for item in svc.unclaimed_admin_notices()
    )

    history = {item["id"]: item for item in cab.list_history(user_id)}
    assert history[old_id]["claim_open"] is False
    assert history[young_id]["claim_open"] is True
    assert paid_id not in history

    bought = cab.purchase_generation(user_id=user_id, generation_id=young_id)
    assert bought["success"] is True
    assert bought["balance"] == 0

    try:
        svc.delete_unclaimed_generation(generation_id=young_id)
        raise AssertionError("купленную песню удалять нельзя")
    except ValueError as exc:
        assert "Купленную" in str(exc)

    try:
        svc.delete_unclaimed_generation(generation_id=paid_id)
        raise AssertionError("купленную песню удалять нельзя")
    except ValueError as exc:
        assert "Купленную" in str(exc)

    try:
        svc.delete_unclaimed_generation(generation_id=fresh_id)
        raise AssertionError("раньше 14 дней удалять нельзя")
    except ValueError as exc:
        assert "14 дней" in str(exc)

    published = svc.publish_unclaimed_generation(
        admin_user_id=user_id,
        admin_role="admin",
        generation_id=old_id,
        variant="A",
        title="Тихая песня",
    )
    removed = svc.delete_unclaimed_generation(generation_id=old_id)
    assert removed["removed_tracks"] == 1
    assert removed["storage_cleared"] is True
    assert removed["title"] == "Тихая песня"

    with get_connection() as conn:
        assert conn.execute(
            "SELECT id FROM generations WHERE id = ?",
            (old_id,),
        ).fetchone() is None
        assert conn.execute(
            "SELECT id FROM user_library WHERE id = ?",
            (published["library_id"],),
        ).fetchone() is None
        follow = conn.execute(
            "SELECT canceled_at FROM messenger_followups WHERE generation_id = ?",
            (old_id,),
        ).fetchone()
        assert follow["canceled_at"]
        fresh = conn.execute(
            "SELECT id FROM generations WHERE id = ?",
            (fresh_id,),
        ).fetchone()
        assert fresh is not None

    explore_ids = [item["id"] for item in cab.list_explore(limit=50)]
    assert published["library_id"] not in explore_ids
