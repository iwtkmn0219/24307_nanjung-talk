// fetch 래퍼. 실패는 모두 결과 객체로 바꿔 돌려준다(예외를 밖으로 던지지 않는다).
import { LIMIT_TEXT, UNAVAILABLE_TEXT } from "./logic.js";

const TIMEOUT_MS = 25000;

async function request(url, init, fetchFn, timeoutMs) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetchFn(url, { ...init, signal: ctrl.signal });
    let body = null;
    try { body = await r.json(); } catch { body = null; }
    return { status: r.status, body };
  } finally {
    clearTimeout(timer);
  }
}

function isChatBody(b) {
  return b && typeof b.answer === "string" && typeof b.mode === "string" && Array.isArray(b.sources);
}

export async function postChat({ base, clientId, message, history, lastSourceIds, fetchFn = fetch, timeoutMs = TIMEOUT_MS }) {
  const unavailable = (body) => ({
    kind: "unavailable",
    answer: typeof body?.answer === "string" ? body.answer : UNAVAILABLE_TEXT,
  });
  let r;
  try {
    r = await request(`${base}/chat`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-client-id": clientId },
      body: JSON.stringify({ message, history, last_source_ids: lastSourceIds }),
    }, fetchFn, timeoutMs);
  } catch {
    return unavailable(null); // 네트워크 끊김·타임아웃
  }
  if (r.status === 200 && isChatBody(r.body)) return { kind: "ok", body: r.body };
  if (r.status === 429) {
    return { kind: "limit", answer: typeof r.body?.answer === "string" ? r.body.answer : LIMIT_TEXT };
  }
  if (r.status === 400) return { kind: "invalid" };
  return unavailable(r.status === 503 ? r.body : null);
}

export async function getDiary({ base, query = "", fetchFn = fetch, timeoutMs = TIMEOUT_MS }) {
  try {
    const r = await request(`${base}/diary${query ? `?${query}` : ""}`, { method: "GET" }, fetchFn, timeoutMs);
    if (r.status === 200 && r.body && r.body.entry) return { kind: "ok", body: r.body };
  } catch { /* 아래 error */ }
  return { kind: "error" };
}
