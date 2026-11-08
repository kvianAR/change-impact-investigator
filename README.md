# Change Impact Investigator

Trace how a Python code change may affect callers, FastAPI endpoints, and tests, with file and line evidence. The project is being built in five-step rounds; see [ROADMAP.md](ROADMAP.md) for scope and limits.

## Quick start

Python 3.11+ is required. Install locally with `pip install .` or with MCP support using `pip install '.[mcp]'`.

```sh
change-impact trace-callers --repo /path/to/repo --symbol package.validators:validate_order
change-impact related-tests --repo /path/to/repo --symbol package.validators:validate_order
change-impact inspect-change-impact --repo /path/to/repo
```

For an MCP client, configure a stdio server with command `change-impact-mcp`. Its tools accept an absolute `repo` path. Source analysis reads files without importing or executing project code. Git impact compares tracked staged and unstaged changes with `HEAD` and includes untracked Python files.

## Before and after comparison

```sh
change-impact baseline --repo /path/to/repo --symbol package.validators:validate_order
# Save the returned baseline_id, edit code, then compare.
change-impact compare --repo /path/to/repo --baseline-id BASELINE_ID
```

Snapshots live in `.impact-cache/` inside the inspected repository. Add that directory to the repository's `.gitignore`. Comparison ignores line movement and reports added/removed callers, routes, tests, and dynamic calls. Removed connections retain their earlier source references.

## Optional AI

Repository investigation runs locally. Summary generation is optional and selected for each request.

```sh
# Local Ollama. Install Ollama and pull the chosen model first.
change-impact summarize --repo /path/to/repo --symbol validate_order --provider ollama --model qwen3.5:2b-q4_K_M

# Online OpenAI. Set OPENAI_API_KEY in the environment first.
change-impact summarize --repo /path/to/repo --symbol validate_order --provider openai --model gpt-4.1-mini
```

Ollama uses `http://127.0.0.1:11434`. OpenAI uses the Responses API and incurs provider charges. The online option sends the structured impact report, including repository paths and call expressions, to OpenAI. API keys stay in the environment. AI output is labeled separately and includes the original evidence report.

## MCP tools

- `trace_callers`
- `inspect_change_impact`
- `find_related_tests`
- `create_impact_baseline`
- `compare_impact`
- `summarize_impact`

## Current limits

Python only. FastAPI route support covers literal paths and basic `FastAPI`/`APIRouter` registration. Calls through runtime dispatch, dependency injection, complex inheritance, and plugin registries can remain unresolved. Test discovery supports direct calls and literal HTTP client calls. Treat results as evidence for investigation, not proof of runtime behavior.
