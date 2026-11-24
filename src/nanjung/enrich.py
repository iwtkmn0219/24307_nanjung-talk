"""일기 하루치를 번역하고 감정·소개·추천 질문을 붙인다."""
from __future__ import annotations

import json
import re
from dataclasses import replace

from . import bedrock
from .models import EMOTIONS, DiaryEntry

MAX_TOKENS = 4096  # 플랜은 1500이나 가장 긴 날(609자)이 잘림(실측)
TEMPERATURE = 0.2
INTRO_MAX = 40       # 프롬프트 요구
INTRO_HARD_MAX = 80  # 검증 상한(넘긴 소개로 적재가 실패하지 않게. 61자 이상이 2회 연속 나온 실측 있음)

# 감정 기준(번역과 감정 재분류가 같은 기준을 쓴다). 비통은 화면 전체를 잿빛으로 가라앉히므로 좁게 쓴다.
EMOTION_RULES = """- "비통": 죽음·상실·통곡·애도에만 쓴다(어머니·아들·가족의 죽음, 전사자, 기일·제사의 슬픔, 통곡 등).
- 몸이 아픈 병고, 걱정·근심·불면, 쓸쓸함·그리움 정도는 "비통"이 아니다. 대개 "일상"으로 분류하고, 원망·화가 뚜렷하면 "분노", 투덜거림·익살이 뚜렷하면 "유머·불평"으로 분류한다.
- 그 밖의 평범한 기록은 "일상"이다."""

SYSTEM = f"""당신은 『난중일기』(이충무공전서본) 한문 원문을 현대 한국어로 옮기는 번역가다.
주어진 하루치 원문을 읽고 아래 키를 가진 JSON 객체 하나만 출력하라. 설명이나 다른 글은 쓰지 마라.
- "translation": 원문 전체를 한 구절도 빠뜨리지 않고 옮긴 자연스러운 현대 한국어 번역. 원문에 없는 내용은 덧붙이지 마라.
- "emotion": 그날 일기의 정서. 반드시 다음 네 값 중 하나: {", ".join(f'"{e}"' for e in EMOTIONS)}
{EMOTION_RULES}
- "intro": 이순신 장군이 1인칭 하오체로 그날을 소개하는 한 문장. {INTRO_MAX}자 이내. 문장 끝은 "~하였소", "~이었소", "~이오", "~다오"처럼 하오체로 맺고, "~네", "~했다", "~해요" 같은 말투는 쓰지 마라.
- "questions": 그날 일기 내용만으로 답할 수 있는, 사용자가 장군에게 물어볼 만한 질문 3개(문자열 배열).
번역 용어:
- 射帿·射侯 N巡: "활 N순을 쏘았다"로 옮겨라. 巡(순)은 화살 다섯 발을 한 차례로 쏘는 단위이므로 "N번"으로 옮기지 마라.
- 天只: 이 일기에서 '천지'는 어머니를 가리킨다. 사람 이름으로 옮기지 말고 "어머님"으로 옮겨라.
- 豚: 사람 이름 앞에 붙은 豚(豚薈·豚蔚·豚葂·豚䓲 등)은 자기 아들을 낮춰 부르는 말이다. "아들 회", "아들 울", "아들 면", "아들 열"처럼 옮기고 "돼지"로 옮기지 마라.
- 䓲: 이순신의 아들 '열'의 이름이다(豚䓲도 "아들 열"). 회·강·면 등 다른 이름으로 옮기지 마라.
- 東軒: 동헌, 公事: 공무, 望闕禮: 망궐례처럼 고유한 관직·의례 용어는 한자음 그대로 살려라."""

FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


class EnrichError(Exception):
    pass


def build_prompt(e: DiaryEntry) -> tuple[str, list[dict]]:
    text = f"날짜: {e.label}\n원문:\n{e.original}"
    return SYSTEM, [{"role": "user", "content": [{"text": text}]}]


def parse_response(text: str) -> dict:
    m = FENCE_RE.match(text)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as ex:
        raise EnrichError(f"JSON 아님: {text[:80]!r}") from ex
    if not isinstance(data, dict):
        raise EnrichError("객체가 아님")
    tr, emo, intro, qs = (data.get(k) for k in ("translation", "emotion", "intro", "questions"))
    if not isinstance(tr, str) or not tr.strip():
        raise EnrichError("translation 없음")
    if emo not in EMOTIONS:
        raise EnrichError(f"emotion 값 오류: {emo!r}")
    if not isinstance(intro, str) or not intro.strip() or len(intro.strip()) > INTRO_HARD_MAX:
        raise EnrichError("intro 오류")
    if not isinstance(qs, list) or len(qs) != 3 or not all(isinstance(q, str) and q.strip() for q in qs):
        raise EnrichError("questions는 문자열 3개여야 함")
    return {"translation": tr.strip(), "emotion": emo, "intro": intro.strip(),
            "questions": [q.strip() for q in qs]}


def enrich(e: DiaryEntry, client=None) -> DiaryEntry:
    system, messages = build_prompt(e)
    last: EnrichError | None = None
    for _ in range(2):
        text = bedrock.converse(system, messages, MAX_TOKENS, TEMPERATURE, client=client)
        try:
            return replace(e, **parse_response(text))
        except EnrichError as ex:
            last = ex
    raise last


# ---- 감정만 다시 분류(번역·소개는 그대로 두고 비용을 줄인다) ----
EMOTION_MAX_TOKENS = 100

EMOTION_SYSTEM = f"""당신은 『난중일기』 하루치의 정서를 분류한다. 원문과 현대어 번역을 읽고 JSON 객체 하나만 출력하라: {{"emotion": "<값>"}}
값은 반드시 다음 네 값 중 하나: {", ".join(f'"{e}"' for e in EMOTIONS)}
{EMOTION_RULES}"""


def build_emotion_prompt(original: str, translation: str) -> tuple[str, list[dict]]:
    return EMOTION_SYSTEM, [{"role": "user", "content": [{"text": f"원문:\n{original}\n\n번역:\n{translation}"}]}]


def parse_emotion(text: str) -> str:
    m = FENCE_RE.match(text)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as ex:
        raise EnrichError(f"JSON 아님: {text[:80]!r}") from ex
    emo = data.get("emotion") if isinstance(data, dict) else None
    if emo not in EMOTIONS:
        raise EnrichError(f"emotion 값 오류: {emo!r}")
    return emo


def reclassify(original: str, translation: str, client=None) -> str:
    system, messages = build_emotion_prompt(original, translation)
    last: EnrichError | None = None
    for _ in range(2):
        text = bedrock.converse(system, messages, EMOTION_MAX_TOKENS, 0.0, client=client)
        try:
            return parse_emotion(text)
        except EnrichError as ex:
            last = ex
    raise last
