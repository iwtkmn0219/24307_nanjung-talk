// fetch 래퍼. 실패는 모두 결과 객체로 바꿔 돌려준다(예외를 밖으로 던지지 않는다).
import { LIMIT_TEXT, SOURCE_NOTE, UNAVAILABLE_TEXT } from "./logic.js";

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

const MODES = new Set(["normal", "serious", "out_of_scope", "modern"]);
const isStr = (v) => typeof v === "string";
const isStrArray = (v) => Array.isArray(v) && v.every(isStr);
const CARD_KEYS = ["id", "label", "original_line", "translation_line"];
const ENTRY_KEYS = ["id", "label", "original", "translation", "emotion", "intro", "solar_date"];

/** 화면이 실제로 쓰는 필드를 API 경계에서 검사한다. 맞지 않으면 null(→ 장애와 같게 처리) */
function chatBody(b) {
  if (!b || !isStr(b.answer) || !MODES.has(b.mode) || !Array.isArray(b.sources)) return null;
  if (!b.sources.every(c => c && typeof c === "object" && CARD_KEYS.every(k => isStr(c[k])))) return null;
  const suggestions = b.suggestions ?? [];
  if (!isStrArray(suggestions)) return null;
  const sources = b.sources.map(c => ({ ...c, note: isStr(c.note) ? c.note : SOURCE_NOTE }));
  return { ...b, sources, suggestions };
}

function diaryBody(b) {
  const e = b?.entry;
  if (!e || typeof e !== "object" || !ENTRY_KEYS.every(k => isStr(e[k]))) return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(e.solar_date)) return null;
  const questions = b.questions ?? [];
  if (!isStrArray(questions) || typeof b.exact !== "boolean") return null;
  return { ...b, questions, source_note: isStr(b.source_note) ? b.source_note : SOURCE_NOTE };
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
  if (r.status === 200) {
    const body = chatBody(r.body);
    return body ? { kind: "ok", body } : unavailable(null);
  }
  // 앱의 하루 한도만 잠금. API Gateway 스로틀(같은 429)은 잠시 뒤 다시 묻게 한다
  if (r.status === 429 && r.body?.answer === LIMIT_TEXT) return { kind: "limit", answer: LIMIT_TEXT };
  if (r.status === 400) return { kind: "invalid" };
  return unavailable(r.status === 503 ? r.body : null);
}

/** md: 브라우저가 계산한 KST 오늘(MM-DD). 화면 문구와 같은 날짜로 요청한다 */
export async function getDiary({ base, md = "", query = "", fetchFn = fetch, timeoutMs = TIMEOUT_MS }) {
  const qs = [md && `md=${encodeURIComponent(md)}`, query].filter(Boolean).join("&");
  try {
    const r = await request(`${base}/diary${qs ? `?${qs}` : ""}`, { method: "GET" }, fetchFn, timeoutMs);
    const body = r.status === 200 ? diaryBody(r.body) : null;
    if (body) return { kind: "ok", body };
  } catch { /* 아래 error */ }
  return { kind: "error" };
}
