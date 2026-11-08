# Project roadmap

## Round 1 — completed

1. Repository and package setup.
2. Python symbol and import index with source locations.
3. Direct caller tracing with unresolved dynamic calls.
4. FastAPI route and related pytest discovery.
5. Git diff impact report and MCP tools.

The first three steps were pushed individually. Subsequent work follows one commit and push per round.

## Round 2 — completed

1. Save symbol investigation baselines.
2. Compare callers, routes, tests, and dynamic calls with source evidence.
3. Add local Ollama and online OpenAI summary options.
4. Expose the new capabilities through CLI and MCP.
5. Run round-end regression and provider integration checks.

## Future rounds

- Before/after snapshots and graph comparison.
- Better Python name resolution, framework adapters, and incremental indexing.
- Benchmarks against labeled repositories, then TypeScript support.

Static analysis cannot prove all runtime behavior. Reports must separate resolved links from candidates and unresolved dynamic calls.

## Round 3 — completed

1. Resolve lexical scopes, local imports, re-exports, methods, and constructor-created instances.
2. Inspect current and historical Git source for deleted symbols and module-level edits.
3. Report parse diagnostics, source hashes, traversal limits, and import evidence.
4. Add an executable FastAPI demo, MCP stdio integration test, and GitHub CI.
5. Run thirty regression and runtime demo tests before pushing the round.

## Round 4 — final Python release scope

1. Harden FastAPI router registration and test matching.
2. Link pytest fixtures to impacted tests.
3. Bound AI summary context and improve provider error handling.
4. Package the usage guide, repeatable demo, and release checks.
5. Run full round-end verification and publish the completed Python release.
