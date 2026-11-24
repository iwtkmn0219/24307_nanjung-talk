from datetime import date

from nanjung.today import build_today_map, pick


def test_today_map_has_366_keys_including_0229():
    m = build_today_map([("1592-04-13", date(1592, 5, 23)), ("1597-09-16", date(1597, 10, 26))])
    assert len(m) == 366 and m["02-29"]["exact"] is False
    assert m["05-23"] == {"ids": ["1592-04-13"], "exact": True}
    assert m["10-26"] == {"ids": ["1597-09-16"], "exact": True}


def test_every_key_points_to_an_existing_id():
    rows = [("1592-04-13", date(1592, 5, 23)), ("1597-09-16", date(1597, 10, 26))]
    m = build_today_map(rows)
    ids = {r[0] for r in rows}
    assert all(v["ids"] and set(v["ids"]) <= ids for v in m.values())


def test_today_map_wraps_year_end():
    m = build_today_map([("1595-11-21", date(1595, 12, 31))])
    assert m["01-01"] == {"ids": ["1595-11-21"], "exact": False}


def test_missing_day_uses_nearest_and_earlier_on_tie():
    m = build_today_map([("a", date(1593, 3, 1)), ("b", date(1593, 3, 5)), ("c", date(1594, 2, 28))])
    assert m["03-02"]["ids"] == ["a"]
    assert m["03-04"]["ids"] == ["b"]
    assert m["03-03"]["ids"] == ["a"]          # 거리 2로 같음 → 앞 날짜
    assert m["02-29"] == {"ids": ["c"], "exact": False}  # 02-28과 03-01 동률 → 앞 날짜


def test_same_month_day_ids_sorted_by_date():
    m = build_today_map([("1597-x", date(1597, 6, 1)), ("1593-x", date(1593, 6, 1))])
    assert m["06-01"]["ids"] == ["1593-x", "1597-x"]


def test_pick_rotates_by_year():
    assert pick({"ids": ["a", "b"]}, 2026) == "a"
    assert pick({"ids": ["a", "b"]}, 2027) == "b"
