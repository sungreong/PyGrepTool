# PyGrepTool

> One-file, zero-dependency local search for AI agents.

PyGrepTool은 AI 에이전트가 로컬 코드와 문서를 검색하고, 답변의 근거가 되는
정확한 파일·줄·열·주변 문맥을 얻도록 만든 경량 검색 도구입니다.

```text
No vector DB. No indexing. No required dependencies.
Just exact file and line references.
```

작은 프로젝트에서는 [`standalone/pygrep_tool.py`](standalone/pygrep_tool.py)
한 파일만 복사해서 시작할 수 있습니다. 더 많은 기능이 필요해지면 정식 Python 패키지로
전환해 `rg → grep → pure Python` fallback, OpenAI tool schema, LangChain adapter,
`search_code → read_context` 흐름을 사용할 수 있습니다.

## 30초 빠른 시작

### 파일 하나만 복사해서 사용

```powershell
Copy-Item standalone\pygrep_tool.py .\pygrep_tool.py
python pygrep_tool.py TODO src tests --include "*.py"
```

```python
from pygrep_tool import search_files

hits = search_files(
    "TODO",
    ["src", "tests"],
    include=["*.py"],
    allowed_roots=["."],
)

for hit in hits:
    print(hit.path, hit.line_number, hit.context)
```

### 전체 패키지를 로컬 설치

Python import 이름은 `pygreptool`, 일반 CLI는 `pygreptool`, agent tool용 JSON CLI는
`pygrep-tool`입니다. 저장소에서 다음과 같이 설치할 수 있습니다.

```bash
python -m pip install -e .
pygreptool TODO src --json
pygrep-tool --schema responses --pretty
```

## 왜 만들었나

작은 내부 자동화에 정확한 로컬 파일 검색이 필요할 때 벡터 DB, 임베딩, 청킹,
인덱싱 파이프라인까지 도입하는 것은 과할 수 있습니다. PyGrepTool은 의미 기반 검색을
대체하지 않습니다. 에러 메시지, 심볼, 설정 키, 코드 패턴처럼 정확한 검색이 필요한
질문을 인덱스 없이 즉시 처리하는 데 집중합니다.

| 특성 | 단일 파일 | 전체 패키지 |
|---|---:|---:|
| 필수 Python 의존성 | 0 | 0 |
| 문자열·정규식·glob 검색 | ✓ | ✓ |
| 파일·줄·열·주변 문맥 | ✓ | ✓ |
| `allowed_roots` 경로 제한 | ✓ | ✓ |
| `rg`·`grep` 자동 fallback |  | ✓ |
| OpenAI tool schema |  | ✓ |
| LangChain adapter |  | Optional |
| `read_context` tool |  | ✓ |

## 검증 상태

```text
68 passed, 4 skipped
```

기본 테스트는 네트워크 없이 실행됩니다. 실제 LLM 호출 테스트는 명시적으로 활성화할
때만 실행됩니다.

```bash
python -m pytest
```

---

## 패키지 상세 문서

`pygreptool`은 Python 코드에서 `rg` 또는 `grep`을 우선 사용하고, 외부 명령어가 없거나 실패하면 순수 Python 검색기로 fallback할 수 있게 만든 작은 개발용 라이브러리입니다. 작은 검색 범위에서는 외부 프로세스 실행 비용을 피하는 `smart` backend도 제공합니다.

추가로 `search_code`라는 LLM tool 포맷을 제공합니다. 모델이 만든 function-call arguments를 `run_search_tool()` 또는 `pygrep-tool --call`에 넣으면 JSON 결과를 받을 수 있습니다.

목표는 ripgrep을 다시 만드는 것이 아닙니다. 목표는 검색 결과를 Python 객체와 tool 결과 JSON으로 표준화해서 다음 정보를 안정적으로 얻는 것입니다.

```text
path
line_number
column
line
match
backend
```

## 구성

```text
pygrep_tool/
  Dockerfile
  docker-compose.yml
  requirements.txt
  pyproject.toml
  src/pygreptool/
    core.py
    cli.py
    tool.py
    tool_cli.py
    backends/
      rg.py
      grep.py
      python.py
  tools/
    search_code.openai.responses.tool.json
    search_code.openai.chat_completions.tool.json
    read_context.openai.responses.tool.json
    read_context.openai.chat_completions.tool.json
  tests/
  examples/
  scripts/
```

## Docker로 실행

```bash
docker compose build
docker compose run --rm app pytest -q
```

CLI 검색 예시입니다.

```bash
docker compose run --rm app pygreptool TODO examples
docker compose run --rm app pygreptool "def .*" src --backend rg
docker compose run --rm app pygreptool TODO examples --backend python
docker compose run --rm app pygreptool TODO examples --json
```

Tool 실행 예시입니다.

```bash
docker compose run --rm app pygrep-tool --schema responses --pretty

docker compose run --rm app sh -lc 'echo "{\"pattern\":\"TODO\",\"roots\":[\"examples\"],\"regex\":false,\"backend\":\"python\"}" | pygrep-tool --call --pretty'
```

## 로컬 Windows 개발 예시

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
pygreptool TODO examples
pygreptool TODO examples --backend smart
pygrep-tool --schema responses --pretty
```

`.gitignore`/`.ignore` 호환 필터링을 Python backend에서도 쓰고 싶다면 optional extra를 설치합니다.

```powershell
pip install -e ".[ignore]"
```

LangChain agent 예제를 실행하려면 agent extra를 설치하고 `.env`에 `OPENAI_API_KEY`, `LLM_MODEL_NAME`을 설정합니다.

```powershell
pip install -e ".[agent]"
$env:PYTHONPATH='src'
python examples\langchain_agent_search.py
```

기본 agent는 `search_code`와 `read_context`를 함께 사용합니다. 먼저 후보 위치를 찾고, 더 넓은 주변 코드가 필요하면 검색 결과의 `read_context_args`로 추가 문맥을 읽습니다.

실제 OpenAI 호출까지 포함한 agent 테스트는 기본 pytest에서는 스킵됩니다. 필요할 때만 켭니다.

```powershell
$env:RUN_LIVE_AGENT_TESTS='1'
$env:PYTHONPATH='src'
python -m pytest tests\test_live_agent_search.py
```

PowerShell에서 tool을 호출하는 예시입니다.

```powershell
'{"pattern":"TODO","roots":["examples"],"regex":false,"backend":"python"}' | pygrep-tool --call --pretty
```

## Python API

```python
from pygreptool import search

results = search("TODO", "examples", backend="auto")

for result in results:
    print(result.path, result.line_number, result.column, result.line)
```

## 설치 없이 단일 파일로 사용

작은 내부 도구나 프로토타입에서는 [`standalone/pygrep_tool.py`](standalone/pygrep_tool.py)
한 파일만 복사해 사용할 수 있습니다. 이 버전은 외부 패키지와 `rg` 설치가 필요 없으며,
문자열/정규식 검색, glob 필터, 주변 문맥, 결과 제한, `allowed_roots`를 지원합니다.

```python
from pygrep_tool import search_files

hits = search_files(
    "TODO",
    ["src", "tests"],
    include=["*.py"],
    allowed_roots=["."],
)

for hit in hits:
    print(hit.path, hit.line_number, hit.context)
```

파일 자체를 CLI처럼 실행해 JSON 결과를 받을 수도 있습니다.

```bash
python pygrep_tool.py TODO src tests --include "*.py"
```

정식 패키지는 여기에 `rg → grep → Python` fallback, ignore 파일 처리,
OpenAI tool schema, LangChain adapter, `read_context` tool을 추가합니다.

에이전트나 컨테이너처럼 실행 위치가 흔들릴 수 있는 환경에서는 `workspace_root`를 고정하면 상대 `roots`와 ignore 파일이 항상 같은 기준으로 해석됩니다.

```python
from pygreptool import search

results = search(
    "TODO",
    ["src", "tests"],
    backend="smart",
    workspace_root="/app",
    ignore_files=(".gitignore", ".ignore", ".agentignore"),
)
```

## Tool API

### 1. Tool schema 가져오기

Responses API 스타일입니다.

```python
from pygreptool import get_openai_responses_read_context_tool_schema, get_openai_responses_tool_schema

tools = [
    get_openai_responses_tool_schema(),
    get_openai_responses_read_context_tool_schema(),
]
```

Chat Completions 스타일입니다.

```python
from pygreptool import get_openai_chat_read_context_tool_schema, get_openai_chat_tool_schema

tools = [
    get_openai_chat_tool_schema(),
    get_openai_chat_read_context_tool_schema(),
]
```

이미 JSON 파일도 제공합니다.

```text
tools/search_code.openai.responses.tool.json
tools/search_code.openai.chat_completions.tool.json
tools/read_context.openai.responses.tool.json
tools/read_context.openai.chat_completions.tool.json
```

### 2. Tool handler 실행하기

모델이 `search_code`를 호출했다고 가정하면, arguments를 그대로 handler에 전달합니다.

```python
from pygreptool import run_search_tool

arguments = {
    "pattern": "TODO",
    "roots": ["examples"],
    "regex": False,
    "include": ["*.py", "*.md"],
    "ignore_case": None,
    "hidden": None,
    "backend": "auto",
    "fallback": None,
    "encoding": None,
    "max_results": 20,
    "max_line_chars": 300,
    "context_before": 3,
    "context_after": 3,
}

result = run_search_tool(arguments, allowed_roots=["."])
```

LLM tool call에는 `workspace_root`나 ignore 설정을 노출하지 않고, runner 생성 시점에 고정할 수도 있습니다.

```python
from pygreptool import create_read_context_tool_runner, create_search_tool_runner

runner = create_search_tool_runner(
    workspace_root="/app",
    allowed_roots=["src", "tests", "docs"],
    ignore_files=(".gitignore", ".ignore", ".agentignore"),
)

result = runner(arguments)

read_context_runner = create_read_context_tool_runner(
    workspace_root="/app",
    allowed_roots=["src", "tests", "docs"],
)
```

결과 형태는 다음과 같습니다.

```json
{
  "ok": true,
  "tool": "search_code",
  "query": {
    "pattern": "TODO",
    "roots": ["examples"],
    "regex": false,
    "include": ["*.py", "*.md"],
    "ignore_case": false,
    "hidden": false,
    "backend": "auto",
    "fallback": true,
    "encoding": "utf-8",
    "max_results": 20,
    "max_line_chars": 300,
    "context_before": 3,
    "context_after": 3
  },
  "count": 1,
  "truncated": false,
  "results": [
    {
      "path": "examples/sample_project/app.py",
      "line_number": 2,
      "column": 3,
      "line": "# TODO: improve greeting",
      "match": "TODO",
      "backend": "python",
      "line_truncated": false,
      "context": {
        "start_line": 1,
        "end_line": 5,
        "content": "# TODO: improve greeting",
        "lines": [
          {"line_number": 2, "line": "# TODO: improve greeting", "is_match": true}
        ],
        "truncated": false
      },
      "read_context_args": {
        "path": "examples/sample_project/app.py",
        "line_number": 2,
        "before": 20,
        "after": 20,
        "full": false
      }
    }
  ],
  "related_tools": [
    {
      "tool": "read_context",
      "available": true,
      "reason": "Use this to inspect more surrounding lines or a larger file slice for selected matches."
    }
  ],
  "error": null
}
```

더 넓은 문맥이 필요하면 `read_context_args`를 그대로 `read_context` handler에 넘길 수 있습니다.

```python
from pygreptool import run_read_context_tool

context = run_read_context_tool(
    result["results"][0]["read_context_args"],
    allowed_roots=["."],
)
```

실패해도 예외를 직접 던지기보다 tool 결과로 직렬화합니다.

```json
{
  "ok": false,
  "tool": "search_code",
  "query": null,
  "count": 0,
  "truncated": false,
  "results": [],
  "related_tools": [
    {
      "tool": "read_context",
      "available": true,
      "reason": "Use this to inspect more surrounding lines or a larger file slice for selected matches."
    }
  ],
  "error": {
    "type": "ToolInputError",
    "message": "roots is required"
  }
}
```

## Tool 입력 필드

```text
pattern
  검색할 문자열 또는 정규식입니다.

roots
  검색할 파일 또는 디렉터리 배열입니다.

regex
  true면 정규식, false면 고정 문자열입니다. null 또는 생략 시 true입니다.

include
  glob 필터 배열입니다. 예: ["*.py", "src/**/*.ts"]

ignore_case
  대소문자 무시 여부입니다.

hidden
  숨김 파일과 디렉터리 포함 여부입니다.

backend
  auto, smart, rg, grep, python 중 하나입니다. null 또는 생략 시 auto입니다.

fallback
  auto 모드에서 실패 시 다음 backend를 시도할지 여부입니다.

encoding
  Python backend와 grep 출력 디코딩에 쓸 인코딩입니다. 기본값은 utf-8입니다.

max_results
  반환할 최대 match 수입니다. 기본값은 50입니다.

max_line_chars
  각 line을 최대 몇 글자까지 유지할지 정합니다. 기본값은 500입니다.

context_before
  각 match 앞쪽 문맥 줄 수입니다. 기본값은 3입니다. 0이면 앞쪽 문맥을 끕니다.

context_after
  각 match 뒤쪽 문맥 줄 수입니다. 기본값은 3입니다. 0이면 뒤쪽 문맥을 끕니다.

read_context
  `path`, `line_number`, `before`, `after`로 특정 위치 주변을 읽습니다.
  결과는 `content` 문자열을 중심으로 주고, 위치 추적용 `start_line`, `end_line`, `lines`도 함께 제공합니다.
  `full=true`이면 파일 앞부분부터 읽되 `max_lines`, `max_chars` 제한을 적용합니다.
```

## 보안상 중요한 점

이 tool은 로컬 파일을 읽습니다. 에이전트에 붙일 때는 `allowed_roots`를 지정하는 편이 안전합니다.

```python
result = run_search_tool(arguments, allowed_roots=["./src", "./tests"])
```

CLI에서는 다음처럼 제한할 수 있습니다.

```bash
pygrep-tool --call args.json --allowed-root ./src --allowed-root ./tests
```

환경 변수도 지원합니다. 여러 경로는 OS별 path separator로 구분합니다.

```bash
export PYGREPKIT_ALLOWED_ROOTS="./src:./tests"
```

## backend 정책

```text
auto
  rg 사용 가능하면 rg
  rg 실패 또는 미설치면 grep
  grep 실패 또는 미설치면 python fallback

smart
  작은 root 또는 단일 파일이면 python
  큰 root이면 auto와 같은 순서로 rg, grep, python fallback

rg
  ripgrep 강제 사용

grep
  grep 강제 사용

python
  순수 Python 검색기 강제 사용
```

주의할 점은 `rg`, `grep`, Python `re`의 정규식 문법이 완전히 같지 않다는 것입니다. 정밀한 일관성이 필요하면 `backend="python"` 또는 `backend="rg"`처럼 하나로 고정하는 편이 안전합니다.

## 개발 명령

```bash
pytest -q
python scripts/demo_search.py
python examples/tool_runtime_example.py
pygreptool TODO examples --backend auto
pygrep-tool --schema both --pretty
```
