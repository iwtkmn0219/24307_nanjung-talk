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

ENRICH_FIELDS = ("translation", "emotion", "intro", "questions")
_conn = None


def s3_client():
    import boto3
    return boto3.client("s3")


def today_table():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["TODAY_TABLE"])


def get_conn():
    global _conn
    if _conn is None:
        _conn = db.connect()
    return _conn


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
        if c is not None:
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


def lambda_handler(event, context):
    action = event.get("action")
    if action == "init_schema":
        db.init_schema(get_conn())
        return {"ok": True}
    if action == "ingest":
        return _ingest(event["key"])
    if action == "build_today_map":
        return _build_today_map()
    raise ValueError(f"알 수 없는 action: {action!r}")
