#!/usr/bin/env python3
"""Дать странице 3 минуты на текст песни. Ключи не читает и не печатает.

Nginx по умолчанию обрывает запрос через 60 секунд. Сонет пишет полную песню
дольше. Скрипт ставит proxy_read_timeout и proxy_send_timeout 180s
в конфиг sozdaipesnu.ru, проверяет nginx и перезагружает его.
Если проверка не прошла, возвращает старый файл.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

READ = "proxy_read_timeout 180s;"
SEND = "proxy_send_timeout 180s;"
ROOTS = (
    Path("/etc/nginx/sites-enabled"),
    Path("/etc/nginx/conf.d"),
    Path("/etc/nginx/sites-available"),
)


def main_confs() -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for root in ROOTS:
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if not path.is_file():
                continue
            real = path.resolve()
            if real in seen:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "sozdaipesnu.ru" not in text or "proxy_pass" not in text:
                continue
            if "podarok.sozdaipesnu.ru" in text and "server_name sozdaipesnu.ru" not in text:
                continue
            seen.add(real)
            found.append(path)
    return found


def patch(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    changed = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        for key, wanted in (
            ("proxy_read_timeout", READ),
            ("proxy_send_timeout", SEND),
        ):
            if stripped.startswith(key):
                indent = line[: len(line) - len(line.lstrip())]
                fresh = f"{indent}{wanted}"
                if line != fresh:
                    changed += 1
                out.append(fresh)
                break
        else:
            out.append(line)
            if "proxy_pass" not in line:
                continue
            window = "\n".join(lines[index : index + 8])
            indent = line[: len(line) - len(line.lstrip())] or "        "
            if "proxy_read_timeout" not in window:
                out.append(f"{indent}{READ}")
                changed += 1
            if "proxy_send_timeout" not in window:
                out.append(f"{indent}{SEND}")
                changed += 1
    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + suffix, changed


def nginx_ok() -> bool:
    return subprocess.run(["nginx", "-t"], capture_output=True, text=True).returncode == 0


def reload_nginx() -> None:
    if subprocess.run(["systemctl", "reload", "nginx"], capture_output=True).returncode == 0:
        return
    subprocess.run(["nginx", "-s", "reload"], check=True)


def main() -> None:
    paths = main_confs()
    if not paths:
        raise SystemExit("Не нашёл nginx-конфиг sozdaipesnu.ru с proxy_pass")
    changed = 0
    for path in paths:
        original = path.read_text(encoding="utf-8", errors="replace")
        updated, added = patch(original)
        if added == 0:
            print(path, "already 180s")
            continue
        backup = path.with_suffix(path.suffix + ".bak-wait")
        shutil.copy2(path, backup)
        path.write_text(updated, encoding="utf-8")
        if not nginx_ok():
            shutil.copy2(backup, path)
            raise SystemExit(f"nginx -t не прошёл, вернул {path}")
        print(path, f"wait 180s ({added})")
        changed += added
    if changed:
        reload_nginx()
        print("nginx reloaded")
    print("DONE")


if __name__ == "__main__":
    main()
