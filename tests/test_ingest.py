import json
from datetime import date

import pytest

from nanjung.handlers import ingest
from nanjung.models import DiaryEntry

HTML = ('<div class="text_body ori">'
        '<div class="xsl_para">十三日壬寅。晴。出東軒公事。</div>'
        '<div class="xsl_para">十四日癸卯。雨。</div></div>')
INDEX = [{"data_id": "X", "title": "壬辰四月"}]


class FakeS3:
    def __init__(self, objects):
        self.objects = dict(objects)
        self.puts = []

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            from botocore.exceptions import ClientError
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        import io
        return {"Body": io.BytesIO(self.objects[Key].encode("utf-8"))}

    def put_object(self, Bucket, Key, Body, **kw):
        self.puts.append(Key)
        self.objects[Key] = Body.decode("utf-8") if isinstance(Body, bytes) else Body


class FakeBedrock:
    def __init__(self):
        self.converse_calls = 0
        self.embed_calls = 0
        self.embedded = []

    def enrich(self, e, client=None):
        self.converse_calls += 1
        from dataclasses import replace
        return replace(e, translation=f"번역{e.lunar_day}", emotion="일상", intro="소개하오.",
                       questions=["q1", "q2", "q3"])

    def embed(self, text, client=None):
        self.embed_calls += 1
        self.embedded.append(text)
        return [0.0] * 1024


class FakeDB:
    def __init__(self, dates=()):
        self.upserts, self.schema_inited, self.dates = [], False, list(dates)

    def init_schema(self, conn): self.schema_inited = True
    def upsert(self, conn, e, emb): self.upserts.append((e, emb))
    def all_dates(self, conn): return self.dates


class FakeTable:
    def __init__(self): self.items = []

    def batch_writer(self):
        table = self

        class W:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def put_item(self, Item): table.items.append(Item)
        return W()


ORIGINALS = {13: "十三日壬寅。晴。出東軒公事。", 14: "十四日癸卯。雨。"}


def processed(lunar_days, originals=ORIGINALS):
    return json.dumps([{"id": f"1592-04-{d}", "original": originals.get(d), "translation": f"캐시{d}",
                        "emotion": "비통", "intro": "캐시 소개하오.", "questions": ["a", "b", "c"]}
                       for d in lunar_days], ensure_ascii=False)


@pytest.fixture
def fakes(monkeypatch):
    def install(objects, dates=()):
        s3, br, fdb, table = FakeS3(objects), FakeBedrock(), FakeDB(dates), FakeTable()
        monkeypatch.setenv("DATA_BUCKET", "b")
        monkeypatch.setattr(ingest, "s3_client", lambda: s3)
        monkeypatch.setattr(ingest, "get_conn", lambda: object())
        monkeypatch.setattr(ingest, "today_table", lambda: table)
        monkeypatch.setattr(ingest, "enrich", br.enrich)
        monkeypatch.setattr(ingest, "embed", br.embed)
        monkeypatch.setattr(ingest, "db", fdb)
        return s3, br, fdb, table
    return install


BASE = {"raw/index.json": json.dumps(INDEX, ensure_ascii=False), "raw/X.html": HTML}


def test_ingest_uses_processed_cache(fakes):
    s3, br, fdb, _ = fakes({**BASE, "processed/X.json": processed([13, 14])})
    out = ingest.lambda_handler({"action": "ingest", "key": "raw/X.html"}, None)
    assert out == {"count": 2}
    assert br.converse_calls == 0 and br.embed_calls == out["count"]
    assert [e.translation for e, _ in fdb.upserts] == ["캐시13", "캐시14"]
    assert br.embedded == ["캐시13", "캐시14"]  # 임베딩 대상은 번역문
    assert s3.puts == []


def test_ingest_enriches_and_saves_processed_when_missing(fakes):
    s3, br, fdb, _ = fakes(dict(BASE))
    out = ingest.lambda_handler({"action": "ingest", "key": "raw/X.html"}, None)
    assert out == {"count": 2} and br.converse_calls == 2
    assert s3.puts == ["processed/X.json"]
    saved = json.loads(s3.objects["processed/X.json"])
    assert [d["id"] for d in saved] == ["1592-04-13", "1592-04-14"]
    assert saved[0]["translation"] == "번역13" and saved[0]["original"].startswith("十三日壬寅")
    e = fdb.upserts[0][0]
    assert e.solar_date == date(1592, 5, 23) and e.label == "임진년(1592) 4월 13일"


def test_ingest_enriches_only_entries_missing_from_cache(fakes):
    s3, br, fdb, _ = fakes({**BASE, "processed/X.json": processed([13])})
    ingest.lambda_handler({"action": "ingest", "key": "raw/X.html"}, None)
    assert br.converse_calls == 1 and s3.puts == ["processed/X.json"]
    assert [e.translation for e, _ in fdb.upserts] == ["캐시13", "번역14"]


def test_init_schema(fakes):
    _, _, fdb, _ = fakes({})
    assert ingest.lambda_handler({"action": "init_schema"}, None) == {"ok": True}
    assert fdb.schema_inited


def test_build_today_map_writes_366_items(fakes):
    _, _, _, table = fakes({}, dates=[("1592-04-13", date(1592, 5, 23))])
    out = ingest.lambda_handler({"action": "build_today_map"}, None)
    assert out == {"count": 366} and len(table.items) == 366
    item = next(i for i in table.items if i["md"] == "05-23")
    assert item == {"md": "05-23", "ids": ["1592-04-13"], "exact": True}


def test_ingest_rejects_key_outside_raw(fakes):
    fakes(dict(BASE))
    with pytest.raises(ValueError):
        ingest.lambda_handler({"action": "ingest", "key": "processed/X.json"}, None)


def test_unknown_action_raises(fakes):
    fakes({})
    with pytest.raises(ValueError):
        ingest.lambda_handler({"action": "drop_everything"}, None)


def test_enrich_failure_saves_finished_entries_then_raises(fakes, monkeypatch):
    s3, br, fdb, _ = fakes(dict(BASE))
    from nanjung.enrich import EnrichError

    def flaky(e, client=None):
        if e.lunar_day == 14:
            raise EnrichError("broken")
        return br.enrich(e)
    monkeypatch.setattr(ingest, "enrich", flaky)
    with pytest.raises(EnrichError):
        ingest.lambda_handler({"action": "ingest", "key": "raw/X.html"}, None)
    saved = json.loads(s3.objects["processed/X.json"])
    assert [d["id"] for d in saved] == ["1592-04-13"] and fdb.upserts == []


def test_cache_with_changed_original_is_re_enriched(fakes):
    s3, br, fdb, _ = fakes({**BASE, "processed/X.json": processed([13, 14], {13: "옛 원문", 14: ORIGINALS[14]})})
    ingest.lambda_handler({"action": "ingest", "key": "raw/X.html"}, None)
    assert br.converse_calls == 1
    assert [e.translation for e, _ in fdb.upserts] == ["번역13", "캐시14"]
    assert json.loads(s3.objects["processed/X.json"])[0]["original"] == ORIGINALS[13]


def test_get_conn_uses_reconnecting_shared_conn(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(ingest, "shared_conn", lambda: sentinel)
    assert ingest.get_conn() is sentinel


def test_stats_reports_count_emotions_and_suspicious_terms(fakes):
    _, _, fdb, _ = fakes({})
    fdb.stats = lambda conn: {"count": 3, "emotions": {"일상": 2, "비통": 1}, "pig_in_son_entries": ["1597-10-14"]}
    assert ingest.lambda_handler({"action": "stats"}, None) == {
        "count": 3, "emotions": {"일상": 2, "비통": 1}, "pig_in_son_entries": ["1597-10-14"]}


def test_diag_reports_resolution_and_similarities(fakes, monkeypatch):
    _, br, fdb, _ = fakes({})
    from nanjung.models import Hit
    calls = []

    def search(conn, qvec, k=5, date_ids=None):
        calls.append(date_ids)
        return [Hit(DiaryEntry("S", "壬辰", 1592, 4, False, 13, "壬寅", "x", id="1597-09-16", emotion="일상"), 0.42)]
    fdb.search = search
    fdb.neighbor = lambda conn, i, d: None
    out = ingest.lambda_handler({"action": "diag", "message": "명량 때 어땠어요?"}, None)
    assert out["date_ids"] == ["1597-09-16"]
    assert out["date_hits"] == [["1597-09-16", 0.42]] and out["general_hits"][0] == ["1597-09-16", 0.42]
    assert calls == [["1597-09-16"], None]


def test_eval_action_scores_questions_and_returns_sweep(fakes, monkeypatch):
    import json as _json
    from nanjung import evaluation as ev
    from nanjung.models import Hit
    _, _, fdb, _ = fakes({})
    qs = _json.loads(ev.QUESTIONS_PATH.read_text(encoding="utf-8"))
    outs = {q["q"] for q in qs if q["expect"] == "out"}
    monkeypatch.setattr(ingest, "embed", lambda text, client=None: [1.0 if text in outs else 0.0])
    ent = DiaryEntry("S", "壬辰", 1592, 4, False, 13, "壬寅", "x", id="1592-04-13")
    fdb.search = lambda conn, qvec, k=5, date_ids=None: [Hit(ent, 0.10 if qvec[0] == 1.0 else 0.50)]
    out = ingest.lambda_handler({"action": "eval"}, None)
    assert len(out["rows"]) == 40 and out["rows"][0] == {"q": qs[0]["q"], "expect": "in", "sim": 0.5, "top_id": "1592-04-13"}
    assert out["best"] == {"threshold": 0.11, "accuracy": 1.0, "in_missed": 0, "out_leaked": 0}
    assert len(out["table"]) == 31 and out["separation"]["overlap"] is False
    assert out["in_dist"]["n"] == 25 and out["out_dist"]["n"] == 15 and out["out_dist"]["max"] == 0.1


def _grief_file():
    return json.dumps([
        {"id": "a", "original": "o1", "translation": "t1", "emotion": "비통", "intro": "i", "questions": ["1", "2", "3"]},
        {"id": "b", "original": "o2", "translation": "t2", "emotion": "비통", "intro": "i", "questions": ["1", "2", "3"]},
        {"id": "c", "original": "o3", "translation": "t3", "emotion": "일상", "intro": "i", "questions": ["1", "2", "3"]},
    ], ensure_ascii=False)


# ---- reclassify: S3(JSON)를 기준으로 확정하고, DB는 JSON에 맞추는 멱등 동기화 ----
RC_INDEX = json.dumps([{"data_id": "X", "title": "壬辰正月"}], ensure_ascii=False)


def _grief_file(emotions=("비통", "비통", "일상")):
    return json.dumps([
        {"id": i, "original": f"o{n}", "translation": f"t{n}", "emotion": e, "intro": "i", "questions": ["1", "2", "3"]}
        for n, (i, e) in enumerate(zip("abc", emotions), start=1)], ensure_ascii=False)


class RcDB(FakeDB):
    """sync_emotions 호출을 기록하고 사건 순서(events)를 S3와 공유한다."""

    def __init__(self, events, result=None):
        super().__init__()
        self.events, self.result, self.sync_calls, self.fail = events, result, [], False

    def sync_emotions(self, conn, items):
        self.events.append("db")
        self.sync_calls.append(list(items))
        if self.fail:
            raise OSError("db down")
        return self.result or {"updated": [], "missing": [], "stale": []}


def _rc(fakes, monkeypatch, objects=None, answers=None, db_result=None):
    s3, br, _fdb, _t = fakes({"raw/index.json": RC_INDEX, "processed/X.json": _grief_file(), **(objects or {})})
    events, asked = [], []
    fdb = RcDB(events, db_result)
    monkeypatch.setattr(ingest, "db", fdb)
    orig_put = s3.put_object
    s3.put_object = lambda **kw: (events.append("s3"), orig_put(**kw))[1]
    answers = answers or {"o1": "일상", "o2": "비통"}

    def fake_reclassify(o, t_, client=None):
        asked.append(o)
        v = answers[o]
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(ingest, "reclassify", fake_reclassify)
    return s3, br, fdb, events, asked


def test_reclassify_restores_db_from_s3_first_then_saves_json_then_syncs_again(fakes, monkeypatch):
    s3, br, fdb, events, asked = _rc(fakes, monkeypatch, db_result={"updated": ["a"], "missing": [], "stale": []})
    out = ingest.lambda_handler({"action": "reclassify", "key": "processed/X.json"}, None)
    assert asked == ["o1", "o2"]                                   # 비통이 아닌 항목은 묻지 않는다
    assert events == ["db", "s3", "db"]                            # 기존 확정값 복구 → 새 판정 S3 → DB
    assert out == {"checked": 2, "changed": [{"id": "a", "from": "비통", "to": "일상"}],
                   "db_updated": ["a"], "db_missing": [], "db_stale": []}
    saved = json.loads(s3.objects["processed/X.json"])
    assert [d["emotion"] for d in saved] == ["일상", "비통", "일상"]
    assert [d["translation"] for d in saved] == ["t1", "t2", "t3"]
    assert fdb.sync_calls[0] == [("a", "o1", "t1", "비통"), ("b", "o2", "t2", "비통"), ("c", "o3", "t3", "일상")]
    assert fdb.sync_calls[1] == [("a", "o1", "t1", "일상"), ("b", "o2", "t2", "비통"), ("c", "o3", "t3", "일상")]
    assert br.embed_calls == 0 and br.converse_calls == 0


def test_reclassify_without_changes_syncs_once_and_writes_no_s3(fakes, monkeypatch):
    s3, _, fdb, events, _ = _rc(fakes, monkeypatch, answers={"o1": "비통", "o2": "비통"})
    out = ingest.lambda_handler({"action": "reclassify", "key": "processed/X.json"}, None)
    assert out["changed"] == [] and events == ["db"] and s3.puts == []


def test_s3_write_failure_leaves_new_decision_unrecorded_and_db_at_checkpoint(fakes, monkeypatch):
    s3, _, fdb, events, asked = _rc(fakes, monkeypatch)

    def boom(**kw):
        raise OSError("s3 down")
    s3.put_object = boom
    with pytest.raises(OSError):
        ingest.lambda_handler({"action": "reclassify", "key": "processed/X.json"}, None)
    assert len(fdb.sync_calls) == 1                                # 기존 S3 값으로만 한 번 맞췄다(새 판정은 DB에 안 감)
    assert json.loads(s3.objects["processed/X.json"])[0]["emotion"] == "비통"


def test_db_failure_after_json_saved_is_recovered_by_rerun_even_if_a_later_item_fails(fakes, monkeypatch):
    # 1차: a=비통→일상 확정(S3 저장) 후 DB 동기화 실패
    s3, _, fdb, events, asked = _rc(fakes, monkeypatch)
    calls = {"n": 0}
    orig = fdb.sync_emotions

    def flaky(conn, items):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("db down")
        return orig(conn, items)
    fdb.sync_emotions = flaky
    with pytest.raises(OSError):
        ingest.lambda_handler({"action": "reclassify", "key": "processed/X.json"}, None)
    assert json.loads(s3.objects["processed/X.json"])[0]["emotion"] == "일상"
    # 2차: 남은 비통 b의 모델 호출이 실패해도, 그 전에 a의 확정값이 DB로 복구돼야 한다
    from nanjung.enrich import EnrichError
    monkeypatch.setattr(ingest, "reclassify", lambda o, t_, client=None: (_ for _ in ()).throw(EnrichError("파싱 오류")))
    fdb.sync_emotions = orig
    before = len(fdb.sync_calls)
    with pytest.raises(EnrichError):
        ingest.lambda_handler({"action": "reclassify", "key": "processed/X.json"}, None)
    assert len(fdb.sync_calls) == before + 1
    assert fdb.sync_calls[-1][0] == ("a", "o1", "t1", "일상")


def test_model_failure_midway_saves_progress_and_syncs_it_before_raising(fakes, monkeypatch):
    from nanjung.enrich import EnrichError
    s3, _, fdb, events, asked = _rc(fakes, monkeypatch, answers={"o1": "일상", "o2": EnrichError("파싱 오류")})
    with pytest.raises(EnrichError):
        ingest.lambda_handler({"action": "reclassify", "key": "processed/X.json"}, None)
    assert [d["emotion"] for d in json.loads(s3.objects["processed/X.json"])] == ["일상", "비통", "일상"]  # a까지 저장
    assert events == ["db", "s3", "db"] and fdb.sync_calls[-1][0] == ("a", "o1", "t1", "일상")


def test_model_failure_on_first_item_writes_nothing_new(fakes, monkeypatch):
    from nanjung.enrich import EnrichError
    s3, _, fdb, events, asked = _rc(fakes, monkeypatch, answers={"o1": EnrichError("x"), "o2": "비통"})
    with pytest.raises(EnrichError):
        ingest.lambda_handler({"action": "reclassify", "key": "processed/X.json"}, None)
    assert events == ["db"] and s3.puts == []


def test_reclassify_reports_rows_missing_or_stale_in_db(fakes, monkeypatch):
    _rc(fakes, monkeypatch, db_result={"updated": [], "missing": ["b"], "stale": ["c"]})
    out = ingest.lambda_handler({"action": "reclassify", "key": "processed/X.json"}, None)
    assert out["db_missing"] == ["b"] and out["db_stale"] == ["c"]


@pytest.mark.parametrize("key", ["raw/X.html", "processed/../X.json", "processed/Y.json", "processed/a/X.json"])
def test_reclassify_rejects_keys_not_in_month_index(fakes, monkeypatch, key):
    _rc(fakes, monkeypatch, objects={"processed/Y.json": _grief_file()})
    with pytest.raises(ValueError):
        ingest.lambda_handler({"action": "reclassify", "key": key}, None)


BAD_FILES = [
    json.dumps({"a": 1}),
    json.dumps([{"id": "a", "emotion": "비통"}]),
    json.dumps([{"id": "a", "original": "o", "translation": "t", "emotion": "비통"},
                {"id": "a", "original": "o", "translation": "t", "emotion": "비통"}]),
    json.dumps([{"id": "", "original": "o", "translation": "t", "emotion": "비통"}]),
    json.dumps([{"id": "a", "original": "o", "translation": "t", "emotion": "기쁨"}]),
]


@pytest.mark.parametrize("bad", BAD_FILES)
def test_reclassify_rejects_malformed_entries_before_any_model_or_db_call(fakes, monkeypatch, bad):
    s3, _, fdb, events, asked = _rc(fakes, monkeypatch, objects={"processed/X.json": bad})
    with pytest.raises(ValueError):
        ingest.lambda_handler({"action": "reclassify", "key": "processed/X.json"}, None)
    assert asked == [] and fdb.sync_calls == [] and s3.puts == []


def test_reclassify_missing_file_raises(fakes, monkeypatch):
    s3, *_ = _rc(fakes, monkeypatch)
    del s3.objects["processed/X.json"]
    with pytest.raises(ValueError):
        ingest.lambda_handler({"action": "reclassify", "key": "processed/X.json"}, None)


def test_reclassify_report_includes_rows_recovered_by_the_checkpoint_sync(fakes, monkeypatch):
    s3, _, fdb, events, asked = _rc(fakes, monkeypatch)
    results = iter([{"updated": ["x"], "missing": [], "stale": []}, {"updated": ["a"], "missing": ["m"], "stale": []}])
    fdb.sync_emotions = lambda conn, items: next(results)
    out = ingest.lambda_handler({"action": "reclassify", "key": "processed/X.json"}, None)
    assert out["db_updated"] == ["x", "a"] and out["db_missing"] == ["m"]
