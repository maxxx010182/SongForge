"""Inject generated legal HTML into index.html."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGAL = ROOT / "scripts" / "legal_html"
INDEX = ROOT / "index.html"

AGREEMENT_BODY = (LEGAL / "agreement.html").read_text(encoding="utf-8")
PRIVACY_BODY = (LEGAL / "privacy.html").read_text(encoding="utf-8")
OFFER_BODY = (LEGAL / "offer.html").read_text(encoding="utf-8")

AGREEMENT_SECTION = f"""<div id="section-agreement" class="doc-section active">
    <div class="glass-panel p-8">
        <div class="text-xs text-zinc-500 mb-2">Последнее обновление: 8 июля 2026 г.</div>
        <h1 class="font-title text-3xl font-bold text-yellow-400 mb-2">Пользовательское соглашение</h1>
        <p class="text-zinc-400 mb-8">Сервис «СоздайСвоюПесню» (sozdaipesnu.ru)</p>

        <div class="prose">
{AGREEMENT_BODY}
        </div>
    </div>
</div>"""

PRIVACY_SECTION = f"""<div id="section-privacy" class="doc-section">
    <div class="glass-panel p-8">
        <div class="text-xs text-zinc-500 mb-2">Последнее обновление: 8 июля 2026 г.</div>
        <h1 class="font-title text-3xl font-bold text-yellow-400 mb-2">Политика конфиденциальности</h1>
        <p class="text-zinc-400 mb-8">В соответствии с Федеральным законом №152-ФЗ «О персональных данных»</p>

        <div class="prose">
{PRIVACY_BODY}
        </div>

        <div class="mt-8 p-5 bg-yellow-400/5 border border-yellow-400/20 rounded-2xl">
            <div class="text-sm font-semibold text-zinc-200 mb-3">Согласие на обработку персональных данных</div>
            <p class="text-xs text-zinc-400 mb-4 leading-relaxed">Регистрируясь в сервисе «СоздайСвоюПесню», я даю согласие ИП Мошкину Максиму Алексеевичу на обработку моих персональных данных (имя, контактные данные, история использования) в целях предоставления услуг сервиса, в порядке и на условиях, определённых Политикой конфиденциальности. Согласие может быть отозвано в любой момент путём обращения на bam8282@mail.ru.</p>
            <label class="flex items-start gap-3 cursor-pointer">
                <input type="checkbox" id="consentCheckbox" class="mt-0.5 w-4 h-4 accent-yellow-400 flex-shrink-0">
                <span class="text-xs text-zinc-300">Я ознакомлен(а) с Политикой конфиденциальности и даю согласие на обработку персональных данных</span>
            </label>
        </div>
    </div>
</div>"""

OFFER_SECTION = f"""<div id="section-offer" class="doc-section">
    <div class="glass-panel p-8">
        <div class="text-xs text-zinc-500 mb-2">Дата публикации: 8 июля 2026 г. · г. Тюмень</div>
        <h1 class="font-title text-3xl font-bold text-yellow-400 mb-2">Публичная оферта</h1>
        <p class="text-zinc-400 mb-8">на оказание услуг посредством сервиса «СоздайСвоюПесню»</p>

        <div class="prose">
{OFFER_BODY}
        </div>
    </div>
</div>"""


def replace_block(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + replacement + text[end:]


def main() -> None:
    html = INDEX.read_text(encoding="utf-8")

    html = replace_block(
        html,
        '<div id="section-agreement"',
        '<!-- ================================================ -->\n<!-- 2. ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ -->',
        AGREEMENT_SECTION + "\n\n<!-- ================================================ -->\n<!-- 2. ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ -->\n",
    )

    html = replace_block(
        html,
        '<div id="section-privacy"',
        '<!-- ================================================ -->\n<!-- 3. ПУБЛИЧНАЯ ОФЕРТА -->',
        PRIVACY_SECTION + "\n\n<!-- ================================================ -->\n<!-- 3. ПУБЛИЧНАЯ ОФЕРТА -->\n",
    )

    html = replace_block(
        html,
        '<div id="section-offer"',
        '<!-- ================================================ -->\n<!-- 4. FAQ -->',
        OFFER_SECTION + "\n\n<!-- ================================================ -->\n<!-- 4. FAQ -->\n",
    )

    if 'data-section="offer"' not in html:
        html = html.replace(
            '<div class="nav-link" data-section="privacy">Конфиденциальность</div>\n        <div class="nav-link" data-section="faq">FAQ</div>',
            '<div class="nav-link" data-section="privacy">Конфиденциальность</div>\n        <div class="nav-link" data-section="offer">Оферта</div>\n        <div class="nav-link" data-section="faq">FAQ</div>',
        )

    INDEX.write_text(html, encoding="utf-8")
    print("Updated index.html legal sections")


if __name__ == "__main__":
    main()