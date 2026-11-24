import base64
import json
from datetime import date, datetime

import pytest

from nanjung.bedrock import BedrockUnavailable
from nanjung.handlers import chat, diary
from nanjung.models import SOURCE_NOTE, DiaryEntry, Hit
from nanjung.quota import KST

CID = "00000000-0000-4000-8000-000000000000"


def entry(eid="1592-04-13", emo="일상"):
    return DiaryEntry("S", "壬辰", 1592, 4, False, 13, "壬寅", "十三日壬寅。晴。", id=eid,
                      solar_date=date(1592, 5, 23), label="임진년(1592) 4월 13일", translation="맑음.",
                      emotion=emo, intro="소개하오.", questions=["q1", "q2", "q3"])


class FakeDB:
    def __init__(self, results=None, entries=None, neighbors=None):
        self.search_calls, self.results = [], results or {}
        self.entries = entries or {}
        self.neighbors = neighbors or {}

    def search(self, conn, qvec, k=5, date_ids=None):
        self.search_calls.append((k, date_ids))
        return list(self.results.get(tuple(date_ids) if date_ids else None, []))

    def neighbor(self, conn, eid, d):
        return self.neighbors.get((eid, d))

    def get(self, conn, ids):
        return [self.entries[i] for i in ids if i in self.entries]


API_CLIENT = object()


class Recorder:
    def __init__(self):
        self.answer_calls, self.quota_calls, self.clients, self.focus = [], [], [], []


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("SIM_THRESHOLD", "0.30")
    monkeypatch.setenv("DAILY_LIMIT", "20")

    def install(db=None, quota_ok=True, embed_exc=None, answer_exc=None):
        fdb, rec = db or FakeDB({None: [Hit(entry(), 0.8)]}), Recorder()
        monkeypatch.setattr(chat, "db", fdb)
        monkeypatch.setattr(chat, "get_conn", lambda: object())
        monkeypatch.setattr(chat, "usage_table", lambda: object())

        def allow(table, cid, now, limit):
            rec.quota_calls.append((cid, limit))
            return quota_ok
        monkeypatch.setattr(chat, "allow", allow)
        rec.refunds = []
        monkeypatch.setattr(chat, "refund", lambda table, cid, now: rec.refunds.append(cid) or True)

        monkeypatch.setattr(chat, "api_client", lambda: API_CLIENT)

        def embed(text, client=None):
            rec.clients.append(("embed", client))
            if embed_exc:
                raise embed_exc
            return [0.0] * 1024
        monkeypatch.setattr(chat, "embed", embed)

        def answer(message, hits, history, mode, client=None, focus_ids=None):
            rec.focus.append(focus_ids)
            rec.clients.append(("answer", client))
            if answer_exc:
                raise answer_exc
            rec.answer_calls.append((message, hits, history, mode))
            return {"answer": "그랬소.", "mode": mode, "sources": [], "suggestions": []}
        monkeypatch.setattr(chat, "answer", answer)
        return fdb, rec
    return install


def ev(body, headers=None, b64=False):
    raw = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    if b64:
        raw = base64.b64encode(raw.encode()).decode()
    return {"headers": {"x-client-id": CID} if headers is None else headers, "body": raw,
            "isBase64Encoded": b64}


def call(event):
    r = chat.lambda_handler(event, None)
    return r["statusCode"], json.loads(r["body"])


def body(msg="배 멀미 하셨어요?", **kw):
    return {"message": msg, "history": [], "last_source_ids": [], **kw}


@pytest.mark.parametrize("b", [body(""), body("   "), body("가" * 301), body(None), {"history": []},
                               "not json", "[1]", body(history="x"), body(last_source_ids=[1])])
def test_chat_400_on_empty_and_long(env, b):
    _, rec = env()
    status, _ = call(ev(b))
    assert status == 400 and rec.quota_calls == []


def test_chat_300_chars_is_ok(env):
    env()
    assert call(ev(body("가" * 300)))[0] == 200


@pytest.mark.parametrize("headers", [{}, {"x-client-id": ""}, {"x-client-id": "not-a-uuid"}])
def test_chat_400_on_missing_or_bad_client_id(env, headers):
    env()
    assert call(ev(body(), headers=headers))[0] == 400


def test_chat_accepts_mixed_case_header_and_base64_body(env):
    _, rec = env()
    status, _ = call(ev(body(), headers={"X-Client-Id": CID}, b64=True))
    assert status == 200 and rec.quota_calls == [(CID, 20)]


def test_chat_429_when_quota_denied(env):
    fdb, rec = env(quota_ok=False)
    status, out = call(ev(body()))
    assert status == 429 and out["answer"].startswith("오늘은 그만 쉬어야겠소")
    assert out == {"answer": "오늘은 그만 쉬어야겠소. 내일 다시 오시오."}
    assert fdb.search_calls == [] and rec.answer_calls == []


def test_chat_503_on_bedrock_unavailable(env):
    env(embed_exc=BedrockUnavailable("throttled"))
    status, out = call(ev(body()))
    assert status == 503 and out == {"answer": "잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오."}


def test_chat_503_when_converse_unavailable(env):
    env(answer_exc=BedrockUnavailable("timeout"))
    assert call(ev(body()))[0] == 503


def test_chat_normal_flow(env):
    fdb, rec = env()
    status, out = call(ev(body(history=[{"role": "user", "content": "앞"}])))
    assert status == 200 and out["answer"] == "그랬소." and out["mode"] == "normal"
    assert fdb.search_calls == [(5, None)]
    assert rec.answer_calls[0][2] == [{"role": "user", "content": "앞"}]


def test_chat_uses_api_bedrock_client(env):
    _, rec = env()
    call(ev(body()))
    assert rec.clients == [("embed", API_CLIENT), ("answer", API_CLIENT)]


def test_chat_uses_resolved_dates(env):
    fdb, _ = env(FakeDB({("1597-09-16",): [Hit(entry("1597-09-16"), 0.05)]}))
    _, out = call(ev(body("명량 때 어땠어요?")))
    assert fdb.search_calls == [(5, ["1597-09-16"])]
    assert out["mode"] == "normal"  # 날짜가 맞으면 기준값 무시


def test_chat_next_day_uses_last_source_ids(env):
    fdb, _ = env(FakeDB({("1592-08-24",): [Hit(entry("1592-08-24"), 0.2)]},
                        neighbors={("1592-06-10", 1): "1592-08-24"}))
    call(ev(body("그다음 날은요?", last_source_ids=["1592-06-10"])))
    assert fdb.search_calls == [(5, ["1592-08-24"])]


def test_chat_next_day_at_end_falls_back_to_general_search(env):
    fdb, _ = env(FakeDB({None: [Hit(entry(), 0.5)]}))
    status, _ = call(ev(body("그다음 날은요?", last_source_ids=["1598-11-17"])))
    assert status == 200 and fdb.search_calls == [(5, None)]


def test_chat_retries_search_without_date_when_empty(env):
    fdb, _ = env(FakeDB({None: [Hit(entry(), 0.1)]}))
    _, out = call(ev(body("정유년 9월 16일 일기")))
    assert fdb.search_calls == [(5, ["1597-09-16"]), (5, None)]
    assert out["mode"] == "out_of_scope"  # 날짜 결과가 없었으므로 기준값 적용


def test_chat_modern_question_with_high_similarity(env):
    env(FakeDB({None: [Hit(entry(), 0.9)]}))
    _, out = call(ev(body("요즘 일본이랑 사이 어때요?")))
    assert out["mode"] == "modern"


def test_chat_response_is_json_utf8(env):
    env()
    r = chat.lambda_handler(ev(body()), None)
    assert r["headers"]["content-type"].startswith("application/json")
    assert "그랬소" in r["body"]


# ---- diary ----

class FakeTodayTable:
    def __init__(self, items):
        self.items = items

    def get_item(self, Key):
        it = self.items.get(Key["md"])
        return {"Item": it} if it else {}


@pytest.fixture
def denv(monkeypatch):
    def install(items, entries, now=datetime(2026, 12, 1, 0, 30, tzinfo=KST)):
        monkeypatch.setattr(diary, "today_table", lambda: FakeTodayTable(items))
        monkeypatch.setattr(diary, "get_conn", lambda: object())
        monkeypatch.setattr(diary, "db", FakeDB(entries=entries))
        monkeypatch.setattr(diary, "now_kst", lambda: now)
    return install


def dcall(params):
    r = diary.lambda_handler({"queryStringParameters": params}, None)
    return r["statusCode"], json.loads(r["body"])


def test_diary_defaults_to_kst_today(denv):
    denv({"12-01": {"md": "12-01", "ids": ["1597-x"], "exact": True}}, {"1597-x": entry("1597-x")})
    status, out = dcall(None)
    assert status == 200 and out["entry"]["id"] == "1597-x"


def test_diary_response_shape(denv):
    e = entry()
    denv({"05-23": {"md": "05-23", "ids": ["1592-04-13"], "exact": False}}, {"1592-04-13": e})
    status, out = dcall({"md": "05-23"})
    assert status == 200
    assert out == {"entry": {"id": e.id, "label": e.label, "original": e.original,
                             "translation": e.translation, "emotion": e.emotion, "intro": e.intro,
                             "solar_date": "1592-05-23"},
                   "questions": ["q1", "q2", "q3"], "exact": False, "source_note": SOURCE_NOTE}


def test_diary_picks_by_kst_year(denv):
    denv({"10-26": {"md": "10-26", "ids": ["a", "b"], "exact": True}}, {"a": entry("a"), "b": entry("b")},
         now=datetime(2027, 1, 1, 0, 0, tzinfo=KST))
    assert dcall({"md": "10-26"})[1]["entry"]["id"] == "b"  # 2027 % 2 == 1


@pytest.mark.parametrize("md", ["13-01", "02-30", "1-1", "abc", "02-29x"])
def test_diary_400_on_bad_md(denv, md):
    denv({}, {})
    assert dcall({"md": md})[0] == 400


def test_diary_accepts_0229(denv):
    denv({"02-29": {"md": "02-29", "ids": ["1592-04-13"], "exact": False}}, {"1592-04-13": entry()})
    assert dcall({"md": "02-29"})[0] == 200


def test_diary_404_when_map_missing(denv):
    denv({}, {})
    assert dcall({"md": "05-23"})[0] == 404


def test_modern_question_survives_bedrock_outage(env, monkeypatch):
    import nanjung.answer as real
    env(embed_exc=BedrockUnavailable("throttled"))
    monkeypatch.setattr(chat, "answer", real.answer)
    status, out = call(ev(body("요즘 일본이랑 사이 어때요?")))
    assert status == 200 and out["mode"] == "modern"
    assert out["answer"].startswith("후대의 일은 모르오.") and out["suggestions"] == []


def test_modern_question_survives_db_outage(env, monkeypatch):
    import nanjung.answer as real
    env()
    monkeypatch.setattr(chat, "answer", real.answer)

    def boom():
        raise OSError("db down")
    monkeypatch.setattr(chat, "get_conn", boom)
    status, out = call(ev(body("요즘 일본이랑 사이 어때요?")))
    assert status == 200 and out["mode"] == "modern" and out["suggestions"] == []


def test_modern_question_uses_search_for_suggestions_when_healthy(env, monkeypatch):
    import nanjung.answer as real
    fdb, _ = env(FakeDB({None: [Hit(entry(), 0.9)]}))
    monkeypatch.setattr(chat, "answer", real.answer)
    _, out = call(ev(body("요즘 일본이랑 사이 어때요?")))
    assert out["suggestions"] == ["q1", "q2", "q3"] and fdb.search_calls == [(5, None)]


class Ctx:
    def __init__(self, ms): self.ms = ms
    def get_remaining_time_in_millis(self): return self.ms


def test_skips_bedrock_when_lambda_time_nearly_gone(env):
    _, rec = env()
    r = chat.lambda_handler(ev(body()), Ctx(100))
    assert r["statusCode"] == 503 and rec.clients == []
    assert json.loads(r["body"]) == {"answer": "잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오."}


def test_slow_db_before_generation_skips_converse(env, monkeypatch):
    fdb, rec = env()
    clock = [1000.0]
    monkeypatch.setattr(chat, "monotonic", lambda: clock[0])
    real_search = fdb.search

    def slow_search(*a, **kw):
        clock[0] += 15  # 검색이 15초 걸림 → 남은 예산이 생성 호출 예산보다 작다
        return real_search(*a, **kw)
    fdb.search = slow_search
    status, out = call(ev(body()))
    assert status == 503 and [c[0] for c in rec.clients] == ["embed"]  # converse 생략


def test_request_budget_is_shorter_than_frontend_timeout():
    assert chat.REQUEST_BUDGET_S < 25  # 프론트 타이머(25초)보다 먼저 503으로 끝낸다


def test_503_refunds_quota(env):
    _, rec = env(embed_exc=BedrockUnavailable("throttled"))
    assert call(ev(body()))[0] == 503 and rec.refunds == [CID]


def test_success_does_not_refund(env):
    _, rec = env()
    assert call(ev(body()))[0] == 200 and rec.refunds == []


def test_refund_failure_still_returns_503(env, monkeypatch):
    env(embed_exc=BedrockUnavailable("throttled"))

    def broken(*a):
        raise RuntimeError("dynamodb down")
    monkeypatch.setattr(chat, "refund", broken)
    status, out = call(ev(body()))
    assert status == 503 and out == {"answer": "잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오."}


def test_refund_uses_same_day_as_charge(env, monkeypatch):
    _, rec = env(embed_exc=BedrockUnavailable("x"))
    times = iter([datetime(2026, 12, 1, 23, 59, 59, tzinfo=KST), datetime(2026, 12, 2, 0, 0, 1, tzinfo=KST)])
    monkeypatch.setattr(chat, "now_kst", lambda: next(times))
    seen = []
    monkeypatch.setattr(chat, "allow", lambda t, c, now, l: seen.append(now) or True)
    monkeypatch.setattr(chat, "refund", lambda t, c, now: seen.append(now) or True)
    call(ev(body()))
    assert seen[0] == seen[1]


def _slow_env(env, monkeypatch, db=None):
    """리뷰 재현: quota 8초 → DB 연결 3초 → embed 9.5초 → 검색 5초 (가상 시계)."""
    fdb, rec = env(db)
    clock = [0.0]
    monkeypatch.setattr(chat, "monotonic", lambda: clock[0])

    def step(sec, ret=None):
        def f(*a, **kw):
            clock[0] += sec
            return ret() if callable(ret) else ret
        return f
    monkeypatch.setattr(chat, "allow", step(8, True))
    monkeypatch.setattr(chat, "get_conn", step(3, object))
    monkeypatch.setattr(chat, "embed", step(9.5, lambda: [0.0] * 1024))
    real_search = fdb.search
    fdb.search = lambda *a, **kw: (clock.__setitem__(0, clock[0] + 5), real_search(*a, **kw))[1]
    return clock, fdb, rec


def test_slow_steps_return_before_frontend_timeout(env, monkeypatch):
    clock, _, rec = _slow_env(env, monkeypatch)
    status, _ = call(ev(body()))
    assert status == 503 and clock[0] < 25 and rec.answer_calls == []


def test_slow_steps_modern_returns_fixed_answer_before_timeout(env, monkeypatch):
    import nanjung.answer as real
    clock, _, _ = _slow_env(env, monkeypatch)
    monkeypatch.setattr(chat, "answer", real.answer)
    status, out = call(ev(body("요즘 일본이랑 사이 어때요?")))
    assert status == 200 and out["mode"] == "modern" and clock[0] < 25


def test_no_time_left_touches_nothing(env):
    _, rec = env()
    r = chat.lambda_handler(ev(body()), Ctx(100))
    assert r["statusCode"] == 503 and rec.quota_calls == [] and rec.refunds == []


def test_date_matched_question_passes_focus_ids_to_answer(env):
    _, rec = env(FakeDB({("1592-08-24",): [Hit(entry("1592-08-24"), 0.2)]},
                        neighbors={("1592-06-10", 1): "1592-08-24"}))
    call(ev(body("그다음 날은요?", last_source_ids=["1592-06-10"])))
    assert rec.focus == [["1592-08-24"]]


def test_general_search_passes_no_focus(env):
    _, rec = env()
    call(ev(body()))
    assert rec.focus == [None]


def test_empty_date_result_falls_back_without_focus(env):
    _, rec = env(FakeDB({None: [Hit(entry(), 0.9)]}))
    call(ev(body("정유년 9월 16일 일기")))
    assert rec.focus == [None]
