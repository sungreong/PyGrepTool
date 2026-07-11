---
title: "Agentic Code Search vs Vector Search"
theme: "midnight"
intent: "pitch"
pageWidth: 1120px
pageHeight: 720px
toc: false
---

# 에이전트 코드 검색 방식 소개 {#cover .cover eyebrow="Technical Deck"}

`pygreptool` 기반 agent-tool 검색과 벡터 검색의 역할 비교

2026-07-08

---
{: .page-break}

## 발표 흐름 {#agenda .agenda}

1. 사용자가 실제로 요구하는 코드 검색 경험
2. `pygreptool`이 에이전트와 통신하는 방식
3. 실제 agent 평가에서 드러난 문제와 개선
4. 벡터 검색과의 장단점 비교
5. 추천 아키텍처와 운영 원칙

---
{: .page-break}

## 핵심 메시지 {#message .message}

정확한 코드 위치 탐색은 벡터 검색보다 agent-tool 검색이 먼저다.
{: .lead}

- `pygreptool`은 `rg`, `grep`, Python fallback 결과를 하나의 tool JSON으로 표준화한다.
- 에이전트는 모델 기억이 아니라 현재 파일시스템 검색 결과로 답한다.
- 벡터 검색은 의미 탐색에 강하고, 줄 번호가 필요한 확인 작업에는 약하다.

---
{: .page-break}

## 사용자의 질문은 자연어다 {#user-questions .icon-list}

- 🔎 | 위치 질문 | `BackendName`은 어디에 정의돼 있나?
- 🧪 | 테스트 질문 | `backend="smart"`를 검증하는 테스트가 있나?
- 📄 | 문서 질문 | `pathspec`은 왜 optional dependency인가?
- 🧭 | 영향 질문 | 특정 패턴이 어떤 파일에 퍼져 있나?

에이전트의 과제는 이 자연어 질문을 현재 코드와 문서의 검증 가능한 근거로 바꾸는 것이다.

---
{: .page-break}

## 프로젝트의 초점 {#focus .message}

`pygreptool`은 검색 엔진을 다시 만드는 프로젝트가 아니다.
{: .lead}

목표는 검색 결과를 Python 객체와 LLM tool 결과 JSON으로 안정적으로 표준화하는 것이다.

- 검색 backend: `rg`, `grep`, `python`
- 선택 정책: `auto`, `smart`, backend 강제 지정
- 결과 표면: `path`, `line_number`, `column`, `line`, `match`, `backend`

---
{: .page-break}

## 에이전트와 tool의 통신 {#flow .card}

| 단계 | 역할 |
| --- | --- |
| 1. 사용자 질문 | 자연어로 코드 위치, 테스트, 문서를 묻는다. |
| 2. Agent prompt | 검색 전제와 재검색 원칙을 적용한다. |
| 3. `search_code` 호출 | LLM이 tool arguments를 만든다. |
| 4. backend 선택 | `smart`, `auto`, `rg`, `grep`, `python` 중 선택한다. |
| 5. JSON 반환 | 결과를 파일 경로와 줄 번호로 정규화한다. |
{: .zebra .bordered .compact .table-fit caption="LLM 답변 전에 tool 호출로 근거를 확보하는 흐름"}

핵심은 LLM이 코드를 기억하는 것이 아니라, 필요할 때 명시적으로 `search_code`를 호출한다는 점이다.

---
{: .page-break}

## tool 계약이 중요한 이유 {#contract .card}

| 구분 | 필드 | 역할 |
| --- | --- | --- |
| 입력 | `pattern`, `roots`, `regex` | 무엇을 어디에서 찾을지 지정 |
| 입력 | `backend`, `fallback` | 검색 엔진과 실패 시 동작 결정 |
| 출력 | `results` | 경로, 줄 번호, 매칭 라인 반환 |
| 출력 | `truncated`, `error`, `hints` | 긴 결과, 실패, 재검색 방향 설명 |
{: .zebra .bordered .compact .table-fit caption="Agent가 의존하는 search_code 입출력 계약"}

이 계약이 흔들리면 에이전트 답변도 “확인 가능한 근거”를 잃는다.

---
{: .page-break}

## 실제 평가 구성 {#evaluation-setup .card}

| 지표 | 값 | 의미 |
| --- | --- | --- |
| 일반 테스트 | `40 passed, 4 skipped` | 네트워크 없는 fixture 검색 검증 |
| Live agent 테스트 | `3 passed` | 실제 ChatOpenAI agent의 tool 호출 검증 |
| 기본 backend | `smart` | 작은 범위는 Python, 큰 범위는 외부 검색 우선 |
| Allowed roots | 프로젝트 루트 | 에이전트 검색 범위 제한 |
{: .zebra .bordered .compact .table-fit caption="일반 fixture 테스트와 live agent 테스트를 분리해 검증"}

---
{: .page-break}

## 평가 결과 {#evaluation-results .timeline}

### 1. 타입 정의 찾기

`src/pygreptool/core.py` line 8에서 `BackendName`과 가능한 값 `auto`, `smart`, `rg`, `grep`, `python`을 찾았다.

### 2. quote style 문제 발견

`backend='smart'` exact search는 실제 코드의 `backend="smart"`와 달라 최초 실패했다.

### 3. 재검색 전략으로 회복

regex variant와 tool `hints`를 통해 fixture와 실제 repo 테스트 위치를 찾았다.

### 4. 문서 검색도 성공

`pathspec`이 검색 엔진이 아니라 ignore/path filtering용 optional extra임을 요약했다.

---
{: .page-break}

## 개선 전후 {#before-after .compare}

### 개선 전

- 사용자의 quote style을 그대로 exact search
- 첫 검색 0건이면 “없다”고 결론
- 재검색 방향이 agent prompt에 약하게만 존재

### 개선 후

- `["']?backend["']?\s*[:=]\s*["']smart["']` 같은 variant 검색 안내
- 검색 결과 0건이면 tool JSON에 `hints` 제공
- 상대 root를 allowed root 내부 경로로 해석

---
{: .page-break}

## `pygreptool` 방식의 강점 {#pygreptool-strengths .icon-list}

- 📍 | 정확한 위치 | 파일 경로, 줄 번호, column, match를 반환한다.
- ⚡ | 현재성 | 인덱스 재생성 없이 현재 파일시스템을 검색한다.
- 🧩 | 낮은 의존성 | `rg`가 없어도 Python backend로 fallback한다.
- 🔐 | 제한된 범위 | `allowed_roots`로 에이전트가 읽을 수 있는 범위를 좁힌다.

---
{: .page-break}

## `pygreptool` 방식의 한계 {#pygreptool-limits .icon-list}

- ✍️ | 표현 차이 | 따옴표, 공백, 인자 순서가 다르면 exact search가 실패할 수 있다.
- 🧠 | 의미 탐색 | “비슷한 책임의 코드” 같은 개념 검색에는 약하다.
- 📚 | 긴 결과 | 흔한 토큰을 넓게 찾으면 LLM context를 많이 쓴다.
- 🧱 | 구조 분석 | 함수, 클래스, 호출 관계는 AST 또는 code graph 계층이 더 적합하다.

---
{: .page-break}

## 벡터 검색의 적합 영역 {#vector-fit .compare}

### 잘 맞는 질문

- 이 기능과 관련된 문서를 찾아줘
- 비슷한 요구사항이 과거에 있었나?
- 이 개념을 설명하는 문서는 어디 있나?

### 덜 맞는 질문

- 정확히 이 문자열이 어디 있나?
- 이 설정값이 몇 번째 줄에 있나?
- 방금 수정한 로컬 파일이 반영됐나?

---
{: .page-break}

## 두 방식의 직접 비교 {#comparison .card}

| 기준 | `pygreptool` tool 검색 | 벡터 검색 |
| --- | --- | --- |
| 검색 단위 | 문자열, regex, 파일 line | 의미적으로 가까운 chunk |
| 강점 | 정확한 위치와 재현성 | 유사 개념 탐색 |
| 약점 | 표현 차이에 취약 | 정확한 line 근거가 약함 |
| 최신성 | 현재 파일 직접 검색 | index 갱신 필요 |
| 인프라 | `rg`/`grep`/Python fallback | embedding model, vector DB |
| 좋은 사용처 | 코드 위치, 테스트, 설정값 확인 | 요구사항, 문서, 초기 탐색 |
{: .zebra .bordered .compact .table-fit caption="질문 성격에 따라 우선 도구가 달라진다"}

---
{: .page-break}

## 추천 아키텍처 {#architecture .card}

| 질문 유형 | 우선 도구 | 이유 |
| --- | --- | --- |
| 정확한 코드, 테스트, 설정 질문 | `search_code` | 파일 경로와 줄 번호가 필요하다. |
| 요구사항, 문서, 유사 사례 질문 | vector search | 표현이 달라도 의미적으로 가까운 자료를 찾는다. |
| 구조, 호출 관계 질문 | AST 또는 code graph tool | 텍스트 매칭보다 구조 정보가 중요하다. |
{: .zebra .bordered .compact .table-fit caption="Router가 질문 성격에 따라 도구를 선택한다"}

하나의 검색 방식으로 모든 질문을 처리하기보다, 질문의 성격에 따라 도구를 나누는 편이 안전하다.

---
{: .page-break}

## 운영 원칙 {#operating-principles .agenda}

1. 코드 위치 질문에는 답하기 전에 `search_code`를 호출한다.
2. `roots`는 `src`, `tests`, `docs`처럼 좁게 잡는다.
3. backend는 기본 `smart`를 쓴다.
4. 정확 검색 실패 시 짧은 토큰이나 regex variant로 재검색한다.
5. 결과가 없다고 말할 때는 사용한 `pattern`과 `roots`를 함께 말한다.
6. 답변에는 file path와 line number를 포함한다.

---
{: .page-break}

## 결론 {#closing .dark}

정답은 대체가 아니라 조합이다.
{: .lead}

- 정확한 위치 탐색: `search_code`
- 넓은 의미 탐색: vector search
- 구조 단위 분석: AST 또는 code graph tool

`pygreptool`은 에이전트가 현재 코드베이스에서 검증 가능한 근거를 찾게 해주는 얇고 안정적인 검색 계약이다.

---
{: .page-break}

## 근거 문서 {#sources .card}

| 문서 | 사용한 근거 |
| --- | --- |
| `README.md` | 프로젝트 목적, tool JSON 계약, backend 정책, `allowed_roots` |
| `docs/agent-tool-evaluation.md` | agent 구성, 테스트 결과, `hints` 개선, prompt 원칙 |
| `docs/python-search-dependency-recommendations.md` | dependency 선택 기준, `smart` backend, `pathspec` optional extra |
| `docs/open-source-references.md` | adapter 방식, `rg`/`grep`/Python backend, 구조 검색 분리 필요성 |
{: .zebra .bordered .compact .table-fit caption="덱 작성에 사용한 프로젝트 내부 문서"}
