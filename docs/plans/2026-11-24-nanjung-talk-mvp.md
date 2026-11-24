# 난중톡(亂中Talk) MVP 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 난중일기 원문(이충무공전서본)에만 근거해 1인칭 하오체로 답하는 이순신 챗봇 웹 서비스를 3주 안에 AWS에 배포한다.

**Architecture:** 로컬 PC 스크립트가 한국고전종합DB에서 월 단위 원문 HTML 61개를 받아 S3 `raw/`에 올린다. VPC 안의 적재 Lambda가 이를 일기 하루 단위로 나누고, 날짜를 변환하고, Bedrock으로 번역·태깅·임베딩한 뒤 RDS(pgvector)와 DynamoDB에 넣는다. 사용자 요청은 CloudFront → API Gateway(HTTP API) → API Lambda 하나(`/chat`·`/diary`) → RDS·Bedrock 순서로 흐른다(기준 구조도: `docs/architecture.png`). 기획서의 "긴 날은 문단 단위로 추가 분할"은 하지 않는다. 가장 긴 하루가 원문 610자라서 하루 = 검색 단위 하나로 충분하다.

**Tech Stack:** Python 3.12 (Lambda), AWS SAM, pg8000, beautifulsoup4, korean-lunar-calendar, boto3, pytest + moto, 바닐라 HTML/JS

**Spec:** `docs/superpowers/specs/2026-11-24-nanjungtalk-spec.md` (기획서 docx를 변환한 것)

## Global Constraints

- 리전: `ap-northeast-2` (서울)
- 임베딩 모델: `amazon.titan-embed-text-v2:0`, body `{"inputText": ..., "dimensions": 1024, "normalize": true}`. 임베딩 대상은 **현대어 번역문**이다.
- 생성 모델: `global.anthropic.claude-haiku-4-5-20251001-v1:0` (Converse API). Haiku 5.5는 이 계정에서 AccessDenied가 나므로 쓰지 않는다.
- 원문 출처: 한국문집총간 `ITKC_MO_0232A`(이충무공전서), 권 데이터 ID `ITKC_MO_0232A_{0080|0090|0100|0110}_010`. 월 문서는 61개, 날짜 항목은 1,593개다(2026-11-24 실측).
- 수집 예절: `robots.txt`가 `Disallow: /`다. 수집은 1회만 하고 요청 간격은 1초 이상 둔다. 받은 원본 HTML은 그대로 보관한다.
- 감정 태그는 정확히 이 네 값만 쓴다: `일상`, `유머·불평`, `분노`, `비통`
- 출처 표기 문구: `원문: 『이충무공전서』 난중일기 / 번역: AI`
- 고정 문구:
  - 사용량 초과: `오늘은 그만 쉬어야겠소. 내일 다시 오시오.`
  - 일기 밖 질문: `처음 듣는 말이라 내 답할 길이 없소.`
  - 현대 정치·외교 질문: `후대의 일은 모르오.`
  - Bedrock 장애: `잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오.`
- 답변 말투: 1인칭 하오체. 주어진 일기에 없는 사실은 지어내지 않는다.
- 로그인은 없다. 브라우저별 `X-Client-Id`(UUID)를 기준으로 하루(KST) 질문 횟수를 `DAILY_LIMIT=20`으로 제한한다.
- 모델 출력과 원문은 프론트에서 `textContent`로만 넣는다. `innerHTML`은 쓰지 않는다.
- DB 비밀번호는 SAM 파라미터(`NoEcho`) → Lambda 환경변수로 넘긴다. Secrets Manager는 엔드포인트 비용 때문에 쓰지 않는다.
- AWS 계정은 개인 루트 계정이다. 첫날 AWS Budgets 알림(월 USD 40(사용자 결정))을 만들고, 이후 작업은 IAM 사용자로 한다.

## Review Focus

1. **현대 정치·외교 질문인데 유사도가 높게 나오는 경우** (예: "요즘 일본이랑 사이 어때요?"는 倭가 나오는 일기와 유사도가 높다): LLM을 호출하지 않고 `후대의 일은 모르오.` 고정 답변을 해야 한다. → Task 8 테스트
2. **"그다음 날은요?"의 다음 날이 공백이거나 일기의 끝인 경우** (임진년 6/10 다음은 8/24, 마지막 날은 무술년 11/17): 다음으로 **존재하는** 일기를 주고, 끝이면 날짜 조건 없이 일반 검색으로 넘어간다. → Task 7 테스트
3. **하루 한도 경계**: 20번째 질문은 허용하고 21번째는 429를 준다. KST 자정이 지나면 다시 허용한다. → Task 9 테스트
4. **Bedrock 스로틀링이나 타임아웃**: 500 스택트레이스가 아니라 503과 함께 `잠시 숨을 고르겠소...` 문구를 돌려준다. → Task 10 테스트
5. **2월 29일 등 일기가 없는 날짜의 '오늘의 일기'**: 366개 월·일 키가 모두 가장 가까운 날의 일기를 가리켜야 한다. → Task 5 테스트

---

## 파일 구조

```
nanjungtalk/
  src/                      # SAM CodeUri (Lambda 패키지 루트)
    requirements.txt        # pg8000, beautifulsoup4, korean-lunar-calendar
    nanjung/
      models.py             # 데이터클래스·상수 (모든 Task 공유)
      parse.py              # 월 HTML → RawEntry
      dates.py              # 음력→양력, 간지 보정, 라벨
      bedrock.py            # embed(), converse() 래퍼
      enrich.py             # 번역·태깅 프롬프트/파싱
      db.py                 # 연결, 스키마, upsert, 검색, 이웃 조회
      today.py              # 오늘의 일기 매핑
      date_resolver.py      # 질문 속 날짜·사건·"다음 날" 해석
      answer.py             # 답변 모드 결정, 프롬프트, 출처 카드
      quota.py              # DynamoDB 사용량 제한
      handlers/ingest.py    # 적재 Lambda
      handlers/api.py       # API Lambda 진입점(routeKey로 /chat, /diary 분기)
      handlers/chat.py diary.py common.py
  scripts/collect.py        # 로컬 PC 전용 수집기
  scripts/ingest_all.sh     # 적재 Lambda 일괄 호출
  sql/schema.sql
  web/index.html app.js style.css config.js
  eval/questions.json run_eval.py
  infra/README.md           # 콘솔 작업 체크리스트 (VPC·RDS·엔드포인트·CloudFront)
  template.yaml
  tests/
```

## 일정 배치

| 주차 | Task |
|---|---|
| 1주 | 1 수집 · 2 파싱 · 3 날짜 · 4 번역·태깅 · 5 임베딩·DB · 6 인프라 + 적재 실행 |
| 2주 | 7 날짜 해석 · 8 검색·답변 · 9 사용량 제한 · 10 API 핸들러·배포 |
| 3주 | 11 프론트엔드 · 12 CloudFront 배포 · 13 기준값 튜닝·최종 점검 |

---

### Task 1: 프로젝트 골격 + 원문 수집기

**Files:**
- Create: `src/nanjung/models.py`, `scripts/collect.py`, `requirements-dev.txt`, `pytest.ini`(`pythonpath = src scripts`), `.gitignore`(`data/`, `.aws-sam/`)
- Test: `tests/test_collect.py`

**Interfaces:**
- Produces (`models.py`):
  - `MonthRef(data_id: str, title: str)`
  - `RawEntry(source_id: str, ganji_year: str, lunar_year: int, lunar_month: int, is_leap: bool, lunar_day: int, day_ganji: str | None, original: str)`
  - `DiaryEntry(RawEntry 필드 + id: str, solar_date: date, ganji_mismatch: bool, label: str, translation: str = "", emotion: str = "", intro: str = "", questions: list[str] = [])`
  - `EMOTIONS = ("일상", "유머·불평", "분노", "비통")`
  - `SOURCE_NOTE = "원문: 『이충무공전서』 난중일기 / 번역: AI"`
- Produces (`collect.py`):
  - `parse_month_list(tree_html: str) -> list[MonthRef]`
  - `collect(out_dir: Path, delay_s: float = 1.0) -> list[MonthRef]`: `data/raw/{data_id}.html`와 `data/raw/index.json`을 쓴다.

엔드포인트(인증키 없음):
- 목록: `https://db.itkc.or.kr/dir/treeAjax?grpId=&itemId=MO&gubun=book&depth=4&cate1=Z&cate2=&dataGubun=문체&dataId={VOL_ID}`
- 본문: `https://db.itkc.or.kr/dir/node?grpId=&itemId=MO&gubun=book&depth=5&cate1=Z&cate2=&dataGubun=최종정보&dataId={data_id}`
- `VOL_IDS = ["ITKC_MO_0232A_0080_010", "ITKC_MO_0232A_0090_010", "ITKC_MO_0232A_0100_010", "ITKC_MO_0232A_0110_010"]`

- [ ] **Step 1: git init, 개발 의존성 설치** (`pytest moto[dynamodb] boto3 beautifulsoup4 requests korean-lunar-calendar pg8000`)
- [ ] **Step 2: 실패하는 테스트 작성**

```python
TREE = """<li data-dataId='ITKC_MO_0232A_0080_010_0010' data-url='...' data-lvl="1"><span title='壬辰正月'>壬辰正月</span></li>
<li data-dataId='ITKC_MO_0232A_0080_010_0020' data-url='...' data-lvl="1"><span title='[壬辰]二月'>[壬辰]二月</span></li>"""

def test_parse_month_list():
    refs = parse_month_list(TREE)
    assert refs == [MonthRef("ITKC_MO_0232A_0080_010_0010", "壬辰正月"),
                    MonthRef("ITKC_MO_0232A_0080_010_0020", "[壬辰]二月")]
```

- [ ] **Step 3: `pytest tests/test_collect.py -v` → FAIL** (import 오류)
- [ ] **Step 4: `models.py`, `collect.py` 구현.** 요청 사이에 `time.sleep(delay_s)`를 넣고, `User-Agent`에 연락처(학교 메일)를 적는다.
- [ ] **Step 5: 테스트 PASS 확인**
- [ ] **Step 6: 로컬 PC에서 실행** `python scripts/collect.py` → `data/raw/`에 HTML 61개와 `index.json`(61개 항목)이 생겨야 한다.
- [ ] **Step 7: Commit** `feat: ITKC 난중일기 원문 수집기`

---

### Task 2: 원문 파싱 (월 HTML → 하루 단위)

**Files:**
- Create: `src/nanjung/parse.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Consumes: `MonthRef`, `RawEntry`
- Produces:
  - `parse_title(title: str) -> tuple[str, int, int, bool]`: (간지 연도, 서기 연도, 월, 윤달 여부). `YEARS = {"壬辰":1592,"癸巳":1593,"甲午":1594,"乙未":1595,"丙申":1596,"丁酉":1597,"戊戌":1598}`
  - `parse_month_page(html: str, ref: MonthRef) -> list[RawEntry]`

실측으로 정한 규칙:
- 본문은 `div.text_body.ori` 아래 `div.xsl_para`에 있다. 문단 하나가 하루다.
- 문단 안의 공백용 `<span style="display:inline-block...">`는 버리고, 공백 문자는 전부 제거한다.
- 날짜 머리 정규식(문단 시작에 고정):
  `^(初[一二三四五六七八九十]|二十[一二三四五六七八九]?|十[一二三四五六七八九]?|三十)日。?(?:([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])|干支。?缺)`
  간지가 빠진 형태(`二十四日干支。缺晴`, `初八日。干支缺`)는 `day_ganji=None`이 된다. 간지 뒤에 `。` 대신 `冬至`가 오는 경우도 매칭된다.
- 정규식이 맞지 않는 문단(예: `初昏發船之際...`)은 바로 앞 날짜의 `original`에 이어 붙인다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
@pytest.mark.parametrize("title,expected", [
    ("壬辰正月", ("壬辰", 1592, 1, False)),
    ("[丙申]閏八月", ("丙申", 1596, 8, True)),
    ("[乙未]十二月", ("乙未", 1595, 12, False)),
])
def test_parse_title(title, expected): assert parse_title(title) == expected

def page(*paras):
    body = "".join(f'<div class="xsl_para">{p}</div>' for p in paras)
    return f'<div class="text_body ori">{body}</div>'

def test_heads_and_variants():
    html = page('初一日庚寅。陰。曉行望<span style="display:inline-block;width:0.8em"></span>闕禮。',
                '十一日乙酉冬至。曉。行望闕禮。',
                '二十四日干支。缺晴。申時。發船',
                '初八日。干支缺詣都督府設慰宴。',
                '初昏發船之際。故停行。')
    es = parse_month_page(html, MonthRef("X", "[甲午]三月"))
    assert [(e.lunar_day, e.day_ganji) for e in es] == [(1,"庚寅"),(11,"乙酉"),(24,None),(8,None)]
    assert es[0].original == "初一日庚寅。陰。曉行望闕禮。"
    assert es[-1].original.endswith("初八日。干支缺詣都督府設慰宴。初昏發船之際。故停行。")

@pytest.mark.skipif(not Path("data/raw/index.json").exists(), reason="원문 미수집")
def test_full_corpus_count():
    assert sum(len(parse_month_page(...)) for ...) == 1593   # index.json의 61개 전부
```

- [ ] **Step 2: FAIL 확인** → **Step 3: 구현** (BeautifulSoup `html.parser`) → **Step 4: PASS 확인** (전체 코퍼스 테스트 포함)
- [ ] **Step 5: Commit** `feat: 난중일기 월 문서 파서`

---

### Task 3: 날짜 변환 (음력 → 양력, 간지 보정)

**Files:**
- Create: `src/nanjung/dates.py`
- Test: `tests/test_dates.py`

**Interfaces:**
- Consumes: `RawEntry`
- Produces:
  - `ganji_of(d: date) -> str`: `GANJI[(d.toordinal() + 14) % 60]` (0 = 甲子). 1592-05-23은 壬寅으로 검증됐다.
  - `to_solar(y: int, m: int, d: int, is_leap: bool, day_ganji: str | None) -> tuple[date, bool]`: (양력 날짜, ganji_mismatch)
  - `assign_dates(entries: list[RawEntry]) -> list[DiaryEntry]`
  - `entry_id(y, m, d, is_leap) -> str`: `"1592-04-13"`, 윤달이면 `"1596-L08-01"`
  - `label(e) -> str`: `"임진년(1592) 4월 13일"`, 윤달이면 `"병신년(1596) 윤8월 1일"`

보정 규칙(실측으로 결정):
- `korean_lunar_calendar`로 기준일을 구한다.
- 일기 간지와 맞는 날짜를 기준일 ±2일 안에서 찾고, 있으면 그 날짜를 쓴다. 정유년 9월은 라이브러리가 하루 이르다.
- ±2일 안에 없으면 라이브러리 값을 그대로 쓰고 `ganji_mismatch=True`로 둔다. 전서본 임진년 5·6월 간지 오류가 이 경우다.
- 간지가 없는 항목은 같은 달의 다른 항목에서 구한 보정값을 쓰고, 같은 달에 간지 있는 항목이 없으면 0을 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
@pytest.mark.parametrize("args,expected", [
    ((1592, 4, 13, False, "壬寅"), (date(1592, 5, 23), False)),
    ((1597, 9, 16, False, "甲辰"), (date(1597, 10, 26), False)),   # 명량, +1 보정
    ((1596, 8, 1, True, "乙丑"), (date(1596, 9, 22), False)),      # 윤8월
    ((1592, 5, 1, False, "庚午"), (date(1592, 6, 10), True)),      # 전서본 간지 오류
])
def test_to_solar(args, expected): assert to_solar(*args) == expected

def test_ganji_of(): assert ganji_of(date(1592, 5, 23)) == "壬寅"
def test_missing_ganji_uses_month_delta():   # 정유 9/15(癸卯) + 9/17(None) → 9/17은 +1 보정 → 1597-10-27
def test_label_and_id():
    assert entry_id(1596, 8, 1, True) == "1596-L08-01"
    assert label(...) == "병신년(1596) 윤8월 1일"
```

- [ ] **Step 2: FAIL** → **Step 3: 구현** → **Step 4: PASS**
- [ ] **Step 5: 전체 코퍼스 점검 스크립트 실행.** `ganji_mismatch=True`인 항목 수를 출력한다. 임진년 5·6월(15건) 외에 나오면 원인을 확인한다.
- [ ] **Step 6: Commit** `feat: 음력-양력 변환과 간지 보정`

---

### Task 4: Bedrock 래퍼 + 번역·감정 태깅

**Files:**
- Create: `src/nanjung/bedrock.py`, `src/nanjung/enrich.py`
- Test: `tests/test_enrich.py`

**Interfaces:**
- Produces:
  - `bedrock.embed(text: str, client=None) -> list[float]` (1024차원)
  - `bedrock.converse(system: str, messages: list[dict], max_tokens: int, temperature: float, client=None) -> str`
  - `class BedrockUnavailable(Exception)`: `ThrottlingException`, `ServiceUnavailableException`, 타임아웃을 이 예외로 감싼다.
  - `enrich.build_prompt(e: DiaryEntry) -> tuple[str, list[dict]]`
  - `enrich.parse_response(text: str) -> dict`: 키는 `translation`, `emotion`, `intro`, `questions`. 잘못되면 `EnrichError`
  - `enrich.enrich(e: DiaryEntry, client=None) -> DiaryEntry`: 파싱이 실패하면 한 번 재시도한다.

프롬프트 결정 사항: 한 번의 호출로 JSON 하나만 출력하게 한다.
- `translation`: 원문 전체를 빠짐없이 옮긴 현대어
- `emotion`: EMOTIONS 중 하나
- `intro`: 장군이 그날을 소개하는 하오체 한 문장, 40자 이내
- `questions`: 그날 일기로 답할 수 있는 추천 질문 3개
- 호출 설정: `max_tokens=1500`, `temperature=0.2`

- [ ] **Step 1: 실패하는 테스트 작성** (가짜 클라이언트 주입)

```python
def test_parse_valid():
    r = parse_response('{"translation":"맑음.","emotion":"일상","intro":"평범한 날이었소.","questions":["a","b","c"]}')
    assert r["emotion"] == "일상" and len(r["questions"]) == 3
@pytest.mark.parametrize("bad", ['{"emotion":"기쁨",...}', 'not json', '{"questions":["a"],...}'])
def test_parse_invalid_raises(bad): ...
def test_parse_strips_code_fence(): # ```json ... ``` 로 감싸진 응답도 통과
def test_enrich_retries_once_then_raises(): # 가짜 클라이언트가 두 번 깨진 응답 → EnrichError, 호출 2회
def test_converse_wraps_throttling(): # ClientError(ThrottlingException) → BedrockUnavailable
```

- [ ] **Step 2: FAIL** → **Step 3: 구현** → **Step 4: PASS**
- [ ] **Step 5: CloudShell이나 로컬에서 실제 호출 1건.** 임진년 4/13 항목을 번역해 본다. "활 열다섯 순"이 번역문에 나오면 통과다.
- [ ] **Step 6: Commit** `feat: Bedrock 래퍼와 번역·태깅`

---

### Task 5: DB 계층 + 오늘의 일기 매핑

**Files:**
- Create: `sql/schema.sql`, `src/nanjung/db.py`, `src/nanjung/today.py`
- Test: `tests/test_db.py`, `tests/test_today.py`

`schema.sql`:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS diary (
  id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
  ganji_year TEXT NOT NULL, lunar_year INT NOT NULL, lunar_month INT NOT NULL,
  is_leap BOOLEAN NOT NULL, lunar_day INT NOT NULL, day_ganji TEXT,
  solar_date DATE NOT NULL, ganji_mismatch BOOLEAN NOT NULL, label TEXT NOT NULL,
  original TEXT NOT NULL, translation TEXT NOT NULL,
  emotion TEXT NOT NULL CHECK (emotion IN ('일상','유머·불평','분노','비통')),
  intro TEXT NOT NULL, questions JSONB NOT NULL, embedding vector(1024) NOT NULL);
CREATE INDEX IF NOT EXISTS diary_embedding_hnsw ON diary USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS diary_solar_date ON diary (solar_date);
```

**Interfaces:**
- Produces (`db.py`):
  - `connect() -> pg8000.native.Connection`: 환경변수 `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, SSL 사용
  - `init_schema(conn) -> None`
  - `upsert(conn, e: DiaryEntry, embedding: list[float]) -> None`: `ON CONFLICT (id) DO UPDATE`
  - `search_sql(date_ids: list[str] | None) -> str`: 유사도는 `1 - (embedding <=> :qvec::vector)`. `date_ids`가 있으면 `WHERE id = ANY(:ids)`. 정렬은 유사도 내림차순, `LIMIT :k`
  - `search(conn, qvec: list[float], k: int = 5, date_ids: list[str] | None = None) -> list[Hit]`
  - `get(conn, ids: list[str]) -> list[DiaryEntry]`
  - `neighbor(conn, entry_id: str, direction: int) -> str | None`: `solar_date` 기준으로 바로 다음(+1)이나 이전(-1)에 **존재하는** 항목. 없으면 None
  - `all_dates(conn) -> list[tuple[str, date]]`
  - `Hit(entry: DiaryEntry, similarity: float)`는 `models.py`에 추가
- Produces (`today.py`):
  - `build_today_map(rows: list[tuple[str, date]]) -> dict[str, dict]`: `"MM-DD"` 키 366개 전부. 값은 `{"ids": [...], "exact": bool}`. 없는 날짜는 원형(12/31↔1/1) 거리로 가장 가까운 월·일의 ids를 쓴다. 거리가 같으면 앞 날짜를 쓴다.
  - `pick(item: dict, year: int) -> str`: `ids[year % len(ids)]`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_search_sql_with_and_without_date():
    assert "ANY(:ids)" in search_sql(["1597-09-16"]) and "ANY" not in search_sql(None)
def test_today_map_has_366_keys_including_0229():
    m = build_today_map([("1592-04-13", date(1592,5,23)), ("1597-09-16", date(1597,10,26))])
    assert len(m) == 366 and m["02-29"]["exact"] is False
    assert m["05-23"] == {"ids": ["1592-04-13"], "exact": True}
def test_today_map_wraps_year_end(): # 12-31 하나만 있을 때 01-01 → 그 id
def test_pick_rotates_by_year(): assert pick({"ids":["a","b"]}, 2026) == "a"
```

- [ ] **Step 2: FAIL** → **Step 3: 구현** → **Step 4: PASS**
- [ ] **Step 5: Commit** `feat: pgvector 스키마와 오늘의 일기 매핑`

---

### Task 6: AWS 인프라 ① + 적재 Lambda + 데이터 적재

**Files:**
- Create: `infra/README.md`, `template.yaml`, `src/requirements.txt`, `src/nanjung/handlers/ingest.py`, `scripts/ingest_all.sh`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: Task 2~5 전부
- Produces: `ingest.lambda_handler(event, context)`. 이벤트는 세 가지다.
  - `{"action": "init_schema"}`
  - `{"action": "ingest", "key": "raw/<data_id>.html"}`: 파싱 → 날짜 → `processed/<data_id>.json`이 있으면 그것을 읽고, 없으면 번역·태깅 후 저장 → 임베딩 → upsert. 반환값은 `{"count": n}`
  - `{"action": "build_today_map"}`: RDS 전체를 읽어 DynamoDB `TodayMap`에 366건을 쓴다.

`infra/README.md`에 적을 콘솔 작업(값 고정):
- VPC `nanjung-vpc` 10.0.0.0/16, 프라이빗 서브넷 2개(2a, 2c). NAT는 만들지 않는다.
- 보안 그룹: `sg-lambda`(아웃바운드 전체), `sg-rds`(5432는 sg-lambda에서만), `sg-endpoint`(443은 sg-lambda에서만)
- VPC 엔드포인트: `com.amazonaws.ap-northeast-2.bedrock-runtime`(Interface, Private DNS 켬, sg-endpoint, **AZ 1개(2a 서브넷)만** — 비용 절감, 사용자 결정), `s3`·`dynamodb`(Gateway, 프라이빗 라우팅 테이블)
- RDS PostgreSQL 16, `db.t4g.micro`, 20GB, 퍼블릭 액세스 끔, 자동 백업 7일, DB 이름 `nanjung`
- S3 버킷 `nanjung-data-<계정ID>`(`raw/`, `processed/`)
- AWS Budgets 월 USD 40 알림(사용자 결정)

`template.yaml`(이 Task 범위):
- `IngestFunction`: python3.12, 512MB, timeout 900, VPC 설정, `ReservedConcurrentExecutions: 2`
- `TodayMapTable`: PK `md`(S)
- IAM 권한
  - `bedrock:InvokeModel`: `arn:aws:bedrock:*::foundation-model/*`, `arn:aws:bedrock:*:${AWS::AccountId}:inference-profile/*`
  - S3 읽기/쓰기, DynamoDB 쓰기
- 파라미터: `DbHost`, `DbPassword`(NoEcho), `SubnetIds`, `LambdaSgId`, `DataBucket`

- [ ] **Step 1: 실패하는 테스트 작성** (S3·Bedrock·DB는 가짜 객체)

```python
def test_ingest_uses_processed_cache(fake_s3_with_processed, fake_bedrock, fake_db):
    out = lambda_handler({"action":"ingest","key":"raw/X.html"}, None)
    assert fake_bedrock.converse_calls == 0 and fake_bedrock.embed_calls == out["count"]
def test_unknown_action_raises(): ...
```

- [ ] **Step 2: FAIL** → **Step 3: 구현** → **Step 4: PASS**
- [ ] **Step 5: 콘솔 체크리스트대로 인프라를 만들고** `sam build && sam deploy --guided`
- [ ] **Step 6: 원문 업로드** `aws s3 sync data/raw s3://nanjung-data-<id>/raw/`
- [ ] **Step 7: 스키마 생성** `aws lambda invoke --function-name <Ingest> --payload '{"action":"init_schema"}' --cli-binary-format raw-in-base64-out out.json`
- [ ] **Step 8: 임진년만 먼저 적재** `bash scripts/ingest_all.sh '0080_010_00[1-7]'` → 결과 count 합계가 130이어야 한다(30+29+29+22+5+10+5). `processed/` JSON 3개를 열어 번역과 태그를 눈으로 확인한다.
- [ ] **Step 9: 나머지 전부 적재** → 이후 `build_today_map` 호출. RDS 행 수 1,593, DynamoDB 항목 366이어야 한다.
- [ ] **Step 10: Commit** `feat: 적재 Lambda와 인프라 템플릿`

---

### Task 7: 질문 속 날짜 해석

**Files:**
- Create: `src/nanjung/date_resolver.py`
- Test: `tests/test_date_resolver.py`

**Interfaces:**
- Consumes: `entry_id()`(Task 3), `db.neighbor`(Task 5)를 `neighbor_fn: Callable[[str, int], str | None]`로 주입받는다.
- Produces: `resolve(message: str, last_source_ids: list[str], neighbor_fn) -> list[str] | None`: 일기 id 목록을 돌려주고, 날짜 조건이 없으면 None

규칙(위에서부터 먼저 맞는 것을 쓴다):
1. 상대 표현 `다음\s*날|다음날|이튿날` → `neighbor_fn(last_source_ids[0], +1)`. `전날|그\s*전날|前날` → `neighbor_fn(last, -1)`. 단, 2번의 사건 키워드와 함께 오면 사건 날짜 ±1을 쓴다("명량 전날" → `1597-09-15`). 이웃이 없거나 `last_source_ids`가 비면 None.
2. 사건 사전(전서본 본문으로 확인함):
   - `명량` → `1597-09-16`
   - `임진왜란`·`왜란 터진` → `1592-04-13`
   - `어머니`+(`돌아가`|`별세`|`부고`) → `1597-04-13`
   - `면`+(`전사`|`죽`) → `1597-10-14`
   - `백의종군`·`출옥`·`감옥` → `1597-04-01`
   - `노량`·`마지막` → `1598-11-17`(일기의 마지막 날)
3. 명시 날짜 `(임진|계사|갑오|을미|병신|정유|무술)년\s*(윤)?(\d{1,2})월\s*(\d{1,2})일`, 또는 `(159[2-8])년\s*(윤)?(\d{1,2})월\s*(\d{1,2})일`(음력으로 해석) → `[entry_id(...)]`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
nb = {("1592-06-10", 1): "1592-08-24", ("1598-11-17", 1): None, ("1597-09-16", -1): "1597-09-15"}.get
def r(msg, last=()): return resolve(msg, list(last), lambda i, d: nb((i, d)))
def test_event(): assert r("명량 때 어땠어요?") == ["1597-09-16"]
def test_event_minus_one(): assert r("명량 전날 뭐 하셨어요?") == ["1597-09-15"]
def test_next_day_skips_gap(): assert r("그다음 날은요?", ["1592-06-10"]) == ["1592-08-24"]
def test_next_day_at_end_returns_none(): assert r("그다음 날은요?", ["1598-11-17"]) is None
def test_next_day_without_history(): assert r("다음날은?") is None
def test_explicit_dates():
    assert r("정유년 9월 16일 일기") == ["1597-09-16"]
    assert r("1596년 윤8월 1일") == ["1596-L08-01"]
def test_plain_question(): assert r("배 멀미 하셨어요?") is None
```

- [ ] **Step 2: FAIL** → **Step 3: 구현** → **Step 4: PASS**
- [ ] **Step 5: Commit** `feat: 질문 속 날짜·사건 해석`

---

### Task 8: 답변 모드, 프롬프트, 출처 카드

**Files:**
- Create: `src/nanjung/answer.py`
- Test: `tests/test_answer.py`

**Interfaces:**
- Consumes: `Hit`, `SOURCE_NOTE`, `bedrock.converse`
- Produces:
  - `MODERN_MARKERS = ("요즘","현대","오늘날","21세기","대통령","정당","선거","국회","총리")`: 단독으로도 modern
  - `CONTEXT_MARKERS = ("정치","외교")`: `NOW_MARKERS = ("요즘","현대","오늘날","지금")` 중 하나와 함께일 때만 modern(사용자 결정. "조선 조정의 정치"는 modern 아님)
  - `decide_mode(message: str, hits: list[Hit], threshold: float, date_matched: bool) -> Literal["normal","serious","out_of_scope","modern"]`
  - `answer(message: str, hits: list[Hit], history: list[dict], mode: str, client=None) -> dict`: 키는 `answer`, `mode`, `sources`, `suggestions`
  - `source_card(h: Hit) -> dict`: 키는 `id`, `label`, `original_line`(원문 첫 문장, 。 기준, 최대 60자), `translation_line`(번역 첫 문장), `note`(SOURCE_NOTE)

모드 결정(이 순서):
1. 메시지에 MODERN_MARKERS가 있거나, CONTEXT_MARKERS와 NOW_MARKERS가 함께 있으면 `modern`
2. `date_matched`가 False이고 최고 유사도 < threshold이면 `out_of_scope`
3. 상위 3개 근거 중 `emotion == "비통"`이 있으면 `serious`
4. 나머지는 `normal`

응답 결정:
- `out_of_scope`·`modern`은 **LLM을 호출하지 않는다.** 답변은 각각 `처음 듣는 말이라 내 답할 길이 없소.`, `후대의 일은 모르오.` 고정이다. 이어서 `"대신 내 일기 이야기를 들려주리다."`를 붙인다. `sources`는 빈 목록, `suggestions`는 최상위 hit의 `questions`다.
- `normal`·`serious`는 상위 3개 근거의 원문·번역과 history(최근 메시지 6개 = 질문·답변 3쌍. frontend 플랜과 같은 기준)를 넣어 converse를 호출한다(`max_tokens=400`, `temperature=0.6`). 카드는 최대 3개다.
- 시스템 프롬프트 필수 지시:
  - 주어진 일기 내용에만 근거할 것
  - 없는 사실은 지어내지 말 것
  - 1인칭 하오체로 말할 것
  - 3문장 이내로 답할 것
  - 후대의 일은 모른다고 할 것
  - `serious`일 때만 추가: 진지하고 담담한 말투, 이모지·감탄 연출 금지. `normal`일 때만 추가: 가볍고 친근하게, 이모지 하나까지 허용

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def hit(sim, emo="일상"): ...
def test_modern_politics_overrides_high_similarity():
    assert decide_mode("요즘 일본이랑 사이 어때요?", [hit(0.9)], 0.3, False) == "modern"
def test_low_similarity_out_of_scope(): assert decide_mode("인공지능이 뭐예요?", [hit(0.1)], 0.3, False) == "out_of_scope"
def test_date_match_bypasses_threshold(): assert decide_mode("정유년 9월 16일", [hit(0.1)], 0.3, True) == "normal"
def test_grief_is_serious(): assert decide_mode("아들 소식", [hit(0.5,"일상"), hit(0.4,"비통")], 0.3, False) == "serious"
def test_out_of_scope_does_not_call_llm(fake_client):
    r = answer("인공지능이 뭐예요?", [hit(0.1)], [], "out_of_scope", client=fake_client)
    assert fake_client.calls == 0 and r["answer"].startswith("처음 듣는 말이라 내 답할 길이 없소.") and r["sources"] == []
def test_serious_prompt_bans_emoji(fake_client): # system 프롬프트에 "이모지" 금지 지시가 들어 있다
def test_source_card_lines(): # original "十三日壬寅。晴。出東軒..." → original_line == "十三日壬寅。", note == SOURCE_NOTE
def test_history_truncated_to_6_turns(fake_client): ...
```

- [ ] **Step 2: FAIL** → **Step 3: 구현** → **Step 4: PASS**
- [ ] **Step 5: Commit** `feat: 답변 모드 결정과 프롬프트`

---

### Task 9: 브라우저별 하루 사용량 제한

**Files:**
- Create: `src/nanjung/quota.py`
- Test: `tests/test_quota.py` (moto)

**Interfaces:**
- Produces: `allow(table, client_id: str, now_kst: datetime, limit: int) -> bool`
  - 키: `pk = f"{client_id}#{now_kst:%Y-%m-%d}"`
  - `UpdateItem ADD cnt :1`, `ConditionExpression: attribute_not_exists(cnt) OR cnt < :limit`
  - `expires_at`(TTL)는 다음 날 KST 자정 + 1일의 epoch
  - 조건 실패면 False

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_20th_allowed_21st_denied(table):
    t = datetime(2026,12,1,23,0,tzinfo=KST)
    assert all(allow(table,"c1",t,20) for _ in range(20)) and allow(table,"c1",t,20) is False
def test_resets_after_kst_midnight(table): # 23:59 한도 소진 → 다음날 00:00 True
def test_clients_are_independent(table): ...
```

- [ ] **Step 2: FAIL** → **Step 3: 구현** → **Step 4: PASS**
- [ ] **Step 5: Commit** `feat: 하루 질문 횟수 제한`

---

### Task 10: API 핸들러 + 배포

**Files:**
- Create: `src/nanjung/handlers/api.py`(진입점), `src/nanjung/handlers/chat.py`, `src/nanjung/handlers/diary.py`
- Modify: `template.yaml` (`ApiFunction` 하나에 HttpApi 이벤트 `POST /chat`·`GET /diary`, `HttpApi`, `UsageTable`(PK `pk`, TTL `expires_at`))
- Test: `tests/test_handlers.py`, `tests/test_api.py`

> 변경(사용자 결정, `docs/architecture.png` 기준): 플랜 초안의 `ChatFunction`·`DiaryFunction` 두 개 대신 API Lambda 하나(`ApiFunction`)가 두 경로를 처리한다. `api.lambda_handler`가 `event["routeKey"]`(`"POST /chat"`, `"GET /diary"`)로 분기하고, 알 수 없는 경로는 404다. 환경변수와 IAM 권한은 두 함수의 것을 합친다. HTTP 계약은 그대로다.

**Interfaces:**
- Consumes: Task 5·7·8·9
- Produces(HTTP 계약, Task 11이 사용):
  - `POST /chat`
    - 헤더 `X-Client-Id`(UUID)
    - body `{"message": str(1~300자), "history": [{"role":"user"|"assistant","content":str}], "last_source_ids": [str]}`
    - 200 `{"answer","mode","sources":[card],"suggestions":[str]}`
    - 400: 메시지 비었거나 300자 초과, 헤더 없음
    - 429: `{"answer":"오늘은 그만 쉬어야겠소. 내일 다시 오시오."}`
    - 503: `{"answer":"잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오."}` (BedrockUnavailable)
  - `GET /diary?md=MM-DD` (md 생략 시 KST 오늘)
    - 200 `{"entry":{"id","label","original","translation","emotion","intro"},"questions":[str],"exact":bool,"source_note":SOURCE_NOTE}`
- 처리 순서(chat):
  1. 검증
  2. quota
  3. `resolve()`
  4. `embed(message)`
  5. `search(k=5, date_ids)`: 날짜 결과가 비면 date_ids 없이 다시 검색
  6. `decide_mode` → `answer`
- 환경변수: `SIM_THRESHOLD`(초기값 `0.30`), `DAILY_LIMIT=20`, `TODAY_TABLE`, `USAGE_TABLE`, DB 관련
- HttpApi CORS: `AllowOrigins: ["http://localhost:5500"]`, `AllowHeaders: ["content-type","x-client-id"]`

- [ ] **Step 1: 실패하는 테스트 작성** (의존성은 모두 가짜)

```python
def test_post_chat_goes_to_chat(): ...       # api.lambda_handler 라우팅
def test_get_diary_goes_to_diary(): ...
def test_unknown_route_is_404(): ...
def test_chat_400_on_empty_and_long(): ...
def test_chat_429_when_quota_denied(): assert body["answer"].startswith("오늘은 그만 쉬어야겠소")
def test_chat_503_on_bedrock_unavailable(): # embed가 BedrockUnavailable → 503, 고정 문구
def test_chat_retries_search_without_date_when_empty(): ...
def test_diary_defaults_to_kst_today(): # now=2026-12-01T00:30+09:00 → md "12-01"
```

- [ ] **Step 2: FAIL** → **Step 3: 구현** → **Step 4: PASS**
- [ ] **Step 5: `sam build && sam deploy`**
- [ ] **Step 6: 실제 호출로 확인**
  - `curl -X POST $API/chat -H 'x-client-id: 00000000-0000-4000-8000-000000000000' -d '{"message":"임진왜란 터진 날 뭐 하고 계셨어요?","history":[],"last_source_ids":[]}'` → `sources[0].id == "1592-04-13"`
  - `curl "$API/diary?md=10-26"` → `entry.id == "1597-09-16"`
- [ ] **Step 7: Commit** `feat: 대화·일기 API`

---

### Task 11: 프론트엔드 — **frontend 플랜으로 대체** (`docs/plans/2026-11-24-nanjung-talk-frontend.md`)

> 이 Task는 사용자가 승인한 frontend 플랜으로 대체되었다. 아래 내용은 기록용이며 실행하지 않는다.

**Files:**
- Create: `web/index.html`, `web/app.js`, `web/style.css`, `web/config.js`(`window.API_BASE = ""`; 로컬에서는 API Gateway URL)

**Interfaces:**
- Consumes: Task 10의 HTTP 계약

화면 결정:
- 첫 화면 '오늘의 일기' 카드
  - 제목 `N년 전 오늘, 장군의 일기`(N = 올해 − 일기 양력 연도), `exact=false`면 "가장 가까운 날의 일기"
  - intro, 원문, 'AI 번역' 배지를 단 번역문
  - 추천 질문 버튼 3개
- 대화 영역
  - 답변 아래 출처 카드(최대 3개, 가로 배치). `out_of_scope`·`modern`이면 카드 대신 suggestions 버튼
  - 요청 중에는 전송 버튼을 비활성화한다
- 상태: `history`는 메모리 배열(최근 메시지 6개), `lastSourceIds`는 직전 응답의 `sources[].id`
- `X-Client-Id`는 `localStorage`에 UUID로 저장한다. 실패하면 메모리 UUID를 쓴다(`try/catch`).
- 모든 텍스트는 `textContent`로만 넣는다.

- [ ] **Step 1: 구현**
- [ ] **Step 2: `grep -n "innerHTML" web/*.js` → 결과 없음**
- [ ] **Step 3: 로컬 확인** (`python -m http.server 5500 -d web`, config.js에 API URL)
  - 오늘의 일기가 뜨는지
  - 추천 질문을 누르면 출처 카드가 붙은 답이 오는지
  - "그다음 날은요?"에 다음 날짜 카드가 오는지
  - "인공지능이 뭐예요?"에 카드 없이 버튼이 뜨는지
  - 시크릿 창에서도 동작하는지
- [ ] **Step 4: 모바일 폭(375px)에서 출처 카드가 세로로 쌓이는지 확인**
- [ ] **Step 5: Commit** `feat: 웹 프론트엔드`

---

### Task 12: 정적 호스팅 + CloudFront

**Files:**
- Modify: `infra/README.md`

- [ ] **Step 1: 웹 버킷 생성** `nanjung-web-<id>` (퍼블릭 차단, 정적 호스팅 끔) → `aws s3 sync web s3://nanjung-web-<id>/`. 업로드 전에 `config.js`의 `API_BASE`를 `""`로 되돌린다.
- [ ] **Step 2: CloudFront 배포 생성**
  - 기본 오리진: 웹 버킷(OAC)
  - 두 번째 오리진: HttpApi 도메인
  - 동작 `/chat`, `/diary*`: 오리진은 API, 허용 메서드 GET·HEAD·OPTIONS·PUT·POST·PATCH·DELETE, 캐시 정책 `CachingDisabled`, 오리진 요청 정책 `AllViewerExceptHostHeader`
  - 기본 루트 객체 `index.html`
- [ ] **Step 3: 확인** `https://<배포>.cloudfront.net`에서 Task 11 Step 3의 다섯 가지를 다시 확인하고, 개발자도구 네트워크 탭에서 `/chat`이 같은 출처로 나가는지 본다.
- [ ] **Step 4: Commit** `docs: CloudFront 배포 절차`

---

### Task 13: 유사도 기준값 튜닝 + 최종 점검

**Files:**
- Create: `eval/questions.json`, `eval/run_eval.py`

**Interfaces:**
- `eval/questions.json`: `[{"q": str, "expect": "in"|"out"}]` 40개. 일기 안 질문 25개(예: "배 멀미 하셨어요?", "어머니 보고 싶으셨어요?", "거북선 시험해 봤어요?"), 일기 밖 질문 15개(예: "인공지능이 뭐예요?", "피자 좋아하세요?", "축구 아세요?")
- `run_eval.py`: 질문마다 `embed` → `search(k=1)`을 돌려 `(q, expect, top_sim)`을 출력한다. 그리고 0.20~0.50을 0.02 간격으로 바꿔 가며 정확도를 출력한다.

- [ ] **Step 1: 질문셋 작성, 평가 실행.** RDS가 프라이빗이라 CloudShell에서는 접속할 수 없다. 적재 Lambda에 `{"action": "eval"}`을 추가해 패키지에 넣은 `eval/questions.json`으로 `run_eval`을 실행하고, 결과를 응답으로 받는다.
- [ ] **Step 2: 정확도가 가장 높은 값을 `SIM_THRESHOLD`로 정해 재배포.** 동률이면 낮은 값을 고른다(일기 안 질문을 놓치는 쪽이 더 나쁘다).
- [ ] **Step 3: 말투 수동 점검 10건.** 비통 근거 3건에 이모지가 없는지, 하오체를 유지하는지, 근거 밖 사실을 지어내지 않는지 본다. 어긋나면 Task 8의 시스템 프롬프트를 고치고 다시 점검한다.
- [ ] **Step 4: 운영 확인**
  - CloudWatch Logs에 오류가 없는지
  - Budgets 알림이 켜져 있는지
  - RDS 자동 백업이 켜져 있는지
  - 21번째 질문에 429 문구가 뜨는지
- [ ] **Step 5: Commit** `chore: 유사도 기준값 확정과 평가셋`
