"""VK ID — OAuth2 authorization code flow."""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import requests

from backend.logger import log
from backend.settings import SITE_URL, VK_APP_ID, VK_APP_SECRET, VK_AUTH_BASE


class VkAuthService:
    def is_configured(self) -> bool:
        return bool(VK_APP_ID and VK_APP_SECRET)

    @property
    def redirect_uri(self) -> str:
        return f"{SITE_URL}/api/auth/vk/callback"

    def build_authorize_url(self, *, state: str) -> str:
        if not VK_APP_ID:
            raise ValueError("VK_APP_ID не настроен")
        params = {
            "response_type": "code",
            "client_id": VK_APP_ID,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": "email",
        }
        return f"{VK_AUTH_BASE.rstrip('/')}/authorize?{urlencode(params)}"

    def exchange_code(self, *, code: str) -> dict:
        if not self.is_configured():
            raise ValueError("VK OAuth не настроен")

        token_url = f"{VK_AUTH_BASE.rstrip('/')}/oauth2/auth"
        try:
            token_res = requests.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": VK_APP_ID,
                    "client_secret": VK_APP_SECRET,
                    "redirect_uri": self.redirect_uri,
                },
                timeout=30,
            )
            token_body = token_res.json() if token_res.content else {}
        except requests.RequestException as exc:
            log.error("VK token exchange failed: %s", exc)
            raise ValueError("Не удалось связаться с VK ID") from exc

        if token_res.status_code >= 400 or "access_token" not in token_body:
            log.error("VK token error: %s", token_body)
            raise ValueError("VK отклонил авторизацию")

        access_token = token_body["access_token"]
        user_url = f"{VK_AUTH_BASE.rstrip('/')}/oauth2/user_info"
        try:
            user_res = requests.post(
                user_url,
                headers={"Authorization": f"Bearer {access_token}"},
                data={"client_id": VK_APP_ID},
                timeout=30,
            )
            user_body = user_res.json() if user_res.content else {}
        except requests.RequestException as exc:
            log.error("VK user_info failed: %s", exc)
            raise ValueError("Не удалось получить профиль VK") from exc

        user = user_body.get("user") or user_body
        vk_id = str(user.get("user_id") or user.get("id") or "").strip()
        if not vk_id:
            log.error("VK user_info empty id: %s", user_body)
            raise ValueError("VK не вернул идентификатор пользователя")

        first = str(user.get("first_name") or "").strip()
        last = str(user.get("last_name") or "").strip()
        email = str(user.get("email") or "").strip().lower() or None

        return {
            "vk_id": vk_id,
            "first_name": first,
            "last_name": last,
            "email": email,
        }

    @staticmethod
    def new_state() -> str:
        return secrets.token_urlsafe(24)