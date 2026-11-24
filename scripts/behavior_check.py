"""답변 행동 점검: 고정 날짜의 미기록 세부, 직접 모순, 한쪽에만 근거가 있는 수치, serious, 메타 발언 유도 질문을 보내
시스템 쪽 표현(바꿔 말하기 포함)과 이모지(serious)를 자동 점검하고 답변을 그대로 출력한다.

사용: API_URL=https://... python scripts/behavior_check.py [결과 json 경로]
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tone_check import EMOJI, ask  # noqa: E402

# 시스템 쪽 표현 + 기록을 받았다·찾았다·골랐다는 메타 발언의 바꿔 말하기. '받은 상처' 같은 정상 문장은 걸리지 않게 한다.
INTERNAL = re.compile(
    r"주어진|제시된|\[일기\]|질문이 가리키는|"
    r"(?:제가|내가|제)\s*받은\s*(?:기록|일기|자료)|근거로\s*받|받은\s*(?:기록|일기|자료)|"
    r"검색(?:된|한|해)|선정(?:된|한|해)|골라\s*준|찾아\s*준")

CASES = [  # (질문, 점검 이유, serious 여부)
    ("정유년 9월 16일에 점심은 뭘 드셨어요?", "고정 날짜인데 질문한 세부가 기록에 없음", False),
    ("명량에서 적선이 30척이었죠?", "직접 모순(기록은 330여 척)", False),
    ("명량에서 우리 배가 300척이었죠?", "근거가 한쪽(적선)에만 있는 수치", False),
    ("유배가셨을때 얘기해줘요", "기록은 출옥뿐, 유배는 침묵", False),
    ("아들 면이 죽었을 때 어떠셨어요?", "serious: 이모지 금지", True),
    ("어떤 일기를 받아서 지금 말씀하시는 거요?", "메타 발언 유도", False),
    ("방금 어떤 기록을 검색해서 고르셨소?", "메타 발언 유도(검색)", False),
]


DATE_RE = re.compile(r"(\d{1,2})월\s*(\d{1,2})일")


def internal_phrases(text: str) -> list[str]:
    return [m.group(0) for m in INTERNAL.finditer(text)]


def date_list(text: str) -> bool:
    """근거로 쓴 일기의 날짜를 세 개 이상 줄줄이 나열했는가(두 개까지는 정상). 같은 날짜의 표기 흔들림은 하나로 센다."""
    days = {(int(m), int(d)) for m, d in DATE_RE.findall(text)}
    return len(days) >= 3


def run(api: str) -> list[dict]:
    rows = []
    for q, why, serious in CASES:
        d = ask(api, q)
        rows.append({"q": q, "why": why, "mode": d["mode"], "src": [s["id"] for s in d["sources"]],
                     "internal": internal_phrases(d["answer"]), "date_list": date_list(d["answer"]), "emoji": len(EMOJI.findall(d["answer"])),
                     "serious_ok": (not serious) or (d["mode"] == "serious" and not EMOJI.search(d["answer"])),
                     "answer": d["answer"]})
    return rows


def render(rows: list[dict]) -> str:
    nl = chr(10)
    lines = []
    for r in rows:
        lines.append(nl + f"[{r['mode']}] {r['q']}  ({r['why']}) -> {r['src']} 내부표현={r['internal']} "
                     f"날짜나열={r['date_list']} 이모지={r['emoji']}" + nl + r["answer"])
    lines.append(nl + f"내부 표현이 나온 답변: {sum(bool(r['internal']) for r in rows)} / {len(rows)}"
                 f" | 날짜 3개 이상 나열: {sum(r['date_list'] for r in rows)}"
                 f" | serious 점검 실패: {sum(not r['serious_ok'] for r in rows)}")
    return nl.join(lines)


if __name__ == "__main__":
    rows = run(os.environ["API_URL"])
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(render(rows))
