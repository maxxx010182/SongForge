"""Одна картинка по описанию. Свой голос и песню этот файл не трогает."""

from __future__ import annotations

import json
from typing import Any

import requests

from backend.logger import log
from backend.settings import KIE_API_KEY, KIE_BASE

MODEL = "nano-banana-2-1"
ASPECT = "3:4"
RESOLUTION = "1K"


class KieImageClient:
    def __init__(self) -> None:
        self._base = (KIE_BASE or "https://api.kie.ai").rstrip("/")

    def configured(self) -> bool:
        return bool(KIE_API_KEY)

    def create_task(self, prompt: str) -> str:
        if not KIE_API_KEY:
            raise RuntimeError("image key missing")
        response = requests.post(
            f"{self._base}/api/v1/jobs/createTask",
            json={
                "model": MODEL,
                "input": {
                    "prompt": prompt,
                    "aspect_ratio": ASPECT,
                    "resolution": RESOLUTION,
                    "output_format": "jpg",
                },
            },
            headers={
                "Authorization": f"Bearer {KIE_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        body = _json_body(response)
        task_id = str((body.get("data") or {}).get("taskId") or "").strip()
        log.info("card task http=%s code=%s", response.status_code, body.get("code"))
        if response.status_code != 200 or body.get("code") != 200 or not task_id:
            raise RuntimeError("image task was not created")
        return task_id

    def read_task(self, task_id: str) -> dict[str, str]:
        response = requests.get(
            f"{self._base}/api/v1/jobs/recordInfo",
            params={"taskId": task_id},
            headers={"Authorization": f"Bearer {KIE_API_KEY}"},
            timeout=20,
        )
        body = _json_body(response)
        data = body.get("data") or {}
        state = str(data.get("state") or "").strip().lower()
        if state not in {"success", "fail"}:
            return {"state": "waiting", "url": ""}
        url = ""
        if state == "success":
            url = _first_url(data.get("resultJson"))
            if not url:
                return {"state": "fail", "url": ""}
        log.info("card state=%s", state)
        return {"state": state, "url": url}


def _json_body(response: requests.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _first_url(raw: Any) -> str:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw or "{}")
        except ValueError:
            return ""
    elif isinstance(raw, dict):
        parsed = raw
    else:
        return ""
    urls = parsed.get("resultUrls") if isinstance(parsed, dict) else None
    if not isinstance(urls, list) or not urls:
        return ""
    return str(urls[0] or "").strip()
