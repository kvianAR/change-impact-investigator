import sqlite3
from pathlib import Path

from change_impact.index import build_index
from change_impact.related import discover_route_map
from change_impact.trace import trace_callers


def test_incremental_cache_reparses_only_changed_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def check(): pass\n")
    (tmp_path / "b.py").write_text("from a import check\ndef run(): check()\n")
    assert build_index(tmp_path).stats["parsed_files"] == 2
    warm = build_index(tmp_path)
    assert warm.stats["cache_hits"] == 2
    assert warm.stats["parsed_files"] == 0
    (tmp_path / "b.py").write_text("def run(): pass\n")
    changed = build_index(tmp_path)
    assert changed.stats["parsed_files"] == 1
    assert changed.stats["cache_hits"] == 1
    assert trace_callers(changed, "a:check")["paths"] == []
    (tmp_path / "b.py").unlink()
    assert set(build_index(tmp_path)) == {"a"}


def test_corrupt_cached_json_falls_back_to_source(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def check(): pass\n")
    build_index(tmp_path)
    with sqlite3.connect(tmp_path / ".impact-cache/index.sqlite3") as database:
        database.execute("UPDATE source_index SET payload = '{}' ")
    index = build_index(tmp_path)
    assert index.stats["parsed_files"] == 1
    assert index["a"].symbols[0].name == "check"


def test_queries_share_one_graph_per_source_snapshot(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def check(): pass\ndef run(): check()\n")
    index = build_index(tmp_path)
    first = trace_callers(index, "a:check")
    assert trace_callers(index, "a:check")["paths"] == first["paths"]
    discover_route_map(index)
    discover_route_map(index)
    assert index.stats["graph_builds"] == 1
    assert index.stats["route_builds"] == 1
