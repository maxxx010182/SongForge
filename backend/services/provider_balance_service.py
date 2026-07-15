"""Балансы внешних провайдеров (Kie, sunoapi.org) для админки."""

from __future__ import annotations

from typing import Any

from backend.logger import log
from backend.settings import (
    KIE_API_KEY,
    LLM_MODEL_LITE,
    LLM_MODEL_PRO,
    LLM_PROVIDER,
    SUNOAPI_ORG_API_KEY,
)


def get_provider_balances() -> dict[str, Any]:
    """Живые остатки кредитов. Ошибки не валят весь ответ."""
    result: dict[str, Any] = {
        "llm_provider": (LLM_PROVIDER or "yandex").strip().lower(),
        "llm_model_pro": LLM_MODEL_PRO or "",
        "llm_model_lite": LLM_MODEL_LITE or "",
        "kie": _kie_balance(),
        "sunoapi": _sunoapi_balance(),
    }
    return result


def _kie_balance() -> dict[str, Any]:
    configured = bool(KIE_API_KEY)
    if not configured:
        return {
            "configured": False,
            "credits": None,
            "ok": False,
            "error": "KIE_API_KEY не задан",
        }
    try:
        from backend.services.kie_client import KieClient

        credits = KieClient().get_credits()
        if credits is None:
            return {
                "configured": True,
                "credits": None,
                "ok": False,
                "error": "не удалось получить баланс",
            }
        return {
            "configured": True,
            "credits": credits,
            "ok": True,
            "error": None,
        }
    except Exception as exc:
        log.warning("provider balance kie: %s", exc)
        return {
            "configured": True,
            "credits": None,
            "ok": False,
            "error": str(exc)[:120],
        }


def _sunoapi_balance() -> dict[str, Any]:
    configured = bool(SUNOAPI_ORG_API_KEY)
    if not configured:
        return {
            "configured": False,
            "credits": None,
            "ok": False,
            "error": "SUNOAPI_ORG_API_KEY не задан",
        }
    try:
        from backend.services.sunoapi_org_client import SunoApiOrgClient

        credits = SunoApiOrgClient().get_credits()
        if credits is None:
            return {
                "configured": True,
                "credits": None,
                "ok": False,
                "error": "не удалось получить баланс",
            }
        return {
            "configured": True,
            "credits": credits,
            "ok": True,
            "error": None,
        }
    except Exception as exc:
        log.warning("provider balance sunoapi: %s", exc)
        return {
            "configured": True,
            "credits": None,
            "ok": False,
            "error": str(exc)[:120],
        }
