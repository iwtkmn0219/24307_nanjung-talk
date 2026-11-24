"""질문 속 날짜·사건·'다음 날' 표현을 일기 id로 바꾼다."""
from __future__ import annotations

import re
from typing import Callable

from .dates import entry_id

NeighborFn = Callable[[str, int], "str | None"]

NEXT_RE = re.compile(r"다음\s*날|다음날|이튿날")
PREV_RE = re.compile(r"전날|그\s*전날|前날")
GANJI_YEARS = {"임진": 1592, "계사": 1593, "갑오": 1594, "을미": 1595, "병신": 1596, "정유": 1597, "무술": 1598}
GANJI_DATE_RE = re.compile(r"(임진|계사|갑오|을미|병신|정유|무술)년\s*(윤)?(\d{1,2})월\s*(\d{1,2})일")
YEAR_DATE_RE = re.compile(r"(159[2-8])년\s*(윤)?(\d{1,2})월\s*(\d{1,2})일")

# '면'·'마지막'은 흔한 글자라 아들 이름(앞뒤가 한글이 아닌 독립된 '면' + 조사)과 구체 표현만 인정한다.
MYEON_RE = re.compile(r"(?:^|[^가-힣])면(?:이|의|은|을|과|이가)?(?=[^가-힣]|$)")
LAST_RE = re.compile(r"마지막\s*(?:일기|날|기록|전투|싸움|해전)")
DEATH_WORDS = ("전사", "죽", "잃")

# 옥에 갇혔다 풀려난 일(정유 4/1 출옥)을 가리키는 말. "옥" 한 글자는 옥수수 등과 겹쳐 쓰지 않는다.
PRISON_WORDS = ("백의종군", "출옥", "감옥", "유배", "귀양", "투옥", "옥살이", "옥에 갇", "파직", "하옥", "압송")

# (판정 함수, 일기 id). 위에서부터 먼저 맞는 것을 쓴다.
EVENTS: list[tuple[Callable[[str], bool], str]] = [
    (lambda m: "명량" in m, "1597-09-16"),
    (lambda m: "임진왜란" in m or "왜란 터진" in m, "1592-04-13"),
    (lambda m: ("어머니" in m or "어머님" in m) and any(w in m for w in ("돌아가", "별세", "부고")), "1597-04-13"),
    (lambda m: (MYEON_RE.search(m) or "아들" in m) and any(w in m for w in DEATH_WORDS), "1597-10-14"),
    (lambda m: any(w in m for w in PRISON_WORDS), "1597-04-01"),
    (lambda m: "노량" in m or bool(LAST_RE.search(m)), "1598-11-17"),
]


def _direction(message: str) -> int:
    if NEXT_RE.search(message):
        return 1
    if PREV_RE.search(message):
        return -1
    return 0


def _event(message: str) -> str | None:
    for matches, eid in EVENTS:
        if matches(message):
            return eid
    return None


def _explicit(message: str) -> str | None:
    m = GANJI_DATE_RE.search(message)
    year = GANJI_YEARS[m[1]] if m else None
    if not m:
        m = YEAR_DATE_RE.search(message)
        year = int(m[1]) if m else None
    if not m:
        return None
    month, day = int(m[3]), int(m[4])
    if not (1 <= month <= 12 and 1 <= day <= 30):
        return None
    return entry_id(year, month, day, bool(m[2]))


def resolve(message: str, last_source_ids: list[str], neighbor_fn: NeighborFn) -> list[str] | None:
    direction = _direction(message)
    target = _explicit(message) or _event(message)  # 명시 날짜가 사건 사전보다 우선
    if direction:
        anchor = target or (last_source_ids[0] if last_source_ids else None)
        if anchor is None:
            return None
        nid = neighbor_fn(anchor, direction)
        return [nid] if nid else None
    return [target] if target else None
