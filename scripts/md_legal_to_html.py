"""Convert legal .md files to HTML fragments for index.html (prose block)."""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inline(text: str) -> str:
    text = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r'<strong style="color:#e4e4e7">\1</strong>', text)


def md_body_to_html(md_content: str) -> str:
    lines = md_content.strip().split("\n")
    out: list[str] = []
    in_ul = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for raw in lines:
        line = raw.strip()
        if not line:
            close_ul()
            continue
        if line == "---":
            close_ul()
            continue
        if line.startswith("Последнее обновление:"):
            continue
        if line.startswith("Дата публикации:"):
            continue
        if line.startswith("# ") and not line.startswith("## "):
            continue
        if line in {
            "ПУБЛИЧНАЯ ОФЕРТА",
            "на оказание услуг посредством сервиса «СоздайСвоюПесню»",
            "г. Тюмень",
        }:
            continue
        if line.startswith("Сервис «СоздайСвоюПесню»") and "создайсвоюпесню" in line:
            continue
        if line.startswith("В соответствии с Федеральным законом"):
            continue
        if line.startswith("## Согласие на обработку"):
            break
        if line.startswith("Я ознакомлен"):
            break
        if line.startswith("## "):
            close_ul()
            out.append(f"<h2>{inline(line[3:])}</h2>")
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
        "agreement": ROOT / "Пользовательское_соглашение_редакция.md",
        "privacy": ROOT / "Политика_конфиденциальности_редакция.md",
        "offer": ROOT / "Публичная_оферта.md",
    }
    out_dir = ROOT / "scripts" / "legal_html"
    out_dir.mkdir(exist_ok=True)
    for name, path in files.items():
        html_content = md_body_to_html(path.read_text(encoding="utf-8"))
        (out_dir / f"{name}.html").write_text(html_content, encoding="utf-8")
        print(f"Wrote {name}.html ({len(html_content)} chars)")


if __name__ == "__main__":
    main()