"""
Загрузка и разбор публичного поиска процедур на b2b-center.ru —
крупнейшей коммерческой B2B-тендерной площадке в РФ.

Откалибровано по реальному HTML (снят через .github/workflows/debug-dump.yml,
2026-07-03). Ключевая находка: поле поиска называется НЕ "query", а
"f_keyword" (+ обязательный флаг "searching=1"), иначе сайт отдаёт общую
ленту последних закупок без фильтра по ключевому слову. Результаты —
таблица `table.search-results` со строками `tbody > tr`: колонки
«Название процедуры» (ссылка + `.search-results-title-desc`),
«Организатор», «Опубликовано», «Актуально до».

Зачем нужен второй источник, кроме ЕИС: 44/223-ФЗ обязывают публиковать
закупки на zakupki.gov.ru только бюджетные и квази-государственные
организации. Чисто коммерческие компании (частные заводы, торговые
дома, застройщики) размещают тендеры на площадках вроде b2b-center —
это как раз тот сегмент, где меньше бюрократии и выше шанс быстрой
сделки.
"""

import re
import time
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.b2b-center.ru"
SEARCH_URL = BASE + "/market/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}

_TENDER_ID_RE = re.compile(r"tender-(\d+)")


def build_url(keyword: str, page: int) -> str:
    params = {"f_keyword": keyword, "searching": 1, "page": page}
    return SEARCH_URL + "?" + urlencode(params, encoding="utf-8")


def fetch(keyword: str, page: int, timeout: int = 30, proxy: str | None = None) -> str:
    url = build_url(keyword, page)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, headers=HEADERS, timeout=timeout, proxies=proxies)
    r.raise_for_status()
    return r.text


def _txt(node) -> str:
    return node.get_text(strip=True) if node else ""


def parse_cards(html: str) -> list[dict]:
    """Разбирает страницу результатов в список карточек-лидов."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.search-results")
    if not table:
        return []
    results = []
    for row in table.select("tbody > tr"):
        cells = row.select("td")
        if len(cells) < 3:
            continue
        title_a = cells[0].select_one("a.search-results-title") or cells[0].select_one("a")
        link = urljoin(BASE, title_a["href"]) if (title_a and title_a.has_attr("href")) else ""

        desc = cells[0].select_one(".search-results-title-desc")
        obj = _txt(desc) or _txt(title_a)

        m = _TENDER_ID_RE.search(link)
        reg_number = m.group(1) if m else ""

        customer = _txt(cells[1].select_one("a")) or _txt(cells[1])
        published = _txt(cells[2]) if len(cells) > 2 else ""
        deadline = _txt(cells[3]) if len(cells) > 3 else ""
        dates = " — ".join(v for v in (published, deadline) if v)

        if not (obj or reg_number):
            continue
        results.append(
            {
                "law": "",
                "reg_number": reg_number,
                "object": obj,
                "customer_name": customer,
                "price": "",
                "dates": dates,
                "link": link,
            }
        )
    return results


def search(keyword: str, pages: int, pause: float = 1.0, proxy: str | None = None) -> list[dict]:
    out = []
    for page in range(1, pages + 1):
        try:
            html = fetch(keyword, page, proxy=proxy)
        except Exception as e:  # noqa: BLE001
            print(f"    [!] ошибка загрузки b2b-center ({keyword}, стр.{page}): {e}")
            break
        cards = parse_cards(html)
        out.extend(cards)
        if not cards:
            break
        time.sleep(pause)
    return out


def debug_dump(keyword: str = "плиты дорожные", path: str = "debug_b2b.html", proxy: str | None = None):
    """Сохраняет сырой HTML первой страницы — чтобы свериться с реальными селекторами."""
    html = fetch(keyword, 1, proxy=proxy)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Сохранил {path} ({len(html)} символов). Открой и проверь селекторы карточек.")


if __name__ == "__main__":
    debug_dump()
