from backend.services import admin_log_tail


def test_tail_keeps_warnings_and_hides_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGFORGE_LOG_DIR", str(tmp_path))
    (tmp_path / "songforge-out.log").write_text(
        "\n".join(
            [
                "2026-10-24 13:35:33,402 [INFO] songforge: обычная строка",
                "2026-10-24 13:35:34,401 [INFO] songforge: LLM provider: kie chain",
                "2026-10-24 13:36:00,100 [WARNING] songforge: LLM Kie/gemini-3-pro failed (timeout): Bearer abcdefghijklmnop",
                "2026-10-24 13:36:01,100 [ERROR] songforge: key-supersecretvalue broke",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "songforge-error.log").write_text(
        "INFO: Started server process [2505401]\n",
        encoding="utf-8",
    )
    report = admin_log_tail.recent_failures()
    texts = [row["text"] for row in report["lines"]]
    joined = " ".join(texts)
    assert report["starts_in_tail"] == 1
    assert len(texts) == 2
    assert "abcdefghijklmnop" not in joined
    assert "supersecretvalue" not in joined
    assert "2505401" not in joined
    assert "обычная строка" not in joined


def test_same_bind_error_is_one_russian_line(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGFORGE_LOG_DIR", str(tmp_path))
    line = (
        "ERROR: [Errno 98] error while attempting to bind on address "
        "('0.0.0.0', 8000): [errno 98] address already in use"
    )
    (tmp_path / "songforge-error.log").write_text((line + "\n") * 5, encoding="utf-8")
    (tmp_path / "songforge-worker-error.log").write_text(
        "\n".join(
            [
                "Traceback (most recent call last):",
                '  File "app.py", line 1, in <module>',
                "RuntimeError: очередь музыки не отвечает",
            ]
        ),
        encoding="utf-8",
    )
    report = admin_log_tail.recent_failures()
    rows = report["lines"]
    assert rows[0]["count"] == 5
    assert "порт 8000" in rows[0]["text"]
    assert "address already in use" not in rows[0]["text"]
    assert rows[1]["text"] == "RuntimeError: очередь музыки не отвечает"


def test_traceback_shows_exception_not_code_or_carets(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGFORGE_LOG_DIR", str(tmp_path))
    (tmp_path / "songforge-error.log").write_text(
        "\n".join(
            [
                "Traceback (most recent call last):",
                '  File "pydantic.py", line 10, in _eval_type',
                "    qualname = getattr(origin, '__qualname__', f'<No __qualname__: {origin}>')",
                "    ~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^",
                "AttributeError: 'NoneType' object has no attribute '__qualname__'",
            ]
        ),
        encoding="utf-8",
    )
    report = admin_log_tail.recent_failures()
    text = report["lines"][0]["text"]
    assert text.startswith("AttributeError:")
    assert "getattr" not in text
    assert "^" not in text


def test_keyboard_interrupt_is_a_restart_not_a_broken_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGFORGE_LOG_DIR", str(tmp_path))
    block = "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "/root/SongForge/backend/worker.py", line 50, in run_forever',
            "    time.sleep(WORKER_POLL_INTERVAL_SEC)",
            "    ~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^",
            "KeyboardInterrupt",
        ]
    )
    (tmp_path / "songforge-worker-error.log").write_text(
        (block + "\n") * 2,
        encoding="utf-8",
    )
    report = admin_log_tail.recent_failures()
    row = report["lines"][0]
    assert row["count"] == 2
    assert "остановили" in row["text"]
    assert "оборванный" not in row["text"]


def test_tail_missing_dir_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGFORGE_LOG_DIR", str(tmp_path / "нет"))
    report = admin_log_tail.recent_failures()
    assert report["lines"] == []
    assert report["starts_in_tail"] == 0
