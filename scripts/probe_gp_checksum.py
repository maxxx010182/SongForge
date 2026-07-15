#!/usr/bin/env python3
"""Probe GetPlatinum webhook checksum algorithms.

Usage on server (with .env):
  cd ~/SongForge && ./venv/bin/python scripts/probe_gp_checksum.py

Or offline (no key match expected without real key):
  python scripts/probe_gp_checksum.py
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Real payload from prod 15.07.2026
RAW = (
    b'{"dealId":"0bab3aa4-8b9f-42b6-96ef-0666e0435c7b","notificationType":1,"isSuccess":true,'
    b'"paymentData":{"mdOrder":76871408,"amount":598,"currency":"RUB","commission":17,'
    b'"commissionCurrency":"RUB","paymentSystem":"sberbank","type":9},"offerId":5,'
    b'"offerName":"383f3d0fe124642a12980338d96df37d",'
    b'"clientInfo":{"email":"b2965bf4-908a-463a-8dcb-d4eb763f47d2@songforge.local","phone":"+79129916896"},'
    b'"checksum":"AA650EF43DF6F8CAD34DDAA78A463D33D1A3759F85C1C4B3B25FA46C4B931CE8",'
    b'"customParams":{"package_id":"notes_1","notes":1}}'
)
TARGET = "AA650EF43DF6F8CAD34DDAA78A463D33D1A3759F85C1C4B3B25FA46C4B931CE8".lower()


def load_secrets() -> list[tuple[str, bytes]]:
    secrets: list[tuple[str, bytes]] = []
    # from env / dotenv
    try:
        from backend.settings import GETPLATINUM_API_KEY

        if GETPLATINUM_API_KEY:
            secrets.append(("GETPLATINUM_API_KEY", GETPLATINUM_API_KEY.encode("utf-8")))
            # variants: strip quotes, whitespace
            k = GETPLATINUM_API_KEY.strip().strip('"').strip("'")
            if k.encode() != secrets[0][1]:
                secrets.append(("API_KEY_stripped_quotes", k.encode()))
    except Exception as exc:
        print("settings load:", exc)

    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("GETPLATINUM_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val and all(val.encode() != s for _, s in secrets):
                    secrets.append(("dotenv_key", val.encode()))

    # offerName from payload looks like a hex id
    payload = json.loads(RAW)
    secrets.append(("offerName", str(payload.get("offerName", "")).encode()))
    secrets.append(("empty", b""))
    return secrets


def strip_checksum(raw: bytes) -> bytes:
    text = raw.decode("utf-8")
    text2, n = re.subn(r',"checksum":"[^"]*"', "", text, count=1)
    return text2.encode() if n else raw


def deep_sort(obj):
    if isinstance(obj, dict):
        return {k: deep_sort(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return [deep_sort(x) for x in obj]
    return obj


def bodies(payload: dict) -> list[tuple[str, bytes]]:
    skip = {k: v for k, v in payload.items() if k != "checksum"}
    out: list[tuple[str, bytes]] = []
    stripped = strip_checksum(RAW)
    out.append(("raw_stripped", stripped))
    out.append(("dumps", json.dumps(skip, ensure_ascii=False, separators=(",", ":")).encode()))
    out.append(
        ("dumps_sorted", json.dumps(skip, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode())
    )
    out.append(
        (
            "dumps_deep_sorted",
            json.dumps(deep_sort(skip), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(),
        )
    )
    out.append(("dumps_spaces", json.dumps(skip, ensure_ascii=False, separators=(", ", ": ")).encode()))
    out.append(("dumps_ascii", json.dumps(skip, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()))
    out.append(("raw_full", RAW))

    # field concatenations
    pd = payload.get("paymentData") or {}
    concats = [
        ("concat_deal_ok", f"{payload['dealId']}{payload['isSuccess']}".encode()),
        (
            "concat_deal_amount",
            f"{payload['dealId']}{pd.get('amount')}{pd.get('currency')}".encode(),
        ),
        (
            "concat_classic",
            f"{payload['dealId']}:{payload['notificationType']}:{payload['isSuccess']}:{pd.get('amount')}".encode(),
        ),
        (
            "concat_deal_success_amount",
            f"{payload['dealId']}{str(payload['isSuccess']).lower()}{pd.get('amount')}".encode(),
        ),
    ]
    out.extend(concats)
    return out


def try_all(secret_name: str, secret: bytes, body_name: str, body: bytes) -> str | None:
    candidates = {
        "hmac_sha256": hmac.new(secret, body, hashlib.sha256).hexdigest(),
        "hmac_sha256_upper": hmac.new(secret, body, hashlib.sha256).hexdigest().upper().lower(),
        "sha256_body_secret": hashlib.sha256(body + secret).hexdigest(),
        "sha256_secret_body": hashlib.sha256(secret + body).hexdigest(),
        "sha256_body": hashlib.sha256(body).hexdigest(),
        "sha256_secret_dot_body": hashlib.sha256(secret + b"." + body).hexdigest(),
        "sha256_body_dot_secret": hashlib.sha256(body + b"." + secret).hexdigest(),
        "hmac_sha1": hmac.new(secret, body, hashlib.sha1).hexdigest(),
        "md5_body_secret": hashlib.md5(body + secret).hexdigest(),
        "hmac_md5": hmac.new(secret, body, hashlib.md5).hexdigest(),
        "b64_hmac": base64.b64encode(hmac.new(secret, body, hashlib.sha256).digest()).decode().lower(),
    }
    for algo, dig in candidates.items():
        if dig.lower() == TARGET:
            return f"MATCH secret={secret_name} body={body_name} algo={algo}"
    return None


def main() -> int:
    payload = json.loads(RAW)
    print("target:", TARGET[:16], "...")
    print("raw_stripped sample:", strip_checksum(RAW)[:80])
    secrets = load_secrets()
    print("secrets:", [n for n, _ in secrets], "key_lens:", [len(s) for _, s in secrets])

    matches = []
    for sn, sec in secrets:
        for bn, body in bodies(payload):
            m = try_all(sn, sec, bn, body)
            if m:
                matches.append(m)
                print(m)

    if not matches:
        print("NO MATCH with available secrets/algorithms")
        # print first few expected digests for API key if present
        for sn, sec in secrets:
            if "API" in sn or "dotenv" in sn or "KEY" in sn:
                body = strip_checksum(RAW)
                print(f"sample hmac[{sn}]:", hmac.new(sec, body, hashlib.sha256).hexdigest()[:24])
                print(f"sample s+b[{sn}]:", hashlib.sha256(sec + body).hexdigest()[:24])
        return 1
    print("FOUND", len(matches), "match(es)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
