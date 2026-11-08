# Project roadmap

## Round 1 — completed

1. Repository and package setup.
2. Python symbol and import index with source locations.
3. Direct caller tracing with unresolved dynamic calls.
4. FastAPI route and related pytest discovery.
5. Git diff impact report and MCP tools.

The first three steps were pushed individually. Rounds 2–4 used one commit per round. Round 5 follows the user's later requirement for at least ten meaningful commits.

## Round 2 — completed

1. Save symbol investigation baselines.
2. Compare callers, routes, tests, and dynamic calls with source evidence.
3. Add local Ollama and online OpenAI summary options.
4. Expose the new capabilities through CLI and MCP.
5. Run round-end regression and provider integration checks.

## Round 3 — completed

1. Resolve lexical scopes, local imports, re-exports, methods, and constructor-created instances.
2. Inspect current and historical Git source for deleted symbols and module-level edits.
3. Report parse diagnostics, source hashes, traversal limits, and import evidence.
4. Add an executable FastAPI demo, MCP stdio integration test, and GitHub CI.
5. Run thirty regression and runtime demo tests before pushing the round.

## Round 4 — completed

1. Harden FastAPI router registration and test matching.
2. Link pytest fixtures to impacted tests.
3. Bound AI summary context and improve provider error handling.
4. Package the usage guide, repeatable demo, and release checks.
5. Run full round-end verification and publish the completed Python release.

## Round 5 — completed in version 0.2

1. Add persistent content-addressed indexes, cache statistics, and reusable analysis graphs.
2. Add C3 inheritance, typed receivers, FastAPI injection/factories, Flask blueprints, and Django URL/view adapters.
3. Add the TypeScript compiler backend, mixed-language CLI/MCP tools, Express/test links, Git diffs, and language-aware snapshots.
4. Run pinned public-repository benchmarks and fix discovered cache, dispatch, route, and invalidation regressions.
5. Execute framework/MCP/TypeScript runtime checks, package the release, update guides, and verify CI.

This round contains fifteen meaningful feature, fix, benchmark, verification, and release commits. Every commit was pushed.

Static analysis cannot prove all runtime behavior. Reports separate static links, candidates, diagnostics, and unresolved dynamic calls.


## Models settings — completed in version 0.3

1. Secure provider credentials and atomic model profiles.
2. OpenRouter/custom provider integration and active-model CLI/MCP summaries.
3. Local Models panel with catalog browsing, manual IDs, and provider key updates.
4. Regression, browser-flow, responsive-layout, and package verification.
5. Documentation, release packaging, and GitHub CI verification.

A live OpenRouter inference request requires a user-supplied key.
