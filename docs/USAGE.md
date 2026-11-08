# Usage guide

## Install from GitHub

```sh
git clone https://github.com/kvianAR/change-impact-investigator.git
cd change-impact-investigator
uv sync --all-extras --no-editable
source .venv/bin/activate
change-impact --help
```

The activation command above is for macOS and Linux. A Python 3.11+ virtual environment with `python -m pip install '.[dev,mcp,demo]'` also works.

For the TypeScript backend, install Node.js 20+ and run `npm ci --ignore-scripts` in the tool checkout. A separately installed package can use a trusted global `tsc`, or an absolute `CHANGE_IMPACT_TYPESCRIPT_PATH` pointing to `typescript/lib/typescript.js`. The analyzer does not automatically execute a compiler package from an inspected repository.

## Select TypeScript or a mixed repository

```sh
change-impact index --repo /absolute/repository --language typescript
change-impact trace-callers --repo /absolute/repository --language typescript --symbol src/validators.ts:validateOrder
change-impact related-tests --repo /absolute/repository --language typescript --symbol src/validators.ts:validateOrder
change-impact inspect-change-impact --repo /absolute/repository --language auto
```

Python is the default backend. TypeScript symbol modules use repository-relative filenames including extensions. `auto` combines both language graphs. A snapshot records the chosen backend, and comparison reuses that choice automatically.

## Investigate one function

```sh
change-impact trace-callers --repo /absolute/repository --symbol package.validators:validate_order
change-impact related-tests --repo /absolute/repository --symbol package.validators:validate_order
change-impact inspect-change-impact --repo /absolute/repository --symbol package.validators:validate_order
```

A unique short name also works. Ambiguous names return the qualified choices. Each call edge contains its call-site file/line and target definition file/line. Imported aliases include separate import evidence.

## Investigate the current diff

```sh
change-impact inspect-change-impact --repo /absolute/repository
change-impact inspect-change-impact --repo /absolute/repository --base main --depth 12
```

The default base is HEAD. Both staged and unstaged tracked edits are compared with that revision. Untracked source files for the selected backend are included. A repository without its first commit is supported. Unsupported changes appear separately. TypeScript configuration and package changes conservatively affect TypeScript symbols. Deleted files retain base-revision evidence, including historical compiler configuration. Parse failures appear in diagnostics.

Caller traversal defaults to eight levels for impact reports and stops at 500 paths per symbol. Set depth from 1 through 32. Check truncation flags before treating a result as complete.

## Compare before and after

```sh
change-impact baseline --repo /absolute/repository --symbol package.validators:validate_order
# Edit code after saving the returned identifier.
change-impact compare --repo /absolute/repository --baseline-id YOUR_BASELINE_ID
```

`symbol_source_changed` compares the parsed symbol structure, so whitespace and line movement preserve identity. `source_file_changed` compares the whole file. Connection additions and removals include source evidence. Renaming or moving a symbol to another module changes its identity. Older snapshots without source fingerprints return null for unavailable source comparisons.

Snapshots contain repository identifiers and evidence. Keep `.impact-cache/` out of version control. The analyzer excludes that directory from its own change reports.

The cache creates its own `.gitignore` and owner-only directory permissions. It stores source syntax trees and graph evidence. `change-impact index` reports reuse counters. Python invalidates edited files individually. TypeScript invalidates the project result when source, configuration, compiler, dependency inputs, or previously missing resolution paths change. Set `CHANGE_IMPACT_CACHE=off` for an uncached investigation.

## Local AI

Start Ollama and make the chosen model available before running a summary. Once downloaded, local inference works without internet access.

```sh
ollama list
change-impact summarize --repo /absolute/repository --symbol validate_order --provider ollama --model qwen3.5:2b-q4_K_M
```

Local requests go to `http://127.0.0.1:11434/api/generate`. The project does not bundle model weights. Specify a model suited to the available memory.

## Online AI

Install the panel extra with `pip install '.[panel]'`, then run `change-impact models`. Select OpenRouter, OpenAI, Ollama, or Custom API. Browse provider models or enter a manual model ID. Save the provider key and choose **Save & activate**. Use **Connections** to replace a key later. Empty key fields preserve saved credentials. Keys are shared across profiles for the selected provider and stored in the system keychain. Custom API uses one shared endpoint.

```sh
# Uses the active saved model, including from MCP summarize_impact.
change-impact summarize --repo /absolute/repository --symbol validate_order

# Explicit selection with OPENROUTER_API_KEY in the environment.
change-impact summarize --repo /absolute/repository --symbol validate_order --provider openrouter --model vendor/model-name

# OpenAI remains available with OPENAI_API_KEY.
change-impact summarize --repo /absolute/repository --symbol validate_order --provider openai --model gpt-4.1-mini
```

OpenRouter and Custom API use Chat Completions. OpenAI uses Responses. Provider pricing applies. Remote summaries send bounded report evidence. Summaries include their provider, model, scope omissions, and the full original evidence report. Core analysis works with no API key. If the system keychain is unavailable, environment keys remain supported. The loopback panel defaults to port 8765. Use `--no-browser` or `--port` as needed.

## Connect an MCP client

Configure a stdio server using the Python interpreter from the installed environment.

```json
{
  "mcpServers": {
    "change-impact": {
      "command": "/absolute/path/to/change-impact-investigator/.venv/bin/python",
      "args": ["-m", "change_impact.server"],
      "env": {
        "CHANGE_IMPACT_TYPESCRIPT_PATH": "/absolute/path/to/change-impact-investigator/node_modules/typescript/lib/typescript.js"
      }
    }
  }
}
```

Restart or reconnect the MCP client after changing its configuration. Supply the absolute repository path in tool requests. Online summaries also require the server process to inherit `OPENAI_API_KEY`.

The seven tools are `index_repository`, `trace_callers`, `inspect_change_impact`, `find_related_tests`, `create_impact_baseline`, `compare_impact`, and `summarize_impact`. Supply `language="typescript"` or `language="auto"` when needed.

Codex also supports registration through `codex mcp add`. Use the absolute interpreter and compiler paths from the configuration above. Reconnect the client after configuration. This follows the [official OpenAI MCP documentation](https://developers.openai.com/codex/mcp/).

From the tool checkout, these commands add the server to the user's Codex profile and show its configuration.

```sh
codex mcp add change-impact-investigator \
  --env "CHANGE_IMPACT_TYPESCRIPT_PATH=$PWD/node_modules/typescript/lib/typescript.js" \
  -- "$PWD/.venv/bin/python" -m change_impact.server
codex mcp get change-impact-investigator --json
```

Start a new chat or reconnect after registration. Large initial indexes can exceed one minute. Configure the client's request timeout for the repository size, or prewarm the index from the CLI.

## Run the demo and checks

```sh
python scripts/run_demo.py
python -m pytest -q
ruff check .
ruff format --check .
npm test
```

The demo creates a separate Git repository, edits the shared validator, then adds `/orders/express`. Its report contains two initially affected routes, four related tests, a source-change comparison, and the new route connection. The original examples remain available for repeated inspection.

The TypeScript example uses Node.js 22.18+ type stripping and an actual Express server. Its native Node tests cover valid/invalid quantities and HTTP responses. Inspect `examples/typescript_shop/validators.ts:validateOrder` with `--language typescript` to find its endpoint and three related tests.
