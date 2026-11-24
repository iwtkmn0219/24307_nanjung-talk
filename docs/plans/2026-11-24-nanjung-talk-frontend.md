# 난중톡 프론트엔드 구현 계획 (MVP 플랜 Task 11 대체)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 승인된 '한지 메신저형' 디자인대로 난중톡 단일 페이지 웹 프론트엔드를 만든다. 오늘의 일기, 대화, 출처 카드, 비통 톤, 한도·장애 안내가 들어간다.

**Architecture:** 빌드 도구 없는 바닐라 ES 모듈이다. 순수 로직(`logic.js`: 날짜, 문구, 상태 전이)과 API 호출(`api.js`)은 `node --test`로 단위 테스트한다. DOM 생성(`view.js`)과 연결(`app.js`)은 로컬 목 API(`scripts/mock_api.py`)를 띄워 브라우저에서 시안과 대조해 확인한다. AWS 배포 전이라 실제 API 없이 모든 화면 상태를 재현할 수 있어야 한다.

**Tech Stack:** HTML/CSS/JS(ES2022 모듈), Node 24 내장 테스트 러너(`node --test`, npm 의존성 없음), Python 3.12 표준 라이브러리(목 서버, 글꼴 수집)

**Spec:**
- 디자인 명세: `docs/design/2026-11-24-nanjung-talk-ui.md` (사용자 승인 완료. 색·크기·간격 값은 모두 여기서 그대로 가져온다)
- 시안: `docs/design/nanjung-talk-ui-mockup.html`
- HTTP 계약: `docs/plans/2026-11-24-nanjung-talk-mvp.md` Task 10, 그리고 실제 구현 `src/nanjung/handlers/{chat,diary}.py`

## Global Constraints

- 모델 출력과 원문은 `textContent`로만 넣는다. `innerHTML`, `outerHTML`, `insertAdjacentHTML`은 `web/` 어디에서도 쓰지 않는다.
- 외부 리소스는 쓰지 않는다. 글꼴은 `web/fonts/` 아래에 두고, CDN·Google Fonts 링크도 쓰지 않는다(모든 요청이 CloudFront를 거친다).
- 다크 모드는 없다: `color-scheme: light`. 색은 명세 §2의 CSS 변수로만 쓰고, 컴포넌트에서 hex를 직접 쓰지 않는다(명세 §6의 비통 말풍선 고정색은 예외).
- 고정 문구(명세·MVP 플랜 그대로):
  - 한도 초과 `오늘은 그만 쉬어야겠소. 내일 다시 오시오.`
  - 장애 `잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오.`
  - 출처 `원문: 『이충무공전서』 난중일기 / 번역: AI`
  - placeholder `장군께 여쭐 말을 적으시오`, 잠금 placeholder `내일 다시 여쭐 수 있소`
  - intro 뒤 문구 `무엇이든 물어보시오.`
- 입력: `maxlength="300"`. 250자 초과 시 글자 수 표시, 280자 초과 시 seal색. IME 조합 중 Enter는 무시한다.
- `X-Client-Id`: `localStorage` 키 `nj_client_id`에 UUID v4로 둔다. 저장소 접근이 실패하면 메모리 UUID를 쓴다.
- 날짜 기준은 KST다. 사용자 기기의 시간대와 상관없이 `Asia/Seoul` 날짜를 쓴다.
- 대화 기록: 서버에 보낼 때 `{role, content}` 최근 **6개 메시지**를 보낸다(백엔드 `HISTORY_MESSAGES = 6`). 429·503 안내는 기록에 넣지 않는다.
- 요청 타임아웃 25초. 초과하면 장애(503)와 같게 처리한다.
- 움직임은 opacity·transform만 쓴다. `prefers-reduced-motion: reduce`에서는 모두 끈다.

## Review Focus

1. **모델 답변이나 원문에 HTML처럼 보이는 문자열**(`<img src=x onerror=...>`)이 들어오면 글자 그대로 보여야 하고, 실행되면 안 된다. → Task 4 목 시나리오 `태그` + Step의 grep 검사
2. **중복 전송:** Enter 연타, 생성 중 chip 클릭, 503 [다시 여쭙기] 연타에도 요청은 하나만 나가야 한다. → Task 2 `reduce` 테스트(pending 중 send 무시)
3. **기기 시간대가 KST가 아닐 때**(예: UTC 15:30 = KST 다음 날 00:30): 오늘의 일기 제목 연도와 "일기는 없소" 날짜가 KST 기준이어야 한다. → Task 2 `kstToday` 테스트
4. **localStorage가 예외를 던지는 환경**(사파리 개인 정보 보호, 차단된 쿠키): 페이지가 멈추지 않고 메모리 UUID로 동작해야 한다. → Task 2 `getClientId` 테스트
5. **네트워크 끊김·타임아웃·5xx·JSON이 아닌 응답**: 빈 화면이나 콘솔 오류가 아니라 `息` 안내와 [다시 여쭙기]가 나와야 한다. → Task 3 `postChat` 테스트

---

## 파일 구조

```
web/                         # S3 웹 버킷에 그대로 올라가는 것만 둔다
  index.html                 # 골격: 헤더 / role=log 대화 영역 / 입력창
  config.js                  # window.API_BASE = ""  (로컬 확인 시에만 목 서버 주소)
  style.css                  # 토큰, 레이아웃, 컴포넌트, 비통 톤, 움직임
  fonts/fonts.css            # @font-face 전부 (Pretendard 3개 + Noto Serif KR 분할)
  fonts/pretendard/*.woff2
  fonts/noto-serif-kr/*.woff2
  fonts/OFL.txt              # 두 글꼴의 라이선스
  js/logic.js                # 순수 함수와 상태 전이 (DOM 없음)
  js/api.js                  # fetch 래퍼 (fetchFn 주입)
  js/view.js                 # DOM 생성 (createElement + textContent)
  js/app.js                  # 진입점: 상태 + api + view 연결
scripts/fetch_fonts.py       # 글꼴 1회 수집 (Google Fonts CSS → 로컬 woff2 + fonts.css)
scripts/mock_api.py          # 로컬 목 API (포트 8787, CORS localhost:5500)
tests/web/logic.test.mjs
tests/web/api.test.mjs
```

테스트 파일은 `web/` 밖에 둔다. 웹 버킷에 테스트가 올라가지 않게 하기 위해서다.

---

### Task 1: 글꼴 자체 호스팅 + 페이지 골격 + 스타일 토큰

**Files:**
- Create: `scripts/fetch_fonts.py`, `web/fonts/**`, `web/index.html`, `web/config.js`, `web/style.css`

**Interfaces:**
- Produces (`index.html`의 DOM 훅. Task 4가 이 id를 쓴다)
  - `#app`(앱 루트, `data-tone`을 다는 곳), `#log`(`role="log" aria-live="polite"`), `#composer`(form), `#q`(input), `#send`(button), `#counter`
  - 스크립트: `<script src="config.js"></script>` 다음에 `<script type="module" src="js/app.js"></script>`
- Produces (`style.css` 클래스. Task 4가 이 이름을 쓴다)
  - `.diary-card .diary-title .diary-meta .pill .original .translation .badge .source-note .skeleton`
  - `.msg .msg-user .msg-general .avatar .name .bubble .is-grief .typing`
  - `.chips .chip .sources .source-card .notice .seal .retry`

글꼴 수집 규칙:
- **Pretendard v1.3.9**: 공식 GitHub 릴리스의 `web/static/woff2-subset/Pretendard-{Regular,Medium,SemiBold}.subset.woff2` 3개를 `web/fonts/pretendard/`에 넣는다. 릴리스 안의 경로가 다르면 같은 subset 파일을 찾아 쓰고 ledger에 Ruling을 남긴다.
- **Noto Serif KR 400·700**: `fetch_fonts.py`가 `https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700&display=swap`를 최신 Chrome User-Agent로 받는다. 그 안의 `@font-face` 블록마다 woff2를 `web/fonts/noto-serif-kr/<굵기>-<순번>.woff2`로 저장하고, `src`만 상대경로로 바꾼다. `unicode-range`는 그대로 두고, `font-display: swap`을 유지해 `fonts.css`에 쓴다.
- Pretendard `@font-face` 3개도 같은 `fonts.css` 맨 위에 손으로 적는다(`font-display: swap`).
- `OFL.txt`에 두 글꼴의 저작권 줄과 SIL OFL 1.1 전문을 넣는다.
- `fetch_fonts.py`는 다시 실행해도 결과가 같아야 한다(이미 있는 파일은 건너뜀). 글꼴 파일은 커밋한다. 배포 때 다시 받지 않는다.

- [ ] **Step 1: `python scripts/fetch_fonts.py` 실행**
  Expected: `web/fonts/noto-serif-kr/`에 woff2가 수십 개(대략 100개 이상) 생기고, `fonts.css`의 `@font-face` 수가 woff2 파일 수 + 3(Pretendard)과 같다.
- [ ] **Step 2: Pretendard 3개 배치, `OFL.txt` 작성**
- [ ] **Step 3: `index.html` + `config.js`(`window.API_BASE = "";`) 작성.** `lang="ko"`, viewport는 명세 §4 그대로, `<link rel="stylesheet" href="fonts/fonts.css">`와 `style.css`를 넣는다. 헤더는 `亂中Talk` + `난중톡` + `日記` 도장(`aria-hidden="true"`)이다. 입력창은 `maxlength="300"`, `aria-label="질문 입력"`, 전송 버튼은 `aria-label="보내기"`와 위쪽 화살표 인라인 SVG(stroke 2.2, 20px)다.
- [ ] **Step 4: `style.css` 작성.** 명세 §2(토큰, 비통 변수, 바탕 점 질감), §3(크기 표), §4(레이아웃, `100dvh`, safe-area, 768px 브레이크포인트), §5 각 컴포넌트, §6 비통(600ms 전환, `.is-grief` 고정색), §7 움직임 + reduced-motion을 옮긴다. 값은 명세 숫자를 그대로 쓴다.
- [ ] **Step 5: 외부 리소스 검사**
  Run: `grep -rnE "https?://" web --include=*.html --include=*.css --include=*.js`
  Expected: 결과 없음(SVG `xmlns="http://www.w3.org/2000/svg"`만 예외로 허용)
- [ ] **Step 6: 정적 확인.** `python -m http.server 5500 -d web` → 브라우저에서 헤더와 입력창이 보인다. 개발자도구 네트워크 탭에서 모든 요청이 `localhost:5500`이고, 글꼴이 `fonts/`에서 받아지는지(한글 Pretendard, 로고 Noto Serif KR) 확인한다.
- [ ] **Step 7: Commit** `feat(web): 글꼴 자체 호스팅과 페이지 골격·스타일 토큰`

---

### Task 2: 순수 로직 (`logic.js`)

**Files:**
- Create: `web/js/logic.js`
- Test: `tests/web/logic.test.mjs`

**Interfaces:**
- Produces (모두 named export)
  - `LIMIT_TEXT`, `UNAVAILABLE_TEXT`, `SOURCE_NOTE`, `MAX_LEN = 300`, `HISTORY_MESSAGES = 6`
  - `kstToday(now: Date) -> {year: number, month: number, day: number, md: "MM-DD"}`: `Intl.DateTimeFormat("en-CA", {timeZone: "Asia/Seoul"})`로 계산
  - `diaryTitle(exact: boolean, solarDate: "YYYY-MM-DD", kstYear: number) -> string`: exact면 `${kstYear - 양력연도}년 전 오늘, 장군의 일기`, 아니면 `가장 가까운 날의 일기`
  - `diaryMeta(label: string, solarDate: string) -> string`: `${label} · 양력 ${M}월 ${D}일`(앞자리 0 없음)
  - `missingPill(today: {month, day}) -> string`: `${month}월 ${day}일의 일기는 없소`
  - `counter(len: number) -> {text: string | null, warn: boolean}`: 250 이하이면 `{text: null, warn: false}`, 초과하면 `{text: "287 / 300", warn: len > 280}`
  - `shouldSubmit(ev: {key, isComposing, keyCode, shiftKey}) -> boolean`: Enter이면서 조합 중이 아니고(`isComposing` false이고 `keyCode !== 229`) Shift가 눌리지 않았을 때만 true
  - `getClientId(storage: Storage | null, uuid: () => string) -> string`: 키 `nj_client_id`. 읽기와 쓰기를 try/catch로 감싼다. 실패하면 uuid() 값을 모듈 변수에 캐시해 같은 탭에서는 같은 값을 쓴다.
  - `canSend(state, text: string) -> boolean`: `state.status === "idle"`이고 `text.trim()` 길이가 1~300일 때 true
  - `initialState() -> {status: "idle", history: [], lastSourceIds: [], lastQuestion: null, tone: null}`
  - `reduce(state, action) -> state` (새 객체 반환. 무시할 때는 **같은 참조**를 반환)
    - `{type: "send", message}`: idle이 아니면 무시. idle이면 `status: "pending"`, `lastQuestion: message`
    - `{type: "answer", message, body}`: `status: "idle"`. history에 user/assistant를 덧붙이고 최근 6개만 남긴다. `lastSourceIds = body.sources.map(s => s.id)`. `tone = body.mode === "serious" ? "grief" : null`
    - `{type: "limit"}`: `status: "locked"`(이후 send는 모두 무시)
    - `{type: "unavailable"}`: `status: "idle"`. history, tone, lastSourceIds는 그대로 둔다.
    - `{type: "diary", emotion}`: `tone = emotion === "비통" ? "grief" : null`

- [ ] **Step 1: 실패하는 테스트 작성**

```js
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
```

- [ ] **Step 2: 실패 확인**
  Run: `node --test tests/web/`
  Expected: FAIL(모듈 없음)
- [ ] **Step 3: `web/js/logic.js` 구현**
- [ ] **Step 4: 통과 확인**
  Run: `node --test tests/web/`
  Expected: 전부 PASS
- [ ] **Step 5: Commit** `feat(web): 프론트 순수 로직과 상태 전이`

---

### Task 3: API 호출 (`api.js`)

**Files:**
- Create: `web/js/api.js`
- Test: `tests/web/api.test.mjs`

**Interfaces:**
- Consumes: `LIMIT_TEXT`, `UNAVAILABLE_TEXT`(Task 2)
- Produces
  - `postChat({base, clientId, message, history, lastSourceIds, fetchFn = fetch, timeoutMs = 25000}) -> Promise<Result>`
    - 요청: `POST ${base}/chat`, 헤더 `content-type: application/json`, `x-client-id`, body `{message, history, last_source_ids}`
    - 200 → `{kind: "ok", body}`
    - 429 → `{kind: "limit", answer: body.answer ?? LIMIT_TEXT}`
    - 400 → `{kind: "invalid"}`
    - 503, 그 밖의 상태, 네트워크 예외, `AbortController` 타임아웃, JSON 파싱 실패 → `{kind: "unavailable", answer: body?.answer ?? UNAVAILABLE_TEXT}`
  - `getDiary({base, fetchFn = fetch, timeoutMs = 25000}) -> Promise<{kind: "ok", body} | {kind: "error"}>`: `GET ${base}/diary`(md는 보내지 않는다. 서버가 KST 오늘로 정한다). 200이 아니거나 예외가 나면 error

- [ ] **Step 1: 실패하는 테스트 작성** (가짜 `fetchFn` 주입)

```js
const res = (status, body) => async () => ({ status, ok: status < 300, json: async () => body });
test("요청 형식", async () => {
  let seen; const f = async (url, init) => { seen = { url, init }; return res(200, { answer: "a", mode: "normal", sources: [], suggestions: [] })(); };
  await postChat({ base: "http://x", clientId: "cid", message: "m", history: [], lastSourceIds: ["d1"], fetchFn: f });
  assert.equal(seen.url, "http://x/chat");
  assert.equal(seen.init.headers["x-client-id"], "cid");
  assert.deepEqual(JSON.parse(seen.init.body), { message: "m", history: [], last_source_ids: ["d1"] });
});
test("429 → limit, 서버 문구 우선", async () => { /* body.answer 있음/없음 두 경우 */ });
test("503 → unavailable", async () => { /* answer === 서버 문구 */ });
test("네트워크 예외 → unavailable 기본 문구", async () => { /* fetchFn이 throw → answer === UNAVAILABLE_TEXT */ });
test("JSON 아님 → unavailable", async () => { /* json()이 throw, status 502 */ });
test("타임아웃 → unavailable", async () => { /* signal abort 때까지 대기하는 fetchFn, timeoutMs: 10 */ });
test("400 → invalid", async () => {});
test("getDiary 200/404/예외", async () => {});
```

- [ ] **Step 2: FAIL 확인** `node --test tests/web/`
- [ ] **Step 3: `web/js/api.js` 구현**
- [ ] **Step 4: PASS 확인** `node --test tests/web/` → Task 2 테스트까지 전부 PASS
- [ ] **Step 5: Commit** `feat(web): 대화·일기 API 호출`

---

### Task 4: 화면 연결 + 로컬 목 API + 시안 대조

**Files:**
- Create: `web/js/view.js`, `web/js/app.js`, `scripts/mock_api.py`

**Interfaces:**
- Consumes: Task 1의 DOM id와 클래스, Task 2의 `reduce`·문구 함수, Task 3의 `postChat`/`getDiary`
- Produces (`view.js`. 모두 DOM 노드를 반환하고, 텍스트는 `textContent`로만 넣는다)
  - `diarySkeleton()`, `diaryCard(body, today)`, `diaryError(onRetry)`
  - `userBubble(text)`, `typing()`, `generalBubble(text, {grief: boolean})`
  - `sources(cards)`: 0개면 null. 카드마다 `<article class="source-card">`, 원문 줄에 `lang="lzh"`
  - `chips(questions, onPick)`
  - `notice(kind: "limit" | "unavailable", answer, onRetry?)`: `role="alert"`, 도장은 limit이면 `休`, unavailable이면 `息`
  - `setComposer({status, text})`: 버튼·입력 disabled, locked이면 placeholder 교체, 글자 수 표시

`app.js` 흐름(명세의 해당 절을 따른다):
1. 시작: `diarySkeleton` → `getDiary`
   - ok이면 `diaryCard` + 장군 말풍선(`intro` + ` 무엇이든 물어보시오.`) + `chips(questions)`, 그리고 `reduce({type: "diary", emotion})`
   - error이면 `diaryError` 박스. [다시 불러오기]를 누르면 다시 시도하고, 입력창은 열어 둔다.
2. 전송(입력창 Enter·버튼·chip 공통): `canSend` → `reduce(send)` → `userBubble` → `typing` → `postChat`
   - ok: typing 자리를 `generalBubble`로 바꾼다. normal·serious면 `이 답의 근거가 된 일기` 캡션과 `sources`, out_of_scope·modern이면 `chips(suggestions)`를 붙인다.
   - limit: `notice("limit")`, 모든 chip disabled, 포커스를 안내 박스로 옮긴다(`tabindex="-1"`).
   - unavailable: `notice("unavailable", answer, retry)`. [다시 여쭙기]는 `lastQuestion`을 다시 보내되 사용자 말풍선은 새로 만들지 않는다. 누른 안내 박스는 typing으로 바꾼다.
   - invalid: unavailable과 같게 처리한다(입력 검증을 통과한 뒤라 정상 흐름에서는 오지 않는다).
3. 상태가 바뀔 때마다 `#app`의 `data-tone`을 `state.tone`에 맞추고, `setComposer`를 부르고, `#log`를 맨 아래로 스크롤한다.
4. pending 동안 모든 chip과 [다시 여쭙기]는 disabled다. 전송이 끝나면 포커스는 입력창에 남긴다.

`mock_api.py` (표준 라이브러리 `http.server`, 포트 8787, `Access-Control-Allow-Origin: http://localhost:5500`, `OPTIONS` 응답, 실제 계약과 같은 JSON. 응답 지연 1.5초)
- `GET /diary`: 기본은 exact=true, 정유년 9월 16일(양력 1597-10-26), emotion `일상`. `?scenario=nearest`이면 exact=false, `?scenario=grief`이면 emotion `비통`, `?scenario=fail`이면 500
  - 페이지에서 시나리오를 고를 수 있게 `config.js`에 `window.MOCK_SCENARIO`(기본 undefined)를 두고, 값이 있을 때만 `app.js`가 쿼리에 붙인다. 운영 `config.js`에는 넣지 않는다.
- `POST /chat`: 메시지 키워드로 응답을 고른다.
  - `아들` → serious, 출처 1개
  - `인공지능` → out_of_scope, sources 비움 + suggestions 3개
  - `한도` → 429
  - `장애` → 503
  - `태그` → normal, answer가 `<img src=x onerror=alert(1)>는 모르오`
  - 그 밖 → normal, 출처 3개

- [ ] **Step 1: `view.js`, `app.js`, `mock_api.py` 구현**
- [ ] **Step 2: innerHTML 계열 사용 검사**
  Run: `grep -rnE "innerHTML|outerHTML|insertAdjacentHTML|document\.write" web`
  Expected: 결과 없음
- [ ] **Step 3: 단위 테스트 재실행** `node --test tests/web/` → 전부 PASS
- [ ] **Step 4: 목 API로 브라우저 확인.** `python scripts/mock_api.py`와 `python -m http.server 5500 -d web`를 띄운다. `config.js`의 `API_BASE`는 `http://localhost:8787`로 바꾸되 커밋하지 않는다. 375px와 1280px 두 폭에서 확인하고, 시안 `docs/design/nanjung-talk-ui-mockup.html`의 같은 번호 화면과 나란히 놓고 스크린샷을 찍어 대조한다(Orca 브라우저 `orca screenshot` 사용 가능).
  - 1-a 오늘의 일기(exact) + intro + chip 3개 / 1-b `nearest` 시나리오의 "가장 가까운 날" + "N월 D일의 일기는 없소" 알약, 로딩 스켈레톤
  - 2-a 375px 대화에서 출처 카드 세로 쌓임, 생성 중 먹점과 입력 잠금 / 2-b 1280px 720px 칼럼, 출처 카드 3열
  - 3-a `아들` → 잿빛 톤 600ms 전환, 다음 일반 질문에서 해제 / `grief` 시나리오로 첫 화면부터 잿빛
  - 3-b `인공지능` → 카드 없이 chip, `장애` → 息 안내 → [다시 여쭙기]가 같은 질문을 다시 보냄(사용자 말풍선 중복 없음), 251자·281자 글자 수 표시
  - 3-c `한도` → 休 안내, 입력·chip 잠금, placeholder 교체, 포커스가 안내 박스로 이동
  - `태그` → `<img ...>`가 글자로 보이고 alert가 뜨지 않음
  - `fail` 시나리오 → 다시 불러오기 박스, 입력창은 사용 가능
  - 한글 입력 중 Enter(조합 확정)로 전송되지 않음, Enter 연타 시 네트워크 탭에 `/chat` 요청 1건
  - 시크릿 창에서 동작, 개발자도구 콘솔 오류 없음
  - 200% 확대에서 가로 스크롤 없음
  - `prefers-reduced-motion` 에뮬레이션에서 움직임 없음
- [ ] **Step 5: 시안과 다른 점이 있으면 명세 쪽 값을 따른다.** 명세와 시안이 서로 다를 때는 명세를 우선하고(명세 §3 주석 참고) ledger에 Ruling을 남긴다.
- [ ] **Step 6: `config.js`가 `window.API_BASE = "";`로 돌아왔고 `MOCK_SCENARIO`가 없는지 확인** `git diff web/config.js` → 변경 없음
- [ ] **Step 7: Commit** `feat(web): 대화 화면 연결과 로컬 목 API`

---

## 이후 작업 (이 플랜 범위 밖)

- 실제 API 연결 확인(MVP 플랜 Task 11 Step 3의 실데이터 확인 항목)은 AWS 배포 승인 뒤 MVP 플랜 Task 10 Step 5~6, Task 12와 함께 한다.
- 웹 버킷에는 `web/`만 올린다. `scripts/`와 `tests/`는 올리지 않는다.
