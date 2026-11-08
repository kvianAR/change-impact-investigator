import subprocess
from pathlib import Path

from change_impact.baseline import compare_impact, create_impact_baseline


def test_baseline_detects_new_caller_and_route(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "validators.py").write_text("def check(value):\n    return bool(value)\n")
    baseline = create_impact_baseline(tmp_path, "validators:check")
    (tmp_path / "api.py").write_text(
        "from fastapi import FastAPI\nfrom validators import check\n"
        "app = FastAPI()\n@app.post('/orders')\n"
        "def route(value):\n    return check(value)\n"
    )
    result = compare_impact(tmp_path, baseline["baseline_id"])
    assert result["changes"]["callers"]["added"][0]["caller"] == "api:route"
    assert result["changes"]["routes"]["added"][0]["path"] == "/orders"


def test_baseline_ignores_line_movement_and_handles_deleted_symbol(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    path = tmp_path / "a.py"
    path.write_text("def check(): pass\ndef run():\n    check()\n")
    baseline = create_impact_baseline(tmp_path, "a:check")
    path.write_text("\n\ndef check(): pass\ndef run():\n    check()\n")
    shifted = compare_impact(tmp_path, baseline["baseline_id"])
    assert shifted["changes"]["callers"] == {"added": [], "removed": []}
    path.write_text("def run():\n    check()\n")
    deleted = compare_impact(tmp_path, baseline["baseline_id"])
    assert deleted["symbol_removed"]
    assert deleted["changes"]["callers"]["removed"][0]["line"] == 3
