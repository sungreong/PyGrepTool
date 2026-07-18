# PyGrepTool

> Read-only, evidence-oriented file navigation tools for agents in a scoped workspace.

[한국어](README.ko.md)

PyGrepTool helps an agent find candidate files, search exact code or document text, and read only the needed lines. It returns file paths, line numbers, and bounded context without requiring a vector database or index.

It is designed to run **inside** a real isolation boundary such as Docker, a VM, or a remote workspace. Its own policy layer narrows what the file tools can disclose; it is not a replacement for a sandbox.

## Why this exists

General file-management toolkits expose broad filesystem operations. In a code-navigation agent, the useful surface is smaller:

- `find_files` for folders, filename fragments, and extensions
- `search_code` for exact text or regular expressions inside files
- `read_context` for a focused, line-bounded follow-up read

The package keeps that surface read-only, produces structured results for people and agents, and applies an allowlist, virtual paths, secret-file denial, redaction, and optional audit events.

## What it is—and is not

| PyGrepTool provides | PyGrepTool does not provide |
| --- | --- |
| `rg → grep → Python` search fallback | A Docker/VM/process sandbox |
| `allowed_roots` and virtual-path guardrails | Shell, write, delete, move, or network tools |
| `find_files → search_code → read_context` navigation | Vector search, embeddings, or indexing |
| OpenAI-compatible schemas and optional LangChain tools | A prebuilt agent or hidden model prompt |

If a process can execute shell commands or access host volumes broadly, it can bypass file-tool path policy. Mount only the intended workspace into a sandbox and give the agent only the tools it needs.

## Install

PyGrepTool has no required runtime dependencies.

### From a checkout

```powershell
python -m pip install -e .
pygreptool TODO src --json
pygrep-tool --schema responses --pretty
```

Optional extras:

```powershell
# .gitignore-compatible filtering in the Python backend
python -m pip install -e ".[ignore]"

# LangChain tool adapters (no model provider)
python -m pip install -e ".[langchain]"

# Runnable OpenAI/LangChain example
python -m pip install -e ".[agent]"
```

### Build and install a wheel

This repository is wheel-ready. Build artifacts are intentionally ignored by Git.

```powershell
python -m pip install --upgrade build
python -m build
python -m pip install --force-reinstall .\dist\pygreptool-0.2.0-py3-none-any.whl
```

`dist/` will contain a universal pure-Python wheel and an sdist. For a GitHub-first release, attach both files to the GitHub Release and let users install the wheel file directly. Publish the same verified artifacts to PyPI later only when a stable public package name and release process are ready.

### Single-file option

For a small internal script, copy only [`standalone/pygrep_tool.py`](standalone/pygrep_tool.py). It has no package or external-command dependency.

```powershell
Copy-Item standalone\pygrep_tool.py .\pygrep_tool.py
python pygrep_tool.py TODO src tests --include "*.py"
```

Use the wheel/package for policy controls, virtual paths, OpenAI schemas, and LangChain integration.

## Add tools to your own agent

PyGrepTool deliberately does not create or own an agent. The application owns the model, prompt, and other tools; it adds this read-only toolkit.

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

`create_pygrep_tools()` returns tools in this order: `find_files`, `search_code`, `read_context`. The descriptions explicitly distinguish their roles so compact models can choose a focused tool. `search_code` returns compact match locations by default; every match contains `read_context_args` for a wider follow-up read.

The toolkit does not require a fixed `find_files → search_code → read_context` sequence. Use `read_context` directly when the user supplied an exact allowed path and line; otherwise start with the smallest tool that answers the question.

Run the complete application-owned example after installing the `agent` extra. It reads `.env` without printing its values.

```powershell
python examples\compose_your_own_agent.py "Find Python service files under /src."
python examples\compose_your_own_agent.py --trace "Find where BackendName is defined and cite the line number."
```

`--trace` prints the model-selected tool name, arguments, and a compact result summary. The default output prints only the final answer.

## Optional agent skill

The package remains framework-neutral. A separate, installable agent skill lives in
[`skills/pygreptool-navigation`](skills/pygreptool-navigation); it is not included in the wheel.
It provides situation-based tool selection, a config-bound Python runner, and requirements for
virtual paths, allowlists, custom ignore files, and policy denial. Install the package first,
then copy that folder into the relevant agent's skill directory.

## Choosing a navigation layer

These tools solve different questions, so raw query latency alone is not a useful ranking.

| Need | Use | Trade-off |
| --- | --- | --- |
| Fast, unrestricted exact-text search in a trusted checkout | `rg` | It returns text, but has no agent-facing virtual paths, policy envelope, or structured follow-up action. |
| Symbol lookup, callers/callees, or impact analysis after indexing | CodeGraph | Its index enables semantic graph queries, but requires initialization and synchronization. Scope and secret handling must be enforced by the surrounding sandbox and mount policy. |
| An agent needs filename/extension search, exact or regex search, and bounded reads inside trusted roots | PyGrepTool or the optional Skill | It does not infer a call graph; in return it needs no index and returns virtual paths, line evidence, policy denials, and an explicit next safe action. |

The checked-in golden set validates four atomic requests and six end-to-end navigation journeys: locate service files, locate a backend setting with line evidence, read minimal context after discovery, find a runbook, and reject a private directory. Each journey records its expected tool-call count, so the report shows both answer correctness and the calls needed to obtain the evidence. Run it with measured medians:

```powershell
python scripts\evaluate_navigation.py --iterations 7
python scripts\evaluate_navigation.py --iterations 7 --with-codegraph
```

The journey counts are a policy-compliant reference plan, not a claim about a particular LLM's behavior. The report separates direct in-process dispatch from Skill-command startup, and only measures CodeGraph for symbol/caller questions it is designed to answer. `--with-codegraph` initializes a local, Git-ignored index when needed. The numbers are environment- and repository-size-dependent; they illustrate process startup, policy validation, and indexed semantic-query costs—not a universal performance claim.

See [the complete Korean evaluation report](docs/navigation-evaluation.md) for the golden questions, tool-call journeys, measured results, comparison boundaries, and reproduction steps.

## Use the tools without LangChain

The handlers accept a JSON-compatible object and return a stable envelope with `ok`, `summary`, `count`, `results`, `next_step`, and `error`.

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

Use `get_openai_responses_*_tool_schema()` or `get_openai_chat_*_tool_schema()` to generate the current OpenAI schema from the installed package. Schema JSON is not duplicated as checked-in files.

### Bound large searches

`search_code` can enforce a deterministic Python scan budget when the host sets any of `max_files_scanned`, `max_total_bytes_scanned`, or `timeout_ms`. Its response then includes `search_stats`, allowing the agent to state that evidence is incomplete rather than claiming the entire repository was searched.

For the separate Skill runner, put these limits in the trusted `.pygreptool.json` policy. The runner clamps a model request to those limits, including when the model omits a limit or asks for a larger one.
Copy `.pygreptool.example.json` to `.pygreptool.json` before customizing it for a workspace; the live config is intentionally Git-ignored.

## Security model

With `virtual_mode=True`, `workspace_root` becomes the agent-visible `/`:

```text
agent path:  /src/main.py
physical:    /workspace/project/src/main.py
```

The tool rejects `..`, `~`, Windows drive/UNC paths, and results that resolve outside `allowed_roots`; it also excludes symlinks escaping the allowlist. In `virtual_mode=True`, failure responses likewise hide physical workspace paths. `CodeAccessPolicy` denies common secret paths such as `.env`, `.git`, PEM/key files and redacts secret-looking content from returned lines.

That is a tool-level defense-in-depth layer, not OS isolation. For real boundaries, use a read-only mounted workspace and no shell/network tool. The Docker demo exercises exactly that arrangement:

```powershell
docker compose build
docker compose run --rm app
docker compose run --rm sandbox-demo
```

Both services run with no runtime network. The demo mounts only `tests/fixtures/agent_sample_project` at `/workspace:ro` and exposes virtual paths such as `/src/alpha_service.py`.

## Repository layout

```text
src/pygreptool/
  core.py                 # normalized search API and context reads
  backends/               # rg, grep, and pure-Python implementations
  file_discovery.py       # filename/extension discovery
  file_tool.py            # find_files schema and handler
  tool.py                 # search_code/read_context schemas and handlers
  runtime_scope.py        # shared workspace and allowlist resolution
  path_policy.py          # physical-to-virtual path mapping
  security_policy.py      # deny, redact, and audit policy
  langchain_tool.py       # individual LangChain adapters
  langchain_toolkit.py    # composable read-only toolkit
  cli.py, tool_cli.py     # human CLI and JSON tool CLI
standalone/pygrep_tool.py # dependency-free single-file variant
examples/                 # direct navigation, agent composition, Docker demo
tests/                    # deterministic, policy, adapter, and live-agent tests
```

Every module in `src/pygreptool` has one runtime responsibility. `__pycache__/` and `pygreptool.egg-info/` may appear locally after running Python or installing editable mode, but `.gitignore` prevents them from being published.

## Verify locally

```powershell
# deterministic test suite; no API key or network required
python -m pip install -e ".[dev,langchain]"
python -m pytest

# optional live tool-selection evaluation; requires .env OPENAI_API_KEY
python -m pip install -e ".[agent]"
python -m pytest -m live_agent
```

The live tests load the key only to initialize the provider and never log its value.

## License

[MIT](LICENSE)
