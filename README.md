# PyGrepTool

> Policy-bound, read-only code navigation tools for AI agents.

[한국어](README.ko.md)

PyGrepTool lets an agent find files, search exact text or regular expressions, and read only the lines needed to support an answer. It returns virtual paths, line evidence, bounded context, and explicit policy denials—without a vector database, index, or prebuilt agent.

It is designed to run inside a real isolation boundary such as Docker, a VM, or a remote workspace. Its policy layer reduces what the file tools can disclose; it is **not** a replacement for process isolation.

## Why PyGrepTool

`rg` is excellent for trusted human use, but it does not define an agent-facing access boundary or result contract. Broad file-management toolkits expose more filesystem capability than a code-navigation agent needs.

PyGrepTool keeps the surface small and read-only:

- `find_files` finds candidates by folder, filename fragment, or extension.
- `search_code` finds exact text or regular expressions and returns line evidence.
- `read_context` performs a focused, line-bounded follow-up read.

| PyGrepTool provides | It deliberately does not provide |
| --- | --- |
| `rg → grep → Python` fallback | A Docker, VM, or process sandbox |
| Virtual paths and `allowed_roots` enforcement | Shell, write, delete, move, or network tools |
| Ignore rules, secret-path denial, redaction, and scan budgets | Embeddings, vector search, indexing, or a call graph |
| Structured tool results and optional LangChain adapters | A hidden prompt or a prebuilt agent |

## Quick start

PyGrepTool has no required runtime dependencies. Clone the repository, then install it in the Python environment that will host your tools.

```powershell
python -m pip install -e .
pygreptool TODO src --json
pygrep-tool --schema responses --pretty
```

Optional extras:

```powershell
# Git-compatible .gitignore/.pygrepignore matching in the Python backend
python -m pip install -e ".[ignore]"

# LangChain tool adapters only
python -m pip install -e ".[langchain]"

# Runnable OpenAI/LangChain example
python -m pip install -e ".[agent]"
```

### Add tools to your own LangChain agent

PyGrepTool does not create or own an agent. Your application owns the model, prompt, and existing tools; it adds the navigation toolkit.

```python
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from pygreptool import CodeAccessPolicy
from pygreptool.langchain_toolkit import create_pygrep_tools

navigation_tools = create_pygrep_tools(
    workspace_root="/workspace/project",
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

`create_pygrep_tools()` returns `find_files`, `search_code`, and `read_context`. Their descriptions distinguish discovery, content search, and narrow follow-up reads so compact models can select the smallest useful tool. A fixed `find_files → search_code → read_context` sequence is not required: use `read_context` directly when the user already supplied an allowed exact path and line.

To see tool selection and arguments in an application-owned example:

```powershell
python examples\compose_your_own_agent.py --trace "Find where BackendName is defined and cite the line number."
```

The example reads `.env` only to initialize the provider and does not print its values.

## Security model and deployment boundary

With `virtual_mode=True`, `workspace_root` is presented to the agent as `/`:

```text
agent path:  /src/main.py
physical:    /workspace/project/src/main.py
```

The tools reject `..`, `~`, Windows drive/UNC paths, and paths resolving outside `allowed_roots`; symlinks escaping the allowlist are excluded. Virtual-mode error responses hide physical workspace paths and tell the agent to use an existing allowed root or request narrowly scoped host approval—not to retry through path transformations. `CodeAccessPolicy` denies common secret paths such as `.env`, `.git`, `credentials.yml`, and PEM/key files, and redacts secret-looking values in returned lines.

This is defense in depth, not a sandbox. If an agent can execute a shell or receives a broad host-volume mount, it can bypass file-tool policy. Use a read-only workspace mount, no shell/network tool, and a real process boundary for security-sensitive deployments.

The checked-in Docker demo tests that arrangement:

```powershell
docker compose build
docker compose run --rm app
docker compose run --rm sandbox-demo
```

The runtime image installs the built wheel rather than the source checkout. Both Compose services run without runtime network access; the demo mounts only the fixture workspace at `/workspace:ro`.

For a key-free view of the agent access contract, run:

```powershell
python examples\agent_access_contract_demo.py
```

It prints an allowed `BACKEND_MODE` search, a denied private-path request with no leaked fixture marker, and the safe next action returned to the agent.

To watch a real LangChain agent choose the same Tools, run the opt-in live service. Compose passes `OPENAI_API_KEY` from the local environment or `.env` without printing it. This service has outbound network access only because it calls the model provider; its file access remains a read-only `/workspace` fixture mount.

```powershell
docker compose --profile live-agent run --rm agent-live-demo
```

Pass your own question as the final argument. It is sent to the agent; only `/src` and `/docs` remain available through the mounted workspace.

```powershell
docker compose --profile live-agent run --rm agent-live-demo "Find BACKEND_MODE under /src and cite the path and line."
docker compose --profile live-agent run --rm agent-live-demo "Can you inspect /private?"
```

For a testable access claim, add expected paths. The runner then exits non-zero and labels the final answer unverified when the agent did not actually call the required path.

```powershell
docker compose --profile live-agent run --rm agent-live-demo --expect-allowed /src --expect-denied /private "Find BACKEND_MODE under /src, then check whether /private can be searched."
```

## Scope, ignore rules, and scan budgets

For the optional Skill runner, copy the tracked template before customizing a workspace:

```powershell
Copy-Item .pygreptool.example.json .pygreptool.json
```

`.pygreptool.json` is local, trusted configuration and is intentionally Git-ignored. It can define `allowed_roots`, `.gitignore`/`.pygrepignore` handling, deny globs, file-size limits, and search limits. The runner clamps tool requests to that policy, even if a model omits a limit or requests a larger one.

When the host sets `max_files_scanned`, `max_total_bytes_scanned`, or `timeout_ms`, `search_code` uses a deterministic Python scan budget and returns `search_stats`. This lets an agent report incomplete evidence instead of claiming it searched an entire repository.

## Choose the right navigation layer

| Need | Use | Trade-off |
| --- | --- | --- |
| Fast, unrestricted exact-text search in a trusted checkout | `rg` | Fast text search, but no agent-facing scope, policy envelope, or structured follow-up action. |
| Symbol/caller analysis after indexing | CodeGraph | Graph queries are useful, but initialization and index synchronization are required. Scope and secret handling belong to the surrounding sandbox and mount policy. |
| An agent needs filename discovery, exact/regex search, and bounded reads within trusted roots | PyGrepTool | No semantic call graph; in return, no index is needed and results include virtual paths, line evidence, policy denials, and a next safe action. |

The golden set covers four atomic requests and six end-to-end journeys, including service discovery, line-evidence search, minimal context reads, runbook discovery, and a denied private directory. It records expected tool-call counts as a policy-compliant reference plan—not as a claim about a particular model.

```powershell
python scripts\evaluate_navigation.py --iterations 7
python scripts\evaluate_navigation.py --iterations 7 --with-codegraph
```

The report separates in-process dispatch, Skill command startup, and CodeGraph's indexed symbol/caller queries. Results depend on the environment and repository size; they are reproducible costs, not a universal performance claim. See the [evaluation report](docs/navigation-evaluation.md) for questions, methodology, and reproduction steps.

## Optional agent Skill

The package stays framework-neutral. The separate [`skills/pygreptool-navigation`](skills/pygreptool-navigation) folder is not included in the wheel. It supplies situation-based tool-selection guidance plus a policy-bound Python runner. Install the package, then copy that folder into the relevant agent's skill directory.

## Use the handlers without LangChain

Handlers accept JSON-compatible input and return a stable envelope containing `ok`, `summary`, `count`, `results`, `next_step`, and `error`.

```python
from pygreptool import CodeAccessPolicy, run_search_tool

result = run_search_tool(
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

Use `get_openai_responses_*_tool_schema()` or `get_openai_chat_*_tool_schema()` to generate the current OpenAI schema from the installed package. Schema JSON is not duplicated as checked-in files.

## Packaging options

### Build and install a wheel

```powershell
python -m pip install --upgrade build
python -m build
python -m pip install --force-reinstall .\dist\pygreptool-0.2.0-py3-none-any.whl
```

The build produces a universal pure-Python wheel and an sdist. For a GitHub-first release, attach both artifacts to a GitHub Release; publish the same verified artifacts to PyPI later once the public package name and release process are stable.

### Single-file option

For a small internal script, copy [`standalone/pygrep_tool.py`](standalone/pygrep_tool.py). It has no package or external-command dependency.

```powershell
Copy-Item standalone\pygrep_tool.py .\pygrep_tool.py
python pygrep_tool.py TODO src tests --include "*.py"
```

Use the package when you need policy controls, virtual paths, OpenAI schemas, or LangChain integration.

## Repository layout

```text
src/pygreptool/             # package implementation
  backends/                 # rg, grep, and pure-Python implementations
  file_tool.py              # find_files schema and handler
  tool.py                   # search_code/read_context schemas and handlers
  runtime_scope.py          # workspace and allowlist resolution
  path_policy.py            # physical-to-virtual path mapping
  security_policy.py        # deny, redact, and audit policy
  langchain_toolkit.py      # composable read-only toolkit
skills/pygreptool-navigation/ # optional agent skill, outside the wheel
standalone/pygrep_tool.py   # dependency-free single-file variant
examples/                   # direct navigation, composition, and Docker demo
tests/                      # deterministic, policy, adapter, and live-agent tests
```

## Verify locally

```powershell
# Deterministic suite; no API key or network required
python -m pip install -e ".[dev,langchain]"
python -m pytest

# Optional live tool-selection tests; requires OPENAI_API_KEY in .env
python -m pip install -e ".[agent]"
python -m pytest -m live_agent
```

The live tests use the key only to initialize the provider and never log its value.

## License

[MIT](LICENSE)
