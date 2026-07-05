import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.settings import DATA_DIR, DB_PATH


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generations (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                created_at TEXT NOT NULL,
                idea TEXT,
                optimized_idea TEXT,
                title TEXT,
                lyrics TEXT,
                style TEXT,
                plan_json TEXT,
                status TEXT NOT NULL,
                music_url_a TEXT,
                music_url_b TEXT,
                image_url_a TEXT,
                image_url_b TEXT,
                duration_a REAL,
                duration_b REAL,
                fail_code TEXT,
                fail_msg TEXT,
                user_id TEXT,
                guest_id TEXT,
                purchased INTEGER NOT NULL DEFAULT 0,
                showcase_eligible INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_generations_task_id ON generations(task_id)"
        )
        _migrate_generations_columns(conn)
        _migrate_users_columns(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_generations_user_id ON generations(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_generations_guest_id ON generations(guest_id)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT,
                display_name TEXT,
                balance INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_identities (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_user_id TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(provider, provider_user_id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guest_sessions (
                guest_id TEXT PRIMARY KEY,
                generations_used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_auth_codes (
                email TEXT PRIMARY KEY,
                code TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_library (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                generation_id TEXT NOT NULL,
                title TEXT,
                variant TEXT,
                audio_url TEXT,
                image_url TEXT,
                duration REAL,
                lyrics TEXT,
                genre TEXT,
                purchased_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_library_user_id ON user_library(user_id)"
        )
        _migrate_user_library_columns(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_orders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                package_id TEXT NOT NULL,
                notes_amount INTEGER NOT NULL,
                price_rub INTEGER NOT NULL,
                status TEXT NOT NULL,
                provider TEXT,
                provider_payment_id TEXT,
                created_at TEXT NOT NULL,
                paid_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_payment_orders_user ON payment_orders(user_id)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                invited_by TEXT,
                created_at TEXT NOT NULL,
                last_access_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_users_role ON admin_users(role)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id TEXT PRIMARY KEY,
                admin_user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                details_json TEXT,
                ip_address TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_log(created_at)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS track_likes (
                user_id TEXT NOT NULL,
                library_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, library_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_track_likes_library ON track_likes(library_id)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS track_comments (
                id TEXT PRIMARY KEY,
                library_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_track_comments_library ON track_comments(library_id)"
        )
        _migrate_engagement_columns(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS showcase_tracks (
                id TEXT PRIMARY KEY,
                generation_id TEXT NOT NULL,
                published_at TEXT NOT NULL,
                preview_url_a TEXT,
                preview_url_b TEXT,
                image_url TEXT,
                title TEXT,
                genre TEXT
            )
            """
        )

def _migrate_user_library_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(user_library)")}
    if "published_at" not in existing:
        conn.execute("ALTER TABLE user_library ADD COLUMN published_at TEXT")
    if "likes" not in existing:
        conn.execute(
            "ALTER TABLE user_library ADD COLUMN likes INTEGER NOT NULL DEFAULT 0"
        )
    if "published_author_name" not in existing:
        conn.execute("ALTER TABLE user_library ADD COLUMN published_author_name TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_library_published ON user_library(published_at)"
    )


def _migrate_users_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "avatar_url" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
    if "trial_generations_used" not in existing:
        conn.execute(
            "ALTER TABLE users ADD COLUMN trial_generations_used INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            """
            UPDATE users
            SET trial_generations_used = 1
            WHERE id IN (
                SELECT DISTINCT user_id FROM generations
                WHERE user_id IS NOT NULL AND user_id != ''
            )
            """
        )
    if "is_persona" not in existing:
        conn.execute(
            "ALTER TABLE users ADD COLUMN is_persona INTEGER NOT NULL DEFAULT 0"
        )
    if "nickname_confirmed" not in existing:
        conn.execute(
            "ALTER TABLE users ADD COLUMN nickname_confirmed INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            """
            UPDATE users
            SET nickname_confirmed = 1
            WHERE COALESCE(is_persona, 0) = 0
            """
        )
        _dedupe_real_user_display_names(conn)
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_display_name_unique
            ON users(LOWER(display_name))
            WHERE COALESCE(is_persona, 0) = 0
              AND display_name IS NOT NULL
              AND TRIM(display_name) != ''
            """
        )


def _dedupe_real_user_display_names(conn: sqlite3.Connection) -> None:
    """Развести дубли display_name у реальных пользователей перед UNIQUE-индексом."""
    rows = conn.execute(
        """
        SELECT id, display_name
        FROM users
        WHERE COALESCE(is_persona, 0) = 0
        ORDER BY created_at ASC, id ASC
        """
    ).fetchall()
    seen: dict[str, str] = {}
    for row in rows:
        raw = (row["display_name"] or "").strip()
        if not raw:
            continue
        key = raw.casefold()
        if key not in seen:
            seen[key] = row["id"]
            continue
        base = raw
        suffix = 2
        while suffix < 1000:
            candidate = f"{base}_{suffix}"
            cand_key = candidate.casefold()
            if cand_key not in seen:
                conn.execute(
                    "UPDATE users SET display_name = ? WHERE id = ?",
                    (candidate, row["id"]),
                )
                seen[cand_key] = row["id"]
                break
            suffix += 1


def _migrate_engagement_columns(conn: sqlite3.Connection) -> None:
    like_cols = {row[1] for row in conn.execute("PRAGMA table_info(track_likes)")}
    if "is_seed" not in like_cols:
        conn.execute(
            "ALTER TABLE track_likes ADD COLUMN is_seed INTEGER NOT NULL DEFAULT 0"
        )

    comment_cols = {row[1] for row in conn.execute("PRAGMA table_info(track_comments)")}
    if "is_seed" not in comment_cols:
        conn.execute(
            "ALTER TABLE track_comments ADD COLUMN is_seed INTEGER NOT NULL DEFAULT 0"
        )


def _migrate_generations_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(generations)")}
    additions = {
        "user_id": "TEXT",
        "guest_id": "TEXT",
        "purchased": "INTEGER NOT NULL DEFAULT 0",
        "showcase_eligible": "INTEGER NOT NULL DEFAULT 1",
        "note_charged": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, col_type in additions.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE generations ADD COLUMN {column} {col_type}")


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)