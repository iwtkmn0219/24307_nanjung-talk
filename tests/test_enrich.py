import json
from datetime import date

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from nanjung import bedrock
from nanjung.bedrock import BedrockUnavailable
from nanjung import enrich as enrich_mod
from nanjung.enrich import EnrichError, build_prompt, enrich, parse_response
from nanjung.models import EMOTIONS, DiaryEntry

GOOD = {"translation": "맑음.", "emotion": "일상", "intro": "평범한 날이었소.", "questions": ["a", "b", "c"]}


def test_parse_valid():
    r = parse_response(json.dumps(GOOD, ensure_ascii=False))
    assert r["emotion"] == "일상" and len(r["questions"]) == 3


@pytest.mark.parametrize("bad", [
    json.dumps({**GOOD, "emotion": "기쁨"}, ensure_ascii=False),
    "not json",
    json.dumps({**GOOD, "questions": ["a"]}, ensure_ascii=False),
    json.dumps({k: v for k, v in GOOD.items() if k != "translation"}, ensure_ascii=False),
    json.dumps({**GOOD, "translation": ""}, ensure_ascii=False),
    json.dumps({**GOOD, "intro": "가" * 81}, ensure_ascii=False),
    json.dumps([GOOD], ensure_ascii=False),
])
def test_parse_invalid_raises(bad):
    with pytest.raises(EnrichError):
        parse_response(bad)


def test_parse_strips_code_fence():
    r = parse_response("```json\n" + json.dumps(GOOD, ensure_ascii=False) + "\n```")
    assert r["translation"] == "맑음."


def entry():
    return DiaryEntry("S", "壬辰", 1592, 4, False, 13, "壬寅", "十三日壬寅。晴。出東軒公事。射帖十五巡。",
                      id="1592-04-13", solar_date=date(1592, 5, 23), label="임진년(1592) 4월 13일")


def test_build_prompt_contains_original_and_emotions():
    system, messages = build_prompt(entry())
    assert all(emo in system for emo in EMOTIONS) and "JSON" in system
    assert messages[0]["role"] == "user"
    assert "十三日壬寅。晴。出東軒公事。射帖十五巡。" in messages[0]["content"][0]["text"]


class FakeConverseClient:
    def __init__(self, replies):
        self.replies, self.calls, self.kwargs = list(replies), 0, []

    def converse(self, **kw):
        self.calls += 1
        self.kwargs.append(kw)
        return {"output": {"message": {"content": [{"text": self.replies.pop(0)}]}}}


def test_enrich_fills_fields():
    c = FakeConverseClient([json.dumps(GOOD, ensure_ascii=False)])
    e = enrich(entry(), client=c)
    assert (e.translation, e.emotion, e.intro, e.questions) == ("맑음.", "일상", "평범한 날이었소.", ["a", "b", "c"])
    kw = c.kwargs[0]
    assert kw["modelId"] == bedrock.CHAT_MODEL_ID
    assert kw["inferenceConfig"] == {"maxTokens": 4096, "temperature": 0.2}  # 가장 긴 날(609자)도 잘리지 않게


def test_enrich_retries_once_then_succeeds():
    c = FakeConverseClient(["broken", json.dumps(GOOD, ensure_ascii=False)])
    assert enrich(entry(), client=c).emotion == "일상" and c.calls == 2


def test_enrich_retries_once_then_raises():
    c = FakeConverseClient(["broken", "still broken"])
    with pytest.raises(EnrichError):
        enrich(entry(), client=c)
    assert c.calls == 2


class RaisingClient:
    def __init__(self, exc): self.exc = exc
    def converse(self, **kw): raise self.exc
    def invoke_model(self, **kw): raise self.exc


def client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "Converse")


@pytest.mark.parametrize("exc", [client_error("ThrottlingException"),
                                 client_error("ServiceUnavailableException"),
                                 ReadTimeoutError(endpoint_url="https://x")])
def test_converse_wraps_throttling(exc):
    with pytest.raises(BedrockUnavailable):
        bedrock.converse("s", [], 10, 0.1, client=RaisingClient(exc))


def test_embed_wraps_throttling():
    with pytest.raises(BedrockUnavailable):
        bedrock.embed("x", client=RaisingClient(client_error("ThrottlingException")))


def test_other_client_errors_propagate():
    with pytest.raises(ClientError):
        bedrock.converse("s", [], 10, 0.1, client=RaisingClient(client_error("ValidationException")))


class FakeEmbedClient:
    def __init__(self): self.kwargs = None

    def invoke_model(self, **kw):
        self.kwargs = kw
        import io
        return {"body": io.BytesIO(json.dumps({"embedding": [0.1] * 1024}).encode())}


def test_embed_request_shape():
    c = FakeEmbedClient()
    v = bedrock.embed("맑음", client=c)
    assert len(v) == 1024
    assert c.kwargs["modelId"] == "amazon.titan-embed-text-v2:0"
    assert json.loads(c.kwargs["body"]) == {"inputText": "맑음", "dimensions": 1024, "normalize": True}


def test_model_timeout_is_unavailable_for_both_calls():
    c = RaisingClient(client_error("ModelTimeoutException"))
    with pytest.raises(BedrockUnavailable):
        bedrock.converse("s", [], 10, 0.1, client=c)
    with pytest.raises(BedrockUnavailable):
        bedrock.embed("x", client=c)


class SlowBody:
    def read(self):
        raise ReadTimeoutError(endpoint_url="https://x")


class SlowStreamClient:
    def invoke_model(self, **kw):
        return {"body": SlowBody()}


def test_embed_stream_read_timeout_is_unavailable():
    with pytest.raises(BedrockUnavailable):
        bedrock.embed("x", client=SlowStreamClient())


def test_api_config_fits_in_lambda_timeout():
    cfg = bedrock.API_CONFIG
    assert cfg.retries["total_max_attempts"] == 1
    from nanjung import db
    worst = 2 * (cfg.connect_timeout + cfg.read_timeout) + db.CONNECT_TIMEOUT
    assert worst < 29  # embed + converse + DB 연결이 API Gateway/Lambda 29초 안에 끝나야 한다


def test_prompt_has_archery_and_hao_style_guidance():
    system, _ = build_prompt(entry())
    assert "巡" in system and "순" in system  # 射帿 N巡 → 활 N순
    assert "하오체" in system and "~네" in system  # intro 말투 지시(반말·해라체 금지 예시)


def test_prompt_glossary_mother():
    system, _ = build_prompt(entry())
    assert "天只" in system and "어머니" in system  # 난중일기의 天只는 어머니


def test_intro_up_to_80_is_accepted():
    # 프롬프트는 40자를 요구하지만, 넘긴 소개 때문에 하루치 적재가 실패하지 않게 80자까지 받는다(실측 61자+ 2회 연속)
    assert parse_response(json.dumps({**GOOD, "intro": "가" * 80}, ensure_ascii=False))["intro"] == "가" * 80


def test_prompt_glossary_son():
    system, _ = build_prompt(entry())
    assert "豚" in system and "아들" in system  # 豚薈 → 아들 회 (돼지로 옮기지 않게)


# ---- 감정 기준 좁히기 / 䓲 통일 / 감정만 재분류 ----
def test_system_prompt_narrows_grief_to_death_and_loss():
    system, _ = build_prompt(entry())
    assert "죽음" in system and "상실" in system and "통곡" in system and "애도" in system
    assert "병고" in system and "근심" in system   # 병고·근심은 비통이 아니라는 지시


def test_system_prompt_unifies_yeol_name():
    system, _ = build_prompt(entry())
    assert "䓲" in system and "아들 열" in system and "豚䓲" in system


def test_emotion_prompt_has_rules_and_text():
    system, messages = enrich_mod.build_emotion_prompt("十三日。哭。", "13일. 통곡했다.")
    assert "비통" in system and "병고" in system and "JSON" in system
    text = messages[0]["content"][0]["text"]
    assert "十三日。哭。" in text and "13일. 통곡했다." in text


def test_parse_emotion_variants():
    assert enrich_mod.parse_emotion('{"emotion":"비통"}') == "비통"
    assert enrich_mod.parse_emotion('```json\n{"emotion":"일상"}\n```') == "일상"
    for bad in ["not json", '{"emotion":"기쁨"}', "[]", '{"x":1}']:
        with pytest.raises(EnrichError):
            enrich_mod.parse_emotion(bad)


def test_reclassify_returns_emotion_and_retries_once():
    c = FakeConverseClient(['{"emotion":"일상"}'])
    assert enrich_mod.reclassify("o", "t", client=c) == "일상"
    assert c.kwargs[0]["inferenceConfig"]["maxTokens"] <= 200
    c2 = FakeConverseClient(["broken", '{"emotion":"비통"}'])
    assert enrich_mod.reclassify("o", "t", client=c2) == "비통" and c2.calls == 2
    c3 = FakeConverseClient(["broken", "broken"])
    with pytest.raises(EnrichError):
        enrich_mod.reclassify("o", "t", client=c3)


def test_parse_emotion_ignores_commentary_around_the_json():
    text = '```json\n{"emotion": "비통"}\n```\n\n**분류 근거:**\n원문의 "不勝懷恨"과 {중괄호} 설명'
    assert enrich_mod.parse_emotion(text) == "비통"
    assert enrich_mod.parse_emotion('설명 먼저 {"emotion": "일상"} 뒤에 설명') == "일상"
    with pytest.raises(EnrichError):
        enrich_mod.parse_emotion('설명만 있고 {"emotion": "기쁨"}')


def test_parse_emotion_two_different_values_is_ambiguous_but_same_value_twice_is_fine():
    two = '예시 {"emotion": "일상"} 그리고 결론 {"emotion": "비통"}'
    with pytest.raises(EnrichError):
        enrich_mod.parse_emotion(two)
    assert enrich_mod.parse_emotion('{"emotion": "비통"}\n설명... {"emotion": "비통"}') == "비통"


def test_reclassify_retries_when_first_reply_is_ambiguous():
    c = FakeConverseClient(['{"emotion":"일상"} 아니 {"emotion":"비통"}', '{"emotion":"비통"}'])
    assert enrich_mod.reclassify("o", "t", client=c) == "비통" and c.calls == 2


def test_system_prompt_unifies_bong_name():
    system, _ = build_prompt(entry())
    assert "菶" in system and "조카 봉" in system
