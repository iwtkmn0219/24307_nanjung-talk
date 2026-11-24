// 진입점: 상태 + api + view 연결
import { postChat, getDiary } from "./api.js";
import { canSend, getClientId, initialState, kstToday, reduce, shouldSubmit } from "./logic.js";
import * as V from "./view.js";

const app = document.getElementById("app");
const log = document.getElementById("log");
const form = document.getElementById("composer");
const input = document.getElementById("q");

const base = typeof window.API_BASE === "string" ? window.API_BASE : "";
const mockQuery = window.MOCK_SCENARIO ? `scenario=${encodeURIComponent(window.MOCK_SCENARIO)}` : "";

function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map(x => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

function safeStorage() {
  try { return window.localStorage; } catch { return null; }
}

const clientId = getClientId(safeStorage(), uuid);
let state = initialState();

function dispatch(action) {
  const next = reduce(state, action);
  if (next !== state) {
    state = next;
    render();
  }
  return next;
}

function render() {
  if (state.tone) app.dataset.tone = state.tone;
  else delete app.dataset.tone;
  V.setComposer({ status: state.status, text: input.value });
  const busy = state.status !== "idle";
  for (const b of log.querySelectorAll(".chip, .retry")) b.disabled = busy;
}

function scrollToEnd() {
  requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
}

function add(node) {
  if (node) log.append(node);
  scrollToEnd();
  return node;
}

// ---- 오늘의 일기 ----
async function loadDiary(slot) {
  const skeleton = V.diarySkeleton();
  if (slot) slot.replaceWith(skeleton); else add(skeleton);
  const r = await getDiary({ base, query: mockQuery });
  if (r.kind !== "ok") {
    const err = V.diaryError(() => loadDiary(err));
    skeleton.replaceWith(err);
    render();
    return;
  }
  const body = r.body;
  skeleton.replaceWith(V.diaryCard(body, kstToday(new Date())));
  const intro = `${body.entry.intro} 무엇이든 물어보시오.`;
  add(V.generalBubble(intro, {}, V.chips(body.questions, pick)));
  dispatch({ type: "diary", emotion: body.entry.emotion });
  render();
}

// ---- 대화 ----
function pick(question) {
  send(question);
}

async function send(text, { retryOf = null } = {}) {
  const message = text.trim();
  if (!canSend(state, message)) return;
  dispatch({ type: "send", message });
  if (!retryOf) {
    add(V.userBubble(message));
    if (input.value.trim() === message) input.value = "";
  }
  const pending = V.typing();
  if (retryOf) retryOf.replaceWith(pending); else add(pending);
  render();
  scrollToEnd();

  const r = await postChat({
    base, clientId, message, history: state.history, lastSourceIds: state.lastSourceIds,
  });

  if (r.kind === "ok") {
    const b = r.body;
    dispatch({ type: "answer", message, body: b });
    const grounded = b.mode === "normal" || b.mode === "serious";
    const cards = grounded ? V.sources(b.sources) : null;
    const extras = grounded
      ? (cards ? [V.sourcesCaption(), cards] : [])
      : [V.chips(b.suggestions, pick)];
    pending.replaceWith(V.generalBubble(b.answer, { grief: b.mode === "serious" }, ...extras));
    render();
    input.focus();
  } else if (r.kind === "limit") {
    dispatch({ type: "limit" });
    const box = V.notice("limit", r.answer);
    pending.replaceWith(box);
    render();
    box.focus();
  } else {
    dispatch({ type: "unavailable" });
    const box = V.notice("unavailable", r.kind === "unavailable" ? r.answer : null,
      () => send(state.lastQuestion ?? message, { retryOf: box }));
    pending.replaceWith(box);
    render();
    input.focus();
  }
  scrollToEnd();
}

// ---- 입력창 ----
input.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter") return;
  ev.preventDefault(); // 폼 기본 제출을 막고, IME 조합 중 Enter는 무시한다
  if (shouldSubmit(ev)) send(input.value);
});
form.addEventListener("submit", (ev) => {
  ev.preventDefault();
  send(input.value);
});
input.addEventListener("input", render);

render();
loadDiary();
