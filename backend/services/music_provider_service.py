"""Единая точка: ApiPass + sunoapi.org, режим fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backend.logger import log
from backend.models import ProductionPlan
from backend.services.apipass_client import ApiPassClient
from backend.services.sunoapi_org_client import SunoApiOrgClient
from backend.settings import APIPASS_API_KEY, MUSIC_PROVIDER, SUNOAPI_ORG_API_KEY

MusicProviderName = Literal["apipass", "sunoapi"]


@dataclass(frozen=True)
class MusicTaskRef:
    task_id: str
    provider: MusicProviderName


class MusicProviderService:
    def __init__(self) -> None:
        self._apipass = ApiPassClient()
        self._sunoapi = SunoApiOrgClient()

    @staticmethod
    def normalize_provider(value: str | None) -> MusicProviderName:
        if (value or "").strip().lower() == "sunoapi":
            return "sunoapi"
        return "apipass"

    def _client(self, provider: MusicProviderName):
        if provider == "sunoapi":
            return self._sunoapi
        return self._apipass

    def configured_providers(self) -> list[MusicProviderName]:
        providers: list[MusicProviderName] = []
        if APIPASS_API_KEY:
            providers.append("apipass")
        if SUNOAPI_ORG_API_KEY:
            providers.append("sunoapi")
        return providers

    def _create_order(self) -> list[MusicProviderName]:
        mode = (MUSIC_PROVIDER or "apipass").strip().lower()
        available = self.configured_providers()
        if not available:
            raise RuntimeError("Ни один музыкальный API не настроен (APIPASS / SUNOAPI)")

        if mode == "sunoapi":
            return ["sunoapi"] if "sunoapi" in available else available
        if mode == "apipass":
            return ["apipass"] if "apipass" in available else available
        if mode == "fallback":
            order: list[MusicProviderName] = []
            if "apipass" in available:
                order.append("apipass")
            if "sunoapi" in available:
                order.append("sunoapi")
            return order or available
        if mode == "fallback_suno":
            order = []
            if "sunoapi" in available:
                order.append("sunoapi")
            if "apipass" in available:
                order.append("apipass")
            return order or available
        return available[:1]

    def create_task(
        self,
        *,
        lyrics: str,
        style: str,
        title: str,
        plan: ProductionPlan,
    ) -> MusicTaskRef:
        order = self._create_order()
        last_error: Exception | None = None

        for index, provider in enumerate(order):
            client = self._client(provider)
            try:
                task_id = client.create_task(
                    lyrics=lyrics,
                    style=style,
                    title=title,
                    plan=plan,
                )
                if index > 0:
                    log.warning(
                        "Music provider fallback: using %s after earlier failure",
                        provider,
                    )
                return MusicTaskRef(task_id=task_id, provider=provider)
            except Exception as exc:
                last_error = exc
                log.warning("Music provider %s failed: %s", provider, exc)
                continue

        if last_error:
            raise last_error
        raise RuntimeError("Music generation failed")

    def get_status(
        self,
        task_id: str,
        *,
        provider: str | None = None,
    ) -> dict[str, Any]:
        primary = self.normalize_provider(provider)
        clients: list[MusicProviderName] = [primary]

        mode = (MUSIC_PROVIDER or "apipass").strip().lower()
        if mode in {"fallback", "fallback_suno"} and not provider:
            preferred: list[MusicProviderName] = []
            if mode == "fallback_suno":
                if "sunoapi" in self.configured_providers():
                    preferred.append("sunoapi")
                if "apipass" in self.configured_providers():
                    preferred.append("apipass")
            else:
                preferred = self.configured_providers()
            for name in preferred:
                if name not in clients:
                    clients.append(name)

        last_error: Exception | None = None
        for name in clients:
            try:
                return self._client(name).get_status(task_id)
            except Exception as exc:
                last_error = exc
                log.debug("get_status %s failed for %s: %s", name, task_id, exc)

        if last_error:
            raise last_error
        raise RuntimeError(f"Cannot poll task {task_id}")