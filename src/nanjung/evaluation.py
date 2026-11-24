"""유사도 기준값(SIM_THRESHOLD) 튜닝용 평가. 순수 계산만 한다(DB·Bedrock 호출은 핸들러가 한다)."""
from __future__ import annotations

from pathlib import Path
from statistics import median

# 소스는 eval/questions.json. Lambda 패키지(CodeUri=src/)에 들어가도록 같은 파일을 여기에 둔다(테스트가 동일성 확인).
QUESTIONS_PATH = Path(__file__).resolve().parent / "eval_questions.json"

LO, HI, STEP = 10, 40, 1  # 0.10 ~ 0.40, 0.01 간격(정수 백분율로 돌려 부동소수 오차를 피한다)


def predict(similarity: float, threshold: float) -> str:
    """answer.decide_mode와 같은 경계: 최고 유사도 < 기준값이면 일기 밖."""
    return "in" if similarity >= threshold else "out"


def sweep(rows: list[tuple[str, str, float]]) -> list[dict]:
    """rows: (질문, 기대 in|out, 최고 유사도). 기준값마다 정확도와 오분류 수."""
    out = []
    for h in range(LO, HI + 1, STEP):
        t = round(h / 100, 2)
        missed = sum(1 for _, exp, sim in rows if exp == "in" and predict(sim, t) == "out")
        leaked = sum(1 for _, exp, sim in rows if exp == "out" and predict(sim, t) == "in")
        out.append({"threshold": t, "accuracy": round((len(rows) - missed - leaked) / len(rows), 4),
                    "in_missed": missed, "out_leaked": leaked})
    return out


def best(table: list[dict]) -> dict:
    """정확도가 가장 높은 값. 동률이면 낮은 값(일기 안 질문을 놓치는 쪽이 더 나쁘다)."""
    return max(table, key=lambda r: (r["accuracy"], -r["threshold"]))


def distribution(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    v = sorted(values)

    def q(p: float) -> float:  # 선형 보간 없이 가까운 순위
        return v[min(len(v) - 1, round(p * (len(v) - 1)))]
    return {"n": len(v), "min": v[0], "p25": q(0.25), "median": median(v), "p75": q(0.75), "max": v[-1]}


def separation(rows: list[tuple[str, str, float]]) -> dict:
    """in 최저 유사도와 out 최고 유사도. 겹치면 기준값 하나로는 완벽히 갈리지 않는다."""
    ins = [s for _, e, s in rows if e == "in"]
    outs = [s for _, e, s in rows if e == "out"]
    lo_in, hi_out = min(ins), max(outs)
    return {"in_min": lo_in, "out_max": hi_out, "overlap": lo_in <= hi_out, "gap": round(lo_in - hi_out, 4)}
