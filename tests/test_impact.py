import subprocess
from pathlib import Path

from change_impact.impact import changed_lines, inspect_change_impact


def test_diff_maps_changed_validator_to_route_and_test(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (tmp_path / "validators.py").write_text("def validate(value):\n    return bool(value)\n")
    (tmp_path / "api.py").write_text("from fastapi import FastAPI\nfrom validators import validate\napp = FastAPI()\n@app.post('/orders')\ndef route(value):\n    return validate(value)\n")
    (tmp_path / "test_validators.py").write_text("from validators import validate\ndef test_validate():\n    assert validate('x')\n")
    git("add", ".")
    git("commit", "-m", "base")
    (tmp_path / "validators.py").write_text("def validate(value):\n    return value is not None\n")
    assert changed_lines(tmp_path) == {"validators.py": {2}}
    report = inspect_change_impact(tmp_path)
    assert len(report["impacts"]) == 1
    assert report["impacts"][0]["affected_routes"][0]["path"] == "/orders"
    assert report["impacts"][0]["related_tests"][0]["test"]["qualname"] == "test_validate"
