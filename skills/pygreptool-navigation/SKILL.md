---
name: pygreptool-navigation
description: Use an installed PyGrepTool runtime for scoped, read-only code navigation with virtual paths and line-level evidence. Use when locating local files by name or extension, finding exact code or documentation text, inspecting a bounded file context, or answering repository questions with citations. Select find_files, search_code, or read_context according to the question; do not use a fixed tool sequence.
---

# PyGrepTool Navigation

Copy this skill folder by itself for a zero-dependency Python runner, or install `pygreptool` to upgrade the same runner automatically. The Skill keeps one request protocol in both modes.

## Mandatory command boundary

Use the bundled `scripts/invoke_pygreptool.py` runner as the **only** command that inspects the configured workspace. Do not use `find`, `ls`, `dir`, `Get-ChildItem`, `rg`, `grep`, `cat`, `type`, or ad-hoc Python to discover files or read their contents.

The runner invocation may be launched through the host shell, but the runner must be the only program that reads the workspace. Without `--config`, the runner treats its current directory as the virtual `/` and allows only that directory tree. Do not scan to find a config file.

For an untrusted agent, do not expose this runner as a general shell command. The host must create a policy-bound dispatcher with its reviewed config and expose only that dispatcher as the agent tool. A model must never choose a different `--config` path.

When a result reports `config_mode: "default_current_directory"`, tell the user that the temporary default is active. Ask whether they want a persistent `.pygreptool.json` and a `.pygrepignore` template. Create them only after the user explicitly agrees or provides the allowed roots/ignore requirements.

## Requirements

- Python 3.10 or newer.
- No package is required for standalone mode. It uses pure Python search, virtual paths, allowlists, basic deny rules, and simple glob-style ignore patterns.
- Install `pygreptool` to use package mode: `rg → grep → Python` fallback, bounded context envelopes, full redaction policy, and Git-compatible ignore handling when `pathspec` is also installed.
- Install `pathspec` only when package mode needs Git-compatible `.gitignore` or `.pygrepignore` matching:

  ```powershell
  python -m pip install "pathspec>=0.12,<1.1"
  ```

- `rg` is optional and improves large-repository search speed. The runtime falls back to `grep`, then pure Python when it is unavailable.
- For untrusted agent input, run inside a sandbox/VM/container and mount only the intended workspace read-only. The runner is a tool-level guardrail, not an operating-system sandbox.

## Project configuration

Configuration is optional. By default, the runner uses the current directory as its workspace, allows only `.` (agent-visible `/`), respects `.gitignore`/`.pygrepignore`, and applies the built-in secret deny rules. Run the agent from the intended repository root or sandbox workspace.

Create `.pygreptool.json` only when the default workspace is too broad or when custom ignore/deny limits are needed. Treat it as trusted configuration: do not let the agent edit it or override its policy values in a request.

```json
{
  "allowed_roots": ["src", "tests", "docs"],
  "ignore_files": [".gitignore", ".pygrepignore"],
  "respect_ignore": true,
  "policy": {
    "deny_globs": ["private/**", "**/*.p12"],
    "max_file_size_bytes": 2097152,
    "max_files_scanned": 5000,
    "max_total_bytes_scanned": 52428800,
    "timeout_ms": 10000
  }
}
```

`allowed_roots` replaces the default `.` and is the hard access boundary. `ignore_files` only improves search relevance; it never grants access. The runner always applies deny rules for `.env`, `.git`, PEM/key files, and private-key names.

`max_files_scanned`, `max_total_bytes_scanned`, and `timeout_ms` are optional host-owned search budgets. When set in trusted config, the runner applies them even if an agent omits them or asks for a larger value. Budgeted searches use the deterministic Python backend and return `search_stats` so an agent can report incomplete evidence instead of pretending the entire workspace was searched.

## Quick start

Copy `pygreptool-navigation` into your agent's skill directory, then run the bundled script from the target repository root. The Skill works without package installation.

```powershell
$skill = "$HOME\.codex\skills\pygreptool-navigation"
@'
{"tool":"find_files","arguments":{"folder":"/src","name_query":"service","extensions":["py"],"max_results":20,"hidden":false}}
'@ | python "$skill\scripts\invoke_pygreptool.py" --pretty
```

Add `--config .pygreptool.json` only when the project needs a narrower `allowed_roots` list or custom policy. Install `pygreptool` in the same Python environment when package mode is desired; no command-line switch is necessary.

### Host-bound integration

For a real agent runtime, load the reviewed configuration once and pass only JSON tool requests to the returned callable. This prevents normal tool calls from changing workspace, allowed roots, ignore files, or policy.

```python
from pathlib import Path
from invoke_pygreptool import create_policy_bound_dispatcher

dispatch = create_policy_bound_dispatcher(Path("/workspace/project/.pygreptool.json"))
result = dispatch(
    {
        "tool": "search_code",
        "arguments": {"pattern": "DATABASE_URL", "roots": ["/src"], "regex": False},
    }
)
```

This is still not an OS sandbox. Run it in a container/VM with only the intended workspace mounted read-only and do not give the agent shell access.

## Create persistent scope only with user approval

After the user approves, create a default config and optional custom-ignore template from the repository root:

```powershell
python "$skill\scripts\invoke_pygreptool.py" --init-config --init-ignore --pretty
```

When the user names the only folders the agent may inspect, pass each one explicitly:

```powershell
python "$skill\scripts\invoke_pygreptool.py" --init-config --init-ignore --allowed-root src --allowed-root docs --pretty
```

Never overwrite an existing config or ignore file. `.gitignore` is a general project ignore file; `.pygrepignore` is only for agent-search noise such as generated files, build output, or large snapshots. Before adding ignore patterns, ask the user which paths should be excluded.

## Select the minimal sufficient tool

Do not follow a mandatory `find_files → search_code → read_context` sequence. Use the current question and already-returned evidence.

| Situation | Select | Notes |
| --- | --- | --- |
| Folder, filename fragment, or extension request | `find_files` | Do not search file contents. |
| Symbol, error text, configuration key, TODO, import, regular expression, or “string inside `src`” | `search_code` | Use `/src` directly when the user named `src`; do not first check whether it exists. |
| More surrounding lines are required for an already-known result | `read_context` | Prefer a result's `read_context_args`. |
| Existing tool result already answers the question | No tool | Cite the returned path and line. |

Prefer the smallest permitted scope, compact `search_code` results (`include_context: false`), and one focused follow-up only when the existing result is insufficient.

## Run one selected tool

Pass exactly one `tool` and its tool-specific `arguments` to the runner. The runner obtains workspace scope, virtual mode, ignore files, and policy exclusively from `.pygreptool.json`.

```powershell
@'
{
  "tool": "search_code",
  "arguments": {
    "pattern": "DATABASE_URL",
    "roots": ["/src"],
    "regex": false,
    "include": ["*.py"],
    "max_results": 20,
    "include_context": false
  }
}
'@ | python /path/to/pygreptool-navigation/scripts/invoke_pygreptool.py --config .pygreptool.json --pretty
```

The three accepted tool names are `find_files`, `search_code`, and `read_context`. The runner emits one JSON result and exits nonzero when configuration or the selected tool request is rejected.

## Safety and answer quality

- Use only virtual paths returned by the runner.
- `find_files` is a PyGrepTool request, not permission to call the shell `find` command.
- Never put `workspace_root`, `allowed_roots`, policy fields, ignore settings, or a config path in a tool request.
- Do not attempt `..`, home-directory, drive, UNC, shell, or arbitrary-Python workarounds.
- Treat policy denial as final unless a human changes the trusted config.
- Cite returned file paths and line numbers. Do not claim a file was inspected when the runner did not return it.
- Keep final answers concise; report when search scope, result limits, or redaction affect the evidence.
