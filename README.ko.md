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

`agent` extra 설치 후 애플리케이션 소유 agent 예제를 실행할 수 있습니다. `.env`는 읽지만 값은 출력하지 않습니다.

```powershell
python examples\compose_your_own_agent.py "Find Python service files under /src."
python examples\compose_your_own_agent.py --trace "Find where BackendName is defined and cite the line number."
```

`--trace`는 model이 선택한 tool 이름, argument, 요약된 결과를 출력합니다. 기본 실행은 최종 답변만 출력합니다.

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

## 보안 모델

`virtual_mode=True`일 때 `workspace_root`는 agent에게 보이는 `/`가 됩니다.

```text
agent path:  /src/main.py
physical:    /workspace/project/src/main.py
```

tool은 `..`, `~`, Windows drive/UNC 경로, `allowed_roots` 바깥으로 resolve되는 결과를 거부합니다. allowlist 밖으로 나가는 symlink도 제외합니다. `CodeAccessPolicy`는 `.env`, `.git`, PEM/key 파일처럼 흔한 secret path를 차단하고 반환 문자열의 secret-like content를 redaction합니다.

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
