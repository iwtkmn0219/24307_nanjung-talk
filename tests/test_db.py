import json
from datetime import date

from nanjung import db
from nanjung.db import search_sql
from nanjung.models import DiaryEntry, Hit


def test_search_sql_with_and_without_date():
    assert "ANY(:ids)" in search_sql(["1597-09-16"]) and "ANY" not in search_sql(None)
    s = search_sql(None)
    assert "1 - (embedding <=> :qvec::vector)" in s and "LIMIT :k" in s and "DESC" in s


class FakeConn:
    def __init__(self, results=()):
        self.results, self.calls = list(results), []

    def run(self, sql, **params):
        self.calls.append((sql, params))
        return self.results.pop(0) if self.results else []


def entry():
    return DiaryEntry("S", "壬辰", 1592, 4, False, 13, "壬寅", "十三日壬寅。", id="1592-04-13",
                      solar_date=date(1592, 5, 23), label="임진년(1592) 4월 13일", translation="맑음",
                      emotion="일상", intro="소개", questions=["q1", "q2", "q3"])


def row(e, extra=()):
    return [e.id, e.source_id, e.ganji_year, e.lunar_year, e.lunar_month, e.is_leap, e.lunar_day,
            e.day_ganji, e.solar_date, e.ganji_mismatch, e.label, e.original, e.translation,
            e.emotion, e.intro, e.questions, *extra]


def test_upsert_sends_all_fields_and_vector_literal():
    c = FakeConn()
    db.upsert(c, entry(), [0.5, 0.25])
    sql, p = c.calls[0]
    assert "ON CONFLICT (id) DO UPDATE" in sql and ":emb::vector" in sql
    assert p["id"] == "1592-04-13" and p["emb"] == "[0.5,0.25]"
    assert json.loads(p["questions"]) == ["q1", "q2", "q3"]


def test_search_maps_rows_to_hits():
    e = entry()
    c = FakeConn([[row(e, [0.82])]])
    hits = db.search(c, [0.1, 0.2], k=3, date_ids=["1592-04-13"])
    assert hits == [Hit(e, 0.82)]
    assert c.calls[0][1] == {"qvec": "[0.1,0.2]", "k": 3, "ids": ["1592-04-13"]}


def test_search_without_dates_has_no_ids_param():
    c = FakeConn([[]])
    db.search(c, [0.1], k=5)
    assert "ids" not in c.calls[0][1]


def test_get_preserves_requested_order():
    a = entry()
    b = DiaryEntry(**{**a.__dict__, "id": "1592-04-14"})
    c = FakeConn([[row(a), row(b)]])
    assert [e.id for e in db.get(c, ["1592-04-14", "1592-04-13"])] == ["1592-04-14", "1592-04-13"]
    assert db.get(FakeConn(), []) == []


def test_questions_json_string_is_decoded():
    e = entry()
    r = row(e)
    r[15] = json.dumps(e.questions)
    assert db.get(FakeConn([[r]]), [e.id])[0].questions == ["q1", "q2", "q3"]


def test_neighbor_direction_and_none():
    c = FakeConn([[["1592-08-24"]], []])
    assert db.neighbor(c, "1592-06-10", +1) == "1592-08-24"
    assert "solar_date >" in c.calls[0][0] and "ASC" in c.calls[0][0]
    assert db.neighbor(c, "1598-11-17", +1) is None
    assert "solar_date <" in db._neighbor_sql(-1) and "DESC" in db._neighbor_sql(-1)


def test_all_dates():
    c = FakeConn([[["1592-04-13", date(1592, 5, 23)]]])
    assert db.all_dates(c) == [("1592-04-13", date(1592, 5, 23))]


def test_init_schema_runs_each_statement():
    c = FakeConn()
    db.init_schema(c)
    sqls = [s for s, _ in c.calls]
    assert any("CREATE EXTENSION" in s for s in sqls) and any("hnsw" in s for s in sqls)
    assert len(sqls) == 4


def test_packaged_schema_matches_sql_dir():
    from pathlib import Path
    assert db.SCHEMA_PATH.read_text(encoding="utf-8") == Path("sql/schema.sql").read_text(encoding="utf-8")


def test_ssl_context_uses_ca_bundle_when_configured(monkeypatch, tmp_path):
    import ssl
    calls = []
    monkeypatch.setattr(ssl, "create_default_context", lambda **kw: calls.append(kw) or "ctx")
    monkeypatch.setenv("DB_SSL_CA", str(tmp_path / "bundle.pem"))
    assert db.ssl_context() == "ctx" and calls == [{"cafile": str(tmp_path / "bundle.pem")}]
    monkeypatch.delenv("DB_SSL_CA")
    db.ssl_context()
    assert calls[-1] == {}
