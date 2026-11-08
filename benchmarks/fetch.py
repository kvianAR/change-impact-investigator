"""Fetch the exact public revisions used by the labeled benchmark cases."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    cases = json.loads(Path(__file__).with_name("cases.json").read_text())
    for case in cases:
        destination = args.directory / case["directory"]
        if destination.exists():
            revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            if revision != case["commit"]:
                raise SystemExit(
                    f"Existing checkout {destination} has another revision. Choose a new directory."
                )
            continue
        destination.mkdir(parents=True)
        for arguments in [
            ["init", "--quiet"],
            ["remote", "add", "origin", case["repository"] + ".git"],
            ["fetch", "--quiet", "--depth", "1", "origin", case["commit"]],
            ["checkout", "--quiet", "--detach", "FETCH_HEAD"],
        ]:
            subprocess.run(["git", *arguments], cwd=destination, check=True)
        print(f"Fetched {case['directory']} at {case['commit']}")


if __name__ == "__main__":
    main()
