/* Repository source is parsed with the compiler API. It is never imported or executed. */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

function hash(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function analyze(request) {
  const root = path.resolve(request.root);
  const compiler = process.env.CHANGE_IMPACT_TYPESCRIPT_PATH || require.resolve("typescript", { paths: [__dirname] });
  const ts = require(compiler);
  const readInputs = new Map();
  const missing = new Set();
  const files = request.files.map(file => path.resolve(root, file));
  const ownFiles = new Set(files);
  const overrides = request.sources;
  const relative = file => path.relative(root, file).split(path.sep).join("/");
  const originalRead = ts.sys.readFile;
  const readFile = file => {
    const absolute = path.resolve(file);
    const name = relative(absolute);
    let value;
    if (overrides && (/\.[cm]?[jt]sx?$/.test(name) || name.endsWith(".json")) && !name.startsWith("../") && !name.includes("node_modules/")) {
      value = Object.hasOwn(overrides, name) ? overrides[name] : undefined;
    } else {
      value = originalRead(absolute);
    }
    if (value !== undefined) readInputs.set(absolute, hash(value));
    return value;
  };
  const fileExists = file => {
    const absolute = path.resolve(file);
    const name = relative(absolute);
    const exists = overrides && (/\.[cm]?[jt]sx?$/.test(name) || name.endsWith(".json")) && !name.startsWith("../") && !name.includes("node_modules/")
      ? Object.hasOwn(overrides, name) : ts.sys.fileExists(absolute);
    if (!exists) missing.add(absolute);
    return exists;
  };
  let options = { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.CommonJS, allowJs: true, checkJs: true, noEmit: true, skipLibCheck: true };
  const diagnostics = [];
  const configFile = path.join(root, "tsconfig.json");
  if (fileExists(configFile)) {
    const config = ts.readConfigFile(configFile, readFile);
    if (config.error) diagnostics.push(config.error);
    else {
      const parsed = ts.parseJsonConfigFileContent(config.config, { ...ts.sys, readFile, fileExists }, path.dirname(configFile));
      options = { ...options, ...parsed.options, noEmit: true, allowJs: true };
      diagnostics.push(...parsed.errors.filter(item => item.code !== 18003));
    }
  }
  const host = ts.createCompilerHost(options);
  host.readFile = readFile;
  host.fileExists = fileExists;
  if (overrides) {
    const directories = new Set();
    for (const file of files) {
      let directory = path.dirname(file);
      while (directory.startsWith(root)) {
        directories.add(directory);
        if (directory === root) break;
        directory = path.dirname(directory);
      }
    }
    const originalDirectoryExists = host.directoryExists;
    host.directoryExists = directory => directories.has(path.resolve(directory)) || originalDirectoryExists(directory);
  }
  host.getSourceFile = (file, target) => {
    const text = readFile(file);
    return text === undefined ? undefined : ts.createSourceFile(file, text, target, true);
  };
  const program = ts.createProgram(files, options, host);
  const checker = program.getTypeChecker();
  const allSources = program.getSourceFiles().filter(source => ownFiles.has(path.resolve(source.fileName)) && !source.isDeclarationFile);
  diagnostics.push(...allSources.flatMap(source => source.parseDiagnostics));
  const sources = allSources.filter(source => source.parseDiagnostics.length === 0);
  const symbols = new Map();
  const nodeIds = new Map();
  const counters = new Map();
  const tests = [];
  const imports = [];
  const edges = [];
  const unresolved = [];
  const objects = new Map();
  const objectDeclarations = new Map();
  const mounts = [];
  const declarations = [];
  const httpCalls = [];
  const string = node => node && (ts.isStringLiteralLike(node) ? node.text : null);
  const line = node => node.getSourceFile().getLineAndCharacterOfPosition(node.getStart()).line + 1;
  const reference = node => ({ file: relative(node.getSourceFile().fileName), line: line(node) });

  function shape(node, bindingsOnly = false) {
    if (bindingsOnly && ts.isFunctionLike(node)) return null;
    if (ts.isIdentifier(node) || ts.isLiteralExpression(node) || ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) return [node.kind, node.text];
    const children = [];
    ts.forEachChild(node, child => { const value = shape(child, bindingsOnly); if (value !== null) children.push(value); });
    return [node.kind, ...children];
  }
  function rootCallName(expression) {
    while (ts.isCallExpression(expression)) expression = expression.expression;
    while (ts.isPropertyAccessExpression(expression)) expression = expression.expression;
    return ts.isIdentifier(expression) ? expression.text : "";
  }
  function testCall(call) {
    return ts.isCallExpression(call) && ["test", "it"].includes(rootCallName(call.expression));
  }
  function register(node, prefix = "") {
    let next = prefix;
    if (ts.isClassDeclaration(node) || ts.isClassExpression(node)) {
      const name = node.name ? node.name.text : `<class>#${line(node)}`;
      next = prefix ? `${prefix}.${name}` : name;
      addSymbol(node, next, "class");
    } else if (ts.isFunctionLike(node) && node.body) {
      let name = node.name && node.name.getText();
      if (!name && ts.isVariableDeclaration(node.parent)) name = node.parent.name.getText();
      if (!name && ts.isPropertyAssignment(node.parent)) name = node.parent.name.getText();
      if (ts.isConstructorDeclaration(node)) name = "constructor";
      const parentCall = ts.isCallExpression(node.parent) ? node.parent : null;
      const countKey = `${relative(node.getSourceFile().fileName)}:${prefix}`;
      const ordinal = (counters.get(countKey) || 0) + 1;
      counters.set(countKey, ordinal);
      const isTest = parentCall && testCall(parentCall);
      if (isTest) name = `test ${string(parentCall.arguments[0]) || "<dynamic>"}#${ordinal}`;
      name ||= `<callback>#${ordinal}`;
      next = prefix ? `${prefix}.${name}` : name;
      const id = addSymbol(node, next, ts.isMethodDeclaration(node) || ts.isConstructorDeclaration(node) ? "method" : "function");
      if (isTest) tests.push({ symbol: id, title: string(parentCall.arguments[0]), ...reference(parentCall) });
    }
    ts.forEachChild(node, child => register(child, next));
  }
  function addSymbol(node, qualname, kind) {
    const file = relative(node.getSourceFile().fileName);
    const id = `${file}:${qualname}`;
    const end = node.getSourceFile().getLineAndCharacterOfPosition(node.getEnd()).line + 1;
    symbols.set(id, { module: file, qualname, file, line: line(node), end_line: end, kind, start_line: line(node), fingerprint: hash(JSON.stringify(shape(node))) });
    nodeIds.set(node, id);
    return id;
  }
  for (const source of sources) register(source);

  function unalias(symbol) {
    const seen = new Set();
    while (symbol && symbol.flags & ts.SymbolFlags.Alias && !seen.has(symbol)) {
      seen.add(symbol);
      symbol = checker.getAliasedSymbol(symbol);
    }
    return symbol;
  }
  function declarationId(declaration) {
    if (!declaration) return null;
    if (nodeIds.has(declaration)) return nodeIds.get(declaration);
    if (ts.isVariableDeclaration(declaration) && declaration.initializer && nodeIds.has(declaration.initializer)) return nodeIds.get(declaration.initializer);
    const symbol = declaration.name && unalias(checker.getSymbolAtLocation(declaration.name));
    return symbol && symbol.declarations && symbol.declarations.map(item => nodeIds.get(item)).find(Boolean) || null;
  }
  function resolve(expression, invocation = null) {
    if (invocation) {
      const signature = checker.getResolvedSignature(invocation);
      const resolved = signature && declarationId(signature.declaration);
      if (resolved) return resolved;
    }
    const symbol = unalias(checker.getSymbolAtLocation(ts.isPropertyAccessExpression(expression) ? expression.name : expression));
    return symbol && symbol.declarations && symbol.declarations.map(declarationId).find(Boolean) || null;
  }
  function addEdge(caller, target, node, resolution = "typescript_checker") {
    const definition = symbols.get(target);
    if (definition) edges.push({ caller, target, ...reference(node), expression: node.expression ? node.expression.getText() : node.getText(), target_file: definition.file, target_line: definition.line, resolution });
  }
  function importBindings(source) {
    const result = new Map();
    for (const statement of source.statements) {
      if (!ts.isImportDeclaration(statement) || !statement.importClause) continue;
      const specifier = string(statement.moduleSpecifier);
      const clause = statement.importClause;
      if (clause.name) result.set(clause.name.text, specifier);
      if (clause.namedBindings && ts.isNamespaceImport(clause.namedBindings)) result.set(clause.namedBindings.name.text, specifier);
      if (clause.namedBindings && ts.isNamedImports(clause.namedBindings)) for (const binding of clause.namedBindings.elements) result.set(binding.name.text, `${specifier}.${(binding.propertyName || binding.name).text}`);
      const names = [clause.name, ...(clause.namedBindings && ts.isNamedImports(clause.namedBindings) ? clause.namedBindings.elements.map(item => item.name) : []), ...(clause.namedBindings && ts.isNamespaceImport(clause.namedBindings) ? [clause.namedBindings.name] : [])].filter(Boolean);
      for (const name of names) {
        const target = resolve(name);
        let resolvedModule = null;
        const imported = unalias(checker.getSymbolAtLocation(name));
        if (imported && imported.declarations) {
          const declaration = imported.declarations.find(item => ownFiles.has(path.resolve(item.getSourceFile().fileName)));
          if (declaration) resolvedModule = relative(declaration.getSourceFile().fileName);
        }
        imports.push({ ...reference(statement), scope: null, alias: name.text, target: target ? target.replace(":", ".") : resolvedModule || specifier, specifier });
      }
    }
    return result;
  }
  const bindings = new Map(sources.map(source => [source.fileName, importBindings(source)]));
  function canonical(expression) {
    if (ts.isIdentifier(expression)) return bindings.get(expression.getSourceFile().fileName).get(expression.text) || expression.text;
    if (ts.isPropertyAccessExpression(expression)) return `${canonical(expression.expression)}.${expression.name.text}`;
    return "";
  }
  function registerObjects(node, caller = null) {
    if (nodeIds.has(node)) caller = nodeIds.get(node);
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer && ts.isCallExpression(node.initializer)) {
      const kind = canonical(node.initializer.expression);
      if (["express", "express.default", "express.Router"].includes(kind)) {
        const id = `${relative(node.getSourceFile().fileName)}:${node.name.text}@${line(node)}`;
        objects.set(id, { kind: kind.endsWith("Router") ? "router" : "app", ...reference(node), caller });
        objectDeclarations.set(node, id);
      }
    }
    ts.forEachChild(node, child => registerObjects(child, caller));
  }
  for (const source of sources) registerObjects(source);
  function objectId(expression) {
    const symbol = unalias(checker.getSymbolAtLocation(expression));
    return symbol && symbol.declarations && symbol.declarations.map(item => objectDeclarations.get(item)).find(Boolean) || null;
  }
  const verbs = new Set(["get", "post", "put", "patch", "delete", "head", "options", "all"]);
  function visit(node, caller = null) {
    if (nodeIds.has(node)) caller = nodeIds.get(node);
    if (ts.isCallExpression(node) || ts.isNewExpression(node)) {
      const current = caller || `${relative(node.getSourceFile().fileName)}:<module>`;
      const type = checker.getTypeAtLocation(node.expression);
      let target = resolve(node.expression, node);
      if (type.isUnion && type.isUnion() && type.types.filter(item => checker.getSignaturesOfType(item, ts.SignatureKind.Call).length).length > 1) {
        target = null;
        unresolved.push({ ...reference(node), caller: current.split(":").slice(1).join(":"), expression: node.expression.getText(), reason: "union_callable_dispatch" });
      } else if (target) addEdge(current, target, node);
      else {
        const symbol = unalias(checker.getSymbolAtLocation(ts.isPropertyAccessExpression(node.expression) ? node.expression.name : node.expression));
        const external = symbol && symbol.declarations && symbol.declarations.some(item => !ownFiles.has(path.resolve(item.getSourceFile().fileName)));
        if (!external && !["test", "it", "describe", "expect", "require"].includes(rootCallName(node.expression))) unresolved.push({ ...reference(node), caller: current.split(":").slice(1).join(":"), expression: node.expression.getText(), reason: "unresolved_typescript_dispatch" });
      }
      if (ts.isPropertyAccessExpression(node.expression)) {
        const method = node.expression.name.text.toLowerCase();
        const owner = objectId(node.expression.expression);
        if (verbs.has(method) && string(node.arguments[0]) !== null) httpCalls.push({ caller: current, method: method.toUpperCase(), path: string(node.arguments[0]), ...reference(node) });
        if (owner && verbs.has(method)) {
          const routePath = string(node.arguments[0]);
          if (routePath === null) diagnostics.push({ file: node.getSourceFile(), start: node.getStart(), messageText: "Dynamic Express route path", code: 0 });
          else for (const argument of node.arguments.slice(1)) {
            const handler = nodeIds.get(argument) || resolve(argument);
            if (handler) declarations.push({ owner, method: method === "all" ? "ANY" : method.toUpperCase(), path: routePath, symbol: handler, ...reference(node) });
          }
        } else if (owner && method === "use") {
          const prefix = string(node.arguments[0]);
          const argumentsList = prefix === null ? node.arguments : node.arguments.slice(1);
          for (const argument of argumentsList) {
            const child = objectId(argument);
            if (child) mounts.push({ parent: owner, child, prefix: prefix || "", ...reference(node) });
          }
        }
      }
    }
    ts.forEachChild(node, child => visit(child, caller));
  }
  for (const source of sources) {
    visit(source);
  }
  const routes = [];
  const reached = new Set();
  const join = (prefix, route) => `${prefix.replace(/\/$/, "")}/${route.replace(/^\//, "")}`;
  function routeTree(owner, prefix, evidence, seen, app) {
    reached.add(owner);
    for (const declaration of declarations) if (declaration.owner === owner) routes.push({ ...declaration, path: join(prefix, declaration.path), app, framework: "express", mount_evidence: evidence });
    for (const mount of mounts) if (mount.parent === owner) {
      if (seen.has(mount.child) || seen.size >= 32) continue;
      routeTree(mount.child, join(prefix, mount.prefix), [...evidence, { file: mount.file, line: mount.line }], new Set([...seen, mount.child]), app);
    }
  }
  for (const [id, object] of objects) if (object.kind === "app") routeTree(id, "", [], new Set([id]), id);
  for (const declaration of declarations) if (!reached.has(declaration.owner)) unresolved.push({ file: declaration.file, line: declaration.line, caller: null, expression: declaration.path, reason: "unmounted_express_router" });
  const modules = sources.map(source => ({ name: relative(source.fileName), file: relative(source.fileName), content_hash: hash(source.text), ast_hash: hash(JSON.stringify(shape(source))), binding_hash: hash(JSON.stringify(shape(source, true))), symbols: [...symbols.values()].filter(symbol => symbol.file === relative(source.fileName)), imports: imports.filter(item => item.file === relative(source.fileName)) }));
  return {
    compiler_version: ts.version,
    modules, edges, routes, tests: tests.map(test => ({ ...test, http_calls: httpCalls.filter(call => call.caller === test.symbol) })),
    unresolved,
    diagnostics: diagnostics.map(item => ({ file: item.file ? relative(item.file.fileName) : null, line: item.file && item.start !== undefined ? item.file.getLineAndCharacterOfPosition(item.start).line + 1 : null, reason: ts.flattenDiagnosticMessageText(item.messageText, "\n"), code: item.code })),
    inputs: Object.fromEntries(readInputs), missing_inputs: [...missing],
  };
}

try {
  const request = JSON.parse(fs.readFileSync(0, "utf8"));
  process.stdout.write(JSON.stringify(analyze(request)));
} catch (error) {
  process.stderr.write(`TypeScript analysis failed: ${error.message}\n`);
  process.exitCode = 1;
}
