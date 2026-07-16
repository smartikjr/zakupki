"""
Проверка компаний по картотеке арбитражных дел (kad.arbitr.ru) — там
регистрируются судебные иски, включая взыскание долгов, с суммами
исковых требований. Если компания фигурирует ответчиком по иску о
взыскании долга на нужную сумму — это тоже сигнал "должник".

ВАЖНО: kad.arbitr.ru исторически тоже активно защищается от массовых
автоматических запросов (капча). debug_dump() проверяет текущее
состояние — HTML главной страницы поиска и реальный API-эндпоинт,
если он виден в разметке/JS.
"""

import requests

BASE = "https://kad.arbitr.ru"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def fetch(url: str, params: dict | None = None, timeout: int = 30, proxy: str | None = None) -> requests.Response:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    return requests.get(url, params=params, headers=HEADERS, timeout=timeout, proxies=proxies)


def debug_dump(path: str = "debug_kad_home.html", proxy: str | None = None):
    r = fetch(BASE + "/", proxy=proxy)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"status: {r.status_code}\nurl: {r.url}\n\n{r.text}")
    print(f"Сохранил {path}. HTTP статус: {r.status_code}")
    has_captcha = any(m in r.text.lower() for m in ("captcha", "recaptcha", "капча"))
    print(f"Признаки капчи: {'ДА' if has_captcha else 'не найдено'}")


def debug_dump_search(inn: str = "7705552444", path: str = "debug_kad_search.txt", proxy: str | None = None):
    """Пробует найденный (или угаданный) API поиска дел по ИНН ответчика."""
    # Известный по открытым источникам внутренний API kad.arbitr.ru —
    # ДОГАДКА, уточнить по реальному ответу/ошибке.
    url = BASE + "/Ru/Search"
    payload = {
        "Page": 1,
        "Count": 10,
        "Courts": [],
        "DateFrom": None,
        "DateTo": None,
        "Sides": [{"Name": inn, "Type": "Ответчик"}],
        "WithVKSInstances": False,
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        r = requests.post(url, json=payload, headers={**HEADERS, "Content-Type": "application/json"}, timeout=30, proxies=proxies)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"status: {r.status_code}\nurl: {r.url}\nheaders: {dict(r.headers)}\n\n{r.text[:5000]}")
        print(f"Сохранил {path}. HTTP статус: {r.status_code}")
    except Exception as e:  # noqa: BLE001
        print(f"    [!] запрос не сработал: {e}")


if __name__ == "__main__":
    debug_dump()
    debug_dump_search()
