from datetime import date

import pytest

from nanjung.answer import (FIXED_MODERN, FIXED_OUT, MODERN_MARKERS, answer, decide_mode,
                            source_card)
from nanjung.models import SOURCE_NOTE, DiaryEntry, Hit

_n = iter(range(10_000))


def hit(sim, emo="일상", original="十三日壬寅。晴。出東軒公事。", translation="13일 임인. 맑음. 동헌에 나가 공무를 보았다."):
    i = next(_n)
    e = DiaryEntry("S", "壬辰", 1592, 4, False, 13, "壬寅", original, id=f"id-{i}",
                   solar_date=date(1592, 5, 23), label=f"라벨{i}", translation=translation,
                   emotion=emo, intro="소개", questions=[f"q{i}a", f"q{i}b", f"q{i}c"])
    return Hit(e, sim)


class FakeClient:
    def __init__(self, reply="그날은 맑았소."):
        self.calls, self.kwargs, self.reply = 0, [], reply

    def converse(self, **kw):
        self.calls += 1
        self.kwargs.append(kw)
        return {"output": {"message": {"content": [{"text": self.reply}]}}}


@pytest.fixture
def fake_client():
    return FakeClient()


def test_modern_politics_overrides_high_similarity():
    assert decide_mode("요즘 일본이랑 사이 어때요?", [hit(0.9)], 0.3, False) == "modern"


def test_modern_overrides_date_match():
    assert decide_mode("정유년 9월 16일이랑 요즘 정치 비교하면?", [hit(0.9)], 0.3, True) == "modern"


@pytest.mark.parametrize("marker", MODERN_MARKERS)
def test_every_marker_is_modern(marker):
    assert decide_mode(f"{marker} 이야기 좀", [hit(0.9, "비통")], 0.3, False) == "modern"


def test_low_similarity_out_of_scope():
    assert decide_mode("인공지능이 뭐예요?", [hit(0.1)], 0.3, False) == "out_of_scope"


def test_threshold_boundary_is_in_scope():
    assert decide_mode("배 멀미", [hit(0.3)], 0.3, False) == "normal"


def test_no_hits_is_out_of_scope_even_with_date_match():
    assert decide_mode("정유년 9월 16일", [], 0.3, True) == "out_of_scope"


def test_date_match_bypasses_threshold():
    assert decide_mode("정유년 9월 16일", [hit(0.1)], 0.3, True) == "normal"


def test_grief_is_serious():
    assert decide_mode("아들 소식", [hit(0.5, "일상"), hit(0.4, "비통")], 0.3, False) == "serious"


def test_grief_outside_top3_is_normal():
    hs = [hit(0.5), hit(0.45), hit(0.4), hit(0.35, "비통")]
    assert decide_mode("아들 소식", hs, 0.3, False) == "normal"


def test_out_of_scope_does_not_call_llm(fake_client):
    top = hit(0.1)
    r = answer("인공지능이 뭐예요?", [top], [], "out_of_scope", client=fake_client)
    assert fake_client.calls == 0 and r["answer"].startswith("처음 듣는 말이라 내 답할 길이 없소.")
    assert r["answer"].endswith("대신 내 일기 이야기를 들려주리다.")
    assert r["sources"] == [] and r["suggestions"] == top.entry.questions and r["mode"] == "out_of_scope"


def test_modern_does_not_call_llm(fake_client):
    r = answer("요즘 일본이랑 사이 어때요?", [hit(0.9)], [], "modern", client=fake_client)
    assert fake_client.calls == 0 and r["answer"].startswith(FIXED_MODERN) and r["sources"] == []
    assert FIXED_MODERN == "후대의 일은 모르오." and FIXED_OUT == "처음 듣는 말이라 내 답할 길이 없소."


def test_fixed_answer_with_no_hits_has_no_suggestions(fake_client):
    assert answer("x", [], [], "out_of_scope", client=fake_client)["suggestions"] == []


def system_of(c):
    return c.kwargs[0]["system"][0]["text"]


@pytest.mark.parametrize("phrase", ["일기", "지어내", "하오체", "3문장", "후대"])
def test_system_prompt_required_instructions(fake_client, phrase):
    answer("배 멀미?", [hit(0.5)], [], "normal", client=fake_client)
    assert phrase in system_of(fake_client)


def test_serious_prompt_bans_emoji(fake_client):
    answer("아들 소식", [hit(0.5, "비통")], [], "serious", client=fake_client)
    s = system_of(fake_client)
    assert "이모지" in s and "금지" in s and "담담" in s and "하나까지" not in s


def test_normal_prompt_allows_one_emoji(fake_client):
    answer("배 멀미?", [hit(0.5)], [], "normal", client=fake_client)
    s = system_of(fake_client)
    assert "이모지 하나까지" in s and "담담" not in s


def test_normal_answer_uses_top3_and_cards(fake_client):
    hs = [hit(0.6, original=f"初{d}日。原文{d}。") for d in "一二三四"]
    r = answer("배 멀미?", hs, [], "normal", client=fake_client)
    assert r["answer"] == "그날은 맑았소." and r["mode"] == "normal"
    assert [c["id"] for c in r["sources"]] == [h.entry.id for h in hs[:3]]
    s = system_of(fake_client)
    assert "原文一" in s and "原文三" in s and "原文四" not in s
    assert fake_client.kwargs[0]["inferenceConfig"] == {"maxTokens": 400, "temperature": 0.6}
    assert r["suggestions"] == hs[0].entry.questions


def test_source_card_lines():
    h = hit(0.5, original="十三日壬寅。晴。出東軒公事。")
    c = source_card(h)
    assert c == {"id": h.entry.id, "label": h.entry.label, "original_line": "十三日壬寅。",
                 "translation_line": "13일 임인.", "note": SOURCE_NOTE}


def test_source_card_original_line_capped_at_60():
    c = source_card(hit(0.5, original="甲" * 100 + "。"))
    assert len(c["original_line"]) == 60


def msgs(n):
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(n)]


def test_history_truncated_to_6_messages(fake_client):
    answer("새 질문", [hit(0.5)], msgs(10), "normal", client=fake_client)
    sent = fake_client.kwargs[0]["messages"]
    assert [m["content"][0]["text"] for m in sent] == ["m4", "m5", "m6", "m7", "m8", "m9", "새 질문"]
    assert [m["role"] for m in sent] == ["user", "assistant"] * 3 + ["user"]


def test_history_sanitized_to_alternate_and_start_with_user(fake_client):
    history = [{"role": "assistant", "content": "a0"}, {"role": "system", "content": "무시"},
               {"role": "user", "content": "u1"}, {"role": "user", "content": "u2"},
               {"role": "assistant", "content": ""}, {"role": "user", "content": 3}]
    answer("새 질문", [hit(0.5)], history, "normal", client=fake_client)
    sent = fake_client.kwargs[0]["messages"]
    roles = [m["role"] for m in sent]
    assert roles[0] == "user" and roles[-1] == "user"
    assert all(a != b for a, b in zip(roles, roles[1:]))
    assert sent[-1]["content"][0]["text"] == "새 질문"


@pytest.mark.parametrize("msg", ["조선 조정의 정치는 어땠소?", "명나라와의 외교는 어땠소?"])
def test_politics_of_the_era_is_not_modern(msg):
    assert decide_mode(msg, [hit(0.9)], 0.3, False) != "modern"


@pytest.mark.parametrize("msg", ["요즘 정치 어때요?", "지금 외교 상황은?", "요즘 일본이랑 사이 어때요?",
                                 "대통령 누구예요?", "21세기에 대해", "선거 결과는?"])
def test_modern_markers(msg):
    assert decide_mode(msg, [hit(0.9)], 0.3, False) == "modern"


def test_focus_diary_is_named_as_the_day_asked(fake_client):
    h = hit(0.5)
    answer("그다음 날은요?", [h], [], "normal", client=fake_client, focus_ids=[h.entry.id])
    s = system_of(fake_client)
    assert h.entry.label in s and "묻는 날" in s
    assert "전날" in s and "다음 날" in s  # 근거를 전날·다음 날로 오해하지 말라는 지시


def test_no_focus_paragraph_without_date_match(fake_client):
    answer("배 멀미?", [hit(0.5)], [], "normal", client=fake_client)
    assert "묻는 날" not in system_of(fake_client)


def test_focus_ignores_ids_not_in_hits(fake_client):
    answer("x", [hit(0.5)], [], "normal", client=fake_client, focus_ids=["nope"])
    assert "묻는 날" not in system_of(fake_client)


def test_focus_label_is_also_attached_to_the_user_turn(fake_client):
    h = hit(0.5)
    answer("그다음 날은요?", [h], [], "normal", client=fake_client, focus_ids=[h.entry.id])
    last = fake_client.kwargs[0]["messages"][-1]
    assert last["role"] == "user"
    text = last["content"][0]["text"]
    assert text.startswith("그다음 날은요?") and h.entry.label in text and "가리키는 날" in text


def test_user_turn_unchanged_without_focus(fake_client):
    answer("배 멀미?", [hit(0.5)], [], "normal", client=fake_client)
    assert fake_client.kwargs[0]["messages"][-1]["content"][0]["text"] == "배 멀미?"


def test_system_prompt_forbids_generalizing_and_keeps_hao_endings(fake_client):
    answer("활은 매일 쏘셨소?", [hit(0.5)], [], "normal", client=fake_client)
    s = system_of(fake_client)
    assert "일부" in s and "일반화" in s          # 몇 날의 일기로 '매일·자주·한 번도'를 단정하지 않는다
    assert "습니다" in s and "나이다" in s          # 쓰지 말 어미를 구체적으로 못박는다


# ---- 답변 단계의 일기 밖 판별 ----
NO_BASIS = "처음 듣는 말이라 내 답할 길이 없소."


def test_model_says_no_basis_becomes_out_of_scope():
    top = hit(0.5)
    c = FakeClient(reply=NO_BASIS)
    r = answer("아이유 노래 들어보셨어요?", [top, hit(0.4)], [], "normal", client=c)
    assert c.calls == 1
    assert r["mode"] == "out_of_scope" and r["sources"] == []
    assert r["answer"] == "처음 듣는 말이라 내 답할 길이 없소. 대신 내 일기 이야기를 들려주리다."
    assert r["suggestions"] == top.entry.questions


def test_no_basis_is_detected_by_prefix_and_surrounding_noise():
    for reply in [NO_BASIS + " 다른 말을 덧붙였소.", "  " + NO_BASIS, '"' + NO_BASIS + '"']:
        r = answer("x", [hit(0.5)], [], "normal", client=FakeClient(reply=reply))
        assert r["mode"] == "out_of_scope" and r["sources"] == [], reply


def test_serious_mode_is_also_filtered():
    r = answer("x", [hit(0.5, "비통")], [], "serious", client=FakeClient(reply=NO_BASIS))
    assert r["mode"] == "out_of_scope"


def test_date_matched_question_is_never_converted():
    h = hit(0.1)
    r = answer("정유년 9월 16일", [h], [], "normal", client=FakeClient(reply=NO_BASIS), focus_ids=[h.entry.id])
    assert r["mode"] == "normal" and r["answer"] == NO_BASIS and len(r["sources"]) == 1


def test_normal_answer_that_merely_mentions_the_phrase_later_is_kept():
    reply = "그날은 맑았소. " + NO_BASIS
    r = answer("x", [hit(0.5)], [], "normal", client=FakeClient(reply=reply))
    assert r["mode"] == "normal" and len(r["sources"]) == 1


def test_system_prompt_tells_model_to_refuse_exactly():
    c = FakeClient()
    answer("x", [hit(0.5)], [], "normal", client=c)
    s = system_of(c)
    assert NO_BASIS in s and "아무 상관 없는" in s and "다른 말" in s


def test_prompt_separates_unrecorded_topic_from_unrelated_topic():
    c = FakeClient()
    answer("배 멀미 하셨어요?", [hit(0.5)], [], "normal", client=c)
    s = system_of(c)
    # 장군의 삶·전쟁·가족·건강처럼 당시 세계의 주제는 '일기에 적지 않아 모른다'로, 당시에 없던 주제만 고정 문구로
    assert "일기에 적지 않아" in s and "당시" in s and "현대" in s
    refuse = s.index(NO_BASIS)
    assert s.index("일기에 적지 않아") != refuse


def test_no_basis_phrase_after_leading_punctuation_is_still_detected():
    for lead in ["…", "「", "“", "— ", "...", "『 "]:
        r = answer("x", [hit(0.5, "비통")], [], "serious", client=FakeClient(reply=lead + NO_BASIS))
        assert r["mode"] == "out_of_scope" and r["sources"] == [], lead


def test_answer_starting_with_other_text_is_never_converted():
    for reply in ["그날은 맑았소. " + NO_BASIS, "처음 듣는 이야기이오만, 그날은 맑았소.", "1. " + NO_BASIS]:
        r = answer("x", [hit(0.5)], [], "normal", client=FakeClient(reply=reply))
        assert r["mode"] == "normal", reply


def test_prompt_quotes_the_refusal_phrase_instead_of_saying_above_phrase():
    c = FakeClient()
    answer("x", [hit(0.5)], [], "normal", client=c)
    assert "위 문구" not in system_of(c)
