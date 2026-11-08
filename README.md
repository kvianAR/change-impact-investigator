# Change Impact Investigator

Trace how Python or TypeScript changes may affect callers, imports, API endpoints, and tests. Every connection carries source references. Save an investigation before editing, then compare source changes and graph changes afterward.

Version 0.3 adds a local Models panel, OpenRouter, custom OpenAI-compatible endpoints, secure provider keys, and active model profiles. Version 0.2 introduced persistent incremental indexes, Python C3 inheritance and typed receivers, FastAPI dependencies/factories, Flask/Django adapters, and TypeScript compiler analysis with Express and test links. See [the usage guide](docs/USAGE.md), [advanced analysis](docs/ADVANCED.md), [pinned benchmarks](benchmarks/README.md), and [verification record](VALIDATION.md).

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

Repository investigation runs locally. AI summaries are optional. Open the local Models panel to configure the provider and model used by CLI and MCP summaries.

```sh
pip install '.[panel,mcp]'
change-impact models
# Headless use or a different local port
change-impact models --no-browser --port 8765
```

Open **Models**, choose **Add model**, select a provider, browse its catalog or enter an exact model ID, enter its API key, and select **Save & activate**. Save more profiles and use **Make active** to switch. **Connections** lets you update a provider key. An empty key field preserves the existing key. Keys and endpoints are shared by all profiles for that provider. Custom API supports one shared OpenAI-compatible endpoint. Display names and output limits are per model.

Supported providers are **OpenRouter**, **OpenAI**, **Ollama**, and **Custom API**. Ollama requires a running local installation with the selected model already pulled. OpenRouter models use their full provider/model IDs. A manual ID can be saved even when the provider catalog is unavailable. **Test model** sends a short prompt to that provider and may incur charges.

API keys entered in the panel go into the operating-system keychain. The panel requires a supported unlocked macOS, Windows, SecretService, or KWallet backend. If secure storage is unavailable, use environment keys. Metadata-only settings live outside the repository, under `~/Library/Application Support/ChangeImpactInvestigator` on macOS or the platform configuration directory. `CHANGE_IMPACT_CONFIG_DIR` overrides that directory. The panel binds to `127.0.0.1`, validates Host/Origin, and uses a per-launch API session token.

```sh
# Use the saved active model.
change-impact summarize --repo /path/to/repo --symbol validate_order

# Or explicitly select a provider and model.
# Set OPENROUTER_API_KEY in the environment before this command.
change-impact summarize --repo /path/to/repo --symbol validate_order --provider openrouter --model vendor/model-name

# Local Ollama
change-impact summarize --repo /path/to/repo --symbol validate_order --provider ollama --model qwen3.5:2b-q4_K_M

# OpenAI remains supported with OPENAI_API_KEY.
change-impact summarize --repo /path/to/repo --symbol validate_order --provider openai --model gpt-4.1-mini
```

Custom API accepts an HTTPS base URL and an optional key, with `CHANGE_IMPACT_CUSTOM_API_KEY` as its environment fallback. HTTP endpoints are supported on loopback. OpenRouter and Custom API use Chat Completions. OpenAI uses the Responses API. Remote summaries send a bounded projection of evidence, including repository paths, symbol names, routes, and test references. `summary_scope` records omissions. AI output includes the original local evidence report.

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
