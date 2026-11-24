"""POST /chat"""
from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from datetime import datetime

from .. import db
from ..answer import answer, decide_mode, is_modern
from ..bedrock import BedrockUnavailable, api_client, embed
from ..date_resolver import resolve
from ..quota import KST, allow
from .common import response, shared_conn

MSG_LIMIT = "오늘은 그만 쉬어야겠소. 내일 다시 오시오."
MSG_UNAVAILABLE = "잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오."
MAX_MESSAGE = 300
MAX_HISTORY_ITEMS = 50
MAX_SOURCE_IDS = 10
SEARCH_K = 5
log = logging.getLogger(__name__)


class BadRequest(Exception):
    pass


def get_conn():
    return shared_conn()


def usage_table():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["USAGE_TABLE"])


def now_kst() -> datetime:
    return datetime.now(KST)


def _client_id(event) -> str:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    cid = (headers.get("x-client-id") or "").strip()
    try:
        return str(uuid.UUID(cid))
    except ValueError:
        raise BadRequest("X-Client-Id 헤더가 UUID가 아님") from None


def _body(event) -> tuple[str, list, list[str]]:
    raw = event.get("body") or ""
    try:
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise BadRequest("JSON 본문이 아님") from None
    if not isinstance(data, dict):
        raise BadRequest("JSON 객체가 아님")
    message = data.get("message")
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_MESSAGE:
        raise BadRequest("message는 1~300자 문자열")
    history = data.get("history", [])
    ids = data.get("last_source_ids", [])
    if not isinstance(history, list):
        raise BadRequest("history는 배열")
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise BadRequest("last_source_ids는 문자열 배열")
    return message.strip(), history[-MAX_HISTORY_ITEMS:], ids[:MAX_SOURCE_IDS]


def _modern(message: str) -> dict:
    """현대 질문은 LLM 없이 고정 답변. 추천 질문용 검색이 실패해도 고정 답변은 돌려준다."""
    try:
        hits = db.search(get_conn(), embed(message, client=api_client()), k=SEARCH_K)
    except Exception:
        log.warning("현대 질문 추천 검색 실패", exc_info=True)
        hits = []
    return answer(message, hits, [], "modern")


def lambda_handler(event, context):
    try:
        client_id = _client_id(event)
        message, history, last_ids = _body(event)
    except BadRequest as e:
        return response(400, {"error": str(e)})

    if not allow(usage_table(), client_id, now_kst(), int(os.environ.get("DAILY_LIMIT", "20"))):
        return response(429, {"answer": MSG_LIMIT})

    if is_modern(message):
        return response(200, _modern(message))

    conn = get_conn()
    try:
        date_ids = resolve(message, last_ids, lambda i, d: db.neighbor(conn, i, d))
        qvec = embed(message, client=api_client())
        hits = db.search(conn, qvec, k=SEARCH_K, date_ids=date_ids) if date_ids else []
        date_matched = bool(hits)
        if not hits:
            hits = db.search(conn, qvec, k=SEARCH_K)
        mode = decide_mode(message, hits, float(os.environ.get("SIM_THRESHOLD", "0.30")), date_matched)
        return response(200, answer(message, hits, history, mode, client=api_client()))
    except BedrockUnavailable:
        return response(503, {"answer": MSG_UNAVAILABLE})
