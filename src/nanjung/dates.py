"""음력 → 양력 변환과 일기 간지를 이용한 보정."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import date, timedelta

from korean_lunar_calendar import KoreanLunarCalendar

from .models import DiaryEntry, RawEntry

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
GANJI = [STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)]
YEAR_KO = {"壬辰": "임진", "癸巳": "계사", "甲午": "갑오", "乙未": "을미",
           "丙申": "병신", "丁酉": "정유", "戊戌": "무술"}
SEARCH_ORDER = (0, 1, -1, 2, -2)


def ganji_of(d: date) -> str:
    return GANJI[(d.toordinal() + 14) % 60]


def _library_date(y: int, m: int, d: int, is_leap: bool) -> date:
    c = KoreanLunarCalendar()
    if not c.setLunarDate(y, m, d, is_leap):
        if d == 30:  # 일기의 달은 30일인데 라이브러리의 달은 29일인 경우 → 29일 + 1
            return _library_date(y, m, 29, is_leap) + timedelta(days=1)
        raise ValueError(f"변환할 수 없는 음력 날짜: {y}-{'L' if is_leap else ''}{m}-{d}")
    return date.fromisoformat(c.SolarIsoFormat())


def _match_delta(base: date, day_ganji: str) -> int | None:
    for delta in SEARCH_ORDER:
        if ganji_of(base + timedelta(days=delta)) == day_ganji:
            return delta
    return None


def to_solar(y: int, m: int, d: int, is_leap: bool, day_ganji: str | None) -> tuple[date, bool]:
    base = _library_date(y, m, d, is_leap)
    if day_ganji is None:
        return base, False
    delta = _match_delta(base, day_ganji)
    if delta is None:
        return base, True
    return base + timedelta(days=delta), False


def entry_id(y: int, m: int, d: int, is_leap: bool) -> str:
    return f"{y}-{'L' if is_leap else ''}{m:02d}-{d:02d}"


def label(e: RawEntry) -> str:
    leap = "윤" if e.is_leap else ""
    return f"{YEAR_KO[e.ganji_year]}년({e.lunar_year}) {leap}{e.lunar_month}월 {e.lunar_day}일"


def assign_dates(entries: list[RawEntry]) -> list[DiaryEntry]:
    month_key = lambda e: (e.lunar_year, e.lunar_month, e.is_leap)  # noqa: E731
    deltas: dict[tuple, Counter] = {}
    for e in entries:
        if e.day_ganji is None:
            continue
        delta = _match_delta(_library_date(e.lunar_year, e.lunar_month, e.lunar_day, e.is_leap),
                             e.day_ganji)
        if delta is not None:
            deltas.setdefault(month_key(e), Counter())[delta] += 1

    out = []
    for e in entries:
        if e.day_ganji is not None:
            solar, mismatch = to_solar(e.lunar_year, e.lunar_month, e.lunar_day, e.is_leap, e.day_ganji)
        else:
            counts = deltas.get(month_key(e))
            # 최빈값, 동률이면 0에 가까운 쪽
            delta = min(counts.items(), key=lambda kv: (-kv[1], abs(kv[0])))[0] if counts else 0
            solar = _library_date(e.lunar_year, e.lunar_month, e.lunar_day, e.is_leap) + timedelta(days=delta)
            mismatch = False
        de = DiaryEntry(**asdict(e),
                        id=entry_id(e.lunar_year, e.lunar_month, e.lunar_day, e.is_leap),
                        solar_date=solar, ganji_mismatch=mismatch)
        de.label = label(de)
        out.append(de)
    return out
