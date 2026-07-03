"""
Загрузка и разбор публичного поиска тендеров на fabrikant.ru —
ещё одна коммерческая тендерная площадка (промышленность, стройка,
энергетика), не завязанная на 44/223-ФЗ.

СТАТУС: адрес поиска — /procedure/search (поле "query", страница —
"page_number"), это подтверждено. Но сайт — Next.js SPA: список закупок
приходит не обычным HTML, а потоком сериализованных React Server
Components (не JSON, не DOM) — requests+BeautifulSoup в принципе не
может это распарсить. Поэтому здесь Playwright — открываем страницу в
headless Chromium, ждём, пока JS реально отрисует список, и парсим уже
готовый DOM.

Требует: `pip install playwright` и `playwright install --with-deps
chromium` (уже добавлено в requirements.txt и .github/workflows).

Селекторы карточек в parse_cards() — рабочая гипотеза, ещё не сверена
с реальным отрендеренным DOM (нет возможности запустить браузер в среде
разработки). Если вернёт 0 карточек — запусти debug_dump() (создаст
debug_fabrikant.html из УЖЕ ОТРЕНДЕРЕННОГО DOM, не сырой HTML) и пришли
файл — поправят за один заход, как и с остальными источниками.
"""

import time
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://www.fabrikant.ru"
SEARCH_URL = BASE + "/procedure/search"


def build_url(keyword: str, page: int) -> str:
    params = {"query": keyword, "page_number": page}
    return SEARCH_URL + "?" + urlencode(params, encoding="utf-8")


def fetch(keyword: str, page: int, timeout: int = 30, proxy: str | None = None) -> str:
    """Открывает страницу в headless Chromium и возвращает DOM ПОСЛЕ рендера JS."""
    url = build_url(keyword, page)
    launch_kwargs = {}
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            page_obj = browser.new_page()
            page_obj.goto(url, timeout=timeout * 1000, wait_until="networkidle")
            html = page_obj.content()
        finally:
            browser.close()
    return html


def _txt(node) -> str:
    return node.get_text(strip=True) if node else ""


def parse_cards(html: str) -> list[dict]:
    """Разбирает отрендеренный DOM в список карточек-лидов."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(
        "a[href*='/procedure/view/'], div[data-testid*='procedure'], "
        "div.trade-item, tr.trade-row, div.search-item"
    )
    results = []
    seen_links = set()
    for c in cards:
        link_a = c if c.name == "a" else c.select_one("a[href*='/procedure/view/'], a")
        link = urljoin(BASE, link_a["href"]) if (link_a and link_a.has_attr("href")) else ""
        if not link or link in seen_links:
            continue
        seen_links.add(link)

        obj = _txt(c.select_one(".trade-item__title, .search-item__title")) or _txt(link_a)
        customer = _txt(c.select_one(".trade-item__customer, .search-item__customer, .company"))
        price = _txt(c.select_one(".trade-item__price, .price"))
        reg_number = _txt(c.select_one(".trade-item__number, .search-item__number"))
        date_val = _txt(c.select_one(".trade-item__date, .search-item__date"))

        if not (obj or reg_number):
            continue
        results.append(
            {
                "law": "",
                "reg_number": reg_number,
                "object": obj,
                "customer_name": customer,
                "price": price,
                "dates": date_val,
                "link": link,
            }
        )
    return results


def search(keyword: str, pages: int, pause: float = 1.0, proxy: str | None = None) -> list[dict]:
    out = []
    for page in range(1, pages + 1):
        try:
            html = fetch(keyword, page, proxy=proxy)
        except Exception as e:  # noqa: BLE001
            print(f"    [!] ошибка загрузки fabrikant ({keyword}, стр.{page}): {e}")
            break
        cards = parse_cards(html)
        out.extend(cards)
        if not cards:
            break
        time.sleep(pause)
    return out


def debug_dump(keyword: str = "плиты дорожные", path: str = "debug_fabrikant.html", proxy: str | None = None):
    """Сохраняет ОТРЕНДЕРЕННЫЙ DOM первой страницы — чтобы свериться с реальными селекторами."""
    html = fetch(keyword, 1, proxy=proxy)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Сохранил {path} ({len(html)} символов). Открой и проверь селекторы карточек.")


if __name__ == "__main__":
    debug_dump()
