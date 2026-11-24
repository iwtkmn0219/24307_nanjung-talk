// DOM 생성. 텍스트는 textContent로만 넣는다(HTML 문자열 주입 API는 쓰지 않는다).
import { SOURCE_NOTE, counter, diaryMeta, diaryTitle, missingPill } from "./logic.js";

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function appear(n, i = 0) {
  n.classList.add("appear");
  if (i > 0) n.classList.add(`appear-${Math.min(i, 3)}`);
  return n;
}

export function diarySkeleton() {
  const card = el("section", "diary-card");
  card.setAttribute("aria-busy", "true");
  card.setAttribute("aria-label", "오늘의 일기를 불러오는 중");
  for (const k of ["is-title", "is-meta", "is-body1", "is-body2", "is-body3"]) card.append(el("div", `skeleton ${k}`));
  return card;
}

/** body: GET /diary 응답, today: kstToday() */
export function diaryCard(body, today) {
  const e = body.entry;
  const card = appear(el("section", "diary-card"));
  card.append(el("h2", "diary-title", diaryTitle(body.exact, e.solar_date, today.year)));
  const meta = el("div", "diary-meta", diaryMeta(e.label, e.solar_date));
  if (!body.exact) meta.append(" ", el("span", "pill", missingPill(today)));
  card.append(meta);
  const orig = el("div", "original", e.original);
  orig.lang = "lzh";
  card.append(orig);
  const tr = el("div", "translation");
  tr.append(el("span", "badge", "AI 번역"), e.translation);
  card.append(tr);
  card.append(el("div", "source-note", body.source_note || SOURCE_NOTE));
  return card;
}

export function diaryError(onRetry) {
  const box = notice("unavailable", null, onRetry, "다시 불러오기");
  box.classList.add("diary-error");
  return box;
}

export function userBubble(text) {
  const row = appear(el("div", "msg msg-user"));
  row.append(el("div", "bubble", text));
  return row;
}

function generalShell() {
  const row = appear(el("div", "msg msg-general"));
  const avatar = el("div", "avatar", "舜");
  avatar.setAttribute("aria-hidden", "true");
  const body = el("div", "msg-body");
  body.append(el("div", "name", "이순신"));
  row.append(avatar, body);
  return { row, body };
}

export function typing() {
  const { row, body } = generalShell();
  const dots = el("div", "typing");
  dots.setAttribute("role", "status");
  dots.setAttribute("aria-label", "답을 쓰는 중");
  dots.append(el("i"), el("i"), el("i"));
  body.append(dots);
  return row;
}

/** 장군 말풍선. 부속(출처·추천)은 extras로 받아 말풍선 아래에 붙인다 */
export function generalBubble(text, { grief = false } = {}, ...extras) {
  const { row, body } = generalShell();
  if (grief) row.classList.add("is-grief");
  body.append(el("div", "bubble", text));
  for (const x of extras) if (x) body.append(x);
  return row;
}

export function sourcesCaption() {
  return el("div", "caption", "이 답의 근거가 된 일기");
}

export function sources(cards) {
  if (!cards || cards.length === 0) return null;
  const wrap = el("div", "sources");
  wrap.dataset.count = String(Math.min(cards.length, 3));
  cards.slice(0, 3).forEach((c, i) => {
    const art = appear(el("article", "source-card"), i + 1);
    art.append(el("div", "src-label", c.label));
    const o = el("div", "src-original", c.original_line);
    o.lang = "lzh";
    art.append(o, el("div", "src-translation", c.translation_line), el("div", "source-note", c.note || SOURCE_NOTE));
    wrap.append(art);
  });
  return wrap;
}

export function chips(questions, onPick) {
  if (!questions || questions.length === 0) return null;
  const wrap = el("div", "chips");
  questions.forEach((q, i) => {
    const b = appear(el("button", "chip", q), i + 1);
    b.type = "button";
    b.addEventListener("click", () => onPick(q));
    wrap.append(b);
  });
  return wrap;
}

const NOTICE = {
  limit: { seal: "休", text: "오늘은 그만 쉬어야겠소.\n내일 다시 오시오.", caption: "오늘 여쭐 수 있는 횟수를 모두 쓰셨소" },
  unavailable: { seal: "息", text: "잠시 숨을 고르겠소.\n조금 뒤 다시 물어 주시오." },
};

/** 안내 박스. answer가 있으면 그 문구를 쓰고, 없으면 기본 문구 */
export function notice(kind, answer, onRetry, retryLabel = "다시 여쭙기") {
  const spec = NOTICE[kind];
  const box = appear(el("div", "notice"));
  box.setAttribute("role", "alert");
  box.tabIndex = -1;
  const seal = el("div", "seal", spec.seal);
  seal.setAttribute("aria-hidden", "true");
  box.append(seal, el("p", "notice-text", answer ? answer.replace(/\. /, ".\n") : spec.text));
  if (spec.caption) box.append(el("div", "caption", spec.caption));
  if (onRetry) {
    const b = el("button", "retry", retryLabel);
    b.type = "button";
    b.addEventListener("click", onRetry);
    box.append(b);
  }
  return box;
}

/** 입력창 상태: status는 idle | pending | locked */
export function setComposer({ status, text }) {
  const input = document.getElementById("q");
  const button = document.getElementById("send");
  const counterEl = document.getElementById("counter");
  const locked = status === "locked";
  input.disabled = status !== "idle";
  if (locked) input.placeholder = "내일 다시 여쭐 수 있소";
  const len = text.trim().length;
  button.disabled = status !== "idle" || len === 0 || len > 300;
  const c = counter(text.length);
  counterEl.textContent = c.text ?? "";
  counterEl.classList.toggle("warn", c.warn);
}
