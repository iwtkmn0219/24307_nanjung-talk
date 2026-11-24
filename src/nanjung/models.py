"""모든 Task가 공유하는 데이터클래스와 상수."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

EMOTIONS = ("일상", "유머·불평", "분노", "비통")
SOURCE_NOTE = "원문: 『이충무공전서』 난중일기 / 번역: AI"


@dataclass(frozen=True)
class MonthRef:
    data_id: str
    title: str


@dataclass
class RawEntry:
    source_id: str
    ganji_year: str
    lunar_year: int
    lunar_month: int
    is_leap: bool
    lunar_day: int
    day_ganji: str | None
    original: str


@dataclass
class DiaryEntry(RawEntry):
    id: str = ""
    solar_date: date | None = None
    ganji_mismatch: bool = False
    label: str = ""
    translation: str = ""
    emotion: str = ""
    intro: str = ""
    questions: list[str] = field(default_factory=list)


@dataclass
class Hit:
    entry: DiaryEntry
    similarity: float
