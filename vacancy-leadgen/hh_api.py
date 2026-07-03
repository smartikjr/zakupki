"""
Клиент открытого API hh.ru — поиск вакансий и данных о работодателях.

Реализует п.7 методики («Поиск заказчиков и объектов на сайтах, где
размещены вакансии»): компании, которые публикуют вакансии вроде
«Начальник строительного участка» / «Прораб» — чаще всего заказчики
или подрядчики, ведущие стройку прямо сейчас.

Авторизация не нужна для базового поиска вакансий, но hh.ru просит
указывать осмысленный User-Agent (описание приложения) — без него
можно получить более жёсткие лимиты или отказ.

Документация: https://api.hh.ru/openapi/redoc
"""

import requests

BASE = "https://api.hh.ru"

HEADERS = {
    "User-Agent": "ZakupkiLeadgen/1.0 (contractor lead search tool)",
    "Accept": "application/json",
}


def _get(path: str, params: dict | None = None, timeout: int = 30, proxy: str | None = None) -> dict:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(f"{BASE}{path}", headers=HEADERS, params=params, timeout=timeout, proxies=proxies)
    if r.status_code >= 400:
        # тело ответа hh.ru обычно объясняет причину (bad_argument,
        # captcha_required и т.п.) — requests его не печатает по умолчанию
        print(f"    [debug] {r.status_code} body: {r.text[:500]}")
    r.raise_for_status()
    return r.json()


def resolve_area_ids(region_names: list[str], proxy: str | None = None) -> dict[str, int]:
    """По списку названий регионов возвращает {название_из_config: area_id}.

    Ищет по дереву регионов hh.ru (страна → регион → город): сначала
    точное совпадение по имени (без учёта регистра), затем частичное
    в обе стороны. Если регион не нашёлся — просто не попадёт в словарь
    (в логе будет видно, что искали по нему без указания area).
    """
    tree = _get("/areas", proxy=proxy)

    flat: list[tuple[int, str]] = []

    def walk(nodes):
        for n in nodes:
            flat.append((int(n["id"]), n["name"]))
            if n.get("areas"):
                walk(n["areas"])

    walk(tree)

    result: dict[str, int] = {}
    for target in region_names:
        target_low = target.lower().strip()
        # 1. точное совпадение
        for area_id, name in flat:
            if name.lower() == target_low:
                result[target] = area_id
                break
        if target in result:
            continue
        # 2. частичное совпадение (в обе стороны)
        for area_id, name in flat:
            name_low = name.lower()
            if target_low in name_low or name_low in target_low:
                result[target] = area_id
                break
    return result


def search_vacancies(
    text: str,
    area_id: int | None,
    page: int = 0,
    per_page: int = 50,
    timeout: int = 30,
    proxy: str | None = None,
) -> dict:
    params = {
        "text": text,
        "search_field": "name",  # искать по названию вакансии, не по всему тексту
        "page": page,
        "per_page": per_page,
    }
    if area_id:
        params["area"] = area_id
    return _get("/vacancies", params=params, timeout=timeout, proxy=proxy)
