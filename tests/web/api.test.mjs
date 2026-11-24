import { test } from "node:test";
import assert from "node:assert/strict";
import { postChat, getDiary } from "../../web/js/api.js";
import { LIMIT_TEXT, UNAVAILABLE_TEXT } from "../../web/js/logic.js";

const res = (status, body) => async () => ({ status, ok: status >= 200 && status < 300, json: async () => body });
const args = (fetchFn, extra = {}) => ({ base: "http://x", clientId: "cid", message: "m", history: [], lastSourceIds: [], fetchFn, ...extra });

test("요청 형식", async () => {
  let seen;
  const f = async (url, init) => { seen = { url, init }; return res(200, { answer: "a", mode: "normal", sources: [], suggestions: [] })(); };
  await postChat({ base: "http://x", clientId: "cid", message: "m", history: [], lastSourceIds: ["d1"], fetchFn: f });
  assert.equal(seen.url, "http://x/chat");
  assert.equal(seen.init.method, "POST");
  assert.equal(seen.init.headers["x-client-id"], "cid");
  assert.equal(seen.init.headers["content-type"], "application/json");
  assert.deepEqual(JSON.parse(seen.init.body), { message: "m", history: [], last_source_ids: ["d1"] });
});

test("200 → ok", async () => {
  const body = { answer: "a", mode: "normal", sources: [], suggestions: [] };
  assert.deepEqual(await postChat(args(res(200, body))), { kind: "ok", body });
});

test("429 + 앱 한도 문구 → limit", async () => {
  assert.deepEqual(await postChat(args(res(429, { answer: LIMIT_TEXT }))), { kind: "limit", answer: LIMIT_TEXT });
  assert.equal((await postChat(args(res(429, {})))).kind, "unavailable");
});

test("503 → unavailable, 서버 문구", async () => {
  assert.deepEqual(await postChat(args(res(503, { answer: "숨 고르기" }))), { kind: "unavailable", answer: "숨 고르기" });
});

test("그 밖의 5xx → unavailable", async () => {
  assert.deepEqual(await postChat(args(res(500, { message: "Internal Server Error" }))), { kind: "unavailable", answer: UNAVAILABLE_TEXT });
});

test("네트워크 예외 → unavailable 기본 문구", async () => {
  const f = async () => { throw new TypeError("Failed to fetch"); };
  assert.deepEqual(await postChat(args(f)), { kind: "unavailable", answer: UNAVAILABLE_TEXT });
});

test("JSON 아님 → unavailable", async () => {
  const f = async () => ({ status: 502, ok: false, json: async () => { throw new SyntaxError("bad json"); } });
  assert.deepEqual(await postChat(args(f)), { kind: "unavailable", answer: UNAVAILABLE_TEXT });
});

test("200인데 JSON 아님 → unavailable", async () => {
  const f = async () => ({ status: 200, ok: true, json: async () => { throw new SyntaxError("html"); } });
  assert.equal((await postChat(args(f))).kind, "unavailable");
});

test("200인데 계약과 다른 본문 → unavailable", async () => {
  assert.equal((await postChat(args(res(200, { foo: 1 })))).kind, "unavailable");
});

test("타임아웃 → unavailable", async () => {
  const f = (url, init) => new Promise((_, reject) => {
    init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  });
  const t0 = Date.now();
  assert.deepEqual(await postChat(args(f, { timeoutMs: 10 })), { kind: "unavailable", answer: UNAVAILABLE_TEXT });
  assert.ok(Date.now() - t0 < 1000);
});

test("400 → invalid", async () => {
  assert.deepEqual(await postChat(args(res(400, { error: "x" }))), { kind: "invalid" });
});

test("getDiary 200/404/예외", async () => {
  let url;
  const body = { entry: { id: "x", label: "L", original: "O", translation: "T", emotion: "일상", intro: "I", solar_date: "1597-10-26" }, questions: [], exact: true, source_note: "n" };
  const ok = async (u) => { url = u; return res(200, body)(); };
  assert.deepEqual(await getDiary({ base: "http://x", fetchFn: ok }), { kind: "ok", body });
  assert.equal(url, "http://x/diary");
  assert.deepEqual(await getDiary({ base: "http://x", fetchFn: res(404, { error: "x" }) }), { kind: "error" });
  assert.deepEqual(await getDiary({ base: "http://x", fetchFn: async () => { throw new Error("net"); } }), { kind: "error" });
});

test("getDiary 쿼리(목 시나리오)는 붙여 보낼 수 있다", async () => {
  let url;
  await getDiary({ base: "", query: "scenario=grief", fetchFn: async (u) => { url = u; return res(200, { entry: {} })(); } });
  assert.equal(url, "/diary?scenario=grief");
});

// ---- 리뷰 반영 ----
const card = { id: "d1", label: "L", original_line: "O", translation_line: "T", note: "N" };
const good = { answer: "a", mode: "normal", sources: [card], suggestions: ["s"] };

test("200 응답의 중첩 필드가 계약과 다르면 unavailable", async () => {
  for (const bad of [
    { ...good, sources: [null] },
    { ...good, sources: [{ id: 1 }] },
    { ...good, mode: "weird" },
    { ...good, suggestions: "x" },
    { ...good, suggestions: [1] },
  ]) {
    assert.equal((await postChat(args(res(200, bad)))).kind, "unavailable", JSON.stringify(bad));
  }
});

test("suggestions 생략은 빈 배열로", async () => {
  const { suggestions, ...rest } = good;
  const r = await postChat(args(res(200, rest)));
  assert.equal(r.kind, "ok"); assert.deepEqual(r.body.suggestions, []);
});

test("게이트웨이 429(앱 한도 문구 아님)는 limit이 아니라 unavailable", async () => {
  assert.equal((await postChat(args(res(429, { message: "Too Many Requests" })))).kind, "unavailable");
  assert.equal((await postChat(args(res(429, { answer: LIMIT_TEXT })))).kind, "limit");
});

const entry = { id: "x", label: "L", original: "O", translation: "T", emotion: "일상", intro: "I", solar_date: "1597-10-26" };

test("getDiary: 필수 필드가 없으면 error", async () => {
  for (const bad of [{ entry: {} }, { entry: { ...entry, solar_date: "x" }, questions: [], exact: true },
                     { entry, questions: "q", exact: true }, { entry, questions: [], exact: "yes" }]) {
    assert.deepEqual(await getDiary({ base: "", fetchFn: res(200, bad) }), { kind: "error" }, JSON.stringify(bad));
  }
  const ok = { entry, questions: ["q"], exact: true, source_note: "n" };
  assert.equal((await getDiary({ base: "", fetchFn: res(200, ok) })).kind, "ok");
});

test("getDiary: 브라우저가 계산한 md를 보낸다(시나리오와 함께)", async () => {
  let url;
  const ok = { entry, questions: [], exact: true };
  await getDiary({ base: "http://x", md: "12-31", query: "scenario=grief", fetchFn: async (u) => { url = u; return res(200, ok)(); } });
  assert.equal(url, "http://x/diary?md=12-31&scenario=grief");
});

test("선택 출처 문구가 문자열이 아니면 기본 문구로 정규화", async () => {
  const { SOURCE_NOTE } = await import("../../web/js/logic.js");
  const evil = { toString: null };
  const c = await postChat(args(res(200, { ...good, sources: [{ ...card, note: evil }] })));
  assert.equal(c.kind, "ok"); assert.equal(c.body.sources[0].note, SOURCE_NOTE);
  const d = await getDiary({ base: "", fetchFn: res(200, { entry, questions: [], exact: true, source_note: evil }) });
  assert.equal(d.kind, "ok"); assert.equal(d.body.source_note, SOURCE_NOTE);
  const keep = await postChat(args(res(200, good)));
  assert.equal(keep.body.sources[0].note, "N");
});
