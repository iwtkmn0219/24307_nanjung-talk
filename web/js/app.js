// 진입점: 상태 + api + view 연결
import { postChat, getDiary } from "./api.js";
import { canSend, getClientId, initialState, kstToday, reduce, requestSourceIds, shouldSubmit } from "./logic.js";
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
// 일기 카드와 첫 인사는 대화 맨 위의 고정 슬롯 하나에 함께 넣는다(늦게 와도 대화 순서를 지킨다).
const diarySlot = document.createElement("div");
diarySlot.className = "diary-slot";
log.prepend(diarySlot);

async function loadDiary() {
  diarySlot.replaceChildren(V.diarySkeleton());
  const today = kstToday(new Date()); // 요청(md)과 화면 문구가 같은 KST 날짜를 쓴다
  const r = await getDiary({ base, md: today.md, query: mockQuery });
  if (r.kind !== "ok") {
    diarySlot.replaceChildren(V.diaryError(() => loadDiary()));
    render();
    return;
  }
  const body = r.body;
  const intro = `${body.entry.intro} 무엇이든 물어보시오.`;
  diarySlot.replaceChildren(V.diaryCard(body, today), V.generalBubble(intro, {}, V.chips(body.questions, q => send(q, { anchorIds: [body.entry.id] }))));
  dispatch({ type: "diary", emotion: body.entry.emotion, id: body.entry.id });
  render();
}

// ---- 대화 ----
function pick(question) {
  send(question);
}

// anchorIds: 오늘 일기 카드에서 누른 질문은 그 일기를 기준으로 보낸다(다른 답변 뒤에 눌러도, 다시 여쭙기에서도 유지)
async function send(text, { retryOf = null, anchorIds = null } = {}) {
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
    base, clientId, message, history: state.history, lastSourceIds: requestSourceIds(state, anchorIds),
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
    // 이 안내 박스의 [다시 여쭙기]는 이 박스를 만든 질문(message)을 다시 보낸다
    const box = V.notice("unavailable", r.kind === "unavailable" ? r.answer : null,
      () => send(message, { retryOf: box, anchorIds }));
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
