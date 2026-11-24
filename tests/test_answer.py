from datetime import date

import pytest

from nanjung.answer import (FIXED_MODERN, FIXED_OUT, FIXED_SUGGESTIONS, MODERN_MARKERS, answer, decide_mode,
                            fixed_suggestions, source_card)
from nanjung.models import SOURCE_NOTE, DiaryEntry, Hit

_n = iter(range(10_000))


def assert_fixed_chips(chips):
    assert len(chips) == 3 and len(set(chips)) == 3 and set(chips) <= set(FIXED_SUGGESTIONS), chips


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
    assert r["sources"] == [] and r["mode"] == "out_of_scope"
    assert_fixed_chips(r["suggestions"])                       # 검색 1등 일기의 질문이 아니라 고정 세트에서


def test_modern_does_not_call_llm(fake_client):
    r = answer("요즘 일본이랑 사이 어때요?", [hit(0.9)], [], "modern", client=fake_client)
    assert fake_client.calls == 0 and r["answer"].startswith(FIXED_MODERN) and r["sources"] == []
    assert FIXED_MODERN == "후대의 일은 모르오." and FIXED_OUT == "처음 듣는 말이라 내 답할 길이 없소."


def test_fixed_answer_with_no_hits_still_has_fixed_suggestions(fake_client):
    assert_fixed_chips(answer("x", [], [], "out_of_scope", client=fake_client)["suggestions"])


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


def card(original, translation):
    c = source_card(hit(0.5, original=original, translation=translation))
    return c["original_line"], c["translation_line"]


def test_source_card_skips_header_and_weather_and_shows_the_content_sentence():
    h = hit(0.5, original="十三日壬寅。晴。出東軒公事。")
    c = source_card(h)
    # 사용자 결정: 날짜·간지 머리 문장과 날씨 문장을 건너뛰고 내용 문장을 보여 준다(이전 계약: 첫 문장 '十三日壬寅。')
    assert c == {"id": h.entry.id, "label": h.entry.label, "original_line": "出東軒公事。",
                 "translation_line": "동헌에 나가 공무를 보았다.", "note": SOURCE_NOTE}


def test_source_card_original_joins_short_sentences_until_enough_content():
    assert card("十七日乙巳。陰。曉。右水使來見。", "17일 을사. 흐림. 새벽. 우수사가 와서 보았다.") ==         ("曉。右水使來見。", "새벽. 우수사가 와서 보았다.")
    # 내용 문장이 충분히 길면 하나만
    assert card("初一日辛酉。晴。得出圓門。到南門外尹生侃奴家。則菶芬同坐。", "초하루 신유일. 맑다. 옥문을 나오게 되어 남문 밖 윤생 간의 종의 집에 도착했다.")[0]         == "得出圓門。到南門外尹生侃奴家。"


def test_source_card_translation_headers_and_weather_forms():
    cases = [
        ("17일 을사. 맑음. 동헌에 나가 공무를 보았다. 활 열다섯 순을 쏘았다.", "동헌에 나가 공무를 보았다."),
        ("초하루 신유일. 맑다. 아침에 공무를 보았다. 늦게 돌아왔다.", "아침에 공무를 보았다. 늦게 돌아왔다."),
        ("초여섯 날 기사. 비가 내렸다. 종일 앉아 있었다.", "종일 앉아 있었다."),
        ("초이레 병오날. 맑고 따뜻하다. 군사들을 점검하고 활을 쏘았다.", "군사들을 점검하고 활을 쏘았다."),
        ("13일 임인. 흐렸다. 새벽. 비가 왔다.", "새벽. 비가 왔다."),
        ("10일. 맑다. 장수들이 와서 의논했다.", "장수들이 와서 의논했다."),
    ]
    for tr, want in cases:
        assert card("十三日壬寅。晴。出東軒公事。", tr)[1] == want, tr


def test_source_card_skips_up_to_two_leading_weather_sentences():
    assert card("十三日壬寅。陰。雨雨終日。坐東軒。處置公事。", "13일 임인. 흐림. 종일 비가 내렸다. 동헌에 앉아 공무를 처리했다.") ==         ("坐東軒。處置公事。", "동헌에 앉아 공무를 처리했다.")


def test_source_card_falls_back_to_first_sentence_when_nothing_follows_the_header():
    assert card("初六日己巳。晴。", "초엿새 기사. 맑다.") == ("初六日己巳。", "초엿새 기사.")
    assert card("十三日壬寅。", "13일 임인.") == ("十三日壬寅。", "13일 임인.")


def test_source_card_keeps_a_first_sentence_that_has_content_inside_the_header():
    assert card("二十四日干支缺到柚島結陣。晴。", "24일 간지 빠짐. 유도에 도착해 진을 쳤다. 맑다.")[0].startswith("二十四日干支缺到柚島結陣。")


def test_source_card_content_is_capped_at_60():
    c = source_card(hit(0.5, original="十三日壬寅。晴。" + "甲" * 100 + "。"))
    assert len(c["original_line"]) == 60
    long_tr = "17일 을사. 맑음. " + "가" * 100 + "."
    assert len(source_card(hit(0.5, translation=long_tr))["translation_line"]) <= 60


def test_source_card_weather_sentence_after_content_is_not_dropped():
    assert card("十三日壬寅。出東軒。晴。", "13일 임인. 동헌에 나갔다. 맑다.") == ("出東軒。晴。", "동헌에 나갔다. 맑다.")


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
    assert_fixed_chips(r["suggestions"])


def test_no_basis_is_detected_by_prefix_and_surrounding_noise():
    for reply in [NO_BASIS + " 다른 말을 덧붙였소.", "  " + NO_BASIS, '"' + NO_BASIS + '"']:
        r = answer("x", [hit(0.5)], [], "normal", client=FakeClient(reply=reply))
        assert r["mode"] == "out_of_scope" and r["sources"] == [], reply


def test_serious_mode_is_also_filtered():
    r = answer("x", [hit(0.5, "비통")], [], "serious", client=FakeClient(reply=NO_BASIS))
    assert r["mode"] == "out_of_scope"


def test_date_matched_question_with_refusal_becomes_out_of_scope_without_cards():
    # 날짜 + 현대·무관 주제 혼합("명량 때 아이유 노래…"): 거절 문구면 카드 없이 chip만 보인다
    h = hit(0.1)
    r = answer("명량 때 아이유 노래 들어보셨어요?", [h], [], "normal", client=FakeClient(reply=NO_BASIS),
               focus_ids=[h.entry.id])
    assert r["mode"] == "out_of_scope" and r["sources"] == []
    assert r["answer"] == "처음 듣는 말이라 내 답할 길이 없소. 대신 내 일기 이야기를 들려주리다."
    assert_fixed_chips(r["suggestions"])


def test_date_matched_normal_answer_is_kept():
    h = hit(0.1)
    r = answer("정유년 9월 16일", [h], [], "normal", client=FakeClient(reply="그날은 맑았소."), focus_ids=[h.entry.id])
    assert r["mode"] == "normal" and r["answer"] == "그날은 맑았소." and len(r["sources"]) == 1


def test_focus_note_allows_refusal_only_for_unrelated_modern_topic(fake_client):
    h = hit(0.5)
    answer("명량 때 아이유 노래?", [h], [], "normal", client=fake_client, focus_ids=[h.entry.id])
    s = system_of(fake_client)
    assert "라고도 답하지 마시오" not in s            # 날짜가 있어도 현대·무관 주제면 거절해야 한다
    assert "현대" in s and NO_BASIS in s and "날짜" in s


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


# ---- 틀린 전제 바로잡기 / 시스템 쪽 표현 금지 ----
def test_prompt_tells_model_to_correct_false_premises_from_the_diary():
    c = FakeClient()
    answer("유배가셨을때 얘기해줘요", [hit(0.5)], [], "normal", client=c)
    s = system_of(c)
    assert "전제" in s and "바로잡" in s
    assert "직접 모순" in s                          # 같은 사람·날·사건에 대해 기록이 직접 모순될 때만 정정
    assert "침묵" in s and "유보" in s               # 기록이 말이 없거나 대상이 다르면 유보
    assert "지어내지" in s and "일기에 적지 않아" in s  # 근거 없는 전제는 바로잡지도 지어내지도 않는다
    assert "유배가 아니라" not in s                  # 출옥 기록만으로 유배 여부까지 부정하게 가르치지 않는다
    assert "유배에 관한 일은 일기에 적지 않았소" in s  # 예시: 출옥 사실은 말하되 유배는 유보


def test_prompt_bans_system_side_wording_and_requires_first_person():
    c = FakeClient()
    answer("x", [hit(0.5)], [], "normal", client=c)
    s = system_of(c)
    for banned in ["주어진 일기", "[일기]", "질문이 가리키는 날"]:
        assert banned in s                           # 금지 목록에 명시
    assert "내 일기" in s and "그날 나는" in s and "1인칭" in s
    assert "나열" in s                               # 근거로 받은 연도·날짜 목록 나열 금지


def test_premise_and_wording_instructions_are_in_every_mode():
    for mode, emo in (("normal", "일상"), ("serious", "비통")):
        c = FakeClient()
        answer("x", [hit(0.5, emo)], [], mode, client=c)
        assert "바로잡" in system_of(c) and "내 일기" in system_of(c), mode


def test_prompt_forbids_meta_talk_about_receiving_or_searching_records():
    c = FakeClient()
    answer("x", [hit(0.5)], [], "normal", client=c)
    s = system_of(c)
    assert "받았다" in s and "검색" in s and "선정" in s     # 기록을 받았다·찾았다·골랐다는 설명 금지(뜻으로)
    assert "제가 받은 기록" in s and "근거로 받은 일기" in s   # 금지 예시


def test_focus_note_separates_found_day_from_missing_detail():
    c = FakeClient()
    h = hit(0.5)
    answer("정유년 9월 16일 점심은?", [h], [], "normal", client=c, focus_ids=[h.entry.id])
    s = system_of(c)
    assert "세부" in s and "그날 있었던 일" in s and "적지 않았" in s


# ---- 모르는 질문도 장군답게: 관련해 남은 일을 먼저, 세부는 없다고 덧붙이기, 같은 말 반복 금지 ----
def test_prompt_leads_with_related_diary_content_instead_of_a_fixed_opener():
    c = FakeClient()
    answer("배 멀미 하셨어요?", [hit(0.5)], [], "normal", client=c)
    s = system_of(c)
    assert "고정 문구처럼 맨 앞에" in s                       # '일기에 적지 않아 모르겠소.'를 맨 앞에 두지 않는다
    assert "먼저" in s and "실제로 남은 일" in s                # 관련해 일기에 실제로 남은 일을 먼저
    assert "그다음" in s or "덧붙" in s                          # 묻는 세부가 기록에 없다는 말은 간단히 뒤에
    assert "한 줄" in s and "솔직" in s                          # 정말 말할 근거가 없으면 한 줄로


def test_prompt_varies_the_unrecorded_phrase_and_forbids_repeating_in_one_answer():
    c = FakeClient()
    answer("x", [hit(0.5)], [], "normal", client=c)
    s = system_of(c)
    assert "매번 다르게" in s and "두 번" in s                   # 표현은 매번 바꾸고 같은 내용을 한 답변에서 두 번 하지 않는다
    assert "일기에 적지 않아" in s                               # 기존 표현은 예시로 남는다


def test_prior_rules_are_kept_with_the_new_tone_rule():
    c = FakeClient()
    answer("x", [hit(0.5)], [], "serious", client=c)
    s = system_of(c)
    for kept in ["3문장 이내", "지어내", "직접 모순", "이모지", "하오체", "처음 듣는 말이라 내 답할 길이 없소."]:
        assert kept in s, kept


def test_source_card_short_content_followed_by_a_long_sentence_is_truncated_not_left_short():
    long_k = "꿈에 나는 말을 타고 언덕 위를 다니다가 말이 발을 헛디뎌 내가 개울에 떨어졌는데도 넘어지지 않았다."
    o, t = card("十四日辛未。晴。夜四更。" + "夢" * 80 + "。", "14일 신미. 맑음. 새벽 4경. " + long_k)
    assert t.startswith("새벽 4경. 꿈에 나는") and len(t) == 60 and t.endswith("…")   # 잘렸다는 표시
    assert o.startswith("夜四更。夢") and len(o) == 60 and o.endswith("…")


def test_source_card_enough_content_before_the_cap_is_not_ellipsized():
    _, t = card("十三日壬寅。出東軒公事。", "13일 임인. 동헌에 나가 공무를 보았다. 활을 쏘았다.")
    assert t == "동헌에 나가 공무를 보았다." and "…" not in t


# ---- 일기 밖·현대 질문의 추천 질문은 고정 세트에서 ----
def test_fixed_suggestion_set_size_style_and_safety():
    assert 8 <= len(FIXED_SUGGESTIONS) <= 10 and len(set(FIXED_SUGGESTIONS)) == len(FIXED_SUGGESTIONS)
    for q in FIXED_SUGGESTIONS:
        assert q.endswith("?") and ("습니까" in q or "십니까" in q), q        # 기존 chip 어투: 장군께 묻는 존대 질문
        assert not any(m in q for m in MODERN_MARKERS), q                  # 눌렀을 때 현대 질문으로 막히면 안 된다
        assert len(q) <= 40, q


def test_fixed_suggestions_pick_three_distinct_and_rotate():
    import random
    a = fixed_suggestions(random.Random(1))
    assert len(a) == 3 and len(set(a)) == 3 and set(a) <= set(FIXED_SUGGESTIONS)
    assert fixed_suggestions(random.Random(1)) == a                        # 같은 씨앗이면 같은 결과
    seen = set()
    for _ in range(60):
        seen |= set(fixed_suggestions())
    assert seen == set(FIXED_SUGGESTIONS)                                  # 호출마다 돌려 써서 전부 노출된다


def test_modern_answer_uses_fixed_suggestions_even_with_irrelevant_top_hit(fake_client):
    r = answer("요즘 정치 어때요?", [hit(0.9)], [], "modern", client=fake_client)
    assert_fixed_chips(r["suggestions"]) and r["sources"] == []


def test_normal_and_serious_keep_the_top_hits_own_questions(fake_client):
    top = hit(0.6)
    assert answer("x", [top], [], "normal", client=fake_client)["suggestions"] == top.entry.questions
    grief = hit(0.6, "비통")
    assert answer("x", [grief], [], "serious", client=fake_client)["suggestions"] == grief.entry.questions


def test_prompt_forbids_adding_feelings_reasons_or_methods_not_in_the_diary():
    c = FakeClient()
    answer("편지를 받으면 기분이 어땠어요?", [hit(0.5)], [], "normal", client=c)
    s = system_of(c)
    assert "느낌" in s and "이유" in s and "결심" in s and "방법" in s     # 일기에 없는 감정·이유·결심·방법 덧붙이기 금지
    assert "도리라 여겼소" in s and "덧붙이지" in s                        # 실제로 나온 사례를 금지 예시로


# ---- 리뷰 반영: 날짜 표기·날씨는 문장 전체와 대조한다 ----
def test_card_keeps_a_sentence_with_a_name_that_contains_a_weather_character():
    assert card("二十八日甲辰。晴。申霽雲除主簿而去。", "28일 갑진. 맑음. 신제운이 주부에서 물러나 떠났다.") == \
        ("申霽雲除主簿而去。", "신제운이 주부에서 물러나 떠났다.")


def test_card_keeps_short_event_sentences_that_start_with_a_weather_character():
    assert card("十四日乙卯。風折船。", "14일 을묘. 바람이 불어 배가 부러졌다.") == ("風折船。", "바람이 불어 배가 부러졌다.")
    assert card("十三日壬寅。晴。風折船。", "13일 임인. 맑다. 배가 바람에 부러졌다.") == ("風折船。", "배가 바람에 부러졌다.")


def test_card_does_not_cut_an_event_attached_to_the_date():
    assert card("十四日出戰。", "14일 출전.") == ("十四日出戰。", "14일 출전.")
    assert card("十四日出戰。晴。賊船來。", "14일 출전. 맑다. 적선이 왔다.")[0].startswith("十四日出戰。")


def test_card_keeps_solar_term_info_after_the_ganji_header():
    o, t = card("十一日乙酉冬至。曉。行望闕禮。", "11일 을유 동지. 새벽. 망궐례를 행했다.")
    assert o.startswith("十一日乙酉冬至。") and "行望闕禮" in o
    assert t.startswith("11일 을유 동지.")


def test_card_skips_missing_ganji_header_and_its_weather_marker():
    assert card("二十四日干支。缺晴。申時。發船。", "24일 간지 빠짐. 맑음. 신시에 배를 출발시켰다.") == ("申時。發船。", "신시에 배를 출발시켰다.")


def test_card_weather_is_matched_against_the_whole_sentence():
    # 날씨 단어가 들어 있어도 사건이 붙은 문장은 날씨가 아니다
    assert card("十三日壬寅。晴而軍器點。", "13일 임인. 맑은 날 군기를 점검했다.") == ("晴而軍器點。", "맑은 날 군기를 점검했다.")
    assert card("十三日壬寅。晴。出東軒。", "13일 임인. 새벽에 배를 출발했다.")[1] == "새벽에 배를 출발했다."
    # 실제 날씨 표현은 건너뛴다
    for w_o, w_k in [("陰而不雨", "흐리고 비는 오지 않았다."), ("朝陰晩晴", "아침은 흐리고 저녁은 맑았다."),
                     ("雨下如注", "비가 쏟아지듯 내렸다."), ("晴且無風", "맑고 바람이 없다."), ("風雨大作", "큰 바람과 비가 불었다.")]:
        assert card(f"十三日壬寅。{w_o}。出東軒。", f"13일 임인. {w_k} 동헌에 나갔다.") == ("出東軒。", "동헌에 나갔다."), w_o


def test_card_preserves_original_punctuation_and_handles_translation_without_spaces_or_with_newlines():
    assert card("十三日壬寅。晴。出東軒公事", "13일 임인. 맑다. 동헌에 나갔다.")[0] == "出東軒公事"          # 없던 '。'를 붙이지 않는다
    assert card("十三日壬寅。晴。出東軒。", "13일 임인.맑다.동헌에 나갔다.")[1] == "동헌에 나갔다."          # 공백 없는 문장
    nl = chr(10)
    assert card("十三日壬寅。晴。出東軒。", "13일 임인。" + nl + "맑다。" + nl + "동헌에 나갔다。")[1] == "동헌에 나갔다。"   # 。와 줄바꿈
    assert card("十三日壬寅。晴。出東軒。", "13일 임인. 맑다. 값이 3.5냥이었다.")[1] == "값이 3.5냥이었다."     # 소수점은 경계가 아니다
