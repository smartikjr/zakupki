"""
Поиск потенциальных заказчиков через вакансии на hh.ru + готовые ссылки
для ручного поиска в Яндексе/Google — по методике из скриншота
(п.7 и п.9; п.8 «выезд на объект» — чисто полевой метод, не
автоматизируется).

Конвейер:
  1. По каждой должности из config.yaml (job_titles) ищем вакансии на
     hh.ru в нужных регионах — открытое API, авторизация не нужна.
  2. Группируем по работодателю (одна компания может дать несколько
     вакансий/регионов) — получаем список компаний, которые прямо
     сейчас нанимают на стройку.
  3. Отсеиваем казённые/бюджетные заказчиков по названию (тот же
     принцип, что в основном сборщике лидов).
  4. Обогащаем через DaData (ИНН, регион, руководитель, ОКВЭД).
  5. Готовим лист с кликабельными Яндекс/Google-запросами по каждому
     региону и категории (п.9) — сам поиск не парсим, см. README.
  6. Выгружаем всё в companies.xlsx (два листа).

Запуск:  python main.py
Токен DaData:  переменная окружения DADATA_TOKEN (или поле в config.yaml)
"""

import os
import time

import yaml

import export
import hh_api
from enrich import enrich as dadata_enrich

DEFAULT_EXCLUDE_KEYWORDS = [
    "учреждение",
    "администрация",
    "департамент",
    "министерство",
    "комитет",
]


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_excluded(name: str, keywords: list[str]) -> bool:
    if not name:
        return False
    n = name.upper()
    return any(kw.upper() in n for kw in keywords)


def collect_companies(cfg: dict, proxy: str | None) -> list[dict]:
    area_map = hh_api.resolve_area_ids(cfg["regions"], proxy=proxy)
    missing = [r for r in cfg["regions"] if r not in area_map]
    if missing:
        print(f"[!] Не нашёл на hh.ru регион(ы): {', '.join(missing)} — поищи без них.")
    print(f"[i] Регионы hh.ru: {area_map}")

    companies: dict[str, dict] = {}
    for region_name, area_id in area_map.items():
        for title in cfg["job_titles"]:
            print(f"[>] HH.ru «{title}» в «{region_name}»")
            page = 0
            pages_limit = cfg.get("pages_per_query", 2)
            while page < pages_limit:
                try:
                    data = hh_api.search_vacancies(title, area_id, page=page, proxy=proxy)
                except Exception as e:  # noqa: BLE001
                    print(f"    [!] ошибка hh.ru ({title}, {region_name}, стр.{page}): {e}")
                    break
                items = data.get("items", [])
                for v in items:
                    employer = v.get("employer") or {}
                    emp_id = employer.get("id")
                    emp_name = employer.get("name")
                    if not emp_id or not emp_name:
                        continue
                    rec = companies.setdefault(
                        emp_id,
                        {
                            "company": emp_name,
                            "hh_url": employer.get("alternate_url", ""),
                            "titles": set(),
                            "regions": set(),
                            "vacancy_count": 0,
                            "last_published": "",
                        },
                    )
                    rec["titles"].add(title)
                    rec["regions"].add(region_name)
                    rec["vacancy_count"] += 1
                    pub = v.get("published_at", "") or ""
                    if pub > rec["last_published"]:
                        rec["last_published"] = pub
                total_pages = data.get("pages", 1)
                if not items or page + 1 >= total_pages:
                    break
                page += 1
                time.sleep(0.3)
    return list(companies.values())


def main() -> None:
    cfg = load_config()
    token = (cfg.get("dadata_token") or "").strip() or os.environ.get("DADATA_TOKEN", "").strip()
    if not token:
        print("[i] DADATA_TOKEN не задан — соберу компании без обогащения (без ИНН/руководителя).")

    proxy = (cfg.get("hh_proxy") or "").strip() or os.environ.get("HH_PROXY", "").strip()
    proxy = proxy or None

    companies = collect_companies(cfg, proxy)
    print(f"[=] Уникальных компаний с hh.ru: {len(companies)}")

    exclude_keywords = cfg.get("exclude_customer_keywords") or DEFAULT_EXCLUDE_KEYWORDS
    companies = [c for c in companies if not is_excluded(c["company"], exclude_keywords)]
    print(f"[=] После отсева казённых/бюджетных: {len(companies)}")

    for i, c in enumerate(companies, 1):
        if token:
            c.update(dadata_enrich(c["company"], token))
            time.sleep(0.15)
        if i % 25 == 0:
            print(f"    обогащено {i}/{len(companies)}")

    links = export.build_search_links(cfg.get("search_categories", []), cfg.get("regions", []))

    out = cfg.get("output_file", "companies.xlsx")
    export.export(companies, links, out)
    print(f"[✓] Готово: {out} ({len(companies)} компаний, {len(links)} готовых ссылок для поиска)")


if __name__ == "__main__":
    main()
