# 난중톡(亂中Talk) 웹 UI 디자인 명세

- 작성: 디자인 세션 / 2026-11-24
- 상태: **사용자 승인 완료 (B안 · 한지 메신저형, 라이트 모드만)**
- 참고 시안: [`nanjung-talk-ui-mockup.html`](./nanjung-talk-ui-mockup.html). 브라우저로 열어 보면 된다. 시안은 확인 편의상 글꼴을 CDN에서 불러오지만, 실제 사이트에서는 §3처럼 자체 호스팅한다.
- 대상: Task 11 프론트엔드 (`web/index.html`, `web/style.css`, `web/app.js`)

---

## 1. 디자인 방향

| 항목 | 결정 |
|---|---|
| 무드 | **한지와 먹.** 한지 미색 바탕, 먹색 글씨, 인주 빨강 포인트 |
| 구조 | **익숙한 메신저형.** 장군 말풍선은 왼쪽, 사용자 말풍선은 오른쪽 |
| 톤 | 진지 7 : 재미 3. 장식은 절제하고, 재미는 장군의 말투가 맡는다 |
| 대상 | 전 연령. 글자 크기 16px 기준(모바일 입력창 포함), 터치 영역 최소 44px |
| 다크 모드 | **만들지 않는다.** `color-scheme: light`로 고정 |
| 감정 표현 | 태그는 글자로 보여 주지 않는다. **비통(serious)일 때만** 화면 톤을 잿빛으로 가라앉힌다(§6) |

한 줄로 말하면 "고서 위에서 하는 카톡"이다. 메신저처럼 바로 쓸 수 있되, 장군의 말과 원문은 명조체로 적어 품격을 지킨다.

**하지 않는 것**
- 이순신 장군의 얼굴·초상 이미지. 프로필 자리에는 '舜' 낙관 도장을 쓴다.
- 이모지 아이콘, 그라데이션 버튼, 보라·네온 같은 "AI 서비스" 색
- 금색·용·태극 같은 과한 전통 장식. 전통 요소는 **도장, 괘선, 명조체** 세 가지로 한정한다.

---

## 2. 색상 토큰

`:root`에 CSS 변수로 정의하고, 컴포넌트에서는 hex를 직접 쓰지 않는다.

```css
:root {
  color-scheme: light;
  --nj-paper:      #F4EFE4; /* 페이지 바탕 (한지) */
  --nj-surface:    #FBF8F1; /* 카드·말풍선·입력창 바탕 */
  --nj-ink:        #2A2622; /* 본문 글자, 사용자 말풍선 바탕, 전송 버튼 */
  --nj-ink-2:      #5C554C; /* 보조 글자 (번역문, 날짜 메타) */
  --nj-ink-3:      #6B6358; /* 3차 글자 (출처 문구, 캡션, 글자 수) */
  --nj-line:       #DCD3C2; /* 테두리·구분선 */
  --nj-seal:       #A8322D; /* 인주 빨강: 도장, 問 표시, 출처 카드 왼쪽 선, 장군 아바타 */
  --nj-seal-soft:  #F3E3DE; /* 인주 연한 배경 (필요할 때만) */
  --nj-disabled:   #BDB4A5; /* 비활성 전송 버튼 */
  --nj-on-ink:     #FBF8F1; /* 먹색·인주 위 글자 */
}

/* 비통 톤 (§6). body 또는 앱 루트에 data-tone="grief" */
[data-tone="grief"] {
  --nj-paper:     #ECEBE6;
  --nj-surface:   #F5F4F0;
  --nj-line:      #D3D1CA;
  --nj-seal:      #55524C; /* 인주색을 잿빛 먹으로 바꾼다 */
  --nj-seal-soft: #E2E0DA;
}
```

**대비 (WCAG AA 4.5:1 이상, 실측)**

| 전경 / 배경 | 대비 |
|---|---|
| ink `#2A2622` / paper | 13.1 |
| ink-2 `#5C554C` / surface | 6.9 |
| ink-3 `#6B6358` / paper | 5.2 |
| ink-3 / grief paper `#ECEBE6` | 4.95 |
| seal `#A8322D` / surface | 6.3 |
| on-ink / seal, on-ink / ink | 6.3 / 14.2 |
| grief seal `#55524C` / grief surface | 7.1 |

**바탕 질감:** 페이지 바탕에만 아주 옅은 점 질감을 깐다. 이미지 파일 없이 CSS로 처리한다. 비통 톤에서는 끈다.
```css
background-image: radial-gradient(rgba(120,100,70,.05) 1px, transparent 1px);
background-size: 5px 5px;
```

---

## 3. 글꼴

| 역할 | 글꼴 | 쓰는 곳 |
|---|---|---|
| 명조 `--nj-serif` | **Noto Serif KR** (OFL) 400·700 | 로고, 오늘의 일기 제목, **한문 원문**, **장군 답변 말풍선**, 안내 문구(한도·장애), 問·舜·도장 글자 |
| 고딕 `--nj-sans` | **Pretendard** (OFL) 400·500·600 | 그 밖의 모든 글(사용자 말풍선, 번역문, 버튼, 메타, 입력창) |

```css
--nj-serif: 'Noto Serif KR', 'Noto Serif TC', 'Batang', serif;
--nj-sans:  'Pretendard', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
```

**자체 호스팅 규칙** (CloudFront 경유 제약)
- 모든 woff2 파일을 `web/fonts/` 아래에 두고, `@font-face`로 직접 선언한다. Google Fonts나 jsDelivr 링크는 쓰지 않는다.
- `font-display: swap`
- **Pretendard:** 공식 배포본의 `pretendard-subset`(KS X 1001 한글 2,350자 + 영문) woff2를 쓴다. 400·500·600 세 굵기면 된다.
- **Noto Serif KR:** 한자 때문에 파일이 크다. 통짜 OTF는 쓰지 않는다. Google Fonts가 나눠 둔 **`unicode-range` 분할 woff2**(400·700)를 내려받아 `@font-face` 여러 개로 그대로 옮긴다. 그러면 브라우저는 화면에 나온 글자가 들어 있는 조각만 받는다.
- 원문에 Noto Serif KR에 없는 드문 한자가 나오면 시스템 명조로 넘어간다(fallback 순서는 위 `--nj-serif`). 이 정도는 허용한다. 한자가 두부(□)로 나오지 않는지만 확인한다.
- 한문 원문 요소에는 `lang="lzh"`(한문)를 붙인다. 브라우저가 글리프를 고를 때 쓰고, 스크린리더가 한국어로 읽지 않게 하는 데도 쓴다.

**크기 체계** (rem 기준 16px)

| 토큰 | 크기 / 행간 | 굵기 | 쓰는 곳 |
|---|---|---|---|
| logo | 19px / 1.2 | serif 700 | 헤더 `亂中Talk` |
| title | 18px / 1.4 | serif 700 | 오늘의 일기 제목 |
| answer | 16px / 1.75 | serif 400 | 장군 답변 말풍선 |
| original | 16px / **30px 고정**, 자간 1.5px | serif 400 | 한문 원문(카드) |
| body | 16px / 1.6 | sans 400 | 사용자 말풍선, 입력창 |
| translation | 15px / 1.6 | sans 400 | 번역문 |
| chip | 15px / 1.4 | sans 400 | 추천 질문 버튼 |
| source-orig | 14px / 1.6, 자간 1px | serif 400 | 출처 카드 원문 |
| meta | 13px / 1.5 | sans 400·600 | 날짜 라벨, 출처 카드 번역 |
| caption | 12px / 1.5 | sans 400 | 출처 문구, 글자 수, "이 답의 근거가 된 일기" |

> 시안은 375px 화면에 맞추려고 몇 곳을 14~15px로 그렸다. 구현할 때는 위 표를 따른다. **입력창은 iOS 확대를 막기 위해 반드시 16px 이상**이어야 한다.

---

## 4. 간격·모양·레이아웃

- **간격 단위 4px:** `4 / 8 / 12 / 16 / 24 / 32`
- **모서리:** 카드·말풍선 14px, 버튼·입력창 12px, 출처 카드 8px, 도장 4px, 배지 999px
- **그림자는 쓰지 않는다.** 깊이는 테두리(`1px solid var(--nj-line)`)와 바탕색 차이로만 낸다.

**레이아웃**
- 화면은 세 덩어리다. 헤더(고정 상단) / 대화 스크롤 영역 / 입력창(고정 하단)
- 본문 칼럼: `width: 100%; max-width: 720px; margin: 0 auto;` 좌우 여백 16px, 768px 이상에서는 24px
- 높이는 `100dvh`로 잡는다(모바일 주소창 대응). 입력창에는 `padding-bottom: max(14px, env(safe-area-inset-bottom))`
- `<meta name="viewport" content="width=device-width, initial-scale=1">`. 확대는 막지 않는다.
- 가로 스크롤이 생기면 안 된다. 긴 원문은 `overflow-wrap: anywhere`

**브레이크포인트**

| 폭 | 규칙 |
|---|---|
| < 768px (모바일, 기준 375px) | 출처 카드 **1열 세로 쌓기**, 사용자 말풍선 왼쪽 여백 48px, 말풍선 최대폭 = 칼럼 − 28px |
| ≥ 768px (태블릿·데스크톱) | 출처 카드 **가로 배치** `grid-template-columns: repeat(N, 1fr)`(N = 카드 수, 최대 3), 말풍선 최대폭 80% |

---

## 5. 컴포넌트

### 5.1 헤더
- 왼쪽: `亂中Talk`(serif 700 19px)와 그 옆 `난중톡`(sans 12px, ink-3)
- 오른쪽: `日記` 2행 도장. 30×30px, `2px solid var(--nj-seal)`, 인주색 글자, `rotate(-4deg)`. 장식이라 `aria-hidden="true"`
- 아래에 1px line 구분선을 두고, 바탕은 paper(불투명)

### 5.2 오늘의 일기 카드
대화 영역 맨 위에 놓이는 첫 메시지 묶음이다. 순서는 다음과 같다.
1. **카드**(surface, line 테두리, radius 14, padding 16)
   - 제목: `N년 전 오늘, 장군의 일기`. `exact=false`면 `가장 가까운 날의 일기`
   - 메타: `{label} · 양력 M월 D일`(ink-2 13px)
   - `exact=false`일 때는 메타 옆에 작은 알약 `M월 D일의 일기는 없소`(오늘 날짜)를 붙인다. paper 바탕, line 테두리, 12px
   - 원문: serif, 행간 30px 고정, 자간 1.5px. 배경에 **붉은 괘선**을 깐다(줄마다 아래에 1px 선).
     ```css
     background-image: repeating-linear-gradient(to bottom, transparent 0 29px, rgba(168,50,45,.18) 29px 30px);
     ```
     비통 톤에서는 선 색을 `rgba(85,82,76,.18)`로 바꾼다.
   - 번역: `[AI 번역]` 배지(11px 알약, ink-3 테두리)를 앞에 붙이고 ink-2 15px로 적는다.
   - 출처 문구: `원문: 『이충무공전서』 난중일기 / 번역: AI`(caption, ink-3)
2. **장군의 첫 말풍선:** `intro`를 그대로 넣고 `무엇이든 물어보시오.`를 덧붙인다.
3. **추천 질문 버튼 3개**(§5.5): 말풍선 아래, 아바타 오른쪽 칼럼에 세로로 놓는다.

**상태**
- 로딩: 같은 크기의 카드 안에 스켈레톤 막대 5개(제목 70%, 메타 45%, 본문 100/85/60%). 색은 `#EBE4D6`↔`#F3EEE4`이고 shimmer는 1.4s다. reduced-motion이면 정지한다. `aria-busy="true"`
- 실패: 카드 자리에 안내 박스(§5.7)를 `잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오.` 문구와 [다시 불러오기] 버튼으로 보여 준다. 입력창은 그대로 쓸 수 있게 둔다.

### 5.3 사용자 말풍선
- 오른쪽 정렬. 바탕 ink, 글자 on-ink, sans 16px
- radius `14 14 4 14`(오른쪽 아래만 뾰족), padding `9px 13px`
- 위 여백 14px

### 5.4 장군 말풍선
- `[아바타 36px] [이름 + 말풍선 + 부속]` 가로 배치, gap 8px
- 아바타: 36×36, radius 8, seal 바탕, on-ink 글자 '舜'(serif 700 17px). `aria-hidden="true"`
- 이름 `이순신`: 12px ink-2, 말풍선 위 3px
- 말풍선: surface 바탕, line 테두리, radius `4 14 14 14`(왼쪽 위만 뾰족), padding `10px 13px`, **serif 16px / 1.75**
- 부속(아래 중 하나)
  - `normal`·`serious`: `이 답의 근거가 된 일기`(caption) + 출처 카드 묶음(§5.6)
  - `out_of_scope`·`modern`: 추천 질문 버튼(§5.5). 출처 카드는 넣지 않는다.
- **생성 중:** 말풍선 자리에 먹점 3개를 넣는다. 각 7px 원, ink색, 1.2s 주기로 0.2s씩 엇갈려 투명도 0.2→0.8과 scale 0.85→1이 바뀐다(먹이 번지는 느낌). `role="status" aria-label="답을 쓰는 중"`. reduced-motion이면 정지(투명도 0.5)

### 5.5 추천 질문 버튼 (chip)
- 너비 100%(아바타 오른쪽 칼럼), 최소 높이 44px, padding `9px 14px`, radius 12, surface 바탕, line 테두리, sans 15px
- 앞에 인주색 serif 700 `問`을 붙이고 간격 10px. CSS `::before`로 넣으므로 스크린리더는 질문 텍스트만 읽는다.
- 버튼 사이 간격 8px

| 상태 | 스타일 |
|---|---|
| 기본 | 위와 같음 |
| hover (포인터 기기만, `@media (hover:hover)`) | 테두리 ink-3, 바탕 `#FFFFFF`, 150ms |
| active(눌림) | 바탕 paper, `transform: scale(.98)`, 100ms |
| focus-visible | `outline: 2px solid var(--nj-ink); outline-offset: 2px` |
| disabled (답변 생성 중, 한도 초과) | `opacity: .5`, `cursor: default` |

- 누르면 그 질문을 바로 전송한다. 입력창을 거치지 않는다.

### 5.6 출처 카드
- 묶음: `display:grid; gap:8px;` 모바일 1열, 768px 이상은 카드 수만큼 열(최대 3)
- 카드: surface 바탕, line 테두리, **왼쪽 3px seal 선**, radius 8, padding `10px 12px`, `<article>`
  1. 날짜 라벨: 13px sans 600, ink (예: `임진년(1592) 4월 13일`)
  2. 원문 첫 문장: serif 14px, 자간 1px, `lang="lzh"`
  3. 번역 첫 문장: 13px ink-2
  4. 출처 문구: caption ink-3, 위 여백 6px
- 클릭 동작은 없다(MVP). hover 효과도 넣지 않는다. 눌러지는 것처럼 보이면 안 된다.
- 데스크톱에서 카드 높이가 다르면 `align-items: stretch`로 맞춘다.

### 5.7 안내 박스 (한도 초과·일시 장애)
대화 흐름 안, 사용자 말풍선 다음에 장군 말풍선 대신 들어간다.
- 가운데 정렬. surface 바탕, **1px dashed ink-3 테두리**, radius 14, padding 16
- 위: 36×36 도장(§5.1 스타일), 아래: serif 16px 문구

| 상황 | 도장 | 문구 | 부가 | 입력창 |
|---|---|---|---|---|
| 429 하루 한도 초과 | `休` | 오늘은 그만 쉬어야겠소.<br>내일 다시 오시오. | caption `오늘 여쭐 수 있는 횟수를 모두 쓰셨소` | **잠금.** placeholder `내일 다시 여쭐 수 있소`, chip도 모두 disabled |
| 503 일시 장애 / 네트워크 오류 | `息` | 잠시 숨을 고르겠소.<br>조금 뒤 다시 물어 주시오. | [다시 여쭙기] 버튼(최소 높이 44, 1px ink 테두리, 투명 바탕). 누르면 직전 질문을 다시 보낸다 | 다시 쓸 수 있게 열어 둔다 |

- 문구는 API가 준 `answer`를 그대로 쓰고, 위 표의 문구는 기본값으로 둔다. `role="alert"`

### 5.8 입력창 (composer)
- 하단 고정. paper 바탕, 위쪽 1px line. padding `10px 12px` + safe-area
- input: 높이 44, radius 12, surface 바탕, line 테두리, padding `0 14px`, **16px**. placeholder `장군께 여쭐 말을 적으시오`, `aria-label="질문 입력"`
- 전송 버튼: 44×44, radius 12, ink 바탕, on-ink 위쪽 화살표 SVG(stroke 2.2, 20px). 이모지는 쓰지 않는다. `aria-label="보내기"`
- Enter로 전송한다. 한글 IME 조합 중(`isComposing`)의 Enter는 무시한다.
- 글자 수: 250자를 넘으면 입력창 아래 오른쪽에 `287 / 300`(caption)을 보여 준다. 280자를 넘으면 seal색. 300자가 상한이다(`maxlength="300"`).

| 상태 | input | 전송 버튼 |
|---|---|---|
| 기본(빈 값) | 활성 | **비활성**(disabled 색) |
| 입력 있음 | 활성 | 활성(ink) |
| focus | 테두리 ink-2, `outline: 2px solid var(--nj-ink); outline-offset: 1px` | – |
| 답변 생성 중 | disabled(글자 ink-3) | disabled |
| 한도 초과 | disabled, placeholder 교체 | disabled |

---

## 6. 감정 톤: 비통(serious)

API 응답 `mode === "serious"`일 때만 적용한다. 다른 감정(일상, 유머·불평, 분노)은 화면에서 구분하지 않는다.

1. **그 답변 말풍선**에 `.is-grief`를 붙이면 계속 남는다.
   - 말풍선 바탕 `#F1F0EC`, 테두리 `#CFCCC4`, 글자 `#34322E`
   - 아바타 바탕 `#55524C`
2. **화면 전체 톤:** 앱 루트에 `data-tone="grief"`를 붙인다. §2의 비통 변수로 바뀌고, 바탕 질감이 꺼지고, 인주 빨강이 잿빛 먹으로 바뀐다.
   - 전환은 `background-color`와 색 변수 **600ms ease**. 천천히 가라앉게 한다.
   - 다음 응답이 `normal`(또는 out_of_scope·modern)이면 `data-tone`을 지운다. 돌아올 때도 600ms
3. **오늘의 일기**의 `entry.emotion === "비통"`이면 첫 화면부터 `data-tone="grief"`로 시작한다.
4. reduced-motion이면 전환 없이 바로 바꾼다.
5. 화면 어디에도 "비통" 같은 글자 태그는 보이지 않는다.

---

## 7. 움직임

| 대상 | 동작 | 시간 |
|---|---|---|
| 새 메시지 등장 | `opacity 0→1`, `translateY(6px→0)` | 200ms ease-out |
| 출처 카드·chip 등장 | 위와 같고, 카드마다 50ms씩 늦게 | 200ms |
| 생성 중 먹점 | §5.4 | 1.2s 반복 |
| 비통 톤 전환 | §6 | 600ms |
| hover·press | 색 / scale | 100~150ms |
| 자동 스크롤 | 새 메시지가 오면 맨 아래로 `scroll-behavior: smooth` | – |

- `@media (prefers-reduced-motion: reduce)`에서는 위 동작을 모두 없앤다(즉시 최종 상태).
- width, height, top 같은 레이아웃 속성은 애니메이션하지 않는다. opacity와 transform만 쓴다.

---

## 8. 접근성 체크리스트

- [ ] 대화 영역 `role="log" aria-live="polite"`. 새 장군 답이 오면 읽어 준다.
- [ ] 장식 요소(도장, 舜 아바타, 問)는 `aria-hidden` 또는 `::before` 처리
- [ ] 모든 버튼에 보이는 텍스트나 `aria-label`
- [ ] focus-visible 링을 지우지 않는다(ink 2px)
- [ ] 터치 영역 44×44 이상, 인접 버튼 간격 8px 이상
- [ ] 한문 원문 `lang="lzh"`
- [ ] 전송 후 포커스는 입력창에 남긴다. 한도 초과로 잠기면 안내 박스로 옮긴다.
- [ ] 색만으로 정보를 전달하지 않는다. 비통 톤은 분위기 장치일 뿐이고, 의미는 답변 텍스트가 전한다.
- [ ] 200% 확대에서 가로 스크롤이 생기지 않는다.

---

## 9. 확인용 화면 목록 (시안 HTML과 대응)

| 시안 번호 | 화면 |
|---|---|
| 1-a | 첫 화면, 오늘의 일기(exact) + intro 말풍선 + 추천 질문 3개(hover 1개) |
| 1-b | exact=false 표기, 오늘의 일기 로딩 스켈레톤 |
| 2-a | 모바일 375px 대화, 출처 카드 세로, 답변 생성 중(입력 잠금) |
| 2-b | 데스크톱, 720px 칼럼, 출처 카드 3열 |
| 3-a | 비통(serious) 톤 |
| 3-b | 일기 밖 질문(카드 없이 chip), 503 안내와 다시 여쭙기, 글자 수 경고 |
| 3-c | 429 하루 한도 초과, 입력 잠금 |

시안에 쓴 원문·번역·답변 문장은 분위기를 보여 주려는 예시다. 실제 데이터와 다르다.
