"""Create an inspectable demo repository, change a validator, and save evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from change_impact.baseline import compare_impact, create_impact_baseline
from change_impact.impact import inspect_change_impact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".impact-cache/demo"))
    args = parser.parse_args()
    destination = args.directory.resolve()
    if destination.exists():
        parser.error("Demo directory already exists. Choose a new --directory.")
    source = Path(__file__).resolve().parents[1] / "examples"
    destination.mkdir(parents=True)
    shutil.copytree(source, destination / "examples", ignore=shutil.ignore_patterns("__pycache__"))

    def git(*arguments: str) -> None:
        subprocess.run(["git", *arguments], cwd=destination, check=True, capture_output=True)

    git("init", "-b", "main")
    git("add", ".")
    git(
        "-c",
        "commit.gpgsign=false",
        "-c",
        "user.name=Impact Demo",
        "-c",
        "user.email=demo@example.invalid",
        "commit",
        "-m",
        "demo baseline",
    )
    symbol = "examples.shop.validators:validate_order"
    baseline = create_impact_baseline(destination, symbol)
    validator = destination / "examples/shop/validators.py"
    validator.write_text(validator.read_text().replace("quantity <= 100", "quantity <= 50"))
    impact = inspect_change_impact(destination)
    body_comparison = compare_impact(destination, baseline["baseline_id"])

    api = destination / "examples/shop/api.py"
    with api.open("a") as output:
        output.write(
            '\n\n@app.post("/orders/express")\ndef express_order_route(order: OrderInput) -> dict:\n    return create_order(order.quantity)\n'
        )
    graph_comparison = compare_impact(destination, baseline["baseline_id"])
    report = {
        "validator_change": impact,
        "body_comparison": body_comparison,
        "new_endpoint_comparison": graph_comparison,
    }
    output_path = destination / "report.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    selected = impact["impacts"][0]
    print(
        json.dumps(
            {
                "report": str(output_path),
                "affected_routes": [
                    f"{route['method']} {route['path']}" for route in selected["affected_routes"]
                ],
                "related_tests": [test["test"]["qualname"] for test in selected["related_tests"]],
                "validator_source_changed": body_comparison["symbol_source_changed"],
                "new_routes": [
                    route["path"] for route in graph_comparison["changes"]["routes"]["added"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
