"""
ГК «БЛОК» — сборщик лидов из госзакупок и коммерческих тендерных площадок.

Конвейер:
  1. читаем config.yaml (ключевики, регионы, законы, источники);
  2. по каждому ключевику тянем ленту по всем включённым источникам
     (ЕИС zakupki.gov.ru — 44/223-ФЗ; опционально b2b-center.ru, fabrikant.ru);
  3. дедуп по (источник, реестровый номер) — независимо от закона: одна и
     та же закупка ЕИС иногда попадает в выдачу и под 44-ФЗ, и под 223-ФЗ;
  4. отсекаем явно бюрократических/бюджетных заказчиков (казённые и
     бюджетные учреждения, администрации, министерства и т.п. — их
     оставляют красным почти без исключений);
  5. обогащаем заказчика через DaData (ИНН, регион, руководитель, ОКВЭД);
  6. фильтруем по нашим регионам;
  7. помечаем тип закупки (Поставка / Работы / Прочее) — материал вs подряд;
  8. выгружаем в Excel.

Запуск:  python leadgen.py
Токен DaData:  переменная окружения DADATA_TOKEN  (или поле в config.yaml)
"""

import os
import re
import time

import yaml

import zakupki
import b2b_center
import fabrikant
import enrich
import export

# Заказчики с такими словами в названии в данных руководителя почти
# всегда помечены "не подходит" (казённые/бюджетные учреждения, органы
# власти) — это чистая бюрократия, не прямые покупатели материалов.
# Список можно расширять через config.yaml → exclude_customer_keywords.
DEFAULT_EXCLUDE_KEYWORDS = [
    "учреждение",  # казённое/бюджетное/автономное — любое, во всех случаях "не подходит"
    "администрация",
    "департамент",
    "министерство",
    "комитет",
    "таможня",
    "муниципальное унитарное предприятие",
]
# "суд" — отдельно, регуляркой по границе слова, чтобы не резать
# "судостроительный", "судоремонтный" и т.п. легитимные названия.
_SUD_RE = re.compile(r"\bСУД\b")

# Признаки "прямая поставка" vs "подрядные работы" в предмете закупки —
# просто метка для сортировки, ничего не отфильтровывает.
_SUPPLY_RE = re.compile(r"поставк|закупк[а-я]* товар|приобретен", re.IGNORECASE)
_WORKS_RE = re.compile(r"выполнени[ея] работ|работы по|ремонт|реконструкц|строительств", re.IGNORECASE)


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_excluded_customer(name: str, keywords: list[str]) -> bool:
    if not name:
        return False
    n = name.upper()
    if _SUD_RE.search(n):
        return True
    return any(kw.upper() in n for kw in keywords)


def deal_type(obj: str) -> str:
    if not obj:
        return ""
    if _SUPPLY_RE.search(obj):
        return "Поставка"
    if _WORKS_RE.search(obj):
        return "Работы"
    return "Прочее"


def region_matches(lead: dict, targets: list[str]) -> bool:
    if not targets:
        return True
    haystack = f"{lead.get('region','')} {lead.get('address','')} {lead.get('customer_name','')}".lower()
    return any(t.lower() in haystack for t in targets)


def collect_zakupki(cfg: dict, proxy: str | None) -> list[dict]:
    out = []
    for law in cfg["laws"]:
        for kw in cfg["keywords"]:
            print(f"[>] ЕИС {law}-ФЗ  «{kw}»")
            for card in zakupki.search(kw, law, cfg.get("pages_per_keyword", 2), proxy=proxy):
                card["source"] = "ЕИС"
                card["matched_keyword"] = kw
                out.append(card)
    return out


def collect_commercial(module, source_name: str, cfg: dict, proxy: str | None) -> list[dict]:
    out = []
    for kw in cfg["keywords"]:
        print(f"[>] {source_name}  «{kw}»")
        for card in module.search(kw, cfg.get("pages_per_keyword", 2), proxy=proxy):
            card["source"] = source_name
            card["matched_keyword"] = kw
            out.append(card)
    return out


def main() -> None:
    cfg = load_config()
    token = (cfg.get("dadata_token") or "").strip() or os.environ.get("DADATA_TOKEN", "").strip()
    if not token:
        print("[i] DADATA_TOKEN не задан — соберу лиды без обогащения (без ИНН/региона).")

    proxy = (cfg.get("zakupki_proxy") or "").strip() or os.environ.get("ZAKUPKI_PROXY", "").strip()
    proxy = proxy or None
    if not proxy:
        print("[i] ZAKUPKI_PROXY не задан — запросы к zakupki.gov.ru пойдут напрямую "
              "(может не работать с GitHub Actions и других зарубежных IP).")

    sources = cfg.get("sources") or ["zakupki"]
    exclude_keywords = cfg.get("exclude_customer_keywords") or DEFAULT_EXCLUDE_KEYWORDS

    # 1–2. Сбор со всех включённых источников
    raw_cards: list[dict] = []
    if "zakupki" in sources:
        raw_cards += collect_zakupki(cfg, proxy)
    if "b2b_center" in sources:
        raw_cards += collect_commercial(b2b_center, "b2b-center", cfg, proxy)
    if "fabrikant" in sources:
        raw_cards += collect_commercial(fabrikant, "fabrikant", cfg, proxy)

    # 3. Дедуп по (источник, реестровый №) — без учёта закона
    seen = set()
    raw_leads: list[dict] = []
    for card in raw_cards:
        reg = card.get("reg_number") or ""
        key = (card["source"], reg) if reg else (card["source"], card.get("object", ""))
        if key in seen:
            continue
        seen.add(key)
        raw_leads.append(card)
    print(f"[=] Собрано уникальных закупок (все источники): {len(raw_leads)}")

    # 4. Отсев бюрократических заказчиков
    filtered = [l for l in raw_leads if not is_excluded_customer(l.get("customer_name", ""), exclude_keywords)]
    print(f"[=] После отсева казённых/бюджетных/административных: {len(filtered)}")

    # 5. Обогащение
    for i, lead in enumerate(filtered, 1):
        if token:
            lead.update(enrich.enrich(lead.get("customer_name", ""), token))
            time.sleep(0.15)  # бережём лимиты DaData
        if i % 25 == 0:
            print(f"    обогащено {i}/{len(filtered)}")

    # 6. Фильтр по регионам
    targets = cfg.get("target_regions", [])
    leads = [l for l in filtered if region_matches(l, targets)]
    print(f"[=] После фильтра по регионам: {len(leads)}")

    # 7. Метка типа закупки
    for lead in leads:
        lead["deal_type"] = deal_type(lead.get("object", ""))

    # 8. Выгрузка
    out = cfg.get("output_file", "leads.xlsx")
    export.export(leads, out)
    print(f"[✓] Готово: {out}  ({len(leads)} лидов)")


if __name__ == "__main__":
    main()
