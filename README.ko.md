# PyGrepTool

> 제한된 workspace 안에서 agent가 근거를 따라 파일을 탐색하도록 돕는 read-only 도구 모음

[English](README.md)

PyGrepTool은 agent가 후보 파일을 찾고, 코드·문서의 정확한 문자열을 검색하고, 필요한 줄만 추가로 읽도록 돕습니다. 파일 경로, 줄 번호, 제한된 문맥을 구조화해 반환하며 vector DB나 사전 인덱싱이 필요하지 않습니다.

이 도구는 Docker, VM, remote workspace 같은 **실제 격리 환경 내부**에서 사용하도록 설계되었습니다. 자체 policy는 file tool이 노출할 수 있는 범위를 좁히지만, sandbox 자체를 대체하지는 않습니다.

## 왜 필요한가

일반적인 파일 관리 toolkit은 넓은 파일시스템 작업을 제공합니다. 하지만 코드 탐색 agent에 필요한 surface는 더 작습니다.

- `find_files`: 폴더, 파일명 일부, 확장자로 후보 파일 찾기
- `search_code`: 파일 안의 정확한 문자열 또는 정규식 찾기
- `read_context`: 선택한 위치의 제한된 추가 문맥 읽기

PyGrepTool은 이 세 작업을 read-only로 제한하고, 사람과 agent가 모두 읽기 쉬운 구조화 결과를 반환합니다. allowlist, 가상 경로, secret 파일 차단, 민감 문자열 redaction, 선택적 audit event도 지원합니다.

## 제공하는 것과 제공하지 않는 것

| 제공 | 제공하지 않음 |
| --- | --- |
| `rg → grep → Python` 검색 fallback | Docker/VM/process sandbox |
| `allowed_roots`와 가상 경로 guardrail | shell, write, delete, move, network tool |
| `find_files → search_code → read_context` 탐색 흐름 | vector search, embedding, indexing |
| OpenAI 호환 schema와 선택적 LangChain tool | 미리 만들어진 agent 또는 숨겨진 system prompt |

프로세스에 shell 실행 권한이나 넓은 host volume 접근 권한이 있으면 file-tool policy를 우회할 수 있습니다. sandbox에는 의도한 workspace만 read-only로 mount하고, agent에는 필요한 tool만 제공하세요.

## 설치

PyGrepTool 자체는 필수 runtime dependency가 없습니다.

### 저장소에서 개발 설치

```powershell
python -m pip install -e .
pygreptool TODO src --json
pygrep-tool --schema responses --pretty
```

선택적 extra입니다.

```powershell
# Python backend에서 .gitignore 호환 필터 사용
python -m pip install -e ".[ignore]"

# LangChain tool adapter만 사용
python -m pip install -e ".[langchain]"

# OpenAI/LangChain 실행 예제까지 사용
python -m pip install -e ".[agent]"
```

### wheel 빌드와 설치

이 저장소는 wheel 배포를 지원합니다. `build/`, `dist/` 산출물은 Git에 올라가지 않습니다.

```powershell
python -m pip install --upgrade build
python -m build
python -m pip install --force-reinstall .\dist\pygreptool-0.2.0-py3-none-any.whl
```

`dist/`에는 범용 pure-Python wheel과 sdist가 만들어집니다. 첫 공개는 두 파일을 GitHub Release asset으로 첨부하는 방식을 권장합니다. PyPI 배포는 패키지명과 버전 정책을 확정한 뒤, 검증한 동일 artifact로 진행하면 됩니다.

### 단일 파일 사용

작은 내부 스크립트에는 [`standalone/pygrep_tool.py`](standalone/pygrep_tool.py) 하나만 복사해 사용할 수 있습니다. 이 버전은 외부 package나 검색 명령어에 의존하지 않습니다.

```powershell
Copy-Item standalone\pygrep_tool.py .\pygrep_tool.py
python pygrep_tool.py TODO src tests --include "*.py"
```

가상 경로, policy, OpenAI schema, LangChain 연동이 필요하면 wheel/package 버전을 사용하세요.

## 내 agent에 tool만 추가하기

PyGrepTool은 agent를 생성하거나 소유하지 않습니다. 애플리케이션이 model, system prompt, 기존 tool을 소유하고 PyGrepTool의 read-only toolkit만 합칩니다.

```python
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from pygreptool import CodeAccessPolicy
from pygreptool.langchain_toolkit import create_pygrep_tools

project_root = "/workspace/project"
application_tools = [my_existing_tool]

navigation_tools = create_pygrep_tools(
    workspace_root=project_root,
    allowed_roots=["src", "tests"],
    virtual_mode=True,
    policy=CodeAccessPolicy(),
)

agent = create_agent(
    model=ChatOpenAI(model="gpt-4o-mini", temperature=0),
    tools=[*application_tools, *navigation_tools],
    system_prompt=(
        "Use find_files for filenames or extensions, search_code for file contents, "
        "and read_context only when additional lines are needed."
    ),
)
```

`create_pygrep_tools()`는 `find_files`, `search_code`, `read_context` 순서의 tool을 반환합니다. 작은 모델도 역할을 구분하도록 description을 작성했습니다. `search_code`는 기본으로 파일·줄 위치만 간결하게 반환하며, 각 match의 `read_context_args`로 필요한 부분만 더 읽을 수 있습니다.

tool은 `find_files → search_code → read_context` 순서로 반드시 호출할 필요가 없습니다. 사용자가 이미 허용된 정확한 파일 경로와 줄을 주었다면 `read_context`를 바로 쓰고, 그 외에는 질문에 답하는 가장 작은 tool부터 선택하세요.

`agent` extra 설치 후 애플리케이션 소유 agent 예제를 실행할 수 있습니다. `.env`는 읽지만 값은 출력하지 않습니다.

```powershell
python examples\compose_your_own_agent.py "Find Python service files under /src."
python examples\compose_your_own_agent.py --trace "Find where BackendName is defined and cite the line number."
```

`--trace`는 model이 선택한 tool 이름, argument, 요약된 결과를 출력합니다. 기본 실행은 최종 답변만 출력합니다.

## 탐색 도구를 고르는 기준

세 도구는 같은 문제를 푸는 것이 아니므로, 단순 조회 시간만으로 순위를 매기면 안 됩니다.

| 필요한 질문 | 선택 | 고려할 점 |
| --- | --- | --- |
| 신뢰할 수 있는 checkout에서 빠르게 정확한 문자열만 찾기 | `rg` | 텍스트는 빠르게 찾지만 agent용 가상 경로, policy 결과, 후속 작업 구조는 제공하지 않습니다. |
| 인덱싱 뒤 심볼, 호출자/피호출자, 영향 범위 찾기 | CodeGraph | semantic graph 질의가 가능하지만 초기화·동기화가 필요합니다. 접근 범위와 비밀 정보 처리는 sandbox와 mount policy에서 별도로 보장해야 합니다. |
| agent가 허용된 루트 안에서 파일명·확장자, 문자열/정규식, 제한된 문맥을 탐색하기 | PyGrepTool 또는 선택적 Skill | call graph를 추론하지 않는 대신 사전 인덱스가 필요 없고, 가상 경로·줄 근거·policy 차단·다음 안전한 행동을 구조화해 반환합니다. |

체크인된 골든셋은 단일 요청 4개와 end-to-end 탐색 여정 6개를 검증합니다. service 파일 찾기, backend 설정의 줄 근거 찾기, 발견 뒤 필요한 문맥만 읽기, runbook 찾기, private 디렉터리 차단이 포함됩니다. 각 여정에는 기대 tool 호출 수가 있어, 결과의 정확도와 근거를 얻기까지 필요한 호출 횟수를 함께 확인할 수 있습니다. 중앙값 지연 시간까지 함께 측정하려면 다음을 실행하세요.

```powershell
python scripts\evaluate_navigation.py --iterations 7
python scripts\evaluate_navigation.py --iterations 7 --with-codegraph
```

여정의 호출 수는 policy를 지키는 기준 계획이며 특정 LLM이 반드시 같은 횟수로 행동한다는 의미는 아닙니다. 보고서는 in-process dispatch와 Skill command 시작 비용을 분리하고, CodeGraph는 실제 강점인 심볼/호출자 질문에서만 측정합니다. `--with-codegraph`는 필요할 때만 Git에 포함되지 않는 로컬 index를 만듭니다. 수치는 실행 환경과 저장소 크기에 따라 달라지므로, 보편적 성능 우위가 아니라 process 시작·policy 검증·semantic index 질의의 비용을 보여 주는 참고값으로 해석하세요.

골든 질문, tool 호출 여정, 측정 결과, 비교 범위, 재현 명령은 [최종 평가 문서](docs/navigation-evaluation.md)에 정리했습니다.

## 선택적 agent Skill

패키지는 framework에 종속되지 않습니다. wheel에 포함하지 않는 별도 agent Skill은
[`skills/pygreptool-navigation`](skills/pygreptool-navigation)에 있습니다. 이 Skill은 상황별 tool 선택,
config에 고정된 Python runner, 가상 경로·allowlist·custom ignore·policy denial의 필수 조건을 제공합니다.
먼저 package를 설치한 뒤, 해당 폴더를 사용하는 agent의 skill directory에 복사하세요.

## LangChain 없이 handler 사용하기

handler는 JSON 호환 object를 받고 `ok`, `summary`, `count`, `results`, `next_step`, `error`가 포함된 안정적인 envelope를 반환합니다.

```python
from pygreptool import CodeAccessPolicy, run_find_files_tool, run_search_tool

files = run_find_files_tool(
    {
        "folder": "/src",
        "name_query": "service",
        "extensions": ["py"],
        "max_results": 20,
        "hidden": False,
    },
    workspace_root="/workspace/project",
    allowed_roots=["src"],
    virtual_mode=True,
    policy=CodeAccessPolicy(),
)

matches = run_search_tool(
    {
        "pattern": "TODO",
        "roots": ["/src"],
        "regex": False,
        "include": ["*.py"],
        "max_results": 20,
    },
    workspace_root="/workspace/project",
    allowed_roots=["src"],
    virtual_mode=True,
    policy=CodeAccessPolicy(),
)
```

현재 OpenAI schema는 설치한 package에서 `get_openai_responses_*_tool_schema()` 또는 `get_openai_chat_*_tool_schema()`로 생성합니다. schema JSON을 파일로 중복 관리하지 않습니다.

### 큰 검색 범위 제한

host는 `max_files_scanned`, `max_total_bytes_scanned`, `timeout_ms` 중 하나를 설정해 `search_code`를 deterministic Python scan budget 안에서 실행할 수 있습니다. 응답의 `search_stats`로 agent는 전체 저장소를 다 검색한 것처럼 말하지 않고, 근거가 불완전한지 보고할 수 있습니다.

별도 Skill runner에서는 이 제한을 trusted `.pygreptool.json` policy에 넣으세요. model이 제한을 생략하거나 더 큰 값을 요청해도 runner가 policy 값으로 제한합니다.
프로젝트에 맞게 수정하려면 `.pygreptool.example.json`을 `.pygreptool.json`으로 복사하세요. 실제 설정 파일은 의도적으로 Git에서 제외합니다.

## 보안 모델

`virtual_mode=True`일 때 `workspace_root`는 agent에게 보이는 `/`가 됩니다.

```text
agent path:  /src/main.py
physical:    /workspace/project/src/main.py
```

tool은 `..`, `~`, Windows drive/UNC 경로, `allowed_roots` 바깥으로 resolve되는 결과를 거부합니다. allowlist 밖으로 나가는 symlink도 제외합니다. `virtual_mode=True`에서는 실패 응답도 물리 workspace 경로를 숨깁니다. `CodeAccessPolicy`는 `.env`, `.git`, PEM/key 파일처럼 흔한 secret path를 차단하고 반환 문자열의 secret-like content를 redaction합니다.

이는 tool 수준의 defense-in-depth이며 OS 격리는 아닙니다. 실제 경계는 read-only workspace mount와 shell/network tool 미제공으로 만드세요. Docker demo는 이 조합을 검증합니다.

```powershell
docker compose build
docker compose run --rm app
docker compose run --rm sandbox-demo
```

두 service 모두 runtime network를 열지 않습니다. demo는 `tests/fixtures/agent_sample_project`만 `/workspace:ro`에 mount하고 `/src/alpha_service.py` 같은 가상 경로만 노출합니다.

## 저장소 구조

```text
src/pygreptool/
  core.py                 # 검색 API와 context read
  backends/               # rg, grep, pure-Python 구현
  file_discovery.py       # 파일명/확장자 후보 탐색
  file_tool.py            # find_files schema와 handler
  tool.py                 # search_code/read_context schema와 handler
  runtime_scope.py        # workspace와 allowlist 공통 해석
  path_policy.py          # physical-to-virtual path mapping
  security_policy.py      # deny, redact, audit policy
  langchain_tool.py       # 개별 LangChain adapter
  langchain_toolkit.py    # 조합 가능한 read-only toolkit
  cli.py, tool_cli.py     # 사람용 CLI와 JSON tool CLI
standalone/pygrep_tool.py # 의존성 없는 단일 파일 버전
examples/                 # 직접 탐색, agent 조합, Docker demo
tests/                    # deterministic/policy/adapter/live-agent 테스트
```

`src/pygreptool`의 각 module은 하나의 runtime 책임을 가집니다. 실행 후 보일 수 있는 `__pycache__/`와 editable install 산출물인 `pygreptool.egg-info/`는 `.gitignore`에 포함되어 GitHub에 올라가지 않습니다.

## 로컬 검증

```powershell
# API key·network가 필요 없는 deterministic test
python -m pip install -e ".[dev,langchain]"
python -m pytest

# 선택적 실제 tool-selection 평가; .env의 OPENAI_API_KEY 필요
python -m pip install -e ".[agent]"
python -m pytest -m live_agent
```

live test는 provider 초기화에만 key를 사용하며 값은 log로 출력하지 않습니다.

## 라이선스

[MIT](LICENSE)
