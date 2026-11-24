import json
from pathlib import Path

import pytest

from nanjung.models import MonthRef
from nanjung.parse import parse_month_page, parse_title


@pytest.mark.parametrize("title,expected", [
    ("壬辰正月", ("壬辰", 1592, 1, False)),
    ("[丙申]閏八月", ("丙申", 1596, 8, True)),
    ("[乙未]十二月", ("乙未", 1595, 12, False)),
])
def test_parse_title(title, expected):
    assert parse_title(title) == expected


def page(*paras):
    body = "".join(f'<div class="xsl_para">{p}</div>' for p in paras)
    return f'<div class="text_body ori">{body}</div>'


def test_heads_and_variants():
    html = page('初一日庚寅。陰。曉行望<span style="display:inline-block;width:0.8em"></span>闕禮。',
                '十一日乙酉冬至。曉。行望闕禮。',
                '二十四日干支。缺晴。申時。發船',
                '初八日。干支缺詣都督府設慰宴。',
                '初昏發船之際。故停行。')
    es = parse_month_page(html, MonthRef("X", "[甲午]三月"))
    assert [(e.lunar_day, e.day_ganji) for e in es] == [(1, "庚寅"), (11, "乙酉"), (24, None), (8, None)]
    assert es[0].original == "初一日庚寅。陰。曉行望闕禮。"
    assert es[-1].original.endswith("初八日。干支缺詣都督府設慰宴。初昏發船之際。故停行。")
    e = es[0]
    assert (e.source_id, e.ganji_year, e.lunar_year, e.lunar_month, e.is_leap) == ("X", "甲午", 1594, 3, False)


def test_whitespace_removed_and_other_divs_ignored():
    html = ('<div class="text_body trans"><div class="xsl_para">十三日壬寅。번역</div></div>'
            + page('十三日壬寅。 晴。\n出東軒。'))
    es = parse_month_page(html, MonthRef("Y", "壬辰四月"))
    assert len(es) == 1 and es[0].original == "十三日壬寅。晴。出東軒。"


def test_three_char_days():
    es = parse_month_page(page("二十九日甲子。晴。", "三十日乙丑。雨。", "初十日丙寅。", "二十日丁卯。", "十五日戊辰。"),
                          MonthRef("Z", "壬辰正月"))
    assert [e.lunar_day for e in es] == [29, 30, 10, 20, 15]


RAW = Path("data/raw")


@pytest.mark.skipif(not (RAW / "index.json").exists(), reason="원문 미수집")
def test_full_corpus_count():
    refs = [MonthRef(**r) for r in json.loads((RAW / "index.json").read_text(encoding="utf-8"))]
    assert len(refs) == 61
    total = sum(len(parse_month_page((RAW / f"{r.data_id}.html").read_text(encoding="utf-8"), r))
                for r in refs)
    assert total == 1593
