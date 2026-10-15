#!/usr/bin/env python3
"""Ежедневная закрытая копия базы и файла настроек.

Песни уже лежат в бакете. Повторно в тот же бакет они не копируются.
Вторая полка (другой оператор) используется, только если в .env заданы
BACKUP2_S3_ENDPOINT, BACKUP2_S3_ACCESS_KEY, BACKUP2_S3_SECRET_KEY
и BACKUP2_S3_BUCKET.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

import requests

KEEP = 14
CRON_LINE = (
    "15 3 * * * /root/SongForge/venv/bin/python "
    "/root/SongForge/scripts/backup_offsite.py "
    ">> /var/log/songforge-backup.log 2>&1"
)


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def backup_sqlite(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    os.chmod(dest, 0o600)


def stale_names(names: list[str], keep: int) -> list[str]:
    ordered = sorted(names, reverse=True)
    return ordered[keep:]


def is_leaked(status: int, size: int) -> bool:
    return status == 200 and size > 0


def public_object_url(env: dict[str, str], key: str) -> str:
    found = candidate_urls(env, key)
    return found[0] if found else ""


BACKUP_BUCKET = "songforge-backup"


def backup_bucket_name(env: dict[str, str]) -> str:
    name = (env.get("BACKUP_S3_BUCKET") or BACKUP_BUCKET).strip().strip("/")
    return name or BACKUP_BUCKET


def backup_urls(endpoint: str, bucket: str, key: str) -> list[str]:
    clean = key.lstrip("/")
    host = (endpoint or "").rstrip("/")
    urls: list[str] = []
    if "://" in host and bucket and clean:
        scheme, rest = host.split("://", 1)
        urls.append(f"{scheme}://{bucket}.{rest}/{clean}")
        urls.append(f"{host}/{bucket}/{clean}")
    unique: list[str] = []
    for url in urls:
        if url not in unique:
            unique.append(url)
    return unique


def candidate_urls(env: dict[str, str], key: str) -> list[str]:
    clean = key.lstrip("/")
    urls: list[str] = []
    base = (env.get("S3_PUBLIC_BASE") or "").rstrip("/")
    if base:
        urls.append(f"{base}/{clean}")
    endpoint = (env.get("S3_ENDPOINT") or "").rstrip("/")
    bucket = (env.get("S3_BUCKET") or "").strip("/")
    if endpoint and bucket:
        urls.append(f"{endpoint}/{bucket}/{clean}")
    unique: list[str] = []
    for url in urls:
        if url not in unique:
            unique.append(url)
    return unique


def merge_cron(existing: str, line: str) -> str:
    rows = [row for row in existing.splitlines() if row.strip()]
    if any("backup_offsite.py" in row for row in rows):
        return "\n".join(rows) + ("\n" if rows else "")
    rows.append(line)
    return "\n".join(rows) + "\n"


def _client(endpoint: str, access: str, secret: str, region: str):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name=region or "ru-1",
    )


def _put_private(client, bucket: str, key: str, body: bytes) -> None:
    common = {
        "Bucket": bucket,
        "Key": key,
        "Body": body,
        "ContentType": "application/octet-stream",
    }
    try:
        client.put_object(**common, ACL="private")
    except Exception as exc:
        code = ""
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code = str(response.get("Error", {}).get("Code") or "")
        if code not in {"AccessControlListNotSupported", "NotImplemented", "InvalidArgument"}:
            raise
        client.put_object(**common)


def _probe(url: str) -> tuple[int, int]:
    response = requests.get(url, timeout=20, stream=True)
    try:
        status = response.status_code
        size = 0
        for chunk in response.iter_content(chunk_size=64):
            size += len(chunk)
            if size > 0:
                break
        return status, size
    finally:
        response.close()


def _delete(client, bucket: str, key: str) -> None:
    client.delete_object(Bucket=bucket, Key=key)


def _upload_checked(
    client,
    bucket: str,
    key: str,
    body: bytes,
    urls: list[str],
) -> str:
    _put_private(client, bucket, key, body)
    if not urls:
        _delete(client, bucket, key)
        return "check-failed"
    for url in urls:
        try:
            status, size = _probe(url)
        except requests.RequestException:
            _delete(client, bucket, key)
            return "check-failed"
        if is_leaked(status, size):
            _delete(client, bucket, key)
            return "public"
    return "closed"


def _prune_prefix(client, bucket: str, prefix: str, keep: int) -> int:
    names: list[str] = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        for item in page.get("Contents") or []:
            names.append(item["Key"])
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    dropped = 0
    for key in stale_names(names, keep):
        _delete(client, bucket, key)
        dropped += 1
    return dropped


def _prune_local(folder: Path, pattern: str, keep: int) -> None:
    files = sorted(folder.glob(pattern), key=lambda path: path.name, reverse=True)
    for path in files[keep:]:
        path.unlink(missing_ok=True)


def _install_cron() -> str:
    current = subprocess.run(
        ["crontab", "-l"],
        check=False,
        capture_output=True,
        text=True,
    )
    existing = current.stdout if current.returncode == 0 else ""
    merged = merge_cron(existing, CRON_LINE)
    if merged == (existing if existing.endswith("\n") or not existing else existing + "\n"):
        return "уже стоит"
    subprocess.run(["crontab", "-"], input=merged, check=True, text=True)
    return "записан на 03:15"


def _shelf_from_env(env: dict[str, str], prefix: str) -> dict[str, str] | None:
    endpoint = (env.get(f"{prefix}ENDPOINT") or "").strip()
    access = (env.get(f"{prefix}ACCESS_KEY") or "").strip()
    secret = (env.get(f"{prefix}SECRET_KEY") or "").strip()
    bucket = (env.get(f"{prefix}BUCKET") or "").strip()
    if not (endpoint and access and secret and bucket):
        return None
    return {
        "endpoint": endpoint,
        "access": access,
        "secret": secret,
        "bucket": bucket,
        "region": (env.get(f"{prefix}REGION") or "ru-1").strip(),
    }


def _copy_missing_tracks(source, source_bucket: str, dest, dest_bucket: str) -> tuple[int, int]:
    source_keys = _list_keys(source, source_bucket, "tracks/")
    dest_keys = set(_list_keys(dest, dest_bucket, "tracks/"))
    copied = 0
    for key in source_keys:
        if key in dest_keys:
            continue
        obj = source.get_object(Bucket=source_bucket, Key=key)
        body = obj["Body"].read()
        _put_private(dest, dest_bucket, key, body)
        copied += 1
    return len(source_keys), copied


def _list_keys(client, bucket: str, prefix: str) -> list[str]:
    names: list[str] = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        for item in page.get("Contents") or []:
            names.append(item["Key"])
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    return names


def main() -> int:
    root = Path(os.environ.get("SONGFORGE_ROOT", "/root/SongForge"))
    db_path = root / "data" / "songforge.db"
    env_path = root / ".env"
    if not db_path.is_file():
        print(f"база не найдена: {db_path}")
        return 1
    env = parse_env(env_path.read_text(encoding="utf-8")) if env_path.is_file() else {}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    local_dir = Path(os.environ.get("SONGFORGE_BACKUP_DIR", "/root/backups/songforge"))
    local_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(local_dir, 0o700)
    local_db = local_dir / f"songforge_{stamp}.db"
    backup_sqlite(db_path, local_db)
    print(f"база: {local_db.stat().st_size} байт")
    print(f"на этом компьютере: {local_db}")

    primary = _shelf_from_env(env, "S3_")
    if primary is None or env.get("S3_ENABLED", "").lower() not in {"1", "true", "yes"}:
        print("хранилище песен не настроено, наружу копия не ушла")
        return 2

    folder = backup_bucket_name(env)
    db_key = f"backups/db/songforge_{stamp}.db"
    client = _client(primary["endpoint"], primary["access"], primary["secret"], primary["region"])
    db_state = _upload_checked(
        client,
        folder,
        db_key,
        local_db.read_bytes(),
        backup_urls(primary["endpoint"], folder, db_key),
    )
    if db_state != "closed":
        print(f"копия базы в папке {folder} не оставлена: {db_state}")
        return 3
    print(f"папка {folder}, база закрыта")

    if env_path.is_file():
        env_key = f"backups/env/songforge_{stamp}.env"
        env_state = _upload_checked(
            client,
            folder,
            env_key,
            env_path.read_bytes(),
            backup_urls(primary["endpoint"], folder, env_key),
        )
        if env_state != "closed":
            print(f"файл настроек в хранилище не оставлен: {env_state}")
            return 3
        local_env = local_dir / f"env_{stamp}.env"
        local_env.write_bytes(env_path.read_bytes())
        os.chmod(local_env, 0o600)
        print("файл настроек закрыт")
    else:
        print("файла настроек нет, его копию пропустил")

    dropped = _prune_prefix(client, folder, "backups/db/", KEEP)
    dropped += _prune_prefix(client, folder, "backups/env/", KEEP)
    _prune_local(local_dir, "songforge_*.db", KEEP)
    _prune_local(local_dir, "env_*.env", KEEP)
    print(f"старых копий снято: {dropped}, держим {KEEP}")
    print("папку с песнями не трогал")

    cron_error = ""
    try:
        print(f"расписание: {_install_cron()}")
    except (OSError, subprocess.CalledProcessError):
        cron_error = "расписание не записалось"

    second = _shelf_from_env(env, "BACKUP2_S3_")
    if second is None:
        print("вторая полка не задана")
    else:
        other = _client(second["endpoint"], second["access"], second["secret"], second["region"])
        other_db = _upload_checked(
            other,
            second["bucket"],
            db_key,
            local_db.read_bytes(),
            [_second_url(second, db_key)],
        )
        if other_db != "closed":
            print(f"вторая полка, база не оставлена: {other_db}")
            return 4
        if env_path.is_file():
            other_env = _upload_checked(
                other,
                second["bucket"],
                env_key,
                env_path.read_bytes(),
                [_second_url(second, env_key)],
            )
            if other_env != "closed":
                print(f"вторая полка, настройки не оставлены: {other_env}")
                return 4
        total, copied = _copy_missing_tracks(client, primary["bucket"], other, second["bucket"])
        _prune_prefix(other, second["bucket"], "backups/db/", KEEP)
        _prune_prefix(other, second["bucket"], "backups/env/", KEEP)
        print(f"вторая полка закрыта, бакет {second['bucket']}, песен всего {total}, дописано {copied}")

    if cron_error:
        print(cron_error)
        return 5
    return 0


def _second_url(shelf: dict[str, str], key: str) -> str:
    endpoint = shelf["endpoint"].rstrip("/")
    return f"{endpoint}/{shelf['bucket']}/{key.lstrip('/')}"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        code = ""
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code = str(response.get("Error", {}).get("Code") or "")
        if code:
            print(f"папка копий отказала: {code}")
        else:
            print(f"копия остановилась: {type(exc).__name__}")
        raise SystemExit(6) from exc
