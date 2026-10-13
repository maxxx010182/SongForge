#!/usr/bin/env python3
"""Read-only: last song, how fast its file starts, and whether the file itself is silent."""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

DB = Path("/root/SongForge/data/songforge.db")
OUT_LOG = Path("/root/.pm2/logs/songforge-out.log")
ERR_LOG = Path("/root/.pm2/logs/songforge-error.log")
SAMPLE_BYTES = 400_000
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def host_of(url: str) -> str:
    try:
        return urlparse(url).netloc or "?"
    except Exception:
        return "?"


def tail_lines(path: Path, limit: int) -> list[str]:
    if not path.is_file():
        return [f"(нет файла {path})"]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def probe_url(label: str, url: str) -> None:
    print(f"--- {label} host={host_of(url)} ---")
    if not url:
        print("адреса нет")
        return
    started = time.perf_counter()
    try:
        resp = requests.get(
            url,
            stream=True,
            timeout=40,
            headers={"User-Agent": UA, "Accept": "*/*"},
        )
    except requests.RequestException as exc:
        print(f"скачать не вышло: {type(exc).__name__}")
        return
    ttfb = time.perf_counter() - started
    print(
        f"ответ {resp.status_code} за {ttfb:.2f} с, "
        f"тип {resp.headers.get('Content-Type', '?')}, "
        f"длина {resp.headers.get('Content-Length', '?')}"
    )
    blob = bytearray()
    first_at = None
    try:
        for chunk in resp.iter_content(chunk_size=32_768):
            if not chunk:
                continue
            if first_at is None:
                first_at = time.perf_counter() - started
            blob.extend(chunk)
            if len(blob) >= SAMPLE_BYTES:
                break
    finally:
        resp.close()
    got = time.perf_counter() - started
    print(f"первый кусок через {first_at or 0:.2f} с, всего {len(blob)} байт за {got:.2f} с")
    if not blob:
        print("файл пустой")
        return
    print(f"начало файла: {blob[:12].hex()}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg на сервере нет, тишину внутри файла отсюда не измерить")
        return
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(blob)
        sample = tmp.name
    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-i",
                sample,
                "-t",
                "20",
                "-af",
                "silencedetect=noise=-40dB:d=0.6",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=40,
        )
    except subprocess.TimeoutExpired:
        print("проверка тишины не успела")
        return
    finally:
        Path(sample).unlink(missing_ok=True)
    interesting = [
        line.strip()
        for line in (proc.stderr or "").splitlines()
        if "silence_" in line or "Duration:" in line or "Audio:" in line
    ]
    if interesting:
        print("\n".join(interesting[:12]))
    else:
        print("тишины длиннее 0.6 с в первых секундах не видно")


def main() -> None:
    if not DB.is_file():
        print(f"базы нет: {DB}")
        return
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT id, substr(created_at,1,19) AS at, title, purchased,
               duration_a, duration_b, music_url_a, music_url_b
        FROM generations
        WHERE status='success'
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        print("готовых песен нет")
        return
    print(
        f"песня {row['at']} | {str(row['title'] or '')[:40]} | "
        f"куплена {row['purchased']} | "
        f"длина A {row['duration_a']} | длина B {row['duration_b']}"
    )
    print(f"id {row['id']}")
    probe_url("A", row["music_url_a"] or "")
    probe_url("B", row["music_url_b"] or "")
    print("--- ERR ---")
    print("\n".join(tail_lines(ERR_LOG, 20)))
    print("--- OUT ---")
    gen_id = str(row["id"])
    matched = [
        line
        for line in tail_lines(OUT_LOG, 400)
        if gen_id in line or "S3 mirror" in line or "preview" in line.lower()
    ]
    print("\n".join(matched[-25:]) or "(в хвосте лога нет строк про эту песню)")


if __name__ == "__main__":
    main()
