"""Админ-витрина: персоны, seed-лайки и комментарии для оживления МузПлощадки."""

from __future__ import annotations

import random
import re
import uuid
from datetime import datetime, timedelta, timezone

from backend.database.db import get_connection, init_db, utc_now
from backend.services.cabinet_service import CabinetService

# Готовые «живые» ники — как на реальной площадке, не «Марина» / «Алексей».
PERSONA_NICKNAMES = (
    "Величайший из величайших",
    "Бешенный",
    "Мракобес",
    "Викуся",
    "Ночной волк",
    "Сладкая ягода",
    "Грустный джаз",
    "Рок-феникс",
    "Тихий гений",
    "Битмейкер из подвала",
    "Король припева",
    "Меломан 3000",
    "Сонный кот",
    "Дерзкий бит",
    "Поэт с крыши",
    "Звёздная пыль",
    "Лунный свет",
    "Огненный такт",
    "Северный ветер",
    "Южный хип-хоп",
    "Кибер-скрипач",
    "Виниловая душа",
    "Басовый монстр",
    "Хрупкий голос",
    "Громкий шёпот",
    "Старый панк",
    "Молодой джаз",
    "Рэп-философ",
    "Инди-фея",
    "Синт-поп мечтатель",
    "Акустический бродяга",
    "Электро-сова",
    "Ритм-охотник",
    "Мелодия в кармане",
    "Хит за хитом",
    "Слушатель №1",
    "Голос из тумана",
    "Соло на закате",
    "Барабанный дождь",
    "Гитарный призрак",
    "Пианист без пианино",
    "Вокалист с балкона",
    "Чилловый котёнок",
    "Драйвовый зайчик",
    "Мрачный оптимист",
    "Весёлый пессимист",
    "Королева куплетов",
    "Принц бриджа",
    "Дедушка фанк",
    "Тётя диско",
    "Капитан хоруса",
    "Пилот автотюна",
    "Шёпот в наушниках",
    "Громкость на максимум",
    "Тихий шторм",
    "Солнечный рефрен",
    "Дождливый вайб",
    "Снежный бит",
    "Песочный рок",
    "Морской ритм",
    "Горный эхо",
    "Лесной мотив",
    "Городской фольк",
    "Деревенский рэп",
    "Космический диджей",
    "Земной мелодист",
    "Небесный бас",
    "Подземный хит",
    "Вечный слушатель",
    "Первый фанат",
    "Последний романтик",
    "Середина ноты",
    "Полтакт",
    "Целая октава",
)

PERSONA_ADJECTIVES = (
    "Бешеный",
    "Тихий",
    "Ночной",
    "Сладкий",
    "Злой",
    "Весёлый",
    "Грустный",
    "Дерзкий",
    "Ленивый",
    "Бодрый",
    "Мрачный",
    "Солнечный",
    "Лунный",
    "Огненный",
    "Ледяной",
    "Космический",
    "Деревенский",
    "Городской",
    "Старый",
    "Молодой",
    "Вечный",
    "Случайный",
    "Настоящий",
    "Секретный",
    "Громкий",
    "Тихий",
)

PERSONA_NOUNS = (
    "меломан",
    "рокер",
    "поэт",
    "битмейкер",
    "вокалист",
    "гитарист",
    "барабанщик",
    "скрипач",
    "фанат",
    "слушатель",
    "диджей",
    "композитор",
    "импровизатор",
    "романтик",
    "панк",
    "джазмен",
    "рэпер",
    "синтезаторщик",
    "охотник за хитами",
    "коллекционер винилов",
    "ночной совёнок",
    "дневной жаворонок",
    "король припева",
    "принц бриджа",
    "фея куплетов",
)

SEED_LIKE_CAP_PER_TRACK = 100
MAX_LIKES_PER_REQUEST = 50

SEED_COMMENT_TEMPLATES = (
    "ого, это реально зашло",
    "второй раз подряд включаю",
    "припев залипательный, честно",
    "для дороги в машину — то что надо",
    "не ожидал такого, приятно удивило",
    "добавил в плейлист на вечер",
    "голос цепляет с первых секунд",
    "вот бы такую на праздник поставить",
    "слушаю и сам улыбаюсь",
    "бас ровно то что надо",
    "куплеты цепляют, не отпускает",
    "под вечерний чай зашло идеально",
    "другу скинул — тоже оценил",
    "аранжировка плотная, кайф",
    "текст живой, не шаблонный",
    "на повторе уже минут пять",
    "для подарка близкому — самое оно",
    "атмосфера ловит сразу",
    "редко такое попадается, респект",
    "под грустное настроение — в точку",
    "энергия есть, не скучно",
    "мелодия в голове осталась",
    "хотелось бы полную версию ещё раз",
    "с первого прослушивания в избранное",
    "звучит дороже чем ожидал",
    "в наушниках раскрывается лучше",
    "припев хочется подпевать",
    "такое слушать приятно",
    "ну красота же",
    "ставлю лайк и иду дальше по ленте",
)


class ShowcaseAdminService:
    def __init__(self) -> None:
        init_db()
        self._cabinet = CabinetService()

    @staticmethod
    def _random_past_iso(*, max_days: int = 7) -> str:
        seconds = random.randint(3600, max(3601, max_days * 24 * 3600))
        moment = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        return moment.isoformat()

    def _assert_showcase_access(self, row, *, admin_user_id: str, admin_role: str) -> None:
        if not row:
            raise ValueError("Опубликованный трек не найден")
        if admin_role != "super_admin" and row["user_id"] != admin_user_id:
            raise PermissionError("Можно редактировать только свои опубликованные треки")

    def _get_published_track(self, conn, library_id: str):
        return conn.execute(
            """
            SELECT ul.*, u.display_name AS author_name
            FROM user_library ul
            LEFT JOIN users u ON u.id = ul.user_id
            WHERE ul.id = ?
              AND ul.published_at IS NOT NULL
              AND ul.published_at != ''
            """,
            (library_id,),
        ).fetchone()

    def list_personas(self, *, limit: int = 100) -> list[dict]:
        limit = max(1, min(limit, 200))
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, display_name, created_at
                FROM users
                WHERE COALESCE(is_persona, 0) = 1
                ORDER BY display_name
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def persona_count(self) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE COALESCE(is_persona, 0) = 1",
            ).fetchone()
        return int(row["c"] if row else 0)

    @staticmethod
    def _compose_persona_nicknames(*, want: int) -> list[str]:
        """Собрать уникальный список креативных ников для новых персон."""
        want = max(1, min(want, 50))
        pool = list(PERSONA_NICKNAMES)
        random.shuffle(pool)
        chosen: list[str] = []
        seen: set[str] = set()

        def add(name: str) -> bool:
            cleaned = re.sub(r"\s+", " ", (name or "").strip())
            if len(cleaned) < 2 or len(cleaned) > 40:
                return False
            key = cleaned.casefold()
            if key in seen:
                return False
            seen.add(key)
            chosen.append(cleaned)
            return True

        for nick in pool:
            if len(chosen) >= want:
                break
            add(nick)

        attempts = 0
        while len(chosen) < want and attempts < want * 40:
            attempts += 1
            adj = random.choice(PERSONA_ADJECTIVES)
            noun = random.choice(PERSONA_NOUNS)
            pattern = random.randint(0, 3)
            if pattern == 0:
                candidate = f"{adj} {noun}"
            elif pattern == 1:
                candidate = f"{noun.capitalize()} {adj.lower()}"
            elif pattern == 2:
                candidate = f"{adj} {noun} {random.randint(2, 99)}"
            else:
                candidate = f"{random.choice(PERSONA_NICKNAMES)} {random.randint(2, 9)}"
            add(candidate)

        return chosen

    def create_personas(
        self,
        *,
        names: list[str] | None = None,
        count: int = 10,
    ) -> list[dict]:
        chosen: list[str] = []
        if names:
            for raw in names:
                name = re.sub(r"\s+", " ", (raw or "").strip())
                if name and name not in chosen:
                    chosen.append(name)
        else:
            chosen = self._compose_persona_nicknames(want=count)

        created: list[dict] = []
        now = utc_now()
        with get_connection() as conn:
            for display_name in chosen:
                existing = conn.execute(
                    """
                    SELECT id FROM users
                    WHERE LOWER(display_name) = LOWER(?)
                    """,
                    (display_name,),
                ).fetchone()
                if existing:
                    continue
                user_id = str(uuid.uuid4())
                email = f"persona-{user_id[:10]}@internal.songforge"
                conn.execute(
                    """
                    INSERT INTO users (
                        id, email, display_name, balance, created_at, is_persona
                    ) VALUES (?, ?, ?, 0, ?, 1)
                    """,
                    (user_id, email, display_name, now),
                )
                created.append(
                    {"id": user_id, "display_name": display_name, "created_at": now}
                )
        return created

    def list_showcase_tracks(
        self,
        *,
        admin_user_id: str,
        admin_role: str,
        limit: int = 50,
    ) -> list[dict]:
        limit = max(1, min(limit, 100))
        params: list = []
        owner_filter = ""
        if admin_role != "super_admin":
            owner_filter = " AND ul.user_id = ?"
            params.append(admin_user_id)
        params.append(limit)

        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    ul.id,
                    ul.title,
                    ul.user_id AS author_user_id,
                    ul.published_at,
                    u.display_name AS author_name,
                    (
                        SELECT COUNT(*) FROM track_likes tl
                        WHERE tl.library_id = ul.id
                    ) AS likes,
                    (
                        SELECT COUNT(*) FROM track_likes tl
                        WHERE tl.library_id = ul.id
                          AND COALESCE(tl.is_seed, 0) = 1
                    ) AS seed_likes,
                    (
                        SELECT COUNT(*) FROM track_comments tc
                        WHERE tc.library_id = ul.id
                    ) AS comments,
                    (
                        SELECT COUNT(*) FROM track_comments tc
                        WHERE tc.library_id = ul.id
                          AND COALESCE(tc.is_seed, 0) = 1
                    ) AS seed_comments
                FROM user_library ul
                LEFT JOIN users u ON u.id = ul.user_id
                WHERE ul.published_at IS NOT NULL
                  AND ul.published_at != ''
                  {owner_filter}
                ORDER BY likes DESC, ul.published_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"] or "Без названия",
                "author_name": (r["author_name"] or "").strip() or "Аноним",
                "author_user_id": r["author_user_id"],
                "likes": int(r["likes"] or 0),
                "seed_likes": int(r["seed_likes"] or 0),
                "comments": int(r["comments"] or 0),
                "seed_comments": int(r["seed_comments"] or 0),
                "published_at": r["published_at"] or "",
            }
            for r in rows
        ]

    def add_seed_likes(
        self,
        *,
        admin_user_id: str,
        admin_role: str,
        library_id: str,
        count: int,
    ) -> dict:
        count = max(1, min(int(count), MAX_LIKES_PER_REQUEST))
        with get_connection() as conn:
            track = self._get_published_track(conn, library_id)
            self._assert_showcase_access(
                track, admin_user_id=admin_user_id, admin_role=admin_role
            )

            seed_total = conn.execute(
                """
                SELECT COUNT(*) AS c FROM track_likes
                WHERE library_id = ? AND COALESCE(is_seed, 0) = 1
                """,
                (library_id,),
            ).fetchone()["c"]
            if int(seed_total) + count > SEED_LIKE_CAP_PER_TRACK:
                raise ValueError(
                    f"Лимит seed-лайков на трек: {SEED_LIKE_CAP_PER_TRACK}"
                )

            personas = conn.execute(
                """
                SELECT u.id
                FROM users u
                WHERE COALESCE(u.is_persona, 0) = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM track_likes tl
                      WHERE tl.library_id = ? AND tl.user_id = u.id
                  )
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (library_id, count),
            ).fetchall()

            if len(personas) < count:
                raise ValueError(
                    f"Недостаточно свободных персон: нужно {count}, "
                    f"доступно {len(personas)}. Создайте ещё персон."
                )

            added = 0
            for persona in personas:
                conn.execute(
                    """
                    INSERT INTO track_likes (
                        user_id, library_id, created_at, is_seed
                    ) VALUES (?, ?, ?, 1)
                    """,
                    (persona["id"], library_id, self._random_past_iso()),
                )
                added += 1

            likes = self._cabinet._sync_library_likes_count(conn, library_id)

        return {"success": True, "added": added, "likes": likes}

    def add_seed_comment(
        self,
        *,
        admin_user_id: str,
        admin_role: str,
        library_id: str,
        persona_id: str,
        text: str,
        created_at: str | None = None,
    ) -> dict:
        body = (text or "").strip()
        if len(body) < 2:
            raise ValueError("Комментарий слишком короткий")
        if len(body) > 500:
            raise ValueError("Комментарий не длиннее 500 символов")

        with get_connection() as conn:
            track = self._get_published_track(conn, library_id)
            self._assert_showcase_access(
                track, admin_user_id=admin_user_id, admin_role=admin_role
            )

            persona = conn.execute(
                """
                SELECT id, display_name FROM users
                WHERE id = ? AND COALESCE(is_persona, 0) = 1
                """,
                (persona_id,),
            ).fetchone()
            if not persona:
                raise ValueError("Персона не найдена")

            comment_id = str(uuid.uuid4())
            when = (created_at or "").strip() or self._random_past_iso()
            conn.execute(
                """
                INSERT INTO track_comments (
                    id, library_id, user_id, text, created_at, is_seed
                ) VALUES (?, ?, ?, ?, ?, 1)
                """,
                (comment_id, library_id, persona_id, body, when),
            )

        return {
            "success": True,
            "id": comment_id,
            "text": body,
            "author_name": (persona["display_name"] or "").strip() or "Аноним",
            "created_at": when,
        }

    def update_track_title(
        self,
        *,
        admin_user_id: str,
        admin_role: str,
        library_id: str,
        title: str,
    ) -> dict:
        new_title = (title or "").strip()
        if len(new_title) < 2:
            raise ValueError("Название слишком короткое")
        if len(new_title) > 120:
            raise ValueError("Название не длиннее 120 символов")

        with get_connection() as conn:
            track = self._get_published_track(conn, library_id)
            self._assert_showcase_access(
                track, admin_user_id=admin_user_id, admin_role=admin_role
            )
            conn.execute(
                "UPDATE user_library SET title = ? WHERE id = ?",
                (new_title, library_id),
            )
        return {"success": True, "title": new_title}

    def update_author_display_name(
        self,
        *,
        admin_user_id: str,
        admin_role: str,
        library_id: str,
        display_name: str,
    ) -> dict:
        name = (display_name or "").strip()
        if len(name) < 2:
            raise ValueError("Имя слишком короткое")
        if len(name) > 60:
            raise ValueError("Имя не длиннее 60 символов")

        with get_connection() as conn:
            track = self._get_published_track(conn, library_id)
            self._assert_showcase_access(
                track, admin_user_id=admin_user_id, admin_role=admin_role
            )
            owner = conn.execute(
                """
                SELECT id, display_name FROM users
                WHERE id = ? AND COALESCE(is_persona, 0) = 0
                """,
                (track["user_id"],),
            ).fetchone()
            if not owner:
                raise ValueError("Владелец трека не найден")
            conn.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (name, owner["id"]),
            )
        return {
            "success": True,
            "author_user_id": owner["id"],
            "display_name": name,
        }

    def clear_seed_engagement(
        self,
        *,
        admin_user_id: str,
        admin_role: str,
        library_id: str,
    ) -> dict:
        with get_connection() as conn:
            track = self._get_published_track(conn, library_id)
            self._assert_showcase_access(
                track, admin_user_id=admin_user_id, admin_role=admin_role
            )
            likes_removed = conn.execute(
                """
                DELETE FROM track_likes
                WHERE library_id = ? AND COALESCE(is_seed, 0) = 1
                """,
                (library_id,),
            ).rowcount
            comments_removed = conn.execute(
                """
                DELETE FROM track_comments
                WHERE library_id = ? AND COALESCE(is_seed, 0) = 1
                """,
                (library_id,),
            ).rowcount
            likes = self._cabinet._sync_library_likes_count(conn, library_id)

        return {
            "success": True,
            "likes_removed": int(likes_removed),
            "comments_removed": int(comments_removed),
            "likes": likes,
        }

    def boost_track(
        self,
        *,
        admin_user_id: str,
        admin_role: str,
        library_id: str,
        likes: int = 12,
        comments: int = 3,
    ) -> dict:
        likes = max(1, min(int(likes), MAX_LIKES_PER_REQUEST))
        comments = max(0, min(int(comments), 8))

        if self.persona_count() < max(comments, 3):
            self.create_personas(count=20)

        like_result = self.add_seed_likes(
            admin_user_id=admin_user_id,
            admin_role=admin_role,
            library_id=library_id,
            count=likes,
        )

        persona_rows = self.list_personas(limit=50)
        random.shuffle(persona_rows)
        added_comments: list[dict] = []
        templates = list(SEED_COMMENT_TEMPLATES)
        random.shuffle(templates)

        for idx in range(comments):
            if not persona_rows:
                break
            persona = persona_rows[idx % len(persona_rows)]
            text = templates[idx % len(templates)]
            added_comments.append(
                self.add_seed_comment(
                    admin_user_id=admin_user_id,
                    admin_role=admin_role,
                    library_id=library_id,
                    persona_id=persona["id"],
                    text=text,
                )
            )

        return {
            "success": True,
            "likes_added": like_result["added"],
            "likes": like_result["likes"],
            "comments_added": len(added_comments),
            "comments": added_comments,
        }