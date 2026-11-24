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
