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

# 옥에 갇혔다 풀려난 일(정유 4/1 출옥). "옥" 한 글자는 옥수수 등과 겹쳐 쓰지 않는다.
PRISON_STRONG = ("백의종군", "출옥", "감옥", "유배", "귀양", "옥살이")   # 이 일을 가리키는 말 → 출옥일 기준으로 쓸 수 있다
PRISON_ENTRY = ("투옥", "옥에 갇", "하옥")                           # 입옥 시점 → 같은 날로는 가되 '다음 날' 기준으로는 쓰지 않는다
PRISON_AMBIGUOUS = ("압송", "파직")                                   # 여러 사건에 쓰이는 말 → 장군 본인 이야기일 때만
SELF_RE = re.compile(r"셨|께서|장군|당신|본인|나으리")
NEGATION_RE = re.compile(r"아니라|아니고|말고|빼고|제외")


def _prison(m: str) -> bool | None:
    """일치하면 '출옥일을 상대 표현의 기준으로 써도 되는지'를, 일치하지 않으면 None을 돌려준다."""
    if any(w in m for w in PRISON_STRONG):
        return True
    if any(w in m for w in PRISON_ENTRY):
        return False
    if any(w in m for w in PRISON_AMBIGUOUS) and SELF_RE.search(m):
        return False
    return None


# (일기 id, 판정 함수 → 일치하면 '상대 표현 기준으로 써도 되는지', 아니면 None)
EVENTS: list[tuple[str, Callable[[str], "bool | None"]]] = [
    ("1597-09-16", lambda m: True if "명량" in m else None),
    ("1592-04-13", lambda m: True if "임진왜란" in m or "왜란 터진" in m else None),
    ("1597-04-13", lambda m: True if ("어머니" in m or "어머님" in m) and any(w in m for w in ("돌아가", "별세", "부고")) else None),
    ("1597-10-14", lambda m: True if (MYEON_RE.search(m) or "아들" in m) and any(w in m for w in DEATH_WORDS) else None),
    ("1597-04-01", _prison),
    ("1598-11-17", lambda m: True if "노량" in m or LAST_RE.search(m) else None),
]


def _direction(message: str) -> int:
    if NEXT_RE.search(message):
        return 1
    if PREV_RE.search(message):
        return -1
    return 0


def _events(message: str) -> list[tuple[str, bool]]:
    """일치한 사건 (id, 상대 표현 기준 가능 여부). 부정("유배 말고…")이 있으면 사건은 쓰지 않는다."""
    if NEGATION_RE.search(message):
        return []
    return [(eid, ok) for eid, fn in EVENTS if (ok := fn(message)) is not None]


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
    explicit = _explicit(message)                     # 명시 날짜가 사건 사전보다 우선
    events = _events(message)
    # 서로 다른 사건이 둘 이상이면 어느 날인지 알 수 없다 → 날짜 조건 없이 일반 검색으로 넘긴다
    event, anchorable = events[0] if len({e for e, _ in events}) == 1 else (None, False)
    if direction:
        anchor = explicit or (event if anchorable else None) or (last_source_ids[0] if last_source_ids else None)
        if anchor is None:
            return None
        nid = neighbor_fn(anchor, direction)
        return [nid] if nid else None
    target = explicit or event
    return [target] if target else None
