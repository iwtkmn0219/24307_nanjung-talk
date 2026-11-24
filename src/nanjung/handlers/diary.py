"""GET /diary?md=MM-DD"""
from __future__ import annotations

import os
from datetime import datetime

from .. import db
from ..models import SOURCE_NOTE
from ..quota import KST
from ..today import KEYS, pick
from .common import response, shared_conn

VALID_MD = frozenset(KEYS)


def get_conn():
    return shared_conn()


def today_table():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["TODAY_TABLE"])


def now_kst() -> datetime:
    return datetime.now(KST)


def lambda_handler(event, context):
    now = now_kst()
    md = ((event.get("queryStringParameters") or {}).get("md") or now.strftime("%m-%d")).strip()
    if md not in VALID_MD:
        return response(400, {"error": "md는 MM-DD 형식의 실제 월·일"})
    item = today_table().get_item(Key={"md": md}).get("Item")
    if not item or not item.get("ids"):
        return response(404, {"error": "오늘의 일기 매핑 없음"})
    entry_id = pick({"ids": list(item["ids"])}, now.year)
    found = db.get(get_conn(), [entry_id])
    if not found:
        return response(404, {"error": "일기 없음"})
    e = found[0]
    return response(200, {
        "entry": {"id": e.id, "label": e.label, "original": e.original, "translation": e.translation,
                  "emotion": e.emotion, "intro": e.intro, "solar_date": e.solar_date.isoformat()},
        "questions": list(e.questions), "exact": bool(item.get("exact")), "source_note": SOURCE_NOTE,
    })
