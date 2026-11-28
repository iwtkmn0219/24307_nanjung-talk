import { test } from "node:test";
import assert from "node:assert/strict";
import * as L from "../../web/js/logic.js";

test("kstToday는 기기 시간대와 무관하게 KST", () => {
  assert.deepEqual(L.kstToday(new Date("2026-11-30T15:30:00Z")), { year: 2026, month: 12, day: 1, md: "12-01" });
});
test("diaryTitle", () => {
  assert.equal(L.diaryTitle(true, "1597-10-26", 2026), "429년 전 오늘, 장군의 일기");
  assert.equal(L.diaryTitle(false, "1597-10-26", 2026), "가장 가까운 날의 일기");
});
test("diaryMeta와 missingPill", () => {
  assert.equal(L.diaryMeta("정유년(1597) 9월 16일", "1597-10-26"), "정유년(1597) 9월 16일 · 양력 10월 26일");
  assert.equal(L.missingPill({ month: 2, day: 29 }), "2월 29일의 일기는 없소");
});
test("counter 경계", () => {
  assert.deepEqual(L.counter(250), { text: null, warn: false });
  assert.deepEqual(L.counter(251), { text: "251 / 300", warn: false });
  assert.deepEqual(L.counter(281), { text: "281 / 300", warn: true });
});
test("IME 조합 중 Enter 무시", () => {
  assert.equal(L.shouldSubmit({ key: "Enter", isComposing: true, keyCode: 13 }), false);
  assert.equal(L.shouldSubmit({ key: "Enter", isComposing: false, keyCode: 229 }), false);
  assert.equal(L.shouldSubmit({ key: "Enter", isComposing: false, keyCode: 13, shiftKey: false }), true);
});
test("localStorage가 던져도 같은 탭에서 같은 id", () => {
  const bad = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  let n = 0; const uuid = () => `u${++n}`;
  const a = L.getClientId(bad, uuid), b = L.getClientId(bad, uuid);
  assert.equal(a, b);
});
test("저장된 id 재사용", () => {
  const m = new Map([["nj_client_id", "keep"]]);
  const s = { getItem: k => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
  assert.equal(L.getClientId(s, () => "new"), "keep");
});
test("pending 중 send는 같은 참조로 무시(중복 전송 방지)", () => {
  const s1 = L.reduce(L.initialState(), { type: "send", message: "a" });
  assert.equal(L.reduce(s1, { type: "send", message: "b" }), s1);
  assert.equal(L.canSend(s1, "b"), false);
});
test("answer: 기록 6개 유지, 출처 id, 비통 톤", () => {
  let s = L.initialState();
  for (let i = 0; i < 4; i++) {
    s = L.reduce(s, { type: "send", message: `q${i}` });
    s = L.reduce(s, { type: "answer", message: `q${i}`, body: { answer: `a${i}`, mode: "normal", sources: [{ id: `d${i}` }] } });
  }
  assert.equal(s.history.length, 6);
  assert.deepEqual(s.history.at(-1), { role: "assistant", content: "a3" });
  assert.deepEqual(s.lastSourceIds, ["d3"]);
  s = L.reduce(L.reduce(s, { type: "send", message: "x" }), { type: "answer", message: "x", body: { answer: "y", mode: "serious", sources: [] } });
  assert.equal(s.tone, "grief");
  s = L.reduce(L.reduce(s, { type: "send", message: "z" }), { type: "answer", message: "z", body: { answer: "w", mode: "out_of_scope", sources: [] } });
  assert.equal(s.tone, null);
});
test("unavailable은 기록·톤 유지, limit 이후 send 무시", () => {
  let s = L.reduce(L.initialState(), { type: "diary", emotion: "비통" });
  s = L.reduce(L.reduce(s, { type: "send", message: "q" }), { type: "unavailable" });
  assert.equal(s.status, "idle"); assert.equal(s.tone, "grief"); assert.deepEqual(s.history, []);
  const locked = L.reduce(L.reduce(s, { type: "send", message: "q" }), { type: "limit" });
  assert.equal(L.reduce(locked, { type: "send", message: "q2" }), locked);
});
test("canSend 길이", () => {
  const s = L.initialState();
  assert.equal(L.canSend(s, "   "), false);
  assert.equal(L.canSend(s, "가".repeat(300)), true);
  assert.equal(L.canSend(s, "가".repeat(301)), false);
});

test("상수", () => {
  assert.equal(L.LIMIT_TEXT, "오늘은 그만 쉬어야겠소. 내일 다시 오시오.");
  assert.equal(L.UNAVAILABLE_TEXT, "잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오.");
  assert.equal(L.SOURCE_NOTE, "원문: 『이충무공전서』 난중일기 / 번역: AI");
  assert.equal(L.MAX_LEN, 300); assert.equal(L.HISTORY_MESSAGES, 6);
});
test("kstToday: KST 자정 직전과 연말", () => {
  assert.deepEqual(L.kstToday(new Date("2026-12-31T14:59:59Z")), { year: 2026, month: 12, day: 31, md: "12-31" });
  assert.deepEqual(L.kstToday(new Date("2026-12-31T15:00:00Z")), { year: 2027, month: 1, day: 1, md: "01-01" });
});
test("diaryMeta는 앞자리 0 없음", () => {
  assert.equal(L.diaryMeta("임진년(1592) 4월 13일", "1592-05-03"), "임진년(1592) 4월 13일 · 양력 5월 3일");
});
test("Shift+Enter와 다른 키는 전송 안 함", () => {
  assert.equal(L.shouldSubmit({ key: "Enter", isComposing: false, keyCode: 13, shiftKey: true }), false);
  assert.equal(L.shouldSubmit({ key: "a", isComposing: false, keyCode: 65 }), false);
});
test("새 id는 저장된다", () => {
  const m = new Map();
  const s = { getItem: k => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
  assert.equal(L.getClientId(s, () => "fresh"), "fresh");
  assert.equal(m.get("nj_client_id"), "fresh");
});
test("storage가 null이어도 동작", () => {
  assert.equal(typeof L.getClientId(null, () => "z"), "string");
});
test("idle 아닐 때 answer/limit 외 send만 무시, 상태는 새 객체", () => {
  const s0 = L.initialState();
  const s1 = L.reduce(s0, { type: "send", message: "a" });
  assert.notEqual(s1, s0); assert.equal(s0.status, "idle");
  assert.equal(s1.status, "pending"); assert.equal(s1.lastQuestion, "a");
});

test("오늘의 일기 감정은 첫 답변 전에만 톤에 반영", () => {
  let s = L.reduce(L.initialState(), { type: "send", message: "q" });
  s = L.reduce(s, { type: "answer", message: "q", body: { answer: "a", mode: "normal", sources: [] } });
  assert.equal(L.reduce(s, { type: "diary", emotion: "비통" }), s);
  const pending = L.reduce(L.initialState(), { type: "send", message: "q" });
  assert.equal(L.reduce(pending, { type: "diary", emotion: "비통" }).tone, "grief");
});

test("오늘의 일기는 첫 맥락(lastSourceIds)이 된다", () => {
  const s = L.reduce(L.initialState(), { type: "diary", emotion: "일상", id: "1596-10-09" });
  assert.deepEqual(s.lastSourceIds, ["1596-10-09"]);
  assert.equal(s.history.length, 0);
});

test("첫 답 이후 도착한 오늘의 일기는 lastSourceIds를 바꾸지 않는다", () => {
  let s = L.reduce(L.initialState(), { type: "send", message: "q" });
  s = L.reduce(s, { type: "answer", message: "q", body: { answer: "a", mode: "normal", sources: [{ id: "1597-09-16" }] } });
  const after = L.reduce(s, { type: "diary", emotion: "비통", id: "1596-10-09" });
  assert.equal(after, s);
  assert.deepEqual(after.lastSourceIds, ["1597-09-16"]);
});

test("오늘의 일기 id가 없으면 lastSourceIds는 비어 있다", () => {
  const s = L.reduce(L.initialState(), { type: "diary", emotion: "일상" });
  assert.deepEqual(s.lastSourceIds, []);
});

test("첫 답이 오기 전(pending)에 도착한 오늘의 일기도 맥락으로 반영된다", () => {
  const pending = L.reduce(L.initialState(), { type: "send", message: "q" });
  assert.deepEqual(L.reduce(pending, { type: "diary", emotion: "일상", id: "1596-10-09" }).lastSourceIds, ["1596-10-09"]);
});
