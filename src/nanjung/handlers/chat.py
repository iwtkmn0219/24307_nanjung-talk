"""POST /chat"""
from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from datetime import datetime
from time import monotonic

from .. import db
from ..answer import answer, decide_mode, is_modern
from ..bedrock import API_CONFIG, BedrockUnavailable, api_client, embed
from ..date_resolver import resolve
from ..quota import KST, allow
from .common import response, shared_conn

MSG_LIMIT = "오늘은 그만 쉬어야겠소. 내일 다시 오시오."
MSG_UNAVAILABLE = "잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오."
MAX_MESSAGE = 300
MAX_HISTORY_ITEMS = 50
MAX_SOURCE_IDS = 10
SEARCH_K = 5
# 요청 전체 마감: 프론트 타이머(25초)와 Lambda 29초보다 먼저 503으로 끝낸다
REQUEST_BUDGET_S = 22.0
LAMBDA_MARGIN_S = 1.0
# Bedrock 호출 하나가 SDK 설정상 걸릴 수 있는 최대 시간(재시도 없음)
BEDROCK_CALL_S = API_CONFIG.connect_timeout + API_CONFIG.read_timeout
log = logging.getLogger(__name__)


class BadRequest(Exception):
    pass


class Deadline:
    """요청 마감. 외부 호출 전에 남은 시간이 그 호출의 최대 시간보다 적으면 BedrockUnavailable(→503)."""

    def __init__(self, context):
        budget = REQUEST_BUDGET_S
        if context is not None and hasattr(context, "get_remaining_time_in_millis"):
            budget = min(budget, context.get_remaining_time_in_millis() / 1000 - LAMBDA_MARGIN_S)
        self.end = monotonic() + budget

    def require(self, seconds: float) -> None:
        if self.end - monotonic() < seconds:
            raise BedrockUnavailable("요청 시간 예산 부족")


def get_conn():
    return shared_conn()


_usage_table = None


def usage_table():
    global _usage_table
    if _usage_table is None:
        import boto3
        from botocore.config import Config
        cfg = Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 2, "mode": "standard"})
        _usage_table = boto3.resource("dynamodb", config=cfg).Table(os.environ["USAGE_TABLE"])
    return _usage_table


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


def _modern(message: str, deadline: "Deadline") -> dict:
    """현대 질문은 LLM 없이 고정 답변. 추천 질문용 검색이 실패해도 고정 답변은 돌려준다."""
    try:
        conn = get_conn()
        deadline.require(BEDROCK_CALL_S)
        hits = db.search(conn, embed(message, client=api_client()), k=SEARCH_K)
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

    deadline = Deadline(context)
    if not allow(usage_table(), client_id, now_kst(), int(os.environ.get("DAILY_LIMIT", "20"))):
        return response(429, {"answer": MSG_LIMIT})

    if is_modern(message):
        return response(200, _modern(message, deadline))

    try:
        conn = get_conn()
        date_ids = resolve(message, last_ids, lambda i, d: db.neighbor(conn, i, d))
        deadline.require(BEDROCK_CALL_S)
        qvec = embed(message, client=api_client())
        hits = db.search(conn, qvec, k=SEARCH_K, date_ids=date_ids) if date_ids else []
        date_matched = bool(hits)
        if not hits:
            hits = db.search(conn, qvec, k=SEARCH_K)
        mode = decide_mode(message, hits, float(os.environ.get("SIM_THRESHOLD", "0.30")), date_matched)
        if mode in ("normal", "serious"):
            deadline.require(BEDROCK_CALL_S)
        return response(200, answer(message, hits, history, mode, client=api_client()))
    except BedrockUnavailable:
        return response(503, {"answer": MSG_UNAVAILABLE})
