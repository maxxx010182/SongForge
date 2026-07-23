"""Отдельные HTML-страницы юрдокументов для /legal/* (анкета GetPlatinum)."""

from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
LEGAL_HTML_DIR = ROOT_DIR / "scripts" / "legal_html"

_PAGES = {
    "terms": {
        "title": "Пользовательское соглашение",
        "subtitle": "Сервис «СоздайСвоюПесню» (sozdaipesnu.ru)",
        "updated": "23 июля 2026 г.",
        "file": "agreement.html",
    },
    "privacy": {
        "title": "Политика конфиденциальности",
        "subtitle": "В соответствии с Федеральным законом №152-ФЗ «О персональных данных»",
        "updated": "8 июля 2026 г.",
        "file": "privacy.html",
    },
    "offer": {
        "title": "Публичная оферта",
        "subtitle": "на оказание услуг посредством сервиса «СоздайСвоюПесню»",
        "updated": "8 июля 2026 г. · г. Тюмень",
        "file": "offer.html",
    },
}


def render_legal_page(slug: str) -> str:
    meta = _PAGES.get(slug)
    if not meta:
        raise KeyError(slug)
    body_path = LEGAL_HTML_DIR / meta["file"]
    if not body_path.is_file():
        raise FileNotFoundError(str(body_path))
    body = body_path.read_text(encoding="utf-8")
    home = "https://sozdaipesnu.ru/"
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{meta["title"]} — СоздайСвоюПесню</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    body {{ font-family: Inter, system-ui, sans-serif; background: #09090b; color: #e4e4e7; }}
    .prose h2 {{ color: #facc15; font-size: 1.25rem; font-weight: 700; margin: 1.5rem 0 0.75rem; }}
    .prose h3 {{ color: #f4f4f5; font-size: 1.05rem; font-weight: 600; margin: 1rem 0 0.5rem; }}
    .prose p, .prose li {{ color: #a1a1aa; line-height: 1.7; margin-bottom: 0.75rem; }}
    .prose ul {{ list-style: disc; padding-left: 1.25rem; margin-bottom: 1rem; }}
    .prose strong {{ color: #e4e4e7; }}
  </style>
</head>
<body class="min-h-screen">
  <header class="border-b border-white/10 bg-zinc-950/80">
    <div class="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
      <a href="{home}" class="text-yellow-400 font-semibold hover:text-yellow-300">← На главную</a>
      <span class="text-xs text-zinc-500">sozdaipesnu.ru</span>
    </div>
  </header>
  <main class="max-w-3xl mx-auto px-4 py-10">
    <div class="text-xs text-zinc-500 mb-2">Последнее обновление: {meta["updated"]}</div>
    <h1 class="text-3xl font-bold text-yellow-400 mb-2">{meta["title"]}</h1>
    <p class="text-zinc-400 mb-8">{meta["subtitle"]}</p>
    <div class="prose">{body}</div>
  </main>
</body>
</html>"""