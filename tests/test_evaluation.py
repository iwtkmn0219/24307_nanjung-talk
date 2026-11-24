import json
from pathlib import Path

from nanjung import evaluation as ev
from nanjung.answer import MODERN_MARKERS, is_modern

ROWS = [("a", "in", 0.30), ("b", "in", 0.20), ("c", "out", 0.15), ("d", "out", 0.25)]


def test_questions_file_shape_and_in_sync_with_package():
    qs = json.loads(Path("eval/questions.json").read_text(encoding="utf-8"))
    assert len(qs) == 40 and sum(q["expect"] == "in" for q in qs) == 25 and sum(q["expect"] == "out" for q in qs) == 15
    assert all(set(q) == {"q", "expect"} and q["expect"] in ("in", "out") for q in qs)
    for must in ["배 멀미 하셨어요?", "어머니 보고 싶으셨어요?", "거북선 시험해 봤어요?", "인공지능이 뭐예요?", "피자 좋아하세요?", "축구 아세요?"]:
        assert any(q["q"] == must for q in qs)
    assert ev.QUESTIONS_PATH.read_text(encoding="utf-8") == Path("eval/questions.json").read_text(encoding="utf-8")


def test_questions_measure_similarity_not_modern_marker():
    qs = json.loads(Path("eval/questions.json").read_text(encoding="utf-8"))
    assert not [q["q"] for q in qs if is_modern(q["q"])], MODERN_MARKERS


def test_in_questions_have_no_date_cue():
    from nanjung.date_resolver import resolve
    qs = json.loads(Path("eval/questions.json").read_text(encoding="utf-8"))
    assert [q["q"] for q in qs if q["expect"] == "in" and resolve(q["q"], [], lambda i, d: None)] == []


def test_predict_matches_decide_mode_boundary():
    assert ev.predict(0.30, 0.30) == "in" and ev.predict(0.2999, 0.30) == "out"


def test_sweep_range_and_counts():
    s = ev.sweep(ROWS)  # in 0.30/0.20, out 0.15/0.25: 겹치므로 완벽한 값은 없다
    assert s[0]["threshold"] == 0.10 and s[-1]["threshold"] == 0.40 and len(s) == 31
    at = {x["threshold"]: x for x in s}
    assert at[0.10]["accuracy"] == 0.5 and at[0.10]["out_leaked"] == 2 and at[0.10]["in_missed"] == 0
    assert at[0.16]["accuracy"] == 0.75 and at[0.16]["out_leaked"] == 1 and at[0.16]["in_missed"] == 0
    assert at[0.20]["accuracy"] == 0.75
    assert at[0.21]["accuracy"] == 0.5 and at[0.21]["in_missed"] == 1 and at[0.21]["out_leaked"] == 1
    assert at[0.26]["accuracy"] == 0.75 and at[0.26]["in_missed"] == 1 and at[0.26]["out_leaked"] == 0
    assert at[0.31]["in_missed"] == 2


def test_best_prefers_lowest_threshold_on_tie():
    assert ev.best(ev.sweep(ROWS))["threshold"] == 0.16  # 0.16~0.20, 0.26~0.30이 모두 0.75 → 가장 낮은 값
    clean = [("a", "in", 0.5), ("b", "out", 0.2)]
    assert ev.best(ev.sweep(clean)) == {"threshold": 0.21, "accuracy": 1.0, "in_missed": 0, "out_leaked": 0}


def test_distribution_summary():
    d = ev.distribution([0.1, 0.2, 0.3, 0.4, 0.5])
    assert d == {"n": 5, "min": 0.1, "p25": 0.2, "median": 0.3, "p75": 0.4, "max": 0.5}
    assert ev.distribution([])["n"] == 0


def test_separation_flags_overlap():
    assert ev.separation(ROWS)["overlap"] is True  # in 최저 0.20 < out 최고 0.25
    ok = [("a", "in", 0.5), ("b", "out", 0.2)]
    s = ev.separation(ok)
    assert s["overlap"] is False and s["gap"] == 0.3


def test_render_marks_best_and_lists_rows():
    import sys
    sys.path.insert(0, "eval")
    from run_eval import render
    rows = [{"q": "a", "expect": "in", "sim": 0.5, "top_id": "x"}, {"q": "b", "expect": "out", "sim": 0.2, "top_id": "y"}]
    trip = [(r["q"], r["expect"], r["sim"]) for r in rows]
    t = ev.sweep(trip)
    res = {"rows": rows, "table": t, "best": ev.best(t), "separation": ev.separation(trip),
           "in_dist": ev.distribution([0.5]), "out_dist": ev.distribution([0.2])}
    txt = render(res)
    assert "<- best" in txt and txt.count("<- best") == 1 and "0.21" in txt and "겹침 False" in txt
