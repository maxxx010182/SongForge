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
    assert report["starts_in_tail"] == 1
    assert len(texts) == 2
    assert all("abcdefghijklmnop" not in item for item in texts)
    assert all("supersecretvalue" not in item for item in texts)
    assert all("2505401" not in item for item in texts)
    assert "обычная строка" not in " ".join(texts)


def test_tail_missing_dir_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGFORGE_LOG_DIR", str(tmp_path / "нет"))
    report = admin_log_tail.recent_failures()
    assert report["lines"] == []
    assert report["starts_in_tail"] == 0
