"""RDS PostgreSQL(pgvector) 접근 계층. pg8000.native 사용."""
from __future__ import annotations

import json
import os
import ssl
from pathlib import Path

from .models import DiaryEntry, Hit

COLUMNS = ("id", "source_id", "ganji_year", "lunar_year", "lunar_month", "is_leap", "lunar_day",
           "day_ganji", "solar_date", "ganji_mismatch", "label", "original", "translation",
           "emotion", "intro", "questions")
_COLS = ", ".join(COLUMNS)
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect():
    import pg8000.native
    return pg8000.native.Connection(
        host=os.environ["DB_HOST"], database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
        port=int(os.environ.get("DB_PORT", "5432")), ssl_context=ssl.create_default_context(),
        timeout=10)


def init_schema(conn) -> None:
    for stmt in SCHEMA_PATH.read_text(encoding="utf-8").split(";"):
        if stmt.strip():
            conn.run(stmt)


def _vec(v: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


def upsert(conn, e: DiaryEntry, embedding: list[float]) -> None:
    params = {c: getattr(e, c) for c in COLUMNS}
    params["questions"] = json.dumps(e.questions, ensure_ascii=False)
    params["emb"] = _vec(embedding)
    values = ", ".join(f":{c}" for c in COLUMNS if c != "questions")
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS[1:]) + ", embedding = EXCLUDED.embedding"
    conn.run(
        f"INSERT INTO diary ({_COLS}, embedding) VALUES ({values}, :questions::jsonb, :emb::vector) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}", **params)


def search_sql(date_ids: list[str] | None) -> str:
    where = " WHERE id = ANY(:ids)" if date_ids else ""
    return (f"SELECT {_COLS}, 1 - (embedding <=> :qvec::vector) AS similarity FROM diary{where} "
            "ORDER BY similarity DESC LIMIT :k")


def _entry(row) -> DiaryEntry:
    d = dict(zip(COLUMNS, row))
    if isinstance(d["questions"], str):
        d["questions"] = json.loads(d["questions"])
    return DiaryEntry(**d)


def search(conn, qvec: list[float], k: int = 5, date_ids: list[str] | None = None) -> list[Hit]:
    params = {"qvec": _vec(qvec), "k": k}
    if date_ids:
        params["ids"] = list(date_ids)
    rows = conn.run(search_sql(date_ids), **params)
    return [Hit(_entry(r[:len(COLUMNS)]), float(r[len(COLUMNS)])) for r in rows]


def get(conn, ids: list[str]) -> list[DiaryEntry]:
    if not ids:
        return []
    by_id = {e.id: e for e in map(_entry, conn.run(f"SELECT {_COLS} FROM diary WHERE id = ANY(:ids)",
                                                   ids=list(ids)))}
    return [by_id[i] for i in ids if i in by_id]


def _neighbor_sql(direction: int) -> str:
    op, order = (">", "ASC") if direction > 0 else ("<", "DESC")
    return (f"SELECT id FROM diary WHERE solar_date {op} "
            "(SELECT solar_date FROM diary WHERE id = :id) "
            f"ORDER BY solar_date {order}, id {order} LIMIT 1")


def neighbor(conn, entry_id: str, direction: int) -> str | None:
    rows = conn.run(_neighbor_sql(direction), id=entry_id)
    return rows[0][0] if rows else None


def all_dates(conn) -> list[tuple[str, object]]:
    return [(r[0], r[1]) for r in conn.run("SELECT id, solar_date FROM diary ORDER BY solar_date, id")]
