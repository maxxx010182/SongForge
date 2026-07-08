"""Convert legal .md files to HTML fragments for index.html (prose block)."""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECTION_RE = re.compile(r"^(\d+)\\?\.\s*(.+)$")
SUBSECTION_RE = re.compile(r"^(\d+)\\?\.\s*(\d+)\\?\.\s*(.+)$")


def inline(text: str) -> str:
    text = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r'<strong style="color:#e4e4e7">\1</strong>', text)


def _should_skip_meta(line: str) -> bool:
    if not line:
        return True
    if line.startswith("Последнее обновление:"):
        return True
    if line.startswith("Дата публикации:"):
        return True
    if line in {"г. Тюмень", "ПУБЛИЧНАЯ ОФЕРТА"}:
        return True
    if line.startswith("на оказание услуг"):
        return True
    if line.startswith("Согласие на обработку"):
        return True
    if line.startswith("Я ознакомлен"):
        return True
    if line.startswith("3\\. ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ"):
        return True
    if line == "Пользовательское соглашение":
        return True
    if line.startswith("Сервис «СоздайСвоюПесню»") and "sozdaipesnu" in line:
        return True
    if line.startswith("В соответствии с Федеральным законом"):
        return True
    if line == "Политика конфиденциальности":
        return True
    if line == "ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ":
        return True
    if line.startswith("# ") and not line.startswith("## "):
        return True
    return False


def md_body_to_html(md_content: str, *, start_at: str | None = None) -> str:
    lines = md_content.strip().split("\n")
    out: list[str] = []
    in_ul = False
    started = start_at is None

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for raw in lines:
        line = raw.strip()
        if not started:
            if start_at and line.startswith(start_at):
                started = True
            continue
        if not line:
            close_ul()
            continue
        if line == "---":
            close_ul()
            continue
        if _should_skip_meta(line):
            continue
        if line.startswith("## Согласие на обработку"):
            break
        if line.startswith("## "):
            close_ul()
            out.append(f"<h2>{inline(line[3:])}</h2>")
            continue
        sub = SUBSECTION_RE.match(line)
        if sub:
            close_ul()
            out.append(f"<p>{inline(line)}</p>")
            continue
        sec = SECTION_RE.match(line)
        if sec and not SUBSECTION_RE.match(line):
            close_ul()
            out.append(f"<h2>{inline(sec.group(1) + '. ' + sec.group(2))}</h2>")
            continue
        if re.fullmatch(r"\*\*.+\*\*", line):
            close_ul()
            out.append(f"<h3>{html.escape(line.strip('*'))}</h3>")
            continue
        if line.startswith("- ") or line.startswith("* "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(line[2:])}</li>")
            continue
        close_ul()
        out.append(f"<p>{inline(line)}</p>")

    close_ul()
    indent = "            "
    return indent + indent.join(out)


def main() -> None:
    files = {
        "agreement": (ROOT / "Пользовательское_соглашение_редакция.md", "1\\. Общие положения"),
        "privacy": (ROOT / "Политика_конфиденциальности_редакция.md", "1\\. Кто мы"),
        "offer": (ROOT / "Публичная_оферта.md", "1\\. ОБЩИЕ ПОЛОЖЕНИЯ"),
    }
    out_dir = ROOT / "scripts" / "legal_html"
    out_dir.mkdir(exist_ok=True)
    for name, (path, start_at) in files.items():
        html_content = md_body_to_html(path.read_text(encoding="utf-8"), start_at=start_at)
        (out_dir / f"{name}.html").write_text(html_content, encoding="utf-8")
        print(f"Wrote {name}.html ({len(html_content)} chars)")


if __name__ == "__main__":
    main()