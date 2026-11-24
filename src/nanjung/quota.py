"""브라우저(X-Client-Id)별 하루(KST) 질문 횟수 제한."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from botocore.exceptions import ClientError

KST = timezone(timedelta(hours=9), "KST")


def allow(table, client_id: str, now_kst: datetime, limit: int) -> bool:
    now = now_kst.astimezone(KST)
    next_midnight = datetime.combine(now.date() + timedelta(days=1), time(0), tzinfo=KST)
    expires_at = int((next_midnight + timedelta(days=1)).timestamp())
    try:
        table.update_item(
            Key={"pk": f"{client_id}#{now:%Y-%m-%d}"},
            UpdateExpression="ADD cnt :one SET expires_at = :exp",
            ConditionExpression="attribute_not_exists(cnt) OR cnt < :limit",
            ExpressionAttributeValues={":one": 1, ":limit": limit, ":exp": expires_at},
        )
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def refund(table, client_id: str, now_kst: datetime) -> bool:
    """allow()로 차감한 1회를 되돌린다. 0 아래로는 내려가지 않는다(없거나 0이면 False)."""
    now = now_kst.astimezone(KST)
    try:
        table.update_item(
            Key={"pk": f"{client_id}#{now:%Y-%m-%d}"},
            UpdateExpression="ADD cnt :minus",
            ConditionExpression="attribute_exists(cnt) AND cnt > :zero",
            ExpressionAttributeValues={":minus": -1, ":zero": 0},
        )
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True
