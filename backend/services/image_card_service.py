"""Проба открытки: описание, форма 3:4, обычный размер.

Кредит списывается только вместе с сохранённой картинкой.
Ноты песни, оплата и очередь музыки здесь не меняются.
"""

from __future__ import annotations

import ipaddress
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from backend.database.db import get_connection, init_db, utc_now
from backend.logger import log
from backend.services import image_gate
from backend.services.kie_image_client import KieImageClient
from backend.services.storage_service import StorageService

DAILY_CAP = 5
CREDIT_COST = 1
DRAW_WAIT_SEC = 48
POLL_PAUSE_SEC = 3
MISSING_TASK_SEC = 120
GIVE_UP_SEC = 600
MIN_IMAGE_BYTES = 8000
MAX_IMAGE_BYTES = 12_000_000


class ImageCardError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class ImageCardService:
    def __init__(self) -> None:
        init_db()
        self._kie = KieImageClient()
        self._storage = StorageService()
        self._lock = threading.Lock()

    def status_for(self, user: dict | None) -> dict:
        if not user:
            return image_gate.guest_view()
        self.settle(str(user["id"]))
        credits = self.credits_of(str(user["id"]))
        used = self.daily_used(str(user["id"]))
        if credits < CREDIT_COST:
            detail = image_gate.NEED_CREDITS
        else:
            detail = image_gate.READY
        return {
            "open": True,
            "trial": True,
            "credits": credits,
            "cost": CREDIT_COST,
            "daily_cap": DAILY_CAP,
            "daily_used": used,
            "detail": detail,
            "cards": self.list_cards(str(user["id"])),
        }

    def draw(self, *, user: dict | None, prompt: str) -> dict:
        if not user:
            raise ImageCardError(401, image_gate.NEED_LOGIN)
        text = (prompt or "").strip()
        if len(text) < 3:
            raise ImageCardError(400, image_gate.EMPTY)
        if len(text) > 20000:
            raise ImageCardError(400, image_gate.EMPTY)
        if not self._kie.configured():
            raise ImageCardError(503, image_gate.BUSY)
        user_id = str(user["id"])
        self.settle(user_id)
        card_id = self._reserve(user_id, text)
        try:
            task_id = self._kie.create_task(text)
        except Exception:
            log.info("card create failed id=%s", card_id)
            self._refund(card_id)
            raise ImageCardError(400, image_gate.FAILED) from None
        self._save_task(card_id, task_id)
        deadline = time.monotonic() + DRAW_WAIT_SEC
        while time.monotonic() < deadline:
            self._settle_one(card_id)
            row = self._get(card_id)
            if not row or row["status"] != "drawing":
                break
            time.sleep(POLL_PAUSE_SEC)
        payload = self.status_for(user)
        row = self._get(card_id)
        payload["card"] = self._public(row) if row else None
        return payload

    def settle(self, user_id: str) -> None:
        for row in self._drawing(user_id):
            self._settle_one(str(row["id"]))

    def credits_of(self, user_id: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT image_credits FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return 0
        return int(row["image_credits"] or 0)

    def daily_used(self, user_id: str) -> int:
        start = datetime.now(timezone.utc).date().isoformat()
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM image_cards
                WHERE user_id = ? AND created_at >= ?
                """,
                (user_id, start),
            ).fetchone()
        return int(row["n"] if row else 0)

    def list_cards(self, user_id: str) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, prompt, status, image_url, created_at
                FROM image_cards
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (user_id,),
            ).fetchall()
        return [self._public(dict(row)) for row in rows]

    def _reserve(self, user_id: str, prompt: str) -> str:
        card_id = str(uuid.uuid4())
        now = utc_now()
        start = datetime.now(timezone.utc).date().isoformat()
        with get_connection() as conn:
            spent = conn.execute(
                """
                UPDATE users
                SET image_credits = image_credits - ?
                WHERE id = ? AND image_credits >= ?
                """,
                (CREDIT_COST, user_id, CREDIT_COST),
            ).rowcount
            if spent != 1:
                raise ImageCardError(403, image_gate.NEED_CREDITS)
            used = conn.execute(
                """
                SELECT COUNT(*) AS n FROM image_cards
                WHERE user_id = ? AND created_at >= ?
                """,
                (user_id, start),
            ).fetchone()
            if int(used["n"] if used else 0) >= DAILY_CAP:
                conn.execute(
                    """
                    UPDATE users
                    SET image_credits = image_credits + ?
                    WHERE id = ?
                    """,
                    (CREDIT_COST, user_id),
                )
                raise ImageCardError(400, image_gate.DAILY)
            conn.execute(
                """
                INSERT INTO image_cards (
                    id, user_id, prompt, status, task_id, image_url,
                    credits_spent, created_at, finished_at
                ) VALUES (?, ?, ?, 'drawing', '', '', 1, ?, '')
                """,
                (card_id, user_id, prompt, now),
            )
        log.info("card reserved id=%s chars=%s", card_id, len(prompt))
        return card_id

    def _save_task(self, card_id: str, task_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE image_cards
                SET task_id = ?
                WHERE id = ? AND status = 'drawing'
                """,
                (task_id, card_id),
            )

    def _settle_one(self, card_id: str) -> None:
        if not self._lock.acquire(blocking=False):
            return
        try:
            row = self._get(card_id)
            if not row or row["status"] != "drawing":
                return
            age = _age_sec(str(row["created_at"]))
            task_id = str(row["task_id"] or "").strip()
            if not task_id:
                if age >= MISSING_TASK_SEC:
                    self._refund(card_id)
                return
            if age >= GIVE_UP_SEC:
                self._refund(card_id)
                return
            try:
                info = self._kie.read_task(task_id)
            except Exception:
                log.info("card poll failed id=%s", card_id)
                return
            state = info.get("state") or "waiting"
            if state == "waiting":
                return
            if state != "success":
                self._refund(card_id)
                return
            try:
                data, kind = self._fetch(info.get("url") or "")
                key = f"cards/{row['user_id']}/{card_id}.{kind[0]}"
                url = self._storage.upload_bytes(
                    key=key, data=data, content_type=kind[1]
                )
            except Exception:
                log.info("card store failed id=%s", card_id)
                if age >= GIVE_UP_SEC:
                    self._refund(card_id)
                return
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE image_cards
                    SET status = 'ready', image_url = ?, finished_at = ?
                    WHERE id = ? AND status = 'drawing'
                    """,
                    (url, utc_now(), card_id),
                )
            log.info("card ready id=%s", card_id)
        finally:
            self._lock.release()

    def _fetch(self, url: str) -> tuple[bytes, tuple[str, str]]:
        if not _public_https(url):
            raise RuntimeError("bad image url")
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        data = response.content
        if len(data) < MIN_IMAGE_BYTES or len(data) > MAX_IMAGE_BYTES:
            raise RuntimeError("bad image size")
        if data.startswith(b"\xff\xd8\xff"):
            return data, ("jpg", "image/jpeg")
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return data, ("png", "image/png")
        raise RuntimeError("not an image")

    def _refund(self, card_id: str) -> None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT user_id, credits_spent FROM image_cards WHERE id = ?",
                (card_id,),
            ).fetchone()
            if not row or int(row["credits_spent"] or 0) != 1:
                conn.execute(
                    """
                    UPDATE image_cards
                    SET status = 'failed', finished_at = ?
                    WHERE id = ? AND status = 'drawing'
                    """,
                    (utc_now(), card_id),
                )
                return
            conn.execute(
                """
                UPDATE image_cards
                SET status = 'failed', credits_spent = 0, finished_at = ?
                WHERE id = ? AND credits_spent = 1
                """,
                (utc_now(), card_id),
            )
            conn.execute(
                """
                UPDATE users
                SET image_credits = image_credits + ?
                WHERE id = ?
                """,
                (CREDIT_COST, row["user_id"]),
            )
        log.info("card refunded id=%s", card_id)

    def _drawing(self, user_id: str) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id FROM image_cards
                WHERE user_id = ? AND status = 'drawing'
                ORDER BY created_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _get(self, card_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM image_cards WHERE id = ?",
                (card_id,),
            ).fetchone()
        return dict(row) if row else None

    def _public(self, row: dict | None) -> dict:
        if not row:
            return {}
        status = str(row.get("status") or "")
        return {
            "id": row.get("id") or "",
            "status": status,
            "image_url": row.get("image_url") or "",
            "prompt": row.get("prompt") or "",
            "created_at": row.get("created_at") or "",
            "message": image_gate.FAILED if status == "failed" else "",
        }


def _age_sec(stamp: str) -> float:
    try:
        created = datetime.fromisoformat(stamp)
    except ValueError:
        return 0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).total_seconds()


def _public_https(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or host == "localhost" or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return bool(address.is_global)
