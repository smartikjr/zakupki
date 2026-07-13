"""
Обогащение лида через DaData (бесплатный тариф, 10 000 запросов/день).

Используем метод suggest/party: по названию заказчика находим организацию
и получаем ИНН, адрес, регион, руководителя, статус и основной ОКВЭД.
Телефонов/почт на бесплатном тарифе нет — их DaData отдаёт только на
«Максимальном» (56 000 ₽/год). Поэтому здесь тянем то, что доступно даром;
телефон снабженца добываем уже вручную по названию/сайту компании.

Документация: https://dadata.ru/api/suggest/party/
"""

import requests

SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"


def enrich(customer_name: str, token: str, timeout: int = 15) -> dict:
    """Возвращает {inn, company, address, region, director, status, okved} или {}."""
    if not token or not customer_name:
        return {}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Token {token}",
    }
    try:
        r = requests.post(
            SUGGEST_URL,
            json={"query": customer_name, "count": 1},
            headers=headers,
            timeout=timeout,
        )
        r.raise_for_status()
        suggestions = r.json().get("suggestions", [])
    except Exception as e:  # noqa: BLE001
        print(f"    [!] DaData ошибка для «{customer_name[:40]}»: {e}")
        return {}

    if not suggestions:
        return {}

    d = suggestions[0].get("data", {})
    address = (d.get("address") or {})
    addr_data = (address.get("data") or {})
    management = (d.get("management") or {})
    name = (d.get("name") or {})
    state = (d.get("state") or {})

    return {
        "inn": d.get("inn", ""),
        "company": name.get("short_with_opf") or suggestions[0].get("value", ""),
        "address": address.get("value", ""),
        "region": addr_data.get("region_with_type", ""),
        "director": management.get("name", ""),
        "status": state.get("status", ""),
        "okved": d.get("okved", ""),
    }
