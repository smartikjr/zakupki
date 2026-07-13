"""
Четвёртое приложение — Единый реестр членов СРО строителей (НОСТРОЙ,
nostroy.ru). Выгружает ОТДЕЛЬНЫЙ Excel-файл `nostroy.xlsx`, не связанный
с остальными тремя приложениями (leadgen.py / vacancy-leadgen /
erz-rts-leadgen).

СТАТУС: nostroy.py откалиброван — реальный API нашёлся в JS-бандле
фронтенда (reestr.nostroy.ru — Vue SPA без SSR, см. докстринг nostroy.py).
Известное ограничение: фильтр по региону пока не применяется (нужен
числовой код региона, который не нашёлся текстом в JS) — собираем общий
список членов СРО без региональной привязки.

Конвейер:
  1. собираем сырые карточки (постранично);
  2. дедуп внутри прогона (по ИНН/ОГРН, а если их нет — по названию);
  3. отсекаем явно бюрократических/бюджетных (тот же список, что в
     остальных приложениях);
  4. обогащаем через DaData;
  5. сверяем с уже выгруженными раньше (не повторяем лиды между
     прогонами — тот же принцип, что в остальных приложениях);
  6. выгружаем в Excel.

Запуск:  python main.py
Токен DaData:  переменная окружения DADATA_TOKEN (или поле в config.yaml)
"""

import os
import re
import time

import yaml

import nostroy
import export
from enrich import enrich as dadata_enrich

DEFAULT_EXCLUDE_KEYWORDS = [
    "учреждение",
    "администрация",
    "департамент",
    "министерство",
    "комитет",
    "таможня",
]
_SUD_RE = re.compile(r"\bСУД\b")


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_excluded(name: str, keywords: list[str]) -> bool:
    if not name:
        return False
    n = name.upper()
    if _SUD_RE.search(n):
        return True
    return any(kw.upper() in n for kw in keywords)


def row_key(row: dict) -> str:
    return row.get("inn") or row.get("ogrn") or row.get("company_name", "")


def collect(cfg: dict, proxy: str | None) -> list[dict]:
    print("[>] НОСТРОЙ (реестр членов СРО, все регионы)")
    out = nostroy.search(pages=cfg.get("pages", 3), page_size=cfg.get("page_size", 50), proxy=proxy)
    seen = set()
    uniq = []
    for card in out:
        key = row_key(card)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(card)
    return uniq


def main() -> None:
    cfg = load_config()
    token = (cfg.get("dadata_token") or "").strip() or os.environ.get("DADATA_TOKEN", "").strip()
    if not token:
        print("[i] DADATA_TOKEN не задан — соберу лиды без обогащения.")

    proxy = (cfg.get("proxy") or "").strip() or os.environ.get("NOSTROY_PROXY", "").strip()
    proxy = proxy or None
    if not proxy:
        print("[i] NOSTROY_PROXY не задан — запросы пойдут напрямую "
              "(может не работать с GitHub Actions и других зарубежных IP).")

    exclude_keywords = cfg.get("exclude_customer_keywords") or DEFAULT_EXCLUDE_KEYWORDS
    out = cfg.get("output_file", "nostroy.xlsx")

    rows = collect(cfg, proxy)
    rows = [r for r in rows if not is_excluded(r.get("company_name", ""), exclude_keywords)]
    print(f"[=] После отсева казённых/бюджетных: {len(rows)}")

    if token:
        for i, r in enumerate(rows, 1):
            r.update(dadata_enrich(r.get("company_name", ""), token))
            time.sleep(0.15)
            if i % 25 == 0:
                print(f"    обогащено {i}/{len(rows)}")

    existing = export.load_existing(out)
    existing_keys = {row_key(r) for r in existing}
    new_rows = [r for r in rows if row_key(r) not in existing_keys]
    print(f"[=] Уже было: {len(rows) - len(new_rows)}, новых: {len(new_rows)}")

    combined = existing + new_rows
    export.export(combined, out)
    print(f"[✓] Готово: {out}  (всего {len(combined)}, новых в этом прогоне: {len(new_rows)})")


if __name__ == "__main__":
    main()
