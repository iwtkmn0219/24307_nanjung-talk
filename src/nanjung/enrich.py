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
INTRO_HARD_MAX = 60  # 검증 상한(약간 넘긴 소개로 적재가 실패하지 않게)

SYSTEM = f"""당신은 『난중일기』(이충무공전서본) 한문 원문을 현대 한국어로 옮기는 번역가다.
주어진 하루치 원문을 읽고 아래 키를 가진 JSON 객체 하나만 출력하라. 설명이나 다른 글은 쓰지 마라.
- "translation": 원문 전체를 한 구절도 빠뜨리지 않고 옮긴 자연스러운 현대 한국어 번역. 원문에 없는 내용은 덧붙이지 마라.
- "emotion": 그날 일기의 정서. 반드시 다음 네 값 중 하나: {", ".join(f'"{e}"' for e in EMOTIONS)}
- "intro": 이순신 장군이 1인칭 하오체로 그날을 소개하는 한 문장. {INTRO_MAX}자 이내. 문장 끝은 "~하였소", "~이었소", "~이오", "~다오"처럼 하오체로 맺고, "~네", "~했다", "~해요" 같은 말투는 쓰지 마라.
- "questions": 그날 일기 내용만으로 답할 수 있는, 사용자가 장군에게 물어볼 만한 질문 3개(문자열 배열).
번역 용어:
- 射帿·射侯 N巡: "활 N순을 쏘았다"로 옮겨라. 巡(순)은 화살 다섯 발을 한 차례로 쏘는 단위이므로 "N번"으로 옮기지 마라.
- 天只: 이 일기에서 '천지'는 어머니를 가리킨다. 사람 이름으로 옮기지 말고 "어머님"으로 옮겨라.
- 豚: 사람 이름 앞에 붙은 豚(豚薈·豚蔚·豚葂 등)은 자기 아들을 낮춰 부르는 말이다. "아들 회", "아들 울", "아들 면"처럼 옮기고 "돼지"로 옮기지 마라.
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
