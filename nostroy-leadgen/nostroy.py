"""
Загрузка данных из Единого реестра членов СРО строителей — НОСТРОЙ
(nostroy.ru / reestr.nostroy.ru).

Зачем этот источник: официальный реестр всех строительных компаний с
допуском СРО (обязателен по закону для большинства строительных работ)
по регионам — большая база реальных подрядчиков. В отличие от ЕРЗ.РФ
(рейтинг только жилых застройщиков) и тендерных площадок (только те,
кто сейчас участвует в конкретной закупке) — здесь просто ВСЕ компании
с допуском к строительству, включая тех, кто пока нигде не засветился
в тендерах, но реально ведёт стройки.

ВАЖНО: селекторы ниже ещё НЕ откалиброваны по реальному HTML — домен
недоступен из песочницы, где пишется этот код (та же стартовая
ситуация, что была с zakupki.py/b2b_center.py/erz.py). debug_dump()
снимает HTML главной страницы nostroy.ru (чтобы найти реальный адрес
реестра в меню — именно так нашли правильный URL для erzrf.ru) и
попытки поиска по угаданному URL реестра — по ним нужно поправить
build_url()/parse_cards().
"""

import time
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

MAIN_BASE = "https://nostroy.ru"
# Реестр СРО обычно живёт на отдельном поддомене — ДОГАДКА, уточнить
# после debug_dump() (см. меню главной страницы nostroy.ru).
REESTR_BASE = "https://reestr.nostroy.ru"
SEARCH_URL = REESTR_BASE + "/api/reestr/search"  # ДОГАДКА

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def build_url(region: str, page: int) -> str:
    params = {"region": region, "page": page}
    return SEARCH_URL + "?" + urlencode(params, encoding="utf-8")


def fetch(url: str, timeout: int = 30, proxy: str | None = None) -> str:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, headers=HEADERS, timeout=timeout, proxies=proxies)
    r.raise_for_status()
    return r.text


def _txt(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def parse_cards(html: str) -> list[dict]:
    """ЗАГЛУШКА до калибровки — правь селекторы после debug_dump()."""
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []
    # TODO: настоящие селекторы карточек компании — заполнить после
    # калибровки по debug_nostroy_*.html.
    return results


def search(region: str, pages: int, pause: float = 1.0, proxy: str | None = None) -> list[dict]:
    out = []
    for page in range(1, pages + 1):
        try:
            html = fetch(build_url(region, page), proxy=proxy)
        except Exception as e:  # noqa: BLE001
            print(f"    [!] ошибка загрузки НОСТРОЙ ({region}, стр.{page}): {e}")
            break
        cards = parse_cards(html)
        out.extend(cards)
        if not cards:
            break
        time.sleep(pause)
    return out


def debug_dump(
    path_main_home: str = "debug_nostroy_main_home.html",
    path_reestr_home: str = "debug_nostroy_reestr_home.html",
    path_search: str = "debug_nostroy_search.html",
    region: str = "Санкт-Петербург",
    proxy: str | None = None,
):
    """Снимает HTML главной nostroy.ru, главной reestr.nostroy.ru и
    угаданного поиска — для калибровки."""
    try:
        main_html = fetch(MAIN_BASE + "/", proxy=proxy)
        with open(path_main_home, "w", encoding="utf-8") as f:
            f.write(main_html)
        print(f"Сохранил {path_main_home} ({len(main_html)} символов).")
    except Exception as e:  # noqa: BLE001
        print(f"    [!] главная nostroy.ru не открылась: {e}")

    try:
        reestr_html = fetch(REESTR_BASE + "/", proxy=proxy)
        with open(path_reestr_home, "w", encoding="utf-8") as f:
            f.write(reestr_html)
        print(f"Сохранил {path_reestr_home} ({len(reestr_html)} символов).")
    except Exception as e:  # noqa: BLE001
        print(f"    [!] главная reestr.nostroy.ru не открылась: {e}")

    try:
        search_html = fetch(build_url(region, 1), proxy=proxy)
        with open(path_search, "w", encoding="utf-8") as f:
            f.write(search_html)
        print(f"Сохранил {path_search} ({len(search_html)} символов).")
    except Exception as e:  # noqa: BLE001
        print(f"    [!] поиск по угаданному URL не сработал: {e}")


if __name__ == "__main__":
    debug_dump()
