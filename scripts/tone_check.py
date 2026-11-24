"""말투 수동 점검용: 배포된 API에 대표 질문 10개를 보내 모드·근거·이모지·답변을 출력한다(Task 13 Step 3).

사용: API_URL=https://... python scripts/tone_check.py [결과 json 경로]
질문마다 새 X-Client-Id를 써서 하루 한도에 걸리지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import uuid

EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
FIRST = "임진왜란 터진 날 뭐 하고 계셨어요?"
QUESTIONS = ["배 멀미 하셨어요?", "활은 매일 쏘셨소?", "아들 소식을 듣고 어떠셨어요?", "어머니 돌아가셨을 때 어떠셨어요?",
             "아들 면이 죽었을 때 어떠셨어요?", "술을 드셨어요?", "원균 장군에 대해 어떻게 생각하셨어요?",
             "인공지능이 뭐예요?", "명량 전날 뭐 하셨어요?"]


def ask(api: str, msg: str, history=(), last=()) -> dict:
    body = json.dumps({"message": msg, "history": list(history), "last_source_ids": list(last)},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(api + "/chat", data=body, headers={
        "content-type": "application/json; charset=utf-8", "x-client-id": str(uuid.uuid4())})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def run(api: str) -> list[dict]:
    first = ask(api, FIRST)
    hist = [{"role": "user", "content": FIRST}, {"role": "assistant", "content": first["answer"]}]
    cases = [("그다음 날은요?", hist, [s["id"] for s in first["sources"]])] + [(q, [], []) for q in QUESTIONS]
    out = []
    for q, h, last in cases:
        d = ask(api, q, h, last)
        out.append({"q": q, "mode": d["mode"], "src": [s["id"] for s in d["sources"]],
                    "emoji": len(EMOJI.findall(d["answer"])), "answer": d["answer"]})
    return out


if __name__ == "__main__":
    res = run(os.environ["API_URL"])
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    for r in res:
        print(f"\n[{r['mode']}] {r['q']} -> {r['src']} 이모지{r['emoji']}\n  {r['answer']}")
