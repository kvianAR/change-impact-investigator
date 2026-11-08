# Change Impact Investigator

Trace how a Python code change may affect callers, FastAPI endpoints, and tests, with file and line evidence. The project is being built in five-step rounds; see [ROADMAP.md](ROADMAP.md) for scope and limits.

## Quick start

Python 3.11+ is required. Install locally with `pip install .` or with MCP support using `pip install '.[mcp]'`.

```sh
change-impact trace-callers --repo /path/to/repo --symbol package.validators:validate_order
change-impact related-tests --repo /path/to/repo --symbol package.validators:validate_order
change-impact inspect-change-impact --repo /path/to/repo
```

For an MCP client, configure a stdio server with command `change-impact-mcp`. Its tools accept an absolute `repo` path. Source analysis reads files without importing or executing project code. Git impact compares tracked staged and unstaged changes with `HEAD` and includes untracked Python files.

## Current limits

Python only. FastAPI route support covers literal paths and basic `FastAPI`/`APIRouter` registration. Calls through runtime dispatch, dependency injection, complex inheritance, and plugin registries can remain unresolved. Test discovery supports direct calls and literal HTTP client calls. Treat results as evidence for investigation, not proof of runtime behavior.
