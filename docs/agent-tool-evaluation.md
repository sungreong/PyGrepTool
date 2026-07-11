# Agent Tool Evaluation

평가일: 2026-07-08

이 문서는 `ChatOpenAI` + LangChain agent + `pygreptool` 검색 툴을 실제로 연결해 테스트한 결과와 개선책을 정리한다. `.env` 파일 내용은 직접 열람하지 않고, 예제 코드에서 `python-dotenv`로만 로드했다.

## 사용한 구성

- Model: `.env`의 `LLM_MODEL_NAME` 값, 기본 fallback은 `gpt-4o-mini`
- API key: `.env`의 `OPENAI_API_KEY`
- Agent: LangChain `create_agent`
- Model wrapper: `langchain_openai.ChatOpenAI`
- Tool wrapper: `pygreptool.langchain_tool.create_langchain_search_tool`
- Tool backend 기본값: `smart`
- Allowed roots: 현재 프로젝트 루트

LangChain 공식 문서는 `create_agent`를 모델, prompt, tools, middleware를 조합하는 agent harness로 설명한다. 이 프로젝트의 요구는 “고정된 검색 툴 하나를 모델이 필요할 때 호출하는 단일 목적 agent”라서 LangChain agent가 적합하다.

## 실제 테스트 결과

테스트는 두 층으로 분리한다.

```text
일반 테스트
  네트워크 없이 fixture 데이터를 검색한다.
  항상 기본 pytest에 포함된다.

live agent 테스트
  실제 ChatOpenAI agent가 tool을 호출한다.
  RUN_LIVE_AGENT_TESTS=1일 때만 실행한다.
```

Fixture 위치:

```text
tests/fixtures/agent_sample_project/
```

일반 테스트:

```powershell
python -m pytest tests\test_agent_fixture_tool.py
```

Live agent 테스트:

```powershell
$env:RUN_LIVE_AGENT_TESTS='1'
$env:PYTHONPATH='src'
python -m pytest tests\test_live_agent_search.py
```

검증 결과:

```text
일반 전체 테스트: 40 passed, 4 skipped
live agent 테스트: 3 passed
```

실행 명령:

```powershell
$env:PYTHONPATH='src'
python examples\langchain_agent_search.py
```

### Test 1. 타입 정의 찾기

Prompt:

```text
Where is BackendName defined, and what values can it take?
```

Result:

- `src/pygreptool/core.py` line 8을 찾았다.
- 가능한 값 `auto`, `smart`, `rg`, `grep`, `python`을 올바르게 답했다.
- 관련 import 위치도 함께 언급했다.

판정: 성공

### Test 2. `backend='smart'` 테스트 찾기

초기 결과:

- 모델이 `backend='smart'` 문자열을 너무 문자 그대로 검색했다.
- 실제 코드는 `backend="smart"`라서 첫 검색이 실패했고, 모델이 바로 “없다”고 답했다.

개선:

- agent system prompt에 “정확 검색 실패 시 짧은 토큰 또는 quote/style variant를 처리하는 regex로 재검색”하라고 추가했다.
- tool 설명에도 같은 재검색 전략을 넣었다.
- `pattern` 필드 설명에 `["']?backend["']?\s*[:=]\s*["']smart["']` 같은 regex 예시를 넣었다.
- 검색 결과가 0건이면 tool JSON에 `hints`를 넣어 짧은 토큰/regex variant/좁은 roots 재검색을 유도한다.
- allowed root가 하나일 때 `roots=["src"]` 같은 상대 root는 allowed root 내부의 `src`로 해석한다.

개선 후 결과:

- fixture live test에서 `src/alpha_service.py`와 `src/beta_service.py`를 모두 찾았다.
- 실제 repo 예제에서는 `tests/test_core.py` line 42, line 53을 찾았다.

판정: 개선 후 성공

### Test 3. `pathspec` 문서 찾기

Prompt:

```text
Find documentation that mentions pathspec and summarize why it is optional.
```

Result:

- `docs/python-search-dependency-recommendations.md`를 중심으로 찾았다.
- `pathspec`이 검색 엔진이 아니라 `.gitignore`/path filtering용 optional extra라는 점을 잘 요약했다.

판정: 성공

## 발견한 문제와 조치

### 1. exact phrase bias

모델은 사용자가 입력한 quote style을 그대로 검색하려는 경향이 있다. 코드에서는 작은따옴표/큰따옴표, 공백, keyword argument 순서가 다를 수 있다.

조치:

- system prompt에서 실패 시 재검색을 명시했다.
- tool 설명에서 재검색 전략을 안내했다.
- schema description에 regex variant 예시를 넣었다.

### 2. 결과 없음 판단이 너무 빠름

한 번의 검색 실패만으로 “없다”고 결론 내릴 수 있다.

조치:

- “Never conclude absent after only one failed exact search” 지침을 agent prompt에 넣었다.

향후 개선 후보:

- `hints`를 더 구조화한다. 예: `suggested_patterns`, `suggested_roots` 배열로 분리.
- agent evaluation용 golden answer를 JSON으로 관리한다.

### 3. tool 결과가 길어질 수 있음

여러 파일에서 많이 매칭되면 LLM context를 낭비할 수 있다.

현재 완화책:

- `max_results` 기본값 20
- `max_line_chars` 기본값 300
- `truncated`를 실제 추가 결과 존재 여부로 정확히 표시

향후 개선 후보:

- 결과에 `next_query_suggestion` 또는 `narrowing_suggestions` 추가
- `roots`가 너무 넓으면 tool이 warning을 포함하도록 개선

## 최종 권장 프롬프트 원칙

Agent prompt에는 다음 원칙이 들어가는 것이 좋다.

```text
1. 코드 위치 질문에는 답하기 전에 search_code를 호출한다.
2. roots는 src, tests, docs처럼 좁게 잡는다.
3. backend는 기본 smart를 쓴다.
4. 정확 검색 실패 시 짧은 토큰이나 regex variant로 한 번 이상 재검색한다.
5. 결과가 없다고 말할 때는 어떤 roots/pattern으로 검색했는지 함께 말한다.
6. 답변에는 file path와 line number를 포함한다.
```

## 참고 링크

- LangChain agents: https://docs.langchain.com/oss/python/langchain/agents
- LangChain tools: https://docs.langchain.com/oss/python/langchain/tools
- LangChain overview: https://docs.langchain.com/oss/python/langchain/overview
