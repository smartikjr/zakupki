"""
ГК «БЛОК» — сборщик лидов из госзакупок.

Конвейер:
  1. читаем config.yaml (ключевики, регионы, законы);
  2. по каждому ключевику тянем ленту ЕИС (44/223-ФЗ);
  3. дедуп по реестровому номеру;
  4. обогащаем заказчика через DaData (ИНН, регион, руководитель, ОКВЭД);
  5. фильтруем по нашим регионам;
  6. выгружаем в Excel.

Запуск:  python leadgen.py
Токен DaData:  переменная окружения DADATA_TOKEN  (или поле в config.yaml)
"""

import os
import time

import yaml

import zakupki
import enrich
import export


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def region_matches(lead: dict, targets: list[str]) -> bool:
    if not targets:
        return True
    haystack = f"{lead.get('region','')} {lead.get('address','')} {lead.get('customer_name','')}".lower()
    return any(t.lower() in haystack for t in targets)


def main() -> None:
    cfg = load_config()
    token = (cfg.get("dadata_token") or "").strip() or os.environ.get("DADATA_TOKEN", "").strip()
    if not token:
        print("[i] DADATA_TOKEN не задан — соберу лиды без обогащения (без ИНН/региона).")

    # 1–3. Сбор + дедуп
    seen = set()
    raw_leads: list[dict] = []
    for law in cfg["laws"]:
        for kw in cfg["keywords"]:
            print(f"[>] {law}-ФЗ  «{kw}»")
            for card in zakupki.search(kw, law, cfg.get("pages_per_keyword", 2)):
                key = (card["reg_number"], card["law"]) if card["reg_number"] else (card["object"], card["law"])
                if key in seen:
                    continue
                seen.add(key)
                card["matched_keyword"] = kw
                raw_leads.append(card)
    print(f"[=] Собрано уникальных закупок: {len(raw_leads)}")

    # 4. Обогащение
    for i, lead in enumerate(raw_leads, 1):
        if token:
            lead.update(enrich.enrich(lead.get("customer_name", ""), token))
            time.sleep(0.15)  # бережём лимиты DaData
        if i % 25 == 0:
            print(f"    обогащено {i}/{len(raw_leads)}")

    # 5. Фильтр по регионам
    targets = cfg.get("target_regions", [])
    leads = [l for l in raw_leads if region_matches(l, targets)]
    print(f"[=] После фильтра по регионам: {len(leads)}")

    # 6. Выгрузка
    out = cfg.get("output_file", "leads.xlsx")
    export.export(leads, out)
    print(f"[✓] Готово: {out}  ({len(leads)} лидов)")


if __name__ == "__main__":
    main()
