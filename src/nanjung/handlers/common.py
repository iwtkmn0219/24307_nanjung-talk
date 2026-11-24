"""HTTP API(payload v2) 공용 응답·연결."""
from __future__ import annotations

import json

from .. import db

_conn = None


def response(status: int, body: dict) -> dict:
    return {"statusCode": status,
            "headers": {"content-type": "application/json; charset=utf-8"},
            "body": json.dumps(body, ensure_ascii=False)}


def shared_conn():
    """Lambda 실행 환경이 살아 있는 동안 연결을 재사용한다. 끊겼으면 다시 연결한다."""
    global _conn
    if _conn is not None:
        try:
            _conn.run("SELECT 1")
        except Exception:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
    if _conn is None:
        _conn = db.connect()
    return _conn
