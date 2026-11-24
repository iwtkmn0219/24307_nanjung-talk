"""'오늘의 일기' 매핑: 366개 월·일 키 → 일기 id 목록."""
from __future__ import annotations

from datetime import date, timedelta

LEAP_YEAR = 2024
DAYS = 366
KEYS = [(date(LEAP_YEAR, 1, 1) + timedelta(days=i)).strftime("%m-%d") for i in range(DAYS)]


def build_today_map(rows: list[tuple[str, date]]) -> dict[str, dict]:
    by_md: dict[str, list[tuple[date, str]]] = {}
    for entry_id, d in rows:
        by_md.setdefault(d.strftime("%m-%d"), []).append((d, entry_id))
    if not by_md:
        raise ValueError("일기가 하나도 없다")
    ids = {md: [i for _, i in sorted(v)] for md, v in by_md.items()}
    out = {}
    for idx, md in enumerate(KEYS):
        if md in ids:
            out[md] = {"ids": ids[md], "exact": True}
            continue
        for dist in range(1, DAYS):
            before, after = KEYS[(idx - dist) % DAYS], KEYS[(idx + dist) % DAYS]
            if before in ids:  # 거리가 같으면 앞 날짜
                out[md] = {"ids": ids[before], "exact": False}
                break
            if after in ids:
                out[md] = {"ids": ids[after], "exact": False}
                break
    return out


def pick(item: dict, year: int) -> str:
    return item["ids"][year % len(item["ids"])]
