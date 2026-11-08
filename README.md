# Change Impact Investigator

Trace how a Python code change may affect callers, imports, mounted FastAPI endpoints, and pytest tests. Every connection carries source references. Save an investigation before editing, then compare source changes and graph changes afterward.

Version 0.1 supports Python with optional local Ollama or online OpenAI summaries. See [the usage guide](docs/USAGE.md), [analysis design](docs/ARCHITECTURE.md), and [verification record](VALIDATION.md).

## Quick start

Python 3.11+ and Git are required. Install locally with `pip install .` or with MCP support using `pip install '.[mcp]'`.

For a complete development environment with uv, run `uv sync --all-extras --no-editable`. Activate `.venv`, then use the commands below.

```sh
change-impact trace-callers --repo /path/to/repo --symbol package.validators:validate_order
change-impact related-tests --repo /path/to/repo --symbol package.validators:validate_order
change-impact inspect-change-impact --repo /path/to/repo
change-impact inspect-change-impact --repo /path/to/repo --base main --depth 12
```

For an MCP client, configure a stdio server with command `change-impact-mcp`. Its tools accept an absolute `repo` path. Source analysis reads files without importing or executing project code. Git impact compares tracked staged and unstaged changes with `HEAD` and includes untracked Python files.

## Before and after comparison

```sh
change-impact baseline --repo /path/to/repo --symbol package.validators:validate_order
# Save the returned baseline_id, edit code, then compare.
change-impact compare --repo /path/to/repo --baseline-id BASELINE_ID
```

Snapshots live in `.impact-cache/` inside the inspected repository. Add that directory to the repository's `.gitignore`. Comparison reports source changes and added/removed callers, routes, imports, tests, and dynamic calls. Named symbol identities survive line movement. Removed connections retain their earlier source references.

## Optional AI

Repository investigation runs locally. Summary generation is optional and selected for each request.

```sh
# Local Ollama. Install Ollama and pull the chosen model first.
change-impact summarize --repo /path/to/repo --symbol validate_order --provider ollama --model qwen3.5:2b-q4_K_M

# Online OpenAI. Set OPENAI_API_KEY in the environment first.
change-impact summarize --repo /path/to/repo --symbol validate_order --provider openai --model gpt-4.1-mini
```

Ollama uses `http://127.0.0.1:11434`. OpenAI uses the Responses API and incurs provider charges. The online option sends a bounded projection of report evidence, including repository paths, symbol names, routes, and test references. `summary_scope` records omissions. API keys stay in the environment. AI output includes the original local evidence report.

## MCP tools

- `trace_callers`
- `inspect_change_impact`
- `find_related_tests`
- `create_impact_baseline`
- `compare_impact`
- `summarize_impact`

## Current limits

Python only. FastAPI support covers literal HTTP route declarations and top-level router mounts, including nested prefixes and aliases. Dynamic, unmounted, and reassigned routers produce diagnostics. Pytest links cover direct calls, fixture parameters, local/conftest fixtures, autouse fixtures, usefixtures markers, and HTTP path candidates.

Runtime dispatch, dependency injection, complex inheritance, monkey patching, and plugin registries can remain unresolved. External installed packages are outside the repository graph. HTTP path matches carry `confidence="candidate"`. Repository-wide unresolved calls have an unknown relationship to the selected symbol. Detailed supported cases and limits appear in the analysis guide.

Call edges include both the call site and target definition. Import evidence records the alias, target, file, line, and lexical scope. Constructor-based method inference is explicitly labeled. Parse failures and duplicate module names appear in diagnostics. Reports include source hashes and traversal truncation flags.

Changes outside functions conservatively mark the module's functions as potentially affected. Deleted functions use source from the selected Git revision and carry `evidence_state="base"`. Current connections carry `evidence_state="working_tree"`.

## Demo

From a repository checkout, install `pip install '.[dev,demo]'`, then run `python -m pytest examples/shop -q`.

```sh
change-impact inspect-change-impact --repo . --symbol examples.shop.validators:validate_order
```

The shared validator reaches `POST /orders` and `POST /orders/preview` through two service functions. Change its quantity limit in `examples/shop/validators.py`, rerun inspection, and run the related demo tests. Baselines let you compare graph changes before and after the edit.

Run `python scripts/run_demo.py` for an isolated, inspectable demo under `.impact-cache/demo`. It changes the validator, adds an endpoint, and saves a complete comparison report. Use `--directory` to choose another location for a repeat run.
