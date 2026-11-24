import json

import pytest

from nanjung.handlers import api


@pytest.fixture
def routes(monkeypatch):
    calls = []
    monkeypatch.setattr(api.chat, "lambda_handler", lambda e, c: calls.append(("chat", e)) or "CHAT")
    monkeypatch.setattr(api.diary, "lambda_handler", lambda e, c: calls.append(("diary", e)) or "DIARY")
    return calls


def test_post_chat_goes_to_chat(routes):
    ev = {"routeKey": "POST /chat", "body": "{}"}
    assert api.lambda_handler(ev, None) == "CHAT" and routes == [("chat", ev)]


def test_get_diary_goes_to_diary(routes):
    ev = {"routeKey": "GET /diary", "queryStringParameters": {"md": "05-23"}}
    assert api.lambda_handler(ev, None) == "DIARY" and routes == [("diary", ev)]


@pytest.mark.parametrize("route", ["GET /chat", "POST /diary", "GET /admin", "$default", None])
def test_unknown_route_is_404(routes, route):
    r = api.lambda_handler({"routeKey": route}, None)
    assert r["statusCode"] == 404 and routes == []
    assert "error" in json.loads(r["body"])
