"""
Проверка компаний на долги через Банк данных исполнительных производств
ФССП (fssp.gov.ru/iss/ip) — публичный реестр, где по названию/ИНН
должника видно, есть ли открытые исполнительные производства и на
какую сумму.

ВАЖНО: у ФССП исторически стояла капча на форме поиска именно для
защиты от массовых автоматических запросов (это ровно наш случай —
проверить 163 компании разом). debug_dump() снимает HTML страницы
поиска — по нему нужно проверить, стоит ли капча сейчас, прежде чем
писать реальный search()/parse_cards().
"""

import requests

BASE = "https://fssp.gov.ru"
SEARCH_PAGE = BASE + "/iss/ip"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def fetch(url: str, timeout: int = 30, proxy: str | None = None) -> str:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, headers=HEADERS, timeout=timeout, proxies=proxies)
    r.raise_for_status()
    return r.text


def debug_dump(path: str = "debug_fssp_search_page.html", proxy: str | None = None):
    """Снимает HTML страницы поиска — проверить, есть ли капча."""
    html = fetch(SEARCH_PAGE, proxy=proxy)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    has_captcha = any(
        marker in html.lower()
        for marker in ("captcha", "recaptcha", "капча", "g-recaptcha")
    )
    print(f"Сохранил {path} ({len(html)} символов).")
    print(f"Признаки капчи в HTML: {'ДА' if has_captcha else 'не найдено'}")


if __name__ == "__main__":
    debug_dump()
