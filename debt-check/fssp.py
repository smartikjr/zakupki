"""
Проверка компаний на долги через Банк данных исполнительных производств
ФССП — публичный реестр, где по ИНН должника видно, есть ли открытые
исполнительные производства и на какую сумму.

Калибровка 2026-07-16: страница поиска (fssp.gov.ru/iss/ip) отдаётся без
капчи, реальная форма шлёт GET на отдельный поддомен
is-go.fssp.gov.ru/ajax_search. Поле ИНН юрлица — `is[inn]`, вариант
поиска `is[variant]=5`, регион `is[region_id][0]=-1` (все регионы).
В разметке есть CSS для `#captcha-popup`, но в самой форме нет обязательного
токена капчи — похоже, всплывает только при превышении лимита запросов
(rate-limit), не на каждый запрос. Проверить фактическое поведение на
живых данных — см. debug_dump_search(), которая делает один реальный
запрос по тестовому ИНН.
"""

import requests

BASE = "https://fssp.gov.ru"
SEARCH_PAGE = BASE + "/iss/ip"
AJAX_SEARCH = "https://is-go.fssp.gov.ru/ajax_search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": SEARCH_PAGE,
}


def fetch(url: str, params: dict | None = None, timeout: int = 30, proxy: str | None = None) -> requests.Response:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout, proxies=proxies)
    return r


def search_by_inn(inn: str, timeout: int = 30, proxy: str | None = None) -> requests.Response:
    params = {
        "system": "ip",
        "is[extended]": "1",
        "nocache": "1",
        "is[variant]": "5",
        "is[region_id][0]": "-1",
        "is[inn]": inn,
    }
    return fetch(AJAX_SEARCH, params=params, timeout=timeout, proxy=proxy)


def debug_dump(path: str = "debug_fssp_search_page.html", proxy: str | None = None):
    """Снимает HTML страницы поиска — проверить, есть ли капча."""
    r = fetch(SEARCH_PAGE, proxy=proxy)
    html = r.text
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    has_captcha = any(
        marker in html.lower()
        for marker in ("captcha", "recaptcha", "капча", "g-recaptcha")
    )
    print(f"Сохранил {path} ({len(html)} символов).")
    print(f"Признаки капчи в HTML: {'ДА' if has_captcha else 'не найдено'}")


def debug_dump_search(inn: str = "7705552444", path: str = "debug_fssp_search_result.txt", proxy: str | None = None):
    """Делает реальный запрос по ИНН и сохраняет сырой ответ — проверить
    формат и не всплывает ли капча/блокировка на реальном поиске."""
    r = search_by_inn(inn, proxy=proxy)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"status: {r.status_code}\nurl: {r.url}\nheaders: {dict(r.headers)}\n\n{r.text}")
    print(f"Сохранил {path}. HTTP статус: {r.status_code}")
    has_captcha = any(marker in r.text.lower() for marker in ("captcha", "recaptcha", "капча"))
    print(f"Признаки капчи в ответе: {'ДА' if has_captcha else 'не найдено'}")


if __name__ == "__main__":
    debug_dump()
    debug_dump_search()
