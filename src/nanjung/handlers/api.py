"""API Lambda 진입점: HTTP API(v2) routeKey로 /chat, /diary 처리기에 나눠 보낸다."""
from __future__ import annotations

from . import chat, diary
from .common import response

ROUTES = {
    "POST /chat": lambda e, c: chat.lambda_handler(e, c),
    "GET /diary": lambda e, c: diary.lambda_handler(e, c),
}


def lambda_handler(event, context):
    route = ROUTES.get(event.get("routeKey"))
    if route is None:
        return response(404, {"error": "없는 경로"})
    return route(event, context)
