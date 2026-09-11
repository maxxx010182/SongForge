"""Клиент MAX Bot API (platform-api2.max.ru)."""

from __future__ import annotations

from pathlib import Path

import requests

from backend.logger import log
from backend.settings import DATA_DIR, ROOT_DIR
from backend.settings import MAX_BOT_TOKEN

MAX_API_BASE = "https://platform-api2.max.ru"
_CERTS_DIR = ROOT_DIR / "backend" / "certs"
_VERIFY_CACHE: str | bool | None = None


def _tls_verify() -> str | bool:
    """certifi + сертификаты НУЦ Минцифры — иначе platform-api2.max.ru не проходит TLS."""
    global _VERIFY_CACHE
    if _VERIFY_CACHE is not None:
        return _VERIFY_CACHE
    ru_files = sorted(_CERTS_DIR.glob("*.pem")) if _CERTS_DIR.is_dir() else []
    if not ru_files:
        _VERIFY_CACHE = True
        return _VERIFY_CACHE
    try:
        import certifi

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out = DATA_DIR / "max_ca_bundle.pem"
        chunks = [Path(certifi.where()).read_bytes()]
        chunks.extend(path.read_bytes() for path in ru_files)
        out.write_bytes(b"\n".join(chunks) + b"\n")
        _VERIFY_CACHE = str(out)
    except Exception:
        log.exception("MAX TLS bundle failed, using default CA store")
        _VERIFY_CACHE = True
    return _VERIFY_CACHE


class MaxApi:
    def __init__(self, token: str | None = None) -> None:
        self.token = (token if token is not None else MAX_BOT_TOKEN).strip()

    def configured(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        timeout: int = 20,
    ) -> dict | None:
        if not self.token:
            return None
        url = f"{MAX_API_BASE}{path}"
        try:
            resp = requests.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=timeout,
                verify=_tls_verify(),
            )
        except requests.RequestException:
            log.exception("MAX API %s %s failed", method, path)
            return None
        if resp.status_code >= 400:
            log.warning(
                "MAX API %s %s -> %s %s",
                method,
                path,
                resp.status_code,
                (resp.text or "")[:300],
            )
            return None
        if not resp.content:
            return {}
        try:
            data = resp.json()
        except ValueError:
            log.warning("MAX API %s %s: not JSON", method, path)
            return None
        return data if isinstance(data, dict) else {}

    def me(self) -> dict | None:
        return self._request("GET", "/me")

    def send_message(
        self,
        *,
        user_id: int | str,
        text: str,
        buttons: list[list[dict]] | None = None,
        image_url: str | None = None,
    ) -> bool:
        body: dict = {"text": text}
        attachments: list[dict] = []
        if image_url:
            attachments.append({"type": "image", "payload": {"url": image_url}})
        if buttons:
            attachments.append(
                {"type": "inline_keyboard", "payload": {"buttons": buttons}}
            )
        if attachments:
            body["attachments"] = attachments
        data = self._request(
            "POST",
            "/messages",
            params={"user_id": int(user_id)},
            json_body=body,
        )
        return data is not None

    def answer_callback(
        self,
        callback_id: str,
        *,
        notification: str = "",
    ) -> bool:
        if not callback_id:
            return False
        body: dict = {}
        if notification:
            body["notification"] = notification
        data = self._request(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json_body=body or None,
        )
        return data is not None

    def list_subscriptions(self) -> list[dict]:
        data = self._request("GET", "/subscriptions")
        if not data:
            return []
        items = data.get("subscriptions") or data.get("url") or []
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
        return []

    def unsubscribe(self, url: str) -> bool:
        data = self._request("DELETE", "/subscriptions", params={"url": url})
        return data is not None

    def subscribe(
        self,
        *,
        url: str,
        secret: str,
        update_types: list[str],
    ) -> bool:
        body = {
            "url": url,
            "update_types": update_types,
            "secret": secret,
        }
        data = self._request("POST", "/subscriptions", json_body=body)
        if data is None:
            return False
        if data.get("success") is False:
            log.warning("MAX subscribe failed: %s", data.get("message"))
            return False
        return True
