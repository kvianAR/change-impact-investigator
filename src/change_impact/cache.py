"""Content-addressed, JSON-only source indexes stored in a local SQLite cache."""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


def _encode(value):
    if isinstance(value, ast.AST):
        return {
            "$ast": type(value).__name__,
            "fields": {name: _encode(item) for name, item in ast.iter_fields(value)},
            "attributes": {
                name: getattr(value, name) for name in value._attributes if hasattr(value, name)
            },
        }
    if dataclasses.is_dataclass(value):
        return {
            "$type": type(value).__name__,
            "fields": {
                field.name: _encode(getattr(value, field.name))
                for field in dataclasses.fields(value)
            },
        }
    if isinstance(value, (tuple, set)):
        return {"$collection": type(value).__name__, "items": [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {name: _encode(item) for name, item in value.items()}
    return value


def _decode(value, classes):
    if isinstance(value, list):
        return [_decode(item, classes) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ast" in value:
        node_type = getattr(ast, value["$ast"], None)
        if not isinstance(node_type, type) or not issubclass(node_type, ast.AST):
            raise ValueError("Invalid cached AST type")
        node = node_type(**{name: _decode(item, classes) for name, item in value["fields"].items()})
        for name, item in value["attributes"].items():
            if name not in node._attributes:
                raise ValueError("Invalid cached AST attribute")
            setattr(node, name, item)
        return node
    if "$type" in value:
        return classes[value["$type"]](
            **{name: _decode(item, classes) for name, item in value["fields"].items()}
        )
    if "$collection" in value:
        constructor = {"tuple": tuple, "set": set}[value["$collection"]]
        return constructor(_decode(item, classes) for item in value["items"])
    return {name: _decode(item, classes) for name, item in value.items()}


class IndexCache:
    """Cache failures fall back to source parsing. Cache data is never executed."""

    def __init__(self, root: Path, parser_file: str):
        self.root = root
        self.connection = None
        self.status = "disabled"
        self.parser_hash = hashlib.sha256(Path(parser_file).read_bytes()).hexdigest()

    def __enter__(self):
        if os.environ.get("CHANGE_IMPACT_CACHE", "on").lower() in {"off", "0", "false"}:
            return self
        directory = self.root / ".impact-cache"
        database = directory / "index.sqlite3"
        if directory.is_symlink() or database.is_symlink():
            self.status = "unsafe_path_disabled"
            return self
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
            self.connection = sqlite3.connect(database, timeout=1)
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS source_index (key TEXT PRIMARY KEY, payload TEXT NOT NULL, touched REAL NOT NULL)"
            )
            self.status = "enabled"
        except (OSError, sqlite3.Error):
            if self.connection:
                self.connection.close()
            self.connection = None
            self.status = "unavailable"
        return self

    def key(self, file: str, module: str, text: str) -> str:
        identity = [
            "1",
            sys.version_info[:2],
            self.parser_hash,
            file,
            module,
            hashlib.sha256(text.encode()).hexdigest(),
        ]
        return hashlib.sha256(json.dumps(identity).encode()).hexdigest()

    def get(self, key: str, classes: dict):
        if self.connection is None:
            return None
        try:
            row = self.connection.execute(
                "SELECT payload FROM source_index WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            module = _decode(json.loads(row[0]), classes)
            if not isinstance(module, classes["Module"]) or not isinstance(module.tree, ast.Module):
                return None
            return module
        except (ValueError, TypeError, KeyError, AttributeError, sqlite3.Error, RecursionError):
            return None

    def put(self, key: str, module) -> None:
        if self.connection is None:
            return
        try:
            payload = json.dumps(_encode(module), separators=(",", ":"))
            self.connection.execute(
                "INSERT OR REPLACE INTO source_index VALUES (?, ?, ?)", (key, payload, time.time())
            )
        except (ValueError, TypeError, sqlite3.Error, RecursionError):
            self.status = "write_unavailable"

    def __exit__(self, *error):
        if self.connection is None:
            return
        try:
            self.connection.execute(
                "DELETE FROM source_index WHERE key NOT IN (SELECT key FROM source_index ORDER BY touched DESC LIMIT 10000)"
            )
            self.connection.commit()
        except sqlite3.Error:
            self.connection.rollback()
        finally:
            self.connection.close()
