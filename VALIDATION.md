# Verification record

## Round 1

- Seven regression tests passed on Python 3.11.
- Built a wheel, installed it into a separate environment, and exercised CLI help.
- Verified the three MCP tool registrations.
- Fixed `src/` layout indexing and package-relative import handling during review.

## Round 2

- Twelve regression tests passed from a separately installed package.
- Verified six MCP tool registrations and CLI argument discovery.
- Tested baseline additions, deleted symbols, and unchanged connections after line movement.
- Tested OpenAI request/response handling with mocked HTTP responses and missing-key behavior.
- Generated a live local summary through installed Ollama model `qwen3.5:2b-q4_K_M`.
- A live online provider request requires the user's API key and remains unverified.

Run regression tests after installing `.[dev,mcp]` with `python -m pytest -q`.

## Round 3

- Thirty tests passed on Python 3.11, including four live FastAPI demo tests.
- Opened a real stdio MCP client session, listed all six tools, and called `trace_callers`.
- Covered parameter shadowing, local imports, package re-exports, dotted imports, methods, constructor inference, lambdas, and comprehensions.
- Covered deleted files, deleted body lines, import-only changes, quoted filenames, subdirectory input, and invalid Git revisions.
- Added CI for Python 3.11 and 3.12. GitHub run status is checked after push.

The Round 3 GitHub CI run passed for both Python versions.

## Round 4

- Forty-seven tests cover the complete Python release scope.
- Added nested/multiple router mount evidence, alias handling, trailing slashes, dynamic/reassigned router diagnostics, parameterized HTTP candidates, and fixture dependency cases.
- Verified transitive conftest fixtures, autouse fixtures, and usefixtures markers.
- Added bounded AI context, omission reporting, provider error handling, and credential-safe error checks.
- Verified source-body changes with unchanged connections, line movement, parse failures, and comment-only Git changes.
- The repeatable demo identified two affected endpoints and four tests, then detected `/orders/express` as a newly connected endpoint.
- A live Ollama request against the final demo produced a summary with model `qwen3.5:2b-q4_K_M` and explicit scope metadata.
- Ruff checks and formatting checks pass. Clean package installation, CLI module entry, and MCP stdio execution are included in final verification.
- Fixed uv non-editable build caching so source changes invalidate the installed package cache.
- The demo dependencies emit one upstream Starlette warning about legacy httpx TestClient support. Runtime tests pass.
- Live OpenAI execution remains pending an API key. Request/response and failure behavior are covered with mocked transport.

## Round 5

- Eighty Python tests and three executable TypeScript/Node tests pass locally.
- Opened real MCP stdio sessions for Python and TypeScript, listed all seven tools, and called the selected backend.
- Exercised real Flask blueprint/factory requests, Django URL include/class-view requests, and an Express server with valid/invalid quantities.
- Verified C3 diamond dispatch, super, constructor precedence over annotations, and conservative local method-replacement handling.
- Verified explicit FastAPI dependency providers, returned factories, Flask prefix overrides, Django dispatch, Express mounts/middleware/chained routes, and native fetch test candidates.
- Verified TypeScript aliases, inherited methods, dynamic dispatch flags, source deletion, syntax failures, historical tsconfig paths, configuration changes, stable test identities, and new dependency-directory invalidation.
- Found and fixed Python cache reuse failures for ellipsis, bytes, complex numbers, and non-finite constants during real-repository benchmarking.
- Verified that source caches are private and ignored by Git even without changing the inspected repository's root ignore file.
- All nine manually labeled direct callers across pinned Flask, FastAPI, and ts-extras revisions matched. Every warm index reported zero successfully reparsed files. Scope and timings are recorded under benchmarks.
- Generated a live local Ollama summary for the TypeScript example, reporting one endpoint and three related tests.
- OPENAI_API_KEY was unavailable in the execution environment. Live online execution remains unverified. Mocked request, response, credential, size, and failure cases pass.
- The global Codex profile is user-managed. The usage guide supplies the official registration procedure and tested server configuration.
