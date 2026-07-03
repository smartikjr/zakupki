"""
Загрузка и разбор публичного поиска тендеров на fabrikant.ru —
ещё одна коммерческая тендерная площадка (промышленность, стройка,
энергетика), не завязанная на 44/223-ФЗ.

СТАТУС: адрес поиска был неверным дважды подряд (404) — сайт оказался
Next.js-приложением (SPA), реальный путь поиска — /procedure/search
(поле "query", номер страницы — "page_number"). НО: большая часть
разметки страницы генерируется JS-бандлами на клиенте, серверный HTML
почти пустой (~2 КБ текста на 200+ КБ файла). Если и с исправленным
адресом parse_cards() будет возвращать 0 карточек — вероятная причина
не в селекторах, а в том, что requests+BeautifulSoup в принципе не
видит то, что дорисовывает JavaScript. В этом случае нужен headless-
браузер (Playwright/Selenium) вместо простого HTTP-запроса — это уже
не быстрая правка, а отдельная задача.
"""

import time
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.fabrikant.ru"
SEARCH_URL = BASE + "/procedure/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def build_url(keyword: str, page: int) -> str:
    params = {"query": keyword, "page_number": page}
    return SEARCH_URL + "?" + urlencode(params, encoding="utf-8")


def fetch(keyword: str, page: int, timeout: int = 30, proxy: str | None = None) -> str:
    url = build_url(keyword, page)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, headers=HEADERS, timeout=timeout, proxies=proxies)
    r.raise_for_status()
    return r.text


def _txt(node) -> str:
    return node.get_text(strip=True) if node else ""


def parse_cards(html: str) -> list[dict]:
    """Разбирает страницу результатов в список карточек-лидов."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.trade-item, tr.trade-row, div.search-item")
    results = []
    for c in cards:
        link_a = c.select_one("a.trade-item__title, a.search-item__title, a")
        link = urljoin(BASE, link_a["href"]) if (link_a and link_a.has_attr("href")) else ""
        obj = _txt(link_a) or _txt(c.select_one(".trade-item__title, .search-item__title"))
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
    """Сохраняет сырой HTML первой страницы — чтобы свериться с реальными селекторами."""
    html = fetch(keyword, 1, proxy=proxy)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Сохранил {path} ({len(html)} символов). Открой и проверь селекторы карточек.")


if __name__ == "__main__":
    debug_dump()
