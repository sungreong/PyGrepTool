---
title: "LLM 에이전트에 코드 검색 툴을 붙인다는 것"
theme: "midnight"
intent: "narrative"
pageWidth: 1120px
pageHeight: 720px
toc: false
---

# LLM 에이전트에 코드 검색 툴을 붙인다는 것 {#cover .cover eyebrow="Blog Deck"}

정확한 코드 위치 검색을 `core.py`, `tool.py`, `langchain_tool.py`, `langchain_agent.py` 관점에서 해설하는 deck-style 블로그

---
{: .page-break}

## 이 글의 질문 {#agenda .agenda}

1. 왜 벡터 검색만으로는 코드 위치 질문이 부족한가
2. 그냥 `search()`를 호출하는 방식과 tool 검색은 무엇이 다른가
3. 내부 모듈은 어떤 계약으로 연결되어 있는가
4. LangChain agent와 OpenAI tool calling은 이 구조에 어떻게 올라타는가
5. 실제 실패 사례와 개선 포인트는 무엇이었는가

---
{: .page-break}

## 핵심 메시지 {#message .message}

코드 검색 agent의 본질은 검색 엔진이 아니라 관찰 계약이다.
{: .lead}

- 검색 결과가 항상 같은 shape으로 나와야 한다.
- 실패도 예외가 아니라 모델이 해석할 수 있는 결과여야 한다.
- 검색 범위, 결과 길이, 재검색 힌트까지 tool 계층에서 보장해야 한다.

---
{: .page-break}

## 벡터 검색만으로 부족한 질문 {#problem .icon-list}

- 📍 | 위치 | `BackendName`은 어디에 정의되어 있나?
- 🧪 | 테스트 | `backend="smart"`를 검증하는 테스트는 어디 있나?
- 📄 | 문서 | `pathspec`은 왜 optional dependency인가?
- 🔄 | 최신성 | 방금 바뀐 로컬 파일을 지금 바로 반영할 수 있나?

이 질문들은 의미적으로 비슷한 문서를 찾는 것보다 현재 저장소의 정확한 line-level 근거가 더 중요하다.

---
{: .page-break}

## 외부 기준으로 보면 {#external-baseline .card}

LangChain은 agent를 “모델이 tools를 loop 안에서 호출하는 구조”로 설명한다. OpenAI function calling은 “JSON schema로 정의된 tool”을 통해 모델이 외부 시스템과 연결된다고 설명한다.

| 관점 | 공식 설명 | 이 프로젝트에서 대응되는 위치 |
| --- | --- | --- |
| Agent loop | model calls tools in a loop | `langchain_agent.py` |
| Tool schema | function tools defined by JSON schema | `tool.py` |
| Tool invocation | model chooses when to call tools | `langchain_tool.py` |
{: .zebra .bordered .compact .table-fit caption="공식 문서 개념이 코드베이스의 어떤 모듈로 내려오는지 보는 것이 중요하다."}

참고:

- [LangChain Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [LangChain Tools](https://docs.langchain.com/oss/python/langchain/tools)
- [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling)

---
{: .page-break}

## 먼저, 그냥 검색하면 {#plain-search .compare}

### 사람이 직접 `search()` 호출

```python
from pygreptool import search

results = search(
    "BackendName",
    "src",
    regex=False,
    backend="smart",
)
```

사람이 pattern, roots, backend를 직접 정한다.

### agent가 필요한 것은 아님

- 입력 검증이 약하다
- 실패를 JSON으로 돌려주지 않는다
- 검색 범위 제한이 호출자 책임이다
- 결과가 0건일 때 재검색 힌트가 없다

---
{: .page-break}

## tool 검색은 무엇이 다른가 {#tool-search .compare}

### `run_search_tool()` 호출

```python
from pygreptool.tool import run_search_tool

result = run_search_tool(
    {
        "pattern": "TODO",
        "roots": ["examples"],
        "regex": False,
        "backend": "auto",
    },
    allowed_roots=["."],
)
```

### 이 계층이 추가하는 것

- JSON-like arguments
- `allowed_roots` 검증
- `max_results`, `max_line_chars`, `truncated`
- 실패의 구조화
- agent runtime이 바로 다시 읽을 수 있는 payload

---
{: .page-break}

## 내부 모듈 지도 {#module-map .card}

```text
core.py
  -> backends/rg.py
  -> backends/grep.py
  -> backends/python.py
  -> tool.py
  -> langchain_tool.py
  -> langchain_agent.py
```

| 모듈 | 역할 |
| --- | --- |
| `core.py` | `search()`와 `SearchResult` 정의 |
| `backends/*` | 실제 line-oriented 검색 수행 |
| `tool.py` | OpenAI tool schema와 JSON handler |
| `langchain_tool.py` | LangChain `StructuredTool` wrapper |
| `langchain_agent.py` | prompt와 tool을 묶는 harness |
{: .zebra .bordered .compact .table-fit caption="프로젝트 이름보다 이 연결 구조가 더 중요하다."}

---
{: .page-break}

## `core.py`가 만드는 공통 계약 {#core-contract .card}

| 계약 | 값 |
| --- | --- |
| `BackendName` | `auto`, `smart`, `rg`, `grep`, `python` |
| `SearchResult.path` | 매칭 파일 경로 |
| `SearchResult.line_number` | 1-based line number |
| `SearchResult.column` | 1-based column |
| `SearchResult.line` | 원본 line text |
| `SearchResult.match` | 매칭된 텍스트 |
| `SearchResult.backend` | 결과를 만든 backend 이름 |
{: .zebra .bordered .compact .table-fit caption="상위 계층은 backend 구현보다 SearchResult shape를 신뢰한다"}

이 데이터 구조 덕분에 상위 계층은 backend 차이를 몰라도 된다. `rg`, `grep`, `python` 중 무엇이 실제로 검색했는지는 `backend` 필드로만 확인하면 된다.

---
{: .page-break}

## backend 선택은 여기서 끝난다 {#backend-policy .card}

```text
backend="rg"
  -> rg backend 강제

backend="grep"
  -> grep backend 강제

backend="python"
  -> Python backend 강제

backend="smart"
  -> 작은 root면 python
  -> 크면 auto 경로

backend="auto"
  -> rg -> grep -> python fallback
```

`smart`가 중요한 이유는 외부 프로세스가 항상 빠른 것이 아니기 때문이다. 작은 범위에서는 `rg`를 띄우는 비용보다 Python 검색이 더 싸다.

참고:

- [ripgrep 프로젝트 소개](https://github.com/burntsushi/ripgrep)

---
{: .page-break}

## Python backend는 최후의 보루다 {#python-backend .card}

```text
roots
  -> iter_candidate_files()
  -> skip dirs(.git, node_modules, .venv ...)
  -> include glob
  -> binary 파일 제외
  -> re.finditer()
  -> SearchResult 반환
```

```python
for match in compiled.finditer(line):
    results.append(
        SearchResult(
            path=path,
            line_number=line_number,
            column=match.start() + 1,
            line=line,
            match=match.group(0),
            backend="python",
        )
    )
```

이 fallback이 있어야 외부 명령어가 없는 환경에서도 기능이 유지된다. `pathspec`이 설치돼 있으면 `.gitignore`와 `.ignore` 기반 경로 필터도 더 정확해진다.

---
{: .page-break}

## `rg`와 `grep`은 빠른 길이다 {#external-backends .compare}

### `rg` backend

```text
rg --json ...
  -> match event만 파싱
  -> byte offset -> character column
```

`ripgrep`은 기본적으로 `gitignore`, 숨김 파일, 바이너리 파일을 존중하는 line-oriented search tool이다.

### `grep` backend

```text
grep -R -n -H -I -Z ...
  -> path + line_number + line
  -> Python regex로 column 계산
```

`grep`은 line candidate를 빠르게 찾고, column 계산은 Python이 보완한다.

---
{: .page-break}

## benchmark는 이렇게 잡았다 {#benchmark-setup .card}

이번 비교는 “tool serialization이나 agent loop가 아니라 raw `search()` 속도만” 측정했다.

| 항목 | 값 |
| --- | --- |
| 반복 횟수 | backend별 9회 |
| 기준값 | median ms |
| 대상 backend | `python`, `rg`, `smart`, `auto`, `grep` |
| 환경 | Windows, `rg` 설치됨, `grep` 미설치 |
| 비교 기준 | 검색 시간, 후보 파일 수, 매칭 파일 수, 총 match 수 |
{: .zebra .bordered .compact .table-fit caption="검색 엔진 자체의 속도만 보려고 tool/agent 오버헤드는 제외했다"}

대표 케이스는 4개로 잡았다.

- 단일 파일 exact symbol
- 문서 디렉터리 literal search
- `src` 디렉터리 regex function search
- `src + tests + docs + examples` 전체 literal keyword search

---
{: .page-break}

## 작은 범위 benchmark 결과 {#benchmark-small .card}

| 케이스 | 후보 파일 수 | winner | median ms | 2위 |
| --- | ---: | --- | ---: | --- |
| `single_file_symbol` | 1 | `python` | 1.092 | `smart` 1.104 |
| `docs_optional_dependency` | 5 | `smart` | 6.280 | `python` 9.839 |
{: .zebra .bordered .compact .table-fit caption="작은 범위에서는 외부 프로세스보다 in-process Python 검색이 유리했다"}

같은 케이스에서 `rg`는 각각 `41.609ms`, `53.914ms`였다. 이 저장소 크기에서는 검색 엔진 자체보다 프로세스 실행 비용이 더 크게 작용했다.

---
{: .page-break}

## 저장소 범위 benchmark 결과 {#benchmark-large .card}

| 케이스 | 후보 파일 수 | winner | median ms | 2위 |
| --- | ---: | --- | ---: | --- |
| `src_regex_functions` | 12 | `python` | 10.192 | `smart` 12.329 |
| `repo_backend_keyword` | 34 | `python` | 32.542 | `smart` 35.844 |
{: .zebra .bordered .compact .table-fit caption="이 저장소에서는 34개 후보 파일 수준까지도 Python이 가장 빨랐다"}

`rg`는 같은 두 케이스에서 `50.252ms`, `65.096ms`였고, `auto`는 `rg`를 먼저 타기 때문에 각각 `49.942ms`, `60.377ms`로 비슷한 수준이었다.

---
{: .page-break}

## benchmark를 해석하면 {#benchmark-takeaway .message}

이 저장소와 이 환경에서는 `python`이 가장 빠르고 `smart`가 가장 안전한 기본값이었다.
{: .lead}

- `smart`는 작은 범위에서 Python backend를 선택하므로 거의 최선에 가깝다.
- `auto`는 `rg`를 먼저 타기 때문에 현재 repo 크기에서는 손해를 본다.
- `rg`가 느리다는 뜻은 아니다.
  이 repo가 작고 후보 파일 수가 적어서 프로세스 실행 비용이 크게 보인 것이다.

---
{: .page-break}

## `tool.py`는 agent용 계약을 만든다 {#tool-contract .card}

| 역할 | 구현 포인트 |
| --- | --- |
| 입력 schema | OpenAI Responses / Chat tool schema 생성 |
| 입력 정규화 | `root` alias, null default, 타입 검증 |
| 보안 경계 | `allowed_roots` 검증 |
| 결과 절단 | `max_results`, `max_line_chars`, `truncated` |
| 실패 처리 | 예외 대신 `ok: false` payload |
{: .zebra .bordered .compact .table-fit caption="tool.py는 검색기보다 runtime 계약에 가깝다."}

이 모듈 덕분에 agent는 성공과 실패를 모두 구조화된 관찰값으로 받는다.

---
{: .page-break}

## 결과 payload는 이렇게 생긴다 {#payload .card}

| 필드 | 의미 |
| --- | --- |
| `ok` | tool 실행 성공 여부 |
| `tool` | 호출된 tool 이름, 여기서는 `search_code` |
| `query` | 실제 적용된 검색 조건 |
| `count` | 반환된 결과 수 |
| `truncated` | 추가 결과 생략 여부 |
| `results[].path` | 매칭 파일 경로 |
| `results[].line_number` | 매칭 줄 번호 |
| `results[].match` | 실제 매칭 텍스트 |
| `error` | 실패 시 오류 정보 |
{: .zebra .bordered .compact .table-fit caption="agent는 payload를 다시 읽고 다음 행동을 결정한다"}

이 형식은 “사람이 읽는 검색 결과”보다 “모델이 다음 행동을 결정하기 쉬운 검색 결과”에 가깝다.

---
{: .page-break}

## LangChain wrapper는 행동을 유도한다 {#langchain-wrapper .card}

```python
search_tool = create_langchain_search_tool(
    allowed_roots=["."]
)
```

이 wrapper가 추가하는 핵심:

- `backend` 기본값을 `smart`로 유도
- `roots`를 `["src"]`, `["tests"]`, `["docs"]`처럼 좁게 잡도록 설명
- quote style과 spacing 차이를 고려한 regex 예시 제공
- 결과가 0건이면 `hints`를 넣어 재검색을 유도

LangChain 공식 문서가 말하는 “well-defined inputs and outputs”가 실제 코드에 내려온 지점이 바로 여기다.

---
{: .page-break}

## agent harness는 prompt까지 포함한다 {#agent-harness .card}

```python
agent = create_search_agent(
    allowed_roots=["."],
    model_name="gpt-4o-mini",
)
```

system prompt가 강제하는 원칙:

1. 위치 질문에는 답하기 전에 `search_code` 호출
2. `roots`는 `src`, `tests`, `docs`처럼 좁게 지정
3. 기본 backend는 `smart`
4. exact search가 실패하면 짧은 토큰이나 regex variant로 재검색
5. file path와 line number를 답변에 포함

검색 tool만 붙였다고 충분하지 않다. prompt, schema, handler, wrapper가 같은 방향을 가리켜야 한다.

---
{: .page-break}

## 실제 실패 사례는 agent 행동이었다 {#failure-case .timeline}

### 1. 초기 질문

사용자가 `backend='smart'` 관련 테스트를 찾아 달라고 요청했다.

### 2. 초기 실패

agent는 작은따옴표까지 그대로 exact search했다. 실제 코드는 `backend="smart"`라서 첫 검색이 0건이었다.

### 3. 잘못된 결론

agent는 한 번의 실패만으로 “없다”고 답할 위험이 있었다.

### 4. 개선

schema, wrapper 설명, prompt에 regex variant와 재검색 원칙을 넣고, empty result에는 `hints`를 추가했다.

---
{: .page-break}

## 개선 전후를 비교하면 {#before-after .compare}

### 개선 전

- exact phrase bias가 강했다
- 0건 결과를 너무 빨리 결론화했다
- 다음 검색 방향이 agent 바깥에 있었다

### 개선 후

- regex variant 예시가 schema에 들어갔다
- `hints`가 empty result에 포함된다
- relative roots를 allowed root 내부로 해석한다
- 실제 평가에서 live agent 테스트 `3 passed`를 기록했다

---
{: .page-break}

## 벡터 검색은 어디에 맞나 {#vector-role .compare}

### 잘 맞는 질문

- 이 기능과 관련된 문서를 찾아줘
- 비슷한 요구사항이 과거에 있었나
- 이 개념을 설명하는 자료는 어디 있나

### 잘 안 맞는 질문

- 정확히 이 문자열이 어디 있나
- 이 설정값이 몇 번째 줄에 있나
- 방금 수정한 로컬 파일이 반영됐나

LangChain retrieval 문서도 semantic search를 문서 split, embeddings, vector store, retriever 흐름으로 설명한다. 이 구조는 의미 검색에는 강하지만 line-level source of truth는 아니다.

참고:

- [LangChain RAG](https://docs.langchain.com/oss/python/langchain/rag)
- [LangChain Semantic Search](https://docs.langchain.com/oss/python/langchain/knowledge-base)

---
{: .page-break}

## 그래서 추천 구조는 이렇다 {#architecture .card}

| 질문 유형 | 우선 도구 | 이유 |
| --- | --- | --- |
| 코드 위치, 테스트, 설정값 확인 | `search_code` | line-level 근거가 필요하다 |
| 요구사항, 문서, 유사 사례 탐색 | vector search | 의미적으로 가까운 자료를 찾는다 |
| 함수, 클래스, 호출 관계 분석 | AST 또는 code graph | 구조 정보를 직접 다뤄야 한다 |
{: .zebra .bordered .compact .table-fit caption="router는 질문 단위를 보고 도구를 나눈다"}

핵심은 도구를 하나로 통일하는 것이 아니라 질문의 단위를 구분하는 것이다.

- line-level 확인은 `search_code`
- semantic retrieval은 vector search
- structural analysis는 AST 또는 graph 계층

---
{: .page-break}

## 정리 {#closing .dark}

이 프로젝트에서 중요한 것은 CLI가 아니라 내부 모듈 계약이다.
{: .lead}

- `core.py`는 결과 shape와 backend 정책을 고정한다.
- backend 모듈은 각자의 검색 방식을 `SearchResult`로 수렴시킨다.
- `tool.py`는 agent runtime이 읽을 JSON 계약을 만든다.
- `langchain_tool.py`는 model behavior를 유도한다.
- `langchain_agent.py`는 검색 후 답변이라는 loop를 완성한다.

그래서 이 구조의 본질은 검색 엔진이 아니라 agent가 신뢰할 수 있는 관찰면이다.

---
{: .page-break}

## 참고 링크 {#references .evidence-ledger}

| 종류 | 문서 | 용도 |
| --- | --- | --- |
| 내부 | `README.md` | tool JSON 계약, backend 정책, `allowed_roots` |
| 내부 | `docs/agent-tool-evaluation.md` | live agent 평가, `hints`, exact phrase bias |
| 내부 | `docs/python-search-dependency-recommendations.md` | `smart` backend, `pathspec`, 의존성 정책 |
| 내부 | `docs/open-source-references.md` | `rg`, `grep`, Python adapter 방식 |
| 내부 | `docs/search-backend-benchmark.md` | backend 속도 비교와 대표 benchmark 결과 |
| 내부 | `scripts/benchmark_search_backends.py` | benchmark 재실행용 스크립트 |
| 외부 | [LangChain Agents](https://docs.langchain.com/oss/python/langchain/agents) | `create_agent`와 tool loop 설명 |
| 외부 | [LangChain Tools](https://docs.langchain.com/oss/python/langchain/tools) | callable tool 개념 설명 |
| 외부 | [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling) | JSON schema 기반 tool calling 설명 |
| 외부 | [ripgrep](https://github.com/burntsushi/ripgrep) | line-oriented search와 기본 ignore 정책 |
| 외부 | [LangChain RAG](https://docs.langchain.com/oss/python/langchain/rag) | vector retrieval 흐름 설명 |
{: .zebra .bordered .compact .table-fit caption="내부 코드와 공식 문서를 함께 보고 읽는 블로그용 deck"}
