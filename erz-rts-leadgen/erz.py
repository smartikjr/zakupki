"""
Загрузка данных о застройщиках/новостройках с erzrf.ru (ЕРЗ.РФ —
«Единый ресурс застройщиков», рейтинговое агентство, публикует реестр
застройщиков и строящихся объектов по регионам).

Зачем этот источник: застройщик, который прямо сейчас строит жильё —
почти гарантированный потребитель ЖБИ (плиты, сваи, кольца и т.п.),
причём это не тендер, который ещё нужно выиграть, а прямой контакт
с компанией, ведущей стройку.

ВАЖНО: селекторы ниже ещё НЕ откалиброваны по реальному HTML — та же
ситуация, что в rts_tender.py (домен недоступен из песочницы).
debug_dump() снимает HTML главной страницы и угаданного списка
застройщиков — по нему нужно поправить build_url()/parse_cards().
"""

import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

BASE = "https://erzrf.ru"
# Реальный адрес найден в меню главной страницы (debug_erz_home.html,
# калибровка 2026-07-13): "/zastroyschiki" — без "h" после "s", не так,
# как логично было бы транслитерировать "застройщики".
LIST_URL = BASE + "/zastroyschiki"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def build_url(region: str, page: int) -> str:
    params = {"region": region, "page": page}
    return LIST_URL + "?" + urlencode(params, encoding="utf-8")


def fetch(url: str, timeout: int = 30, proxy: str | None = None) -> str:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, headers=HEADERS, timeout=timeout, proxies=proxies)
    r.raise_for_status()
    return r.text


def _txt(node) -> str:
    return node.get_text(strip=True) if node else ""


def parse_cards(html: str) -> list[dict]:
    """ЗАГЛУШКА до калибровки — правь селекторы после debug_dump()."""
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []
    # TODO: настоящие селекторы карточек застройщика/объекта — заполнить
    # после калибровки по debug_erz_list.html.
    return results


def search(region: str, pages: int, pause: float = 1.0, proxy: str | None = None) -> list[dict]:
    out = []
    for page in range(1, pages + 1):
        try:
            html = fetch(build_url(region, page), proxy=proxy)
        except Exception as e:  # noqa: BLE001
            print(f"    [!] ошибка загрузки ЕРЗ.РФ ({region}, стр.{page}): {e}")
            break
        cards = parse_cards(html)
        out.extend(cards)
        if not cards:
            break
        time.sleep(pause)
    return out


def debug_dump(
    path_home: str = "debug_erz_home.html",
    path_list_plain: str = "debug_erz_list_plain.html",
    path_list: str = "debug_erz_list.html",
    region: str = "Санкт-Петербург",
    proxy: str | None = None,
):
    """Снимает HTML главной, списка без фильтра и списка с фильтром — для калибровки."""
    home_html = fetch(BASE + "/", proxy=proxy)
    with open(path_home, "w", encoding="utf-8") as f:
        f.write(home_html)
    print(f"Сохранил {path_home} ({len(home_html)} символов).")

    try:
        plain_html = fetch(LIST_URL, proxy=proxy)
        with open(path_list_plain, "w", encoding="utf-8") as f:
            f.write(plain_html)
        print(f"Сохранил {path_list_plain} ({len(plain_html)} символов).")
    except Exception as e:  # noqa: BLE001
        print(f"    [!] список без фильтра не сработал: {e}")

    try:
        list_html = fetch(build_url(region, 1), proxy=proxy)
        with open(path_list, "w", encoding="utf-8") as f:
            f.write(list_html)
        print(f"Сохранил {path_list} ({len(list_html)} символов).")
    except Exception as e:  # noqa: BLE001
        print(f"    [!] список по угаданному URL не сработал: {e}")


if __name__ == "__main__":
    debug_dump()
