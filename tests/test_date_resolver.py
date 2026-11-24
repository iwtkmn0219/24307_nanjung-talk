import pytest

from nanjung.date_resolver import resolve

nb = {("1592-06-10", 1): "1592-08-24", ("1598-11-17", 1): None, ("1597-09-16", -1): "1597-09-15",
      ("1597-09-16", 1): "1597-09-17", ("1592-04-14", -1): "1592-04-13"}.get


def r(msg, last=()):
    return resolve(msg, list(last), lambda i, d: nb((i, d)))


def test_event():
    assert r("명량 때 어땠어요?") == ["1597-09-16"]


def test_event_minus_one():
    assert r("명량 전날 뭐 하셨어요?") == ["1597-09-15"]


def test_event_plus_one():
    assert r("명량 다음날은요?") == ["1597-09-17"]


def test_next_day_skips_gap():
    assert r("그다음 날은요?", ["1592-06-10"]) == ["1592-08-24"]


def test_next_day_at_end_returns_none():
    assert r("그다음 날은요?", ["1598-11-17"]) is None


def test_next_day_without_history():
    assert r("다음날은?") is None


@pytest.mark.parametrize("msg", ["이튿날은요?", "그 다음 날?", "다음 날 이야기"])
def test_next_day_variants(msg):
    assert r(msg, ["1592-06-10"]) == ["1592-08-24"]


@pytest.mark.parametrize("msg", ["전날은요?", "그 전날은?", "前날은?"])
def test_previous_day_variants(msg):
    assert r(msg, ["1592-04-14"]) == ["1592-04-13"]


@pytest.mark.parametrize("msg,expected", [
    ("임진왜란 때 뭐 하셨어요?", "1592-04-13"),
    ("왜란 터진 날", "1592-04-13"),
    ("어머니 돌아가셨을 때", "1597-04-13"),
    ("어머님 부고를 들으셨을 때", "1597-04-13"),
    ("면이 전사했을 때", "1597-10-14"),
    ("아들 면이 죽었을 때", "1597-10-14"),
    ("백의종군 하실 때", "1597-04-01"),
    ("감옥에서 나오셨을 때", "1597-04-01"),
    ("노량 해전", "1598-11-17"),
    ("마지막 일기", "1598-11-17"),
    ("마지막 날 일기", "1598-11-17"),
    ("면의 죽음", "1597-10-14"),
    ("아들이 죽었다는 소식", "1597-10-14"),
])
def test_event_dictionary(msg, expected):
    assert r(msg) == [expected]


def test_explicit_dates():
    assert r("정유년 9월 16일 일기") == ["1597-09-16"]
    assert r("1596년 윤8월 1일") == ["1596-L08-01"]
    assert r("임진년 4월13일") == ["1592-04-13"]


def test_explicit_date_beats_event():
    assert r("명량 말고 정유년 9월 1일") == ["1597-09-01"]
    assert r("정유년 9월 16일 일기를 마지막으로 보여 주시오") == ["1597-09-16"]


@pytest.mark.parametrize("msg", ["그러면 죽을 뻔했소?", "마지막으로 묻겠소", "라면 먹다 죽는 줄", "마지막 질문이오"])
def test_common_words_are_not_events(msg):
    assert r(msg) is None


def test_plain_question():
    assert r("배 멀미 하셨어요?") is None


def test_mother_word_alone_is_not_event():
    assert r("어머니 보고 싶으셨어요?") is None


def test_explicit_date_with_relative_uses_that_date_as_anchor():
    assert r("정유년 9월 16일 전날", ["1592-06-10"]) == ["1597-09-15"]


@pytest.mark.parametrize("msg", [
    "유배가셨을때 얘기해줘요", "옥살이 하실 때 어떠셨어요?", "귀양 가신 적 있으세요?", "투옥되셨을 때는요?",
    "옥에 갇히셨을 때 마음이 어땠어요?", "파직당하셨을 때 기분이 어땠어요?", "하옥되신 이유가 뭐예요?", "압송되셨을 때 이야기해 주세요",
])
def test_imprisonment_and_exile_words_map_to_release_day(msg):
    assert r(msg) == ["1597-04-01"]


@pytest.mark.parametrize("msg", ["옥수수 좋아하세요?", "독옥이 뭐예요?", "배 멀미 하셨어요?", "배를 타고 가셨어요?",
                                 "압력이 높았나요?", "파도가 높았던 날은?", "옥구슬을 보셨어요?"])
def test_words_that_merely_contain_the_syllables_do_not_match(msg):
    assert r(msg) is None


def test_event_words_combine_with_relative_day():
    nb2 = {("1597-04-01", 1): "1597-04-02"}.get
    assert resolve("유배 다음날은요?", [], lambda i, d: nb2((i, d))) == ["1597-04-02"]


# ---- 리뷰 반영: 여러 사건에 쓰이는 말·충돌·부정·입옥 시점 ----
@pytest.mark.parametrize("msg", [
    "유배가 아니라 노량에서의 상황을 묻소",              # 충돌 + 부정
    "유배 말고 다른 이야기 해줘요",                      # 부정
    "유배는 아니고 명량 이야기가 궁금해요",
    "포로 압송 기록이 있나요?",                          # 장군 본인 맥락 없는 압송
    "원균은 언제 파직됐어요?",                            # 장군 본인 맥락 없는 파직
    "명량과 노량 이야기를 해줘요",                        # 사건 둘
])
def test_conflicting_negated_or_not_about_the_general_falls_back_to_general_search(msg):
    assert r(msg) is None


@pytest.mark.parametrize("msg", ["압송되셨을 때 이야기해 주세요", "장군께서 파직당하셨을 때는요?", "본인이 압송된 이유가 뭐예요?"])
def test_ambiguous_words_map_when_the_question_is_about_the_general(msg):
    assert r(msg) == ["1597-04-01"]


def test_entering_prison_words_do_not_anchor_a_relative_day_on_the_release_day():
    # '투옥 다음 날'은 입옥이 아니라 출옥을 기준으로 이웃 날짜를 구하면 안 된다 → 직전 근거 기준
    assert r("투옥 다음 날은요?") is None
    assert r("투옥 다음 날은요?", ["1592-06-10"]) == ["1592-08-24"]
    assert r("하옥 다음날은?", ["1592-06-10"]) == ["1592-08-24"]
    assert r("투옥되셨을 때는요?") == ["1597-04-01"]      # 상대 표현이 없으면 그대로 출옥일


def test_release_words_still_anchor_relative_day():
    nb2 = {("1597-04-01", 1): "1597-04-02", ("1597-04-01", -1): "1597-03-31"}.get
    assert resolve("출옥 다음 날은요?", [], lambda i, d: nb2((i, d))) == ["1597-04-02"]
    assert resolve("유배 전날은요?", [], lambda i, d: nb2((i, d))) == ["1597-03-31"]


def test_explicit_date_still_wins_over_negated_or_conflicting_events():
    assert r("유배 말고 정유년 9월 16일 일기") == ["1597-09-16"]
    assert r("노량과 유배 말고 정유년 9월 1일은요?") == ["1597-09-01"]


def test_ambiguous_word_without_the_general_does_not_pull_in_the_release_day():
    # 압송이 본인 맥락이 아니면 사건으로 치지 않으므로 노량 하나만 남는다(출옥일 아님)
    assert r("노량 전투 뒤 포로 압송에 관한 기록이 있소?") == ["1598-11-17"]


# ---- 재리뷰 반영: 입옥 표현이 강한 키워드와 겹침 / 제3자 존칭 / 충돌·부정 + 상대 표현 ----
def test_entering_prison_phrase_wins_over_strong_word_for_anchoring():
    assert r("감옥에 갇히신 다음 날은요?") is None
    assert r("감옥에 갇히신 다음 날은요?", ["1592-06-10"]) == ["1592-08-24"]
    assert r("감옥에 갇혔을 때는요?") == ["1597-04-01"]      # 상대 표현이 없으면 같은 날로는 간다


@pytest.mark.parametrize("msg", ["원균께서 파직되셨을 때는요?", "권율 장군께서 파직당하셨을 때는요?", "임금께서 압송을 명하셨나요?",
                                 "포로가 압송되셨을 때는요?"])
def test_ambiguous_words_with_a_named_third_party_do_not_map(msg):
    assert r(msg) is None


def test_generals_own_ambiguous_phrases_still_map():
    assert r("장군께서 파직당하셨을 때는요?") == ["1597-04-01"]
    assert r("압송되셨을 때 이야기해 주세요") == ["1597-04-01"]


@pytest.mark.parametrize("msg", ["명량과 노량 전날은요?", "유배 말고 노량 전날은요?", "유배 말고 전날은요?",
                                 "유배는 아니고 명량 다음날은요?"])
def test_conflict_or_negation_with_relative_day_goes_to_general_search_not_previous_diary(msg):
    assert r(msg, ["1592-06-10"]) is None


def test_followup_without_any_event_still_uses_previous_diary():
    assert r("그다음 날은요?", ["1592-06-10"]) == ["1592-08-24"]
    assert r("그 전날은요?", ["1597-09-16"]) == ["1597-09-15"]


def test_explicit_date_still_beats_conflict_and_negation_with_relative_day():
    assert r("유배 말고 정유년 9월 16일 전날은요?", ["1592-06-10"]) == ["1597-09-15"]


# ---- 명량 키워드 확장: 울돌목·鳴梁 단독, 12·13척은 싸움 동사와 함께 ----
@pytest.mark.parametrize("msg", ["울돌목에서 무슨 일이 있었어요?", "鳴梁 이야기를 해 주세요", "울돌목 해전은 어땠소?"])
def test_ulddolmok_and_myeongnyang_hanja_map_alone(msg):
    assert r(msg) == ["1597-09-16"]


@pytest.mark.parametrize("msg", [
    "12척의 배로 이긴 것이 사실?", "13척으로 싸우셨나요?",
    "열두 척으로 승리하셨죠?", "열세 척의 배로 물리치셨다던데요", "12척으로 대첩을 거두셨어요?", "열두척으로 이긴 게 맞아요?",
    "12 척으로 전투를 치르셨죠?",
])
def test_twelve_or_thirteen_ships_with_a_fighting_verb_map(msg):
    assert r(msg) == ["1597-09-16"]


@pytest.mark.parametrize("msg", [
    "배 12척을 만들었나요?", "열두 척이 있었나요?", "13척의 배는 어디에 있었어요?", "112척으로 이기셨어요?", "열두 척 정도 보셨어요?",
])
def test_ship_counts_without_a_fighting_verb_do_not_map(msg):
    assert r(msg) is None


def test_new_myeongnyang_words_work_with_relative_day_and_explicit_date():
    nb2 = {("1597-09-16", -1): "1597-09-15"}.get
    assert resolve("울돌목 전날은요?", [], lambda i, d: nb2((i, d))) == ["1597-09-15"]
    assert r("12척으로 이긴 날 말고 정유년 9월 1일은요?") == ["1597-09-01"]


# ---- '오늘' 질문 → 오늘의 일기 ----
@pytest.mark.parametrize("msg", [
    "오늘의 장군님은 어떠셨습니까", "오늘의 일기 보여 주세요", "오늘 일기 알려줘요", "오늘은 어떠셨어요?", "오늘 장군님은 뭐 하세요?",
    "오늘의 장군은요?", "430년 전 오늘 무슨 일이 있었어요?", "400년 전 오늘은요?",
])
def test_today_expressions_are_detected(msg):
    from nanjung.date_resolver import is_today_question
    assert is_today_question(msg) is True


@pytest.mark.parametrize("msg", ["오늘 점심 메뉴 추천해 주세요", "오늘 날씨 어때요?", "오늘날의 정치", "배 멀미 하셨어요?", "일기는 매일 쓰셨어요?",
                                 "오늘 뭐 먹을까요?"])
def test_plain_today_word_alone_is_not_enough(msg):
    from nanjung.date_resolver import is_today_question
    assert is_today_question(msg) is False
