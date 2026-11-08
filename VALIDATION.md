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
