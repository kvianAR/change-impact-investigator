# Analysis design

```mermaid
flowchart TD
    Agent[CLI or MCP request] --> Git[Git base and working tree changes]
    Agent --> Parse[Python AST or TypeScript compiler]
    Git --> Historical[Historical source from Git objects]
    Historical --> Parse
    Parse --> Resolve[Symbol and import resolution]
    Resolve --> Graph[Call edges with source evidence]
    Graph --> Routes[FastAPI Flask Django Express routes]
    Graph --> Tests[Pytest fixtures and TypeScript tests]
    Routes --> Report[Deterministic impact report]
    Tests --> Report
    Report --> Snapshot[Baseline comparison]
    Report --> AI[Optional Ollama or OpenAI summary]
```

## Source and symbol index

Git-aware enumeration respects ignored files. Standard environment, build, and generated cache directories are excluded. Symlink files are skipped. Python encoding declarations are supported. Syntax and decoding failures produce diagnostics.

The index records functions, classes, methods, lambdas, imports, lexical bindings, and call sites. Conventional `src/` layouts are supported. Duplicate module identities are diagnosed and excluded from resolution.

Lexical resolution handles local definitions, explicit imports, aliases, relative imports, re-exports, nested functions, module-qualified calls, method receivers, and simple constructor-created instances. Constructor inference has its own resolution label. Parameters and assignments prevent unrelated same-name functions from being linked.

Version 0.2 adds C3 method order for repository-defined bases, declared-class super lookup, and annotated receiver inference. Explicit constructor assignment takes precedence over an annotation. Local method replacement is flagged as unresolved. Unknown external bases keep inherited lookup uncertain.

TypeScript uses the compiler checker for declarations, signatures, aliases, imports, inherited methods, and callable targets. The Node helper reads tsconfig metadata and source without importing application modules. A trusted compiler installation is selected independently of the inspected repository. Mixed mode combines independent backend graphs.

## Persistent indexing

Python modules are serialized as JSON syntax trees, symbols, lexical scopes, and calls in a content-addressed SQLite cache. Keys include source content, module identity, parser code, and interpreter version. Edits invalidate individual files. Corrupt entries fall back to parsing. Python bytes, ellipsis, complex numbers, and non-finite constants use explicit data encodings.

TypeScript caches a complete compiler result. Source hashes, compiler content, configuration reads, dependency reads, and missing resolution paths guard reuse. An edit rebuilds the TypeScript program. Both backends reuse graph calculations within an investigation. The cache has a bounded entry count, private directory permissions, and an internal Git ignore rule.

## Graph traversal

Each resolved edge records its caller, target, source call location, target definition location, expression, and resolution method. Reverse traversal produces caller paths. Path-specific visited sets prevent recursive cycles while preserving alternate paths. Depth and path-count limits produce a truncation flag.

Unresolved calls remain separate from resolved graph edges. The unresolved list covers the repository. A dynamic target can have an unknown relationship to the selected symbol.

## Git changes

The analyzer reads current files and the selected commit's Python blobs without checking out or executing historical code. Deleted symbols keep base-revision evidence. Function body, signature, and decorator changes map to their containing symbol. Module-level edits conservatively affect functions in that module. Non-Python files are listed separately.

Comment and formatting changes with an unchanged module AST are listed as non-semantic changes. They produce no inferred code impact in diff-based reports.

Parse failures preserve historical evidence with a distinct reason. Baseline comparison stops when a selected symbol's current file cannot be indexed. A parse failure therefore remains distinguishable from a deletion.

## Framework relationships

FastAPI adapters identify public `FastAPI` and `APIRouter` constructors, literal route paths, HTTP methods, and top-level `include_router` calls. Mounted prefixes are composed through nested routers. Mount evidence includes every registration location. Dynamic prefixes, unresolved mounts, cycles, depth limits, unmounted routers, and reassigned router variables produce diagnostics.

Returned FastAPI application factories are inspected statically. Explicit Depends/Security providers in parameters, Annotated metadata, decorators, and mounted registration configuration add dependency edges.

Flask discovery covers application factories, Blueprint registration, prefix overrides, decorators, and add_url_rule function references. Django discovery follows literal ROOT_URLCONF settings, urlpatterns, includes, and repository-defined class HTTP methods/dispatch. Express discovery covers imported or CommonJS-created applications/routers, mounts, middleware relationships, chained routes, and returned applications.

Pytest discovery follows default test filename and Test-class naming patterns. Direct call paths provide static links. Fixture parameters, local/imported/conftest fixtures, transitive fixture dependencies, autouse fixtures, and function-level usefixtures markers add fixture evidence. Literal HTTP calls can match parameterized routes and query strings. HTTP matches are candidates because receiver behavior is not proven by a method name.

TypeScript test/it callbacks supply test symbols. Direct calls provide static links. Literal client methods and native fetch URL paths provide HTTP candidates. Named test identities remain stable when unrelated named functions are inserted.

## Snapshots and AI

Baseline JSON stores the investigation evidence. Symbol AST fingerprints distinguish source edits from line movement. Connection identities omit line numbers so moved references retain their relationships. Removed edges keep their earlier locations.

AI receives a bounded evidence projection. Scope counts expose omitted impacts, routes, tests, paths, and unresolved calls. The original deterministic report is returned alongside the summary. Provider transport uses environment-based credentials and bounded responses.

## Supported limits

- Source syntax must be understood by the Python interpreter running the analyzer.
- Custom source roots, runtime import hooks, runtime subclass dispatch, global monkey patching, and decorator replacement can require manual review.
- Factories must expose supported static object creation and return patterns. Runtime route builders and WebSocket routes are outside the adapters.
- Pytest plugins, custom collection rules, runtime fixture lookup, complex fixture overrides, and class-level markers can require manual investigation.
- External installed dependency source and constant/dataflow dependencies are outside the repository call graph.
- TypeScript project references and JSX component composition are outside the current relationship model. Python and TypeScript graphs do not infer cross-language runtime calls.
- TypeScript rebuilds the compiler program after edits. Persistent per-file Python reuse and unchanged-project TypeScript reuse are implemented and measured.
- Pinned public-repository measurements cover nine labeled direct caller symbols. They do not establish global precision or recall.
- A static path indicates possible reachability. Behavioral breakage requires review or execution of relevant tests.
