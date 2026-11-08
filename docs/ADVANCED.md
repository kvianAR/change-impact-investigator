# Advanced analysis in version 0.2

## Backend selection and identities

Python remains the default. Select `--language typescript` for TypeScript/JavaScript or `--language auto` for both backends. MCP tools accept the same language values. TypeScript requires Node.js 20+ and the trusted compiler installed by the tool checkout's npm lockfile, a trusted global tsc, or CHANGE_IMPACT_TYPESCRIPT_PATH.

Python symbol identities use module and qualified name, such as `shop.validators:validate_order`. TypeScript identities include the source extension, such as `src/validators.ts:validateOrder`. Named test titles retain stable identities across unrelated function insertions. Duplicate titles and anonymous callback insertion can require interpreting identity changes.

## Python relationships

- C3 method order handles repository-defined multiple inheritance, including diamond hierarchies.
- `super()` and explicit two-argument super lookup use the declaring class's static method order.
- Named and forward-reference parameter annotations support receiver inference.
- A known constructor assignment takes precedence over an annotation.
- Local runtime replacement of a method keeps its call unresolved.
- Unknown external base classes keep inherited lookup unresolved.

Resolution labels expose static, constructor, annotation, super, dependency-injection, and framework-dispatch relationships. Runtime subclasses and Python's dynamic object model can change dispatch beyond these rules.

## Framework adapters

### FastAPI

The adapter supports public FastAPI/APIRouter constructors and aliases, literal HTTP declarations, nested router prefixes, multiple mounts, and direct application factory returns. Explicit Depends and Security references in defaults, Annotated parameters, decorators, and registration configuration become graph edges.

Annotation-only Depends calls, runtime provider factories, dynamic prefixes, indirect application construction, and runtime registry mutation can require manual review. Diagnostic records preserve source locations.

### Flask

The adapter supports Flask/Blueprint constructors, returned application factories, route/method decorators, nested blueprint registration, registration prefix overrides, and add_url_rule with a known function reference. Blueprint prefixes follow Flask's override behavior. Unmounted or unresolved blueprints are diagnosed.

Dynamic view factories, MethodView registration through opaque as_view calls, and arbitrary extension registries remain outside this adapter.

### Django

The adapter supports literal ROOT_URLCONF, static urlpatterns lists/concatenation, includes, converter paths, function views, and repository-defined class HTTP methods. Known dispatch overrides become framework graph edges. Without literal settings, unreferenced URLconf roots are labeled candidates.

Function views use method ANY because their full decorator/middleware policy is not inferred. re_path declarations remain visible, but regex paths are excluded from HTTP test matching. Dynamic settings, plugin URL loaders, and external generic-view internals can remain unresolved.

### Express

The compiler backend supports ESM/CommonJS-created apps and routers, literal mounts, nested routers, middleware dependencies, method registrations, chained app.route calls, and returned application objects. Dynamic mount prefixes and reassigned/unreturned application objects produce route diagnostics. Route warnings remain distinct from syntax failures.

Middleware control flow, runtime route mutation, custom wrapper libraries, and plugin factories can require manual review.

## Tests and confidence

Python supports default pytest naming, direct calls, parameter/conftest fixtures, imported fixtures, transitive fixture dependencies, autouse fixtures, and function-level usefixtures markers.

TypeScript supports callback registrations named test or it, including common Jest, Vitest, and Node test forms. Compiler call paths provide static links. Literal HTTP methods and fetch/new URL paths provide candidates. Renamed test DSL imports, arbitrary test wrappers, parameter-generated names, and runtime mocks can need manual investigation.

HTTP matches are labeled candidate because a matching path alone does not prove which deployed application receives the request. Every returned test includes source evidence and its relationship type.

## Cache behavior and evidence state

`.impact-cache/index.sqlite3` holds JSON-only source and compiler data. Its private directory and internal ignore rule keep generated indexes out of normal Git status. The cache is local source-derived data. Python reuses unchanged modules individually. TypeScript reuses unchanged project results and rebuilds after edits or resolution-input changes. Cache failures fall back to parsing.

Use `change-impact index` and inspect index_stats to measure actual reuse. Set CHANGE_IMPACT_CACHE=off to disable persistence. Persisted entries are bounded to 10,000. Baselines remain separate JSON files.

Git reports preserve base-commit evidence for removed definitions. Syntax failures remain distinct from deletions. TypeScript snapshots read historical source and compiler JSON configuration. Configuration/package changes conservatively affect TypeScript symbols. Comments and formatting with unchanged syntax are reported separately.

## Verification boundaries

The release contains executable framework examples, real Python/TypeScript MCP sessions, and pinned repository cases. The benchmark covers nine manually labeled direct caller symbols across Flask, FastAPI, and ts-extras. Metrics apply to those cases. Global accuracy, arbitrary framework extensions, and every runtime dispatch path remain open-ended analysis problems.

Local Ollama summaries are optional. Online OpenAI summaries require OPENAI_API_KEY and incur provider charges. Summaries retain the deterministic evidence and report scope omissions.
