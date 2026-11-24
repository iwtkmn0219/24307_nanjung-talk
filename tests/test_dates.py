from datetime import date

import pytest

from nanjung.dates import assign_dates, entry_id, ganji_of, label, to_solar
from nanjung.models import RawEntry


@pytest.mark.parametrize("args,expected", [
    ((1592, 4, 13, False, "壬寅"), (date(1592, 5, 23), False)),
    ((1597, 9, 16, False, "甲辰"), (date(1597, 10, 26), False)),   # 명량, +1 보정
    ((1596, 8, 1, True, "乙丑"), (date(1596, 9, 22), False)),      # 윤8월
    ((1592, 5, 1, False, "庚午"), (date(1592, 6, 10), True)),      # 전서본 간지 오류
    ((1592, 4, 13, False, None), (date(1592, 5, 23), False)),      # 간지 없음 → 라이브러리 값
])
def test_to_solar(args, expected):
    assert to_solar(*args) == expected


def test_ganji_of():
    assert ganji_of(date(1592, 5, 23)) == "壬寅"


def raw(y, m, d, g, leap=False, gy="丁酉"):
    return RawEntry("S", gy, y, m, leap, d, g, f"{d}日")


def test_missing_ganji_uses_month_delta():
    out = assign_dates([raw(1597, 9, 15, "癸卯"), raw(1597, 9, 17, None)])
    assert [e.solar_date for e in out] == [date(1597, 10, 25), date(1597, 10, 27)]
    assert not any(e.ganji_mismatch for e in out)


def test_missing_ganji_without_month_reference_uses_zero():
    (e,) = assign_dates([raw(1597, 9, 17, None)])
    assert e.solar_date == date(1597, 10, 26) and e.ganji_mismatch is False


def test_mismatched_entries_do_not_set_month_delta():
    out = assign_dates([raw(1592, 5, 1, "庚午", gy="壬辰"), raw(1592, 5, 2, None, gy="壬辰")])
    assert out[0].ganji_mismatch is True
    assert out[1].solar_date == date(1592, 6, 11)


def test_assign_dates_fills_id_label_and_keeps_raw_fields():
    (e,) = assign_dates([RawEntry("SRC", "丙申", 1596, 8, True, 1, "乙丑", "初一日乙丑。")])
    assert e.id == "1596-L08-01" and e.label == "병신년(1596) 윤8월 1일"
    assert e.source_id == "SRC" and e.original == "初一日乙丑。" and e.day_ganji == "乙丑"


def test_label_and_id():
    assert entry_id(1596, 8, 1, True) == "1596-L08-01"
    assert entry_id(1592, 4, 13, False) == "1592-04-13"
    (e,) = assign_dates([raw(1592, 4, 13, "壬寅", gy="壬辰")])
    assert label(e) == "임진년(1592) 4월 13일"
