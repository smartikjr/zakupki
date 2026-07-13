"""
Загрузка и разбор поиска на rts-tender.ru — одной из крупнейших
электронных торговых площадок РФ (работает и по 44-ФЗ, и по
коммерческим закупкам вне 44/223-ФЗ).

ВАЖНО: селекторы ниже ещё НЕ откалиброваны по реальному HTML — домен
недоступен из песочницы, где пишется этот код (та же ситуация была
изначально с zakupki.py/b2b_center.py/fabrikant.py). debug_dump()
снимает HTML главной страницы и попытки поиска по угаданному URL —
по нему нужно поправить build_url()/parse_cards() (см. debug-dump.yml).

Калибровка 2026-07-13, первая попытка (без прокси, с GitHub Actions IP):
даже главная страница не открылась — "Connection reset by peer" сразу
на TCP-уровне. Это похоже на блокировку по IP (как изначально было с
zakupki.gov.ru), а не на защиту от ботов на уровне заголовков — сайт
рвёт соединение до ответа, а не отдаёт капчу/403. Следующая попытка —
с ERZ_RTS_PROXY (тот же российский резидентский прокси, что уже
работает для zakupki.gov.ru/hh.ru).
"""

import time
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.rts-tender.ru"
SEARCH_URL = BASE + "/poisk"  # ДОГАДКА — уточнить после debug_dump()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Connection": "keep-alive",
}


def build_url(keyword: str, page: int) -> str:
    params = {"text": keyword, "page": page}
    return SEARCH_URL + "?" + urlencode(params, encoding="utf-8")


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
    # TODO: настоящие селекторы карточек тендера — заполнить после
    # калибровки по debug_rts_search.html.
    return results


def search(keyword: str, pages: int, pause: float = 1.0, proxy: str | None = None) -> list[dict]:
    out = []
    for page in range(1, pages + 1):
        try:
            html = fetch(build_url(keyword, page), proxy=proxy)
        except Exception as e:  # noqa: BLE001
            print(f"    [!] ошибка загрузки rts-tender ({keyword}, стр.{page}): {e}")
            break
        cards = parse_cards(html)
        out.extend(cards)
        if not cards:
            break
        time.sleep(pause)
    return out


def debug_dump(
    path_home: str = "debug_rts_home.html",
    path_search: str = "debug_rts_search.html",
    keyword: str = "плиты дорожные",
    proxy: str | None = None,
):
    """Снимает HTML главной страницы и угаданного поиска — для калибровки."""
    home_html = fetch(BASE + "/", proxy=proxy)
    with open(path_home, "w", encoding="utf-8") as f:
        f.write(home_html)
    print(f"Сохранил {path_home} ({len(home_html)} символов).")

    try:
        search_html = fetch(build_url(keyword, 1), proxy=proxy)
        with open(path_search, "w", encoding="utf-8") as f:
            f.write(search_html)
        print(f"Сохранил {path_search} ({len(search_html)} символов).")
    except Exception as e:  # noqa: BLE001
        print(f"    [!] поиск по угаданному URL не сработал: {e}")


if __name__ == "__main__":
    debug_dump()
