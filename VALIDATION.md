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
