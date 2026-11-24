"""적재 Lambda: init_schema / ingest / build_today_map."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, replace

from botocore.exceptions import ClientError

from .. import db
from ..bedrock import embed
from ..dates import assign_dates
from ..enrich import enrich
from ..models import MonthRef
from ..parse import parse_month_page
from ..today import build_today_map
from .common import shared_conn

ENRICH_FIELDS = ("translation", "emotion", "intro", "questions")


def s3_client():
    import boto3
    return boto3.client("s3")


def today_table():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["TODAY_TABLE"])


def get_conn():
    return shared_conn()


def _read(s3, key: str) -> str | None:
    try:
        obj = s3.get_object(Bucket=os.environ["DATA_BUCKET"], Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return None
        raise
    return obj["Body"].read().decode("utf-8")


def _ingest(key: str) -> dict:
    if not (key.startswith("raw/") and key.endswith(".html")):
        raise ValueError(f"raw/<data_id>.html 형식이 아님: {key!r}")
    data_id = key[len("raw/"):-len(".html")]
    s3 = s3_client()
    index = {r["data_id"]: r["title"] for r in json.loads(_read(s3, "raw/index.json") or "[]")}
    if data_id not in index:
        raise ValueError(f"raw/index.json에 없는 문서: {data_id}")
    html = _read(s3, key)
    if html is None:
        raise ValueError(f"S3에 없음: {key}")
    entries = assign_dates(parse_month_page(html, MonthRef(data_id, index[data_id])))

    cache_key = f"processed/{data_id}.json"
    cached = {d["id"]: d for d in json.loads(_read(s3, cache_key) or "[]")}
    done, changed = [], False

    def save():
        body = json.dumps([asdict(e) for e in done], ensure_ascii=False, default=str, indent=1)
        s3.put_object(Bucket=os.environ["DATA_BUCKET"], Key=cache_key, Body=body.encode("utf-8"),
                      ContentType="application/json")

    for e in entries:
        c = cached.get(e.id)
        if c is not None and c.get("original") == e.original:  # 원문이 바뀐 날은 다시 번역
            done.append(replace(e, **{f: c[f] for f in ENRICH_FIELDS}))
            continue
        try:
            done.append(enrich(e))
        except Exception:
            if changed:
                save()  # 이미 번역한 항목은 다음 실행에서 다시 번역하지 않도록 남긴다
            raise
        changed = True
    if changed:
        save()

    conn = get_conn()
    for e in done:
        db.upsert(conn, e, embed(e.translation))
    return {"count": len(done)}


def _build_today_map() -> dict:
    m = build_today_map(db.all_dates(get_conn()))
    with today_table().batch_writer() as w:
        for md, v in m.items():
            w.put_item(Item={"md": md, "ids": v["ids"], "exact": v["exact"]})
    return {"count": len(m)}


def _diag(message: str) -> dict:
    """운영 점검용: 질문 하나의 날짜 해석과 날짜 검색·일반 검색 상위 유사도를 돌려준다."""
    from ..date_resolver import resolve
    conn = get_conn()
    date_ids = resolve(message, [], lambda i, d: db.neighbor(conn, i, d))
    qvec = embed(message)
    fmt = lambda hits: [[h.entry.id, round(h.similarity, 4)] for h in hits]  # noqa: E731
    return {"date_ids": date_ids,
            "date_hits": fmt(db.search(conn, qvec, k=5, date_ids=date_ids)) if date_ids else [],
            "general_hits": fmt(db.search(conn, qvec, k=5))}


def _eval() -> dict:
    """SIM_THRESHOLD 튜닝: 평가 질문마다 일기 전체에서 최고 유사도를 구하고 기준값별 정확도를 계산한다."""
    from .. import evaluation as ev
    questions = json.loads(ev.QUESTIONS_PATH.read_text(encoding="utf-8"))
    conn = get_conn()
    rows = []
    for q in questions:
        hits = db.search(conn, embed(q["q"]), k=1)
        top = hits[0] if hits else None
        rows.append({"q": q["q"], "expect": q["expect"], "sim": round(top.similarity, 4) if top else 0.0,
                     "top_id": top.entry.id if top else None})
    triples = [(r["q"], r["expect"], r["sim"]) for r in rows]
    table = ev.sweep(triples)
    return {"rows": rows, "table": table, "best": ev.best(table), "separation": ev.separation(triples),
            "in_dist": ev.distribution([r["sim"] for r in rows if r["expect"] == "in"]),
            "out_dist": ev.distribution([r["sim"] for r in rows if r["expect"] == "out"])}


def lambda_handler(event, context):
    action = event.get("action")
    if action == "init_schema":
        db.init_schema(get_conn())
        return {"ok": True}
    if action == "ingest":
        return _ingest(event["key"])
    if action == "build_today_map":
        return _build_today_map()
    if action == "stats":
        return db.stats(get_conn())
    if action == "diag":
        return _diag(event["message"])
    if action == "eval":
        return _eval()
    raise ValueError(f"알 수 없는 action: {action!r}")
