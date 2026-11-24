"""유사도 기준값 평가 실행기. 적재 Lambda의 {"action": "eval"}을 호출해 결과를 표로 출력한다.

사용: INGEST_FUNCTION=<함수 이름> python eval/run_eval.py [결과 json 저장 경로]
(RDS가 프라이빗이라 로컬에서 직접 검색할 수 없어 Lambda 안에서 계산한다)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def invoke(function: str) -> dict:
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out.json"
        r = subprocess.run(["aws", "lambda", "invoke", "--function-name", function, "--payload", '{"action":"eval"}',
                            "--cli-binary-format", "raw-in-base64-out", "--cli-read-timeout", "300", str(out),
                            "--query", "FunctionError", "--output", "text"],
                           capture_output=True, text=True, encoding="utf-8")
        body = out.read_text(encoding="utf-8") if out.exists() else ""
        if r.returncode or r.stdout.strip() not in ("", "None"):
            raise SystemExit(f"eval 실패: {r.stdout.strip()} {r.stderr.strip()} {body[:500]}")
        return json.loads(body)


def render(res: dict) -> str:
    lines = ["질문별 최고 유사도 (기대 / 유사도 / 최상위 일기 / 질문)"]
    for r in sorted(res["rows"], key=lambda r: (r["expect"], -r["sim"])):
        lines.append(f"  {r['expect']:>3}  {r['sim']:.4f}  {r['top_id']}  {r['q']}")
    for name in ("in_dist", "out_dist"):
        d = res[name]
        lines.append(f"{name}: n={d['n']} min={d['min']} p25={d['p25']} median={d['median']} p75={d['p75']} max={d['max']}")
    sep = res["separation"]
    lines.append(f"분리: in 최저 {sep['in_min']} / out 최고 {sep['out_max']} / 겹침 {sep['overlap']} / 간격 {sep['gap']}")
    lines.append("기준값  정확도  in놓침  out통과")
    for t in res["table"]:
        mark = "  <- best" if t["threshold"] == res["best"]["threshold"] else ""
        lines.append(f"  {t['threshold']:.2f}  {t['accuracy']:.3f}  {t['in_missed']:>5}  {t['out_leaked']:>6}{mark}")
    return "\n".join(lines)


if __name__ == "__main__":
    res = invoke(os.environ["INGEST_FUNCTION"])
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(render(res))
