"""한국고전종합DB에서 난중일기(이충무공전서본) 월 문서 원문 HTML을 받는다.

로컬 PC 전용. robots.txt가 Disallow: / 이므로 1회만, 요청 간격 1초 이상으로 실행한다.
연락처는 환경변수 NANJUNG_CONTACT_EMAIL 로 넣는다(미설정 시 실행하지 않는다).
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from nanjung.models import MonthRef  # noqa: E402

BASE = "https://db.itkc.or.kr/dir"
TREE_URL = (BASE + "/treeAjax?grpId=&itemId=MO&gubun=book&depth=4&cate1=Z&cate2="
            "&dataGubun=문체&dataId={vol_id}")
NODE_URL = (BASE + "/node?grpId=&itemId=MO&gubun=book&depth=5&cate1=Z&cate2="
            "&dataGubun=최종정보&dataId={data_id}")
VOL_IDS = ["ITKC_MO_0232A_0080_010", "ITKC_MO_0232A_0090_010",
           "ITKC_MO_0232A_0100_010", "ITKC_MO_0232A_0110_010"]
CONTACT_ENV = "NANJUNG_CONTACT_EMAIL"


def parse_month_list(tree_html: str) -> list[MonthRef]:
    soup = BeautifulSoup(tree_html, "html.parser")
    refs = []
    for li in soup.find_all("li"):
        data_id = li.get("data-dataid")  # html.parser는 속성 이름을 소문자로 바꾼다
        span = li.find("span")
        if not data_id or span is None:
            continue
        refs.append(MonthRef(data_id, span.get("title") or span.get_text(strip=True)))
    return refs


def user_agent() -> str:
    contact = os.environ.get(CONTACT_ENV, "").strip()
    if not contact:
        raise SystemExit(f"{CONTACT_ENV} 환경변수에 연락처 메일을 넣어야 실행할 수 있다.")
    return f"nanjungtalk-collector/1.0 (one-time research crawl; contact: {contact})"


def _write_atomic(path: Path, text: str) -> None:
    """임시 파일에 다 쓴 뒤 이름을 바꾼다. 중단돼도 일부만 쓴 파일이 path에 남지 않는다."""
    tmp = path.with_name(path.name + ".part")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def collect(out_dir: Path, delay_s: float = 1.0, session=None) -> list[MonthRef]:
    import requests

    delay_s = max(delay_s, 1.0)
    s = session or requests.Session()
    s.headers["User-Agent"] = user_agent()
    raw = Path(out_dir) / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    def get(url: str) -> str:
        r = s.get(url, timeout=30)
        r.raise_for_status()
        time.sleep(delay_s)
        return r.text

    refs: list[MonthRef] = []
    for vol in VOL_IDS:
        refs.extend(parse_month_list(get(TREE_URL.format(vol_id=vol))))
    for ref in refs:
        path = raw / f"{ref.data_id}.html"
        if path.exists():  # 이미 받은 문서는 다시 요청하지 않는다
            continue
        _write_atomic(path, get(NODE_URL.format(data_id=ref.data_id)))
    _write_atomic(raw / "index.json", json.dumps([asdict(r) for r in refs], ensure_ascii=False, indent=1))
    return refs


if __name__ == "__main__":
    out = collect(Path("data"))
    print(f"{len(out)} month documents")
