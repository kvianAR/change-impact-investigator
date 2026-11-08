# Project roadmap

## Round 1: working Python foundation

1. Repository and package setup.
2. Python symbol and import index with source locations.
3. Direct caller tracing with unresolved dynamic calls.
4. FastAPI route and related pytest discovery.
5. Git diff impact report and MCP tools.

Each step is a separate commit pushed to GitHub.

## Future rounds

- Before/after snapshots and graph comparison.
- Better Python name resolution, framework adapters, and incremental indexing.
- Benchmarks against labeled repositories, then TypeScript support.

Static analysis cannot prove all runtime behavior. Reports must separate resolved links from candidates and unresolved dynamic calls.
