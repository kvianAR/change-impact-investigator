"""Read Git worktree changes and historical Python source without checkout."""

from __future__ import annotations

import io
import os
import re
import subprocess
import tokenize
from dataclasses import dataclass
from pathlib import Path

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class Change:
    file: str
    status: str
    old_lines: set[int]
    new_lines: set[int]


def _git(root: Path, *args: str, input: bytes | None = None) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, input=input, capture_output=True)
    if result.returncode:
        raise ValueError(f"Git command failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def repository_root(path: Path) -> Path:
    if not path.is_dir():
        raise ValueError(f"Repository directory does not exist: {path}")
    return Path(os.fsdecode(_git(path, "rev-parse", "--show-toplevel")).strip()).resolve()


def resolve_base(root: Path, base: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"],
        cwd=root,
        capture_output=True,
    )
    if result.returncode == 0:
        return result.stdout.decode().strip()
    if (
        base == "HEAD"
        and subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=root, capture_output=True
        ).returncode
    ):
        return None
    raise ValueError(f"Git base revision does not exist: {base}")


def diff_changes(root: Path, base_commit: str | None) -> list[Change]:
    changes: list[Change] = []
    if base_commit is None:
        filenames = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        for raw in dict.fromkeys(filter(None, filenames.split(b"\0"))):
            filename = os.fsdecode(raw)
            if ".impact-cache" in Path(filename).parts:
                continue
            path = root / filename
            if path.is_file() and not path.is_symlink():
                count = len(path.read_bytes().splitlines()) if filename.endswith(".py") else 0
                changes.append(Change(filename, "A", set(), set(range(1, count + 1))))
        return changes
    raw_changes = _git(
        root, "diff", "--name-status", "-z", "--no-renames", base_commit, "--"
    ).split(b"\0")
    for offset in range(0, len(raw_changes) - 1, 2):
        status, filename = raw_changes[offset].decode(), os.fsdecode(raw_changes[offset + 1])
        if ".impact-cache" in Path(filename).parts:
            continue
        patch = (
            _git(
                root,
                "diff",
                "--unified=0",
                "--no-ext-diff",
                "--no-textconv",
                "--no-color",
                "--no-renames",
                base_commit,
                "--",
                filename,
            ).decode(errors="replace")
            if filename.endswith(".py")
            else ""
        )
        older: set[int] = set()
        newer: set[int] = set()
        for line in patch.splitlines():
            if match := HUNK.match(line):
                old_start, old_count, new_start, new_count = (
                    int(value) if value is not None else 1 for value in match.groups()
                )
                older.update(range(old_start, old_start + old_count))
                newer.update(range(new_start, new_start + new_count))
        changes.append(Change(filename, status, older, newer))
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    for raw in filter(None, untracked.split(b"\0")):
        filename = os.fsdecode(raw)
        if ".impact-cache" in Path(filename).parts:
            continue
        path = root / filename
        if path.is_file() and not path.is_symlink():
            count = len(path.read_bytes().splitlines()) if filename.endswith(".py") else 0
            changes.append(Change(filename, "A", set(), set(range(1, count + 1))))
    return changes


def read_revision_sources(root: Path, commit: str) -> tuple[dict[str, str], list[dict]]:
    tree = _git(root, "ls-tree", "-r", "-z", commit)
    entries: list[tuple[str, str]] = []
    for entry in filter(None, tree.split(b"\0")):
        metadata, filename = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode().split()
        path = os.fsdecode(filename)
        excluded = {".venv", "venv", "node_modules", "build", "dist", "__pycache__"}
        if (
            mode in {"100644", "100755"}
            and kind == "blob"
            and path.endswith(".py")
            and not excluded.intersection(Path(path).parts)
        ):
            entries.append((path, object_id))
    if not entries:
        return {}, []
    objects = io.BytesIO(
        _git(
            root,
            "cat-file",
            "--batch",
            input="".join(f"{object_id}\n" for _, object_id in entries).encode(),
        )
    )
    sources: dict[str, str] = {}
    diagnostics: list[dict] = []
    for filename, _ in entries:
        _, _, size = objects.readline().decode().split()
        data = objects.read(int(size))
        objects.read(1)
        try:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
            sources[filename] = data.decode(encoding)
        except (SyntaxError, UnicodeError) as exc:
            diagnostics.append(
                {"file": filename, "line": None, "reason": type(exc).__name__, "state": "base"}
            )
    return sources, diagnostics
