from collect import parse_month_list
from nanjung.models import MonthRef

TREE = """<li data-dataId='ITKC_MO_0232A_0080_010_0010' data-url='...' data-lvl="1"><span title='壬辰正月'>壬辰正月</span></li>
<li data-dataId='ITKC_MO_0232A_0080_010_0020' data-url='...' data-lvl="1"><span title='[壬辰]二月'>[壬辰]二月</span></li>"""


def test_parse_month_list():
    refs = parse_month_list(TREE)
    assert refs == [MonthRef("ITKC_MO_0232A_0080_010_0010", "壬辰正月"),
                    MonthRef("ITKC_MO_0232A_0080_010_0020", "[壬辰]二月")]


import json
import pytest
import collect as collect_mod


class FakeResp:
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class FakeSession:
    def __init__(self):
        self.headers, self.urls = {}, []

    def get(self, url, timeout):
        self.urls.append(url)
        return FakeResp(TREE if "treeAjax" in url else "<html>본문</html>")


def test_collect_requires_contact_email(monkeypatch, tmp_path):
    monkeypatch.delenv("NANJUNG_CONTACT_EMAIL", raising=False)
    with pytest.raises(SystemExit):
        collect_mod.collect(tmp_path, session=FakeSession())


def test_collect_writes_html_and_index_with_delay(monkeypatch, tmp_path):
    monkeypatch.setenv("NANJUNG_CONTACT_EMAIL", "x@example.com")
    sleeps = []
    monkeypatch.setattr(collect_mod.time, "sleep", sleeps.append)
    s = FakeSession()
    refs = collect_mod.collect(tmp_path, delay_s=0.1, session=s)
    assert len(refs) == 8  # 권 4개 × 가짜 트리 2개
    assert "x@example.com" in s.headers["User-Agent"]
    assert all(d >= 1.0 for d in sleeps) and len(sleeps) == len(s.urls)
    idx = json.loads((tmp_path / "raw" / "index.json").read_text(encoding="utf-8"))
    assert len(idx) == 8
    assert (tmp_path / "raw" / "ITKC_MO_0232A_0080_010_0010.html").exists()
