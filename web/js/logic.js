// 순수 로직과 상태 전이. DOM에 닿지 않는다(node --test로 검사).

export const LIMIT_TEXT = "오늘은 그만 쉬어야겠소. 내일 다시 오시오.";
export const UNAVAILABLE_TEXT = "잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오.";
export const SOURCE_NOTE = "원문: 『이충무공전서』 난중일기 / 번역: AI";
export const MAX_LEN = 300;
export const HISTORY_MESSAGES = 6;
const COUNTER_FROM = 250;
const WARN_FROM = 280;
const CLIENT_ID_KEY = "nj_client_id";

const kstFormat = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
});

/** 기기 시간대와 상관없이 KST(Asia/Seoul) 날짜 */
export function kstToday(now) {
  const parts = Object.fromEntries(kstFormat.formatToParts(now).map(p => [p.type, p.value]));
  const month = Number(parts.month), day = Number(parts.day);
  return { year: Number(parts.year), month, day, md: `${parts.month}-${parts.day}` };
}

function solarParts(solarDate) {
  const [y, m, d] = solarDate.split("-").map(Number);
  return { y, m, d };
}

export function diaryTitle(exact, solarDate, kstYear) {
  if (!exact) return "가장 가까운 날의 일기";
  return `${kstYear - solarParts(solarDate).y}년 전 오늘, 장군의 일기`;
}

export function diaryMeta(label, solarDate) {
  const { m, d } = solarParts(solarDate);
  return `${label} · 양력 ${m}월 ${d}일`;
}

export function missingPill(today) {
  return `${today.month}월 ${today.day}일의 일기는 없소`;
}

export function counter(len) {
  if (len <= COUNTER_FROM) return { text: null, warn: false };
  return { text: `${len} / ${MAX_LEN}`, warn: len > WARN_FROM };
}

/** Enter 전송. 한글 IME 조합 중(isComposing 또는 keyCode 229)과 Shift+Enter는 제외 */
export function shouldSubmit(ev) {
  return ev.key === "Enter" && !ev.isComposing && ev.keyCode !== 229 && !ev.shiftKey;
}

let memoryClientId = null;

/** localStorage의 nj_client_id. 저장소가 막혀 있으면 이 탭 동안 같은 메모리 UUID */
export function getClientId(storage, uuid) {
  try {
    const saved = storage?.getItem(CLIENT_ID_KEY);
    if (saved) return saved;
  } catch { /* 사파리 개인 정보 보호 등 */ }
  const id = uuid();
  try {
    if (storage) {
      storage.setItem(CLIENT_ID_KEY, id);
      return id;
    }
  } catch { /* 저장 실패 → 메모리 */ }
  memoryClientId ??= id;
  return memoryClientId;
}

export function initialState() {
  return { status: "idle", history: [], lastSourceIds: [], lastQuestion: null, tone: null };
}

export function canSend(state, text) {
  const len = text.trim().length;
  return state.status === "idle" && len >= 1 && len <= MAX_LEN;
}

/** 상태 전이. 무시할 때는 같은 참조를 돌려준다(중복 전송 방지 판단에 쓴다). */
export function reduce(state, action) {
  switch (action.type) {
    case "send":
      if (state.status !== "idle") return state;
      return { ...state, status: "pending", lastQuestion: action.message };
    case "answer": {
      const body = action.body;
      const history = [...state.history,
        { role: "user", content: action.message },
        { role: "assistant", content: body.answer }].slice(-HISTORY_MESSAGES);
      return {
        ...state, status: "idle", history,
        lastSourceIds: (body.sources ?? []).map(s => s.id),
        tone: body.mode === "serious" ? "grief" : null,
      };
    }
    case "limit":
      return { ...state, status: "locked" };
    case "unavailable":
      if (state.status === "locked") return state;
      return { ...state, status: "idle" };
    case "diary":
      return { ...state, tone: action.emotion === "비통" ? "grief" : null };
    default:
      return state;
  }
}
