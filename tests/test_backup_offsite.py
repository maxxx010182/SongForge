import importlib.util
import sqlite3
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "scripts" / "backup_offsite.py"
spec = importlib.util.spec_from_file_location("backup_offsite", PATH)
backup = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(backup)


def test_parse_env_skips_comments_and_keeps_values():
    parsed = backup.parse_env("# note\nS3_BUCKET=songs\nEMPTY=\nBACKUP2_S3_REGION='ru-1'\n")
    assert parsed["S3_BUCKET"] == "songs"
    assert parsed["EMPTY"] == ""
    assert parsed["BACKUP2_S3_REGION"] == "ru-1"
    assert "note" not in parsed


def test_sqlite_backup_is_a_readable_copy(tmp_path: Path):
    source = tmp_path / "songforge.db"
    conn = sqlite3.connect(source)
    conn.execute("create table users (id integer)")
    conn.execute("insert into users values (1)")
    conn.commit()
    conn.close()
    dest = tmp_path / "copy.db"
    backup.backup_sqlite(source, dest)
    copied = sqlite3.connect(dest)
    assert copied.execute("select id from users").fetchone()[0] == 1
    copied.close()


def test_public_answer_is_a_leak_and_a_refusal_is_not():
    assert backup.is_leaked(200, 12)
    assert not backup.is_leaked(403, 80)
    assert not backup.is_leaked(404, 0)
    assert not backup.is_leaked(200, 0)


def test_old_copies_fall_off_the_end():
    names = [f"backups/db/songforge_202610{day:02d}.db" for day in range(1, 20)]
    dropped = backup.stale_names(names, 14)
    assert len(dropped) == 5
    assert "backups/db/songforge_20261001.db" in dropped
    assert "backups/db/songforge_20261019.db" not in dropped


def test_public_url_uses_the_music_base():
    url = backup.public_object_url(
        {"S3_PUBLIC_BASE": "https://songs.example", "S3_BUCKET": "songs"},
        "backups/db/songforge.db",
    )
    assert url == "https://songs.example/backups/db/songforge.db"


def test_both_shelf_addresses_are_checked():
    urls = backup.candidate_urls(
        {
            "S3_PUBLIC_BASE": "https://songs.example",
            "S3_ENDPOINT": "https://s3.example",
            "S3_BUCKET": "songs",
        },
        "backups/db/songforge.db",
    )
    assert urls == [
        "https://songs.example/backups/db/songforge.db",
        "https://s3.example/songs/backups/db/songforge.db",
    ]


def test_cron_line_is_not_added_twice():
    line = backup.CRON_LINE
    once = backup.merge_cron("", line)
    twice = backup.merge_cron(once, line)
    assert twice.count("backup_offsite.py") == 1
