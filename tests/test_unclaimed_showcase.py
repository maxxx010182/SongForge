"""Unit tests for unclaimed generations showcase and 60-second preview limit."""

import uuid
from datetime import datetime, timedelta, timezone

from backend.database.db import get_connection, init_db
from backend.services.cabinet_service import CabinetService
from backend.services.showcase_admin_service import ShowcaseAdminService
from backend.settings import PREVIEW_LIMIT_SEC


def test_preview_limit_setting():
    assert PREVIEW_LIMIT_SEC == 60


def test_cabinet_history_preview_reports_60s():
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
    assert res["preview_limit_sec"] == 60
    assert "/api/audio/preview/" in res["preview_url"]


def test_list_and_publish_unclaimed_generations():
    init_db()
    svc = ShowcaseAdminService()
    uid = uuid.uuid4().hex[:8]
    admin_id = f"admin-{uid}"

    # Past date > 48 hours ago
    past_time = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
    # Recent date < 48 hours ago
    recent_time = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()

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
        # 1. Eligible unclaimed generation (>48h, unpurchased, success)
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
        # 2. Ineligible recent generation (<48h)
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

    # Original generation remains unpurchased so user can buy it later
    with get_connection() as conn:
        g = conn.execute(
            "SELECT purchased FROM generations WHERE id = ?", (old_gen_id,)
        ).fetchone()
        assert g["purchased"] == 0
