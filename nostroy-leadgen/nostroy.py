"""
Загрузка данных из Единого реестра членов СРО строителей — НОСТРОЙ
(reestr.nostroy.ru).

Зачем этот источник: официальный реестр всех строительных компаний с
допуском СРО (обязателен по закону для большинства строительных работ)
по регионам — большая база реальных подрядчиков. В отличие от ЕРЗ.РФ
(рейтинг только жилых застройщиков) и тендерных площадок (только те,
кто сейчас участвует в конкретной закупке) — здесь просто ВСЕ компании
с допуском к строительству, включая тех, кто пока нигде не засветился
в тендерах, но реально ведёт стройки.

Откалибровано по реальному коду фронтенда (2026-07-13): reestr.nostroy.ru
— Vue SPA без server-side рендеринга (реального контента в HTML нет,
как у fabrikant.ru), но реальный backend-API нашёлся прямо в JS-бандле
приложения (константа `i="https://reestr.nostroy.ru/api/"` рядом с
списком эндпоинтов). Все запросы — POST с JSON-телом
`{filters, page, pageCount, sortBy, searchString}`, `Content-Type:
application/json`. Нужный эндпоинт — "sro/all/member/list" (список
членов СРО по всем СРО сразу, а не по одной конкретной) — соответствует
компоненту "MemberListByAllSro" с полями фильтра:
region_number, sro_registration_number, sro_full_description,
member_status, full_description (название члена), inn, ogrnip,
registry_registration_date, director.

ИЗВЕСТНОЕ ОГРАНИЧЕНИЕ: `region_number`, судя по названию поля — числовой
код субъекта РФ (как `regionKey` у ЕРЗ.РФ), а не текстовое название.
Соответствие "название региона → числовой код" нигде не нашлось в JS
текстом (видимо, тянется отдельным запросом `dictionaries/get` в момент
открытия формы фильтра в браузере). Пока фильтр по региону не
применяется — search() запрашивает список без фильтра по региону,
разбирая нужные записи только по названию/адресу постфактум, если
получится. Если нужна точная региональная выборка — придётся либо
вызвать `dictionaries/get` и найти нужные коды регионов, либо смотреть
в браузере (devtools → Network) при выборе региона в фильтре на сайте.
"""

import time

import requests

API_BASE = "https://reestr.nostroy.ru/api/"
ENDPOINT_MEMBER_LIST_ALL = "sro/all/member/list"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Content-Type": "application/json",
}


def api_post(endpoint: str, payload: dict, timeout: int = 30, proxy: str | None = None) -> dict:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.post(API_BASE + endpoint, json=payload, headers=HEADERS, timeout=timeout, proxies=proxies)
    r.raise_for_status()
    return r.json()


def _get(d: dict, *keys, default=""):
    if not isinstance(d, dict):
        return default
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return default


def parse_cards(data) -> list[dict]:
    """Разбирает JSON-ответ sro/all/member/list в список карточек-лидов.

    Точная форма ответа ещё не проверена на реальных данных — правь при
    необходимости после первого живого запроса (см. debug_dump()).
    """
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("data", "items", "list"):
            v = data.get(key)
            if isinstance(v, list):
                items = v
                break
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        company_name = _get(item, "full_description", "fullDescription", "name")
        if not company_name:
            continue
        results.append(
            {
                "company_name": company_name,
                "inn": _get(item, "inn"),
                "ogrn": _get(item, "ogrnip", "ogrn"),
                "sro_name": _get(item, "sro_full_description", "sroFullDescription"),
                "region": _get(item, "region_number", "regionNumber", "region"),
                "status_sro": _get(item, "member_status", "memberStatus"),
                "admission_date": _get(item, "registry_registration_date", "registryRegistrationDate"),
                "director": _get(item, "director"),
                "address": _get(item, "place", "address"),
                "link": "",
            }
        )
    return results


def search(pages: int = 1, page_size: int = 50, pause: float = 1.0, proxy: str | None = None) -> list[dict]:
    """Собирает список членов СРО (по всем СРО сразу). Фильтр по региону
    пока не применяется — см. докстринг модуля."""
    out = []
    for page in range(1, pages + 1):
        payload = {"filters": {}, "page": page, "pageCount": page_size, "sortBy": {}, "searchString": ""}
        try:
            data = api_post(ENDPOINT_MEMBER_LIST_ALL, payload, proxy=proxy)
        except Exception as e:  # noqa: BLE001
            print(f"    [!] ошибка загрузки НОСТРОЙ (стр.{page}): {e}")
            break
        try:
            cards = parse_cards(data)
        except Exception as e:  # noqa: BLE001
            print(f"    [!] ошибка разбора ответа НОСТРОЙ (стр.{page}): {e}")
            break
        out.extend(cards)
        if not cards:
            break
        time.sleep(pause)
    return out


def debug_dump(path_response: str = "debug_nostroy_api_response.json", proxy: str | None = None):
    """Делает реальный POST-запрос к sro/all/member/list и сохраняет
    сырой JSON-ответ — для калибровки parse_cards(). Сохраняет ответ
    ДО попытки разбора, чтобы файл остался даже если parse_cards() упадёт."""
    import json

    payload = {"filters": {}, "page": 1, "pageCount": 5, "sortBy": {}, "searchString": ""}
    try:
        data = api_post(ENDPOINT_MEMBER_LIST_ALL, payload, proxy=proxy)
    except Exception as e:  # noqa: BLE001
        print(f"    [!] запрос к API не сработал: {e}")
        return

    with open(path_response, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Сохранил {path_response} (тип: {type(data).__name__}).")

    try:
        cards = parse_cards(data)
        print(f"Найдено карточек: {len(cards)}")
    except Exception as e:  # noqa: BLE001
        print(f"    [!] parse_cards() упал на реальном ответе: {e}")


if __name__ == "__main__":
    debug_dump()
