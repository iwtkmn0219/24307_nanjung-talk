"""배포된 /chat에 평가 질문 40개를 보내, 일기 안 질문이 막혔는지·일기 밖 질문이 통과했는지 센다(Task 13).

사용: API_URL=https://... python scripts/eval_chat.py [결과 json 경로]
질문마다 새 X-Client-Id를 써서 하루 한도에 걸리지 않는다. 질문 40개 = Haiku 호출 최대 40회.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tone_check import ask  # noqa: E402

BLOCKED = {"out_of_scope", "modern"}


def summarize(rows: list[dict]) -> dict:
    """mode가 'error'(HTTP 오류, 예: Bedrock 503)인 질문은 따로 모으고 정확도 계산에서 뺀다."""
    errors = [r["q"] for r in rows if r["mode"] == "error"]
    rows = [r for r in rows if r["mode"] != "error"]
    ins = [r for r in rows if r["expect"] == "in"]
    outs = [r for r in rows if r["expect"] == "out"]
    in_blocked = [r["q"] for r in ins if r["mode"] in BLOCKED]
    out_passed = [r["q"] for r in outs if r["mode"] not in BLOCKED]
    wrong = len(in_blocked) + len(out_passed)
    return {"in_total": len(ins), "in_blocked": in_blocked, "out_total": len(outs), "out_passed": out_passed,
            "errors": errors, "accuracy": round((len(rows) - wrong) / len(rows), 4) if rows else 0.0}


def run(api: str) -> list[dict]:
    qs = json.loads((Path(__file__).resolve().parent.parent / "eval" / "questions.json").read_text(encoding="utf-8"))
    rows = []
    for q in qs:
        try:
            d = ask(api, q["q"])
        except urllib.error.HTTPError as e:
            rows.append({"q": q["q"], "expect": q["expect"], "mode": "error", "sources": 0, "answer": f"HTTP {e.code}"})
            continue
        rows.append({"q": q["q"], "expect": q["expect"], "mode": d["mode"], "sources": len(d["sources"]),
                     "answer": d["answer"]})
    return rows


if __name__ == "__main__":
    rows = run(os.environ["API_URL"])
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    s = summarize(rows)
    print(json.dumps(s, ensure_ascii=False, indent=1))
