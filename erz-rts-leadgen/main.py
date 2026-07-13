"""
Третье приложение — сбор лидов из ЕРЗ.РФ (застройщики/новостройки) и
РТС-тендер (ещё одна тендерная площадка, помимо zakupki.gov.ru и
b2b-center.ru из корневого приложения). Выгружает ОТДЕЛЬНЫЙ Excel с
двумя листами — по требованию не смешивать эти два источника ни между
собой, ни с корневым leads.xlsx.

ВАЖНО: селекторы rts_tender.py/erz.py ещё не откалиброваны по
реальному HTML (см. их докстринги) — первый прогон почти наверняка
вернёт 0 строк по обоим источникам, пока не откалибровать через
debug-dump.yml.

Конвейер (по каждому источнику независимо):
  1. собираем сырые карточки;
  2. дедуп внутри прогона;
  3. отсекаем явно бюрократических/бюджетных (тот же список, что в
     корневом приложении);
  4. обогащаем через DaData;
  5. сверяем с уже выгруженными раньше (не повторяем лиды между
     прогонами — тот же принцип, что в корневом leadgen.py);
  6. выгружаем в Excel (два листа).

Запуск:  python main.py
Токен DaData:  переменная окружения DADATA_TOKEN (или поле в config.yaml)
"""

import os
import re
import time

import yaml

import erz
import rts_tender
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


def collect_rts(cfg: dict, proxy: str | None) -> list[dict]:
    out: list[dict] = []
    for kw in cfg.get("keywords", []):
        print(f"[>] РТС-тендер «{kw}»")
        out.extend(rts_tender.search(kw, cfg.get("pages_per_keyword", 2), proxy=proxy))
    seen = set()
    uniq = []
    for card in out:
        key = card.get("reg_number") or card.get("object", "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(card)
    return uniq


def collect_erz(cfg: dict, proxy: str | None) -> list[dict]:
    out: list[dict] = []
    for region in cfg.get("regions", []):
        print(f"[>] ЕРЗ.РФ «{region}»")
        out.extend(erz.search(region, cfg.get("pages_per_region", 2), proxy=proxy))
    seen = set()
    uniq = []
    for card in out:
        key = f"{card.get('developer','')}|{card.get('project','')}"
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

    proxy = (cfg.get("proxy") or "").strip() or os.environ.get("ERZ_RTS_PROXY", "").strip()
    proxy = proxy or None
    if not proxy:
        print("[i] ERZ_RTS_PROXY не задан — запросы пойдут напрямую "
              "(может не работать с GitHub Actions и других зарубежных IP).")

    exclude_keywords = cfg.get("exclude_customer_keywords") or DEFAULT_EXCLUDE_KEYWORDS
    out = cfg.get("output_file", "erz_rts.xlsx")

    # --- РТС-тендер ---
    rts_rows = collect_rts(cfg, proxy)
    rts_rows = [r for r in rts_rows if not is_excluded(r.get("customer_name", ""), exclude_keywords)]
    print(f"[=] РТС-тендер после отсева: {len(rts_rows)}")
    if token:
        for i, r in enumerate(rts_rows, 1):
            r.update(dadata_enrich(r.get("customer_name", ""), token))
            time.sleep(0.15)
    rts_existing = export.load_existing(out, export.RTS_SHEET, export.RTS_COLUMNS)
    rts_existing_keys = {r.get("reg_number") or r.get("object", "") for r in rts_existing}
    rts_new = [r for r in rts_rows if (r.get("reg_number") or r.get("object", "")) not in rts_existing_keys]
    print(f"[=] РТС-тендер уже было: {len(rts_rows) - len(rts_new)}, новых: {len(rts_new)}")
    rts_combined = rts_existing + rts_new

    # --- ЕРЗ.РФ ---
    erz_rows = collect_erz(cfg, proxy)
    erz_rows = [r for r in erz_rows if not is_excluded(r.get("developer", ""), exclude_keywords)]
    print(f"[=] ЕРЗ.РФ после отсева: {len(erz_rows)}")
    if token:
        for i, r in enumerate(erz_rows, 1):
            r.update(dadata_enrich(r.get("developer", ""), token))
            time.sleep(0.15)
    erz_existing = export.load_existing(out, export.ERZ_SHEET, export.ERZ_COLUMNS)
    erz_existing_keys = {f"{r.get('developer','')}|{r.get('project','')}" for r in erz_existing}
    erz_new = [r for r in erz_rows if f"{r.get('developer','')}|{r.get('project','')}" not in erz_existing_keys]
    print(f"[=] ЕРЗ.РФ уже было: {len(erz_rows) - len(erz_new)}, новых: {len(erz_new)}")
    erz_combined = erz_existing + erz_new

    export.export(erz_combined, rts_combined, out)
    print(
        f"[✓] Готово: {out}  "
        f"(ЕРЗ.РФ: {len(erz_combined)} всего/{len(erz_new)} новых, "
        f"РТС-тендер: {len(rts_combined)} всего/{len(rts_new)} новых)"
    )


if __name__ == "__main__":
    main()
