"""
Загрузка данных о застройщиках с erzrf.ru (ЕРЗ.РФ — «Единый ресурс
застройщиков», рейтинговое агентство, публикует рейтинг застройщиков и
базу новостроек по регионам).

Зачем этот источник: застройщик, который прямо сейчас строит жильё —
почти гарантированный потребитель ЖБИ (плиты, сваи, кольца и т.п.),
причём это не тендер, который ещё нужно выиграть, а прямой контакт
с компанией, ведущей стройку.

Откалибровано по реальному HTML (снят через .github/workflows/
erz-rts-leadgen.yml, 2026-07-13). Сайт — Angular-приложение, но с
server-side рендерингом (Angular Universal): реальные данные видны в
обычном HTML без Playwright/браузера.

Реальный адрес реестра — "/zastroyschiki" (без "h" после "s" — не так,
как логично было бы транслитерировать «застройщики»; найден в меню
главной страницы). Внутри — не плоский список, а рейтинг: карточки
`li.developer` внутри `.dev-table__title` (название + ссылка на профиль
застройщика), `.dev-table__percent` (доля в регионе), `.dev-table__
volume-min` (объём стройки в регионе, м²), `.dev-table__volume` без
`-min` (всего проектов в ЕРЗ), `.dev-table__year` (год основания).

ИЗВЕСТНОЕ ОГРАНИЧЕНИЕ: фильтр по региону на сайте требует ДВА параметра
одновременно — `region` (транслит-слаг, например "moskva") И `regionKey`
(числовой ID региона, например 143443001 для Москвы) — без регистрации
числового кода фильтр молча игнорируется, и сайт отдаёт вид по
умолчанию (Москва). Числовые regionKey других регионов на сайте нигде
не даны текстом (это внутренний ID из БД ЕРЗ) — узнать их без захода в
реальный браузер с devtools не получилось. Поэтому пока collect_erz()
в main.py делает ОДИН запрос (без фильтра по региону) и возвращает
топ-рейтинг застройщиков по всей РФ — это уже реальные, живые лиды
(крупные девелоперы, которые почти наверняка строят и в наших целевых
регионах тоже), просто без разбивки по региону. Если понадобится
именно региональная выборка — нужно вручную посмотреть в браузере,
какой regionKey соответствует каждому региону (открыть /zastroyschiki,
выбрать регион в фильтре на сайте, скопировать regionKey из адресной
строки) и передать эти пары в build_url().
"""

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://erzrf.ru"
LIST_URL = BASE + "/zastroyschiki"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}

_RANK_RE = re.compile(r"№\s*\d+\s*в\s*РФ")
_PERCENT_RE = re.compile(r"\d+[.,]?\d*\s*%")
_VOLUME_RE = re.compile(r"[\d\s]+м²")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_REGION_RE = re.compile(r"[?&]region=([^&]+)")


def fetch(url: str, timeout: int = 30, proxy: str | None = None) -> str:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(url, headers=HEADERS, timeout=timeout, proxies=proxies)
    r.raise_for_status()
    return r.text


def _txt(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def parse_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for li in soup.select("li.developer"):
        title_div = li.select_one(".dev-table__title")
        if not title_div:
            continue
        name_a = title_div.select_one('a[href*="/zastroyschiki/brand/"]')
        if not name_a:
            continue
        developer = _txt(name_a)
        link = urljoin(BASE, name_a["href"])

        rank_m = _RANK_RE.search(_txt(title_div))
        rank = rank_m.group(0) if rank_m else ""

        percent_div = li.select_one(".dev-table__percent")
        percent_m = _PERCENT_RE.search(_txt(percent_div)) if percent_div else None
        share_percent = percent_m.group(0) if percent_m else ""

        volume_div = li.select_one(".dev-table__volume-min")
        volume_m = _VOLUME_RE.search(_txt(volume_div)) if volume_div else None
        volume_building = volume_m.group(0).strip() if volume_m else ""

        total_div = li.select_one(".dev-table__volume:not(.dev-table__volume-min)")
        total_a = total_div.select_one('a[href*="/novostroyki"]') if total_div else None
        total_projects = _txt(total_a)

        year_div = li.select_one(".dev-table__year")
        year_m = _YEAR_RE.search(_txt(year_div)) if year_div else None
        founded_year = year_m.group(0) if year_m else ""

        region_m = _REGION_RE.search(link)
        region = region_m.group(1) if region_m else ""

        if not developer:
            continue
        results.append(
            {
                "developer": developer,
                "rank": rank,
                "region": region,
                "share_percent": share_percent,
                "volume_building": volume_building,
                "total_projects": total_projects,
                "founded_year": founded_year,
                "link": link,
            }
        )
    return results


def search(pages: int = 1, pause: float = 1.0, proxy: str | None = None) -> list[dict]:
    """Собирает рейтинг застройщиков. Пагинации на сайте не нашли —
    страница отдаёт фиксированный топ-список за один запрос, поэтому
    `pages` пока игнорируется (оставлен для совместимости сигнатуры)."""
    try:
        html = fetch(LIST_URL, proxy=proxy)
    except Exception as e:  # noqa: BLE001
        print(f"    [!] ошибка загрузки ЕРЗ.РФ: {e}")
        return []
    return parse_cards(html)


def debug_dump(
    path_home: str = "debug_erz_home.html",
    path_list_plain: str = "debug_erz_list_plain.html",
    proxy: str | None = None,
):
    """Снимает HTML главной и списка застройщиков — для калибровки."""
    home_html = fetch(BASE + "/", proxy=proxy)
    with open(path_home, "w", encoding="utf-8") as f:
        f.write(home_html)
    print(f"Сохранил {path_home} ({len(home_html)} символов).")

    list_html = fetch(LIST_URL, proxy=proxy)
    with open(path_list_plain, "w", encoding="utf-8") as f:
        f.write(list_html)
    print(f"Сохранил {path_list_plain} ({len(list_html)} символов). "
          f"Найдено карточек: {len(parse_cards(list_html))}")


if __name__ == "__main__":
    debug_dump()
