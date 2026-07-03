"""
Загрузка и разбор публичного поиска тендеров на fabrikant.ru —
ещё одна коммерческая тендерная площадка (промышленность, стройка,
энергетика), не завязанная на 44/223-ФЗ.

СТАТУС: /procedure/search?query=...&page_number=... грузится (URL
верный), но параметр query НЕ фильтрует результаты — сайт показывает
общую ленту закупок независимо от него (проверено: искали «плиты
дорожные», получили канцтовары и хозматериалы). Похоже, поиск
запускается только реальным взаимодействием с формой, а не через
URL-параметры. Поэтому здесь Playwright не просто грузит страницу, а
эмулирует пользователя: открывает /procedure/search, вводит ключевое
слово в поле #search и жмёт кнопку «Найти» (button[aria-label="Найти"]),
затем ждёт и парсит DOM.

Требует: `pip install playwright` и `playwright install --with-deps
chromium` (уже добавлено в requirements.txt и .github/workflows).

Пагинация (аргумент `page` в search()) пока НЕ реализована — форма
пагинации тоже наверняка интерактивная (клик, не URL), это отдельная
доработка. Сейчас всегда берём только первую страницу выдачи.

Селекторы карточек в parse_cards() — рабочая гипотеза по структуре,
которую видно после клика «Найти» на живом рендере (см. debug_dump()).
Если после клика карточки всё равно не те/не найдены — пришли свежий
debug_fabrikant.html, поправят за один заход.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://www.fabrikant.ru"


def fetch(keyword: str, timeout: int = 30, proxy: str | None = None) -> str:
    """Открывает поиск в headless Chromium, реально вводит запрос и жмёт «Найти»."""
    launch_kwargs = {}
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            page_obj = browser.new_page()
            # Заход сразу на /procedure/search не даёт #search появиться за
            # 30с (проверено). Строка поиска подтверждённо есть на главной
            # (SSR) — заходим туда, вводим запрос, жмём «Найти» и ждём
            # перехода на страницу результатов.
            page_obj.goto(BASE + "/", timeout=timeout * 1000, wait_until="domcontentloaded")
            page_obj.wait_for_selector("#search", timeout=timeout * 1000)
            page_obj.fill("#search", keyword)
            with page_obj.expect_navigation(timeout=timeout * 1000):
                page_obj.click('button[aria-label="Найти"]')
            page_obj.wait_for_timeout(4000)
            html = page_obj.content()
        finally:
            browser.close()
    return html


def _txt(node) -> str:
    return node.get_text(strip=True) if node else ""


# Карточки не имеют стабильных классов (Tailwind, сгенерированные
# имена) — вместо CSS-селекторов на конкретные классы берём ссылку на
# процедуру и регуляркой разбираем текст ближайшего контейнера,
# содержащего "Организатор" (устойчивый текстовый лейбл в разметке).
_REG_RE = re.compile(r"№\s*(\d+)")
_CUSTOMER_RE = re.compile(r"Организатор\s+(.+?)(?:\s+Дата публикации|\s+Цена|$)")
_DATE_RE = re.compile(r"Дата публикации\s+([\d.]+\s+[\d:]+)")


def parse_cards(html: str) -> list[dict]:
    """Разбирает отрендеренный DOM в список карточек-лидов."""
    soup = BeautifulSoup(html, "lxml")
    results = []
    seen_links = set()
    for link_a in soup.select("a[href*='/procedure/view/']"):
        href = link_a.get("href", "")
        link = urljoin(BASE, href)
        if not link or link in seen_links:
            continue
        seen_links.add(link)

        obj = _txt(link_a)
        if not obj:
            continue

        container_text = ""
        node = link_a
        for _ in range(6):
            node = node.parent
            if node is None:
                break
            container_text = node.get_text(" ", strip=True)
            if "Организатор" in container_text:
                break

        reg_m = _REG_RE.search(container_text)
        cust_m = _CUSTOMER_RE.search(container_text)
        date_m = _DATE_RE.search(container_text)

        results.append(
            {
                "law": "",
                "reg_number": reg_m.group(1) if reg_m else "",
                "object": obj,
                "customer_name": cust_m.group(1).strip() if cust_m else "",
                "price": "",
                "dates": date_m.group(1) if date_m else "",
                "link": link,
            }
        )
    return results


def search(keyword: str, pages: int, pause: float = 1.0, proxy: str | None = None) -> list[dict]:
    # Пагинация не реализована (см. докстринг модуля) — pages игнорируется,
    # всегда только первая страница выдачи.
    try:
        html = fetch(keyword, proxy=proxy)
    except Exception as e:  # noqa: BLE001
        print(f"    [!] ошибка загрузки fabrikant ({keyword}): {e}")
        return []
    return parse_cards(html)


def debug_dump(keyword: str = "плиты дорожные", path: str = "debug_fabrikant.html", proxy: str | None = None):
    """Сохраняет ОТРЕНДЕРЕННЫЙ DOM после поиска — чтобы свериться с реальными селекторами."""
    html = fetch(keyword, proxy=proxy)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Сохранил {path} ({len(html)} символов). Открой и проверь селекторы карточек.")


if __name__ == "__main__":
    debug_dump()
