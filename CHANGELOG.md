# Changelog

## 0.3.0

- Added a local Models settings panel with saved profiles, provider catalogs, manual model IDs, connection testing, and active-model switching.
- Added OpenRouter and custom OpenAI-compatible Chat Completions providers while preserving OpenAI and local Ollama.
- Added OS-keychain credential storage, environment fallback, metadata-only settings, atomic writes, revision conflicts, and credential rollback.
- CLI and MCP summaries use the active model unless a provider is explicitly selected.
- Protected the loopback panel with session tokens, Host/Origin validation, restrictive browser headers, bounded requests, and credential-safe responses.

## 0.2.0

- Added content-addressed SQLite source indexes and index_repository statistics.
- Reused graph and route calculations within each source snapshot.
- Added Python C3 inheritance, super lookup, typed receivers, and conservative local method-replacement handling.
- Added FastAPI dependency providers and application factories.
- Added Flask blueprint/factory/function-view and Django URL/include/class-dispatch adapters.
- Added the trusted TypeScript compiler backend, Express routes/middleware, named test identities, native fetch candidates, and mixed-language analysis.
- Added language-aware Git diffs and baselines, historical compiler configuration, and TypeScript configuration-change impact.
- Added pinned accuracy/performance benchmarks, runtime framework checks, a TypeScript Express example, and TypeScript MCP verification.
- Fixed caching of Python ellipsis/bytes/complex constants, dependency resolution invalidation, dynamic Express prefix reporting, and cache privacy/ignore defaults.

Existing Python commands retain their default backend. Baselines without a language field remain Python baselines. TypeScript is optional and requires a trusted Node/compiler runtime. Cached source data is local under .impact-cache.

## 0.1.0

Initial Python CLI/MCP release with source evidence, FastAPI/pytest relationships, Git impact, snapshots, optional Ollama/OpenAI summaries, and runnable validation examples.
