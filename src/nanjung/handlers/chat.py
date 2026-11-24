"""POST /chat"""
from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from datetime import datetime
from time import monotonic

from botocore.config import Config

from .. import db
from ..answer import answer, decide_mode, is_modern
from ..bedrock import API_CONFIG, BedrockUnavailable, api_client, embed
from ..date_resolver import resolve
from ..quota import KST, allow, refund
from .common import response, shared_conn

MSG_LIMIT = "오늘은 그만 쉬어야겠소. 내일 다시 오시오."
MSG_UNAVAILABLE = "잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오."
MAX_MESSAGE = 300
MAX_HISTORY_ITEMS = 50
MAX_SOURCE_IDS = 10
SEARCH_K = 5
# 요청 마감 목표 22초(단계 시작 판단용): 각 네트워크 단계는 시작 전에 "그 단계의 설정상 최대 시간"이
# 남았는지 확인하고, 모자라면 503이다. pg8000 timeout은 소켓 대기 1회 기준이라 쿼리 하나가 DB_OP_S를
# 넘을 수 있으므로 25초 안 응답을 엄격히 보장하지는 않는다. 넘으면 프론트 25초 타이머가 503과 같은 안내를 띄운다.
REQUEST_BUDGET_S = 22.0
LAMBDA_MARGIN_S = 1.0
DDB_CONFIG = Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 1, "mode": "standard"})
DDB_CALL_S = DDB_CONFIG.connect_timeout + DDB_CONFIG.read_timeout          # quota·refund
DB_OP_S = float(db.CONNECT_TIMEOUT)                                         # pg8000 소켓 제한(쿼리 1회)
DB_CONN_S = 2 * DB_OP_S                                                     # 헬스체크 + 재연결
BEDROCK_CALL_S = API_CONFIG.connect_timeout + API_CONFIG.read_timeout       # embed·converse(재시도 없음)
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
            raise OutOfTime(f"남은 시간이 {seconds}초보다 적음")


class OutOfTime(BedrockUnavailable):
    """요청 마감 안에 다음 단계를 끝낼 수 없음 → 503과 같게 처리"""


def get_conn():
    return shared_conn()


_usage_table = None


def usage_table():
    global _usage_table
    if _usage_table is None:
        import boto3
        _usage_table = boto3.resource("dynamodb", config=DDB_CONFIG).Table(os.environ["USAGE_TABLE"])
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
    try:  # 추천 질문은 시간이 남을 때만. 모자라거나 실패하면 추천 없이 고정 답변
        deadline.require(DB_CONN_S)
        conn = get_conn()
        deadline.require(BEDROCK_CALL_S)
        qvec = embed(message, client=api_client())
        deadline.require(DB_OP_S)
        hits = db.search(conn, qvec, k=SEARCH_K)
    except OutOfTime:
        hits = []
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
    charged_at = now_kst()
    try:
        deadline.require(DDB_CALL_S)
    except OutOfTime:
        return response(503, {"answer": MSG_UNAVAILABLE})  # 아직 차감 전
    if not allow(usage_table(), client_id, charged_at, int(os.environ.get("DAILY_LIMIT", "20"))):
        return response(429, {"answer": MSG_LIMIT})

    if is_modern(message):
        return response(200, _modern(message, deadline))

    try:
        deadline.require(DB_CONN_S)
        conn = get_conn()

        def neighbor(i, d):
            deadline.require(DB_OP_S)
            return db.neighbor(conn, i, d)
        date_ids = resolve(message, last_ids, neighbor)
        deadline.require(BEDROCK_CALL_S)
        qvec = embed(message, client=api_client())
        hits = []
        if date_ids:
            deadline.require(DB_OP_S)
            hits = db.search(conn, qvec, k=SEARCH_K, date_ids=date_ids)
        date_matched = bool(hits)
        if not hits:
            deadline.require(DB_OP_S)
            hits = db.search(conn, qvec, k=SEARCH_K)
        mode = decide_mode(message, hits, float(os.environ.get("SIM_THRESHOLD", "0.30")), date_matched)
        if mode in ("normal", "serious"):
            deadline.require(BEDROCK_CALL_S)
        return response(200, answer(message, hits, history, mode, client=api_client()))
    except BedrockUnavailable:
        _refund(client_id, charged_at, deadline)
        return response(503, {"answer": MSG_UNAVAILABLE})


def _refund(client_id: str, charged_at: datetime, deadline: Deadline) -> None:
    """장애로 답하지 못한 요청은 하루 사용량에서 뺀다. 실패하거나 시간이 없으면 건너뛰고 503은 그대로 나간다."""
    try:
        deadline.require(DDB_CALL_S)
        refund(usage_table(), client_id, charged_at)
    except Exception:
        log.warning("사용량 되돌리기 실패", exc_info=True)
