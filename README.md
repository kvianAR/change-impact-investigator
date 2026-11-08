# Change Impact Investigator

Trace how Python or TypeScript changes may affect callers, imports, API endpoints, and tests. Every connection carries source references. Save an investigation before editing, then compare source changes and graph changes afterward.

Version 0.2 adds persistent incremental indexes, Python C3 inheritance and typed receivers, FastAPI dependencies/factories, Flask/Django adapters, and TypeScript compiler analysis with Express and test links. See [the usage guide](docs/USAGE.md), [advanced analysis](docs/ADVANCED.md), [pinned benchmarks](benchmarks/README.md), and [verification record](VALIDATION.md).

## Quick start

Python 3.11+ and Git are required. Install locally with `pip install .` or with MCP support using `pip install '.[mcp]'`.

For a complete development environment with uv, run `uv sync --all-extras --no-editable`. Activate `.venv`, then use the commands below.

For TypeScript, also run `npm ci --ignore-scripts` in the tool checkout. The backend requires Node.js 20+ and a trusted TypeScript compiler. The runnable TypeScript example uses Node.js 22.18+.

```sh
change-impact trace-callers --repo /path/to/repo --symbol package.validators:validate_order
change-impact related-tests --repo /path/to/repo --symbol package.validators:validate_order
change-impact inspect-change-impact --repo /path/to/repo
change-impact inspect-change-impact --repo /path/to/repo --base main --depth 12
change-impact index --repo /path/to/repo
change-impact trace-callers --repo /path/to/ts-repo --language typescript --symbol src/validators.ts:validateOrder
change-impact inspect-change-impact --repo /path/to/mixed-repo --language auto
```

For an MCP client, configure a stdio server with command `change-impact-mcp`. Tools accept an absolute `repo` path and a `language` argument. Python is the default. `auto` combines Python and TypeScript graphs. Source analysis reads files without importing or executing project code. Git impact includes staged, unstaged, untracked, and deleted source files.

## Before and after comparison

```sh
change-impact baseline --repo /path/to/repo --symbol package.validators:validate_order
# Save the returned baseline_id, edit code, then compare.
change-impact compare --repo /path/to/repo --baseline-id BASELINE_ID
```

Snapshots and source indexes live in `.impact-cache/` inside the inspected repository. The cache creates its own ignore file and private directory permissions. Comparison reports source changes and added/removed callers, routes, imports, tests, and dynamic calls. Named symbols and named tests retain identity across line movement. Baselines remember their language. Removed connections retain their earlier source references.

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

- `index_repository`
- `trace_callers`
- `inspect_change_impact`
- `find_related_tests`
- `create_impact_baseline`
- `compare_impact`
- `summarize_impact`

## Current limits

FastAPI, Flask, Django, and Express adapters inspect supported static registrations and application factories. Python links include explicit FastAPI dependency providers and pytest fixture relationships. TypeScript links use the compiler checker and recognize test/it callbacks, Express routes/middleware, and literal HTTP request candidates.

Runtime dispatch, external base classes, complex factories, monkey patching, and plugin registries can require manual review. HTTP path matches carry `confidence="candidate"`. Repository-wide unresolved calls have an unknown relationship to the selected symbol. The advanced guide documents supported registrations and remaining static-analysis limits.

Call edges include both the call site and target definition. Import evidence records the alias, target, file, line, and lexical scope. Constructor-based method inference is explicitly labeled. Parse failures and duplicate module names appear in diagnostics. Reports include source hashes and traversal truncation flags.

Changes outside functions conservatively mark the module's functions as potentially affected. Deleted functions use source from the selected Git revision and carry `evidence_state="base"`. Current connections carry `evidence_state="working_tree"`.

## Demo

From a repository checkout, install `pip install '.[dev,demo]'`, then run `python -m pytest examples/shop -q`.

```sh
change-impact inspect-change-impact --repo . --symbol examples.shop.validators:validate_order
```

The shared validator reaches `POST /orders` and `POST /orders/preview` through two service functions. Change its quantity limit in `examples/shop/validators.py`, rerun inspection, and run the related demo tests. Baselines let you compare graph changes before and after the edit.

Run `python scripts/run_demo.py` for an isolated, inspectable demo under `.impact-cache/demo`. It changes the validator, adds an endpoint, and saves a complete comparison report. Use `--directory` to choose another location for a repeat run.

Run `npm test` for three executable TypeScript tests against an actual Express server, then inspect the example.

```sh
change-impact inspect-change-impact --repo . --language typescript --symbol examples/typescript_shop/validators.ts:validateOrder
```

Python indexes reuse unchanged files. TypeScript reuses a complete compiler result while project inputs remain unchanged and rebuilds the program after edits. `index_stats` exposes reuse. Set `CHANGE_IMPACT_CACHE=off` to disable persistence.
