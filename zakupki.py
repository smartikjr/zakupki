"""
Загрузка и разбор публичной ленты ЕИС (zakupki.gov.ru).

ВАЖНО: ЕИС не отдаёт удобный открытый API — мы парсим публичную HTML-ленту
extendedsearch. Вёрстка ЕИС иногда меняется, поэтому CSS-селекторы ниже,
возможно, придётся поправить при первом живом запуске.
Если parse_cards() вернёт 0 карточек — запусти debug_dump() (см. ниже),
посмотри реальный HTML и поправь селекторы (Claude Code сделает это за минуту).

Если же запросы падают с ConnectTimeoutError (не доходит даже до HTML) —
дело не в селекторах, а в блокировке по IP: zakupki.gov.ru не пускает
запросы с зарубежных дата-центровых адресов (например, с GitHub Actions
runners). В этом случае нужен proxy с российским IP — см. `proxy` в
fetch()/search() и `zakupki_proxy` в config.yaml.
"""

import time
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://zakupki.gov.ru"
SEARCH_URL = BASE + "/epz/order/extendedsearch/results.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def build_url(keyword: str, law: int, page: int) -> str:
    params = {
        "searchString": keyword,
        "morphology": "on",
        "pageNumber": page,
        "sortDirection": "false",
        "recordsPerPage": "_50",
        "sortBy": "UPDATE_DATE",
        "fz44": "on" if law == 44 else "off",
        "fz223": "on" if law == 223 else "off",
        "af": "on",   # приём заявок
        "ca": "on",   # работа комиссии
        "pc": "on",   # закупка завершена
        "pa": "on",   # закупка отменена
    }
    return SEARCH_URL + "?" + urlencode(params, encoding="utf-8")


def fetch(keyword: str, law: int, page: int, timeout: int = 30, proxy: str | None = None) -> str:
    url = build_url(keyword, law, page)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, headers=HEADERS, timeout=timeout, proxies=proxies)
    r.raise_for_status()
    return r.text


def _txt(node) -> str:
    return node.get_text(strip=True) if node else ""


def parse_cards(html: str, law: int) -> list[dict]:
    """Разбирает страницу результатов в список карточек-лидов."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.search-registry-entry-block")
    results = []
    for c in cards:
        num_a = c.select_one(".registry-entry__header-mid__number a")
        link = urljoin(BASE, num_a["href"]) if (num_a and num_a.has_attr("href")) else ""
        reg_number = _txt(num_a).replace("№", "").strip()

        obj = _txt(c.select_one(".registry-entry__body-value"))
        customer = _txt(c.select_one(".registry-entry__body-href a")) or _txt(
            c.select_one(".registry-entry__body-href")
        )
        price = _txt(c.select_one(".price-block__value"))

        # даты (публикация / окончание) — берём как есть, что нашли
        date_vals = [_txt(d) for d in c.select(".data-block__value")]
        dates = " | ".join(v for v in date_vals if v)

        if not (reg_number or obj):
            continue
        results.append(
            {
                "law": law,
                "reg_number": reg_number,
                "object": obj,
                "customer_name": customer,
                "price": price,
                "dates": dates,
                "link": link,
            }
        )
    return results


def search(keyword: str, law: int, pages: int, pause: float = 1.0, proxy: str | None = None) -> list[dict]:
    out = []
    for page in range(1, pages + 1):
        try:
            html = fetch(keyword, law, page, proxy=proxy)
        except Exception as e:  # noqa: BLE001
            print(f"    [!] ошибка загрузки ({keyword}, {law}-ФЗ, стр.{page}): {e}")
            break
        cards = parse_cards(html, law)
        out.extend(cards)
        if not cards:
            break
        time.sleep(pause)
    return out


def debug_dump(keyword: str = "плиты дорожные", law: int = 44, path: str = "debug_eis.html", proxy: str | None = None):
    """Сохраняет сырой HTML первой страницы — чтобы свериться с реальными селекторами."""
    html = fetch(keyword, law, 1, proxy=proxy)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Сохранил {path} ({len(html)} символов). Открой и проверь селекторы карточек.")


if __name__ == "__main__":
    debug_dump()
