"""월 문서 HTML → 하루 단위 RawEntry."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .models import MonthRef, RawEntry

YEARS = {"壬辰": 1592, "癸巳": 1593, "甲午": 1594, "乙未": 1595,
         "丙申": 1596, "丁酉": 1597, "戊戌": 1598}
DIGITS = {c: i for i, c in enumerate("一二三四五六七八九", start=1)}
MONTHS = {"正": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
          "九": 9, "十": 10, "十一": 11, "十二": 12}

TITLE_RE = re.compile(r"^\[?(?P<year>[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])\]?"
                      r"(?P<leap>閏)?(?P<month>正|十[一二]?|[一二三四五六七八九])月$")
HEAD_RE = re.compile(
    r"^(初[一二三四五六七八九十]|二十[一二三四五六七八九]?|十[一二三四五六七八九]?|三十)日。?"
    r"(?:([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])|干支。?缺)")
WS_RE = re.compile(r"\s+")


def parse_title(title: str) -> tuple[str, int, int, bool]:
    m = TITLE_RE.match(WS_RE.sub("", title))
    if not m:
        raise ValueError(f"알 수 없는 월 제목: {title!r}")
    gy = m["year"]
    return gy, YEARS[gy], MONTHS[m["month"]], bool(m["leap"])


def day_number(s: str) -> int:
    if s.startswith("初"):
        return 10 if s[1] == "十" else DIGITS[s[1]]
    if s.startswith("三十"):
        return 30
    if s.startswith("二十"):
        return 20 + (DIGITS[s[2]] if len(s) > 2 else 0)
    return 10 + (DIGITS[s[1]] if len(s) > 1 else 0)  # 十, 十X


def _para_text(div) -> str:
    for span in div.find_all("span", style=re.compile(r"display\s*:\s*inline-block")):
        span.decompose()
    return WS_RE.sub("", div.get_text())


def parse_month_page(html: str, ref: MonthRef) -> list[RawEntry]:
    gy, year, month, leap = parse_title(ref.title)
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("div.text_body.ori")
    if body is None:
        return []
    entries: list[RawEntry] = []
    for div in body.select("div.xsl_para"):
        text = _para_text(div)
        if not text:
            continue
        m = HEAD_RE.match(text)
        if m:
            entries.append(RawEntry(ref.data_id, gy, year, month, leap,
                                    day_number(m[1]), m[2], text))
        elif entries:
            entries[-1].original += text
    return entries
