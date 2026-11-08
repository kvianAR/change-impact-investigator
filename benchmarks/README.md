# Pinned repository benchmark

The manifest contains three repository queries with nine manually checked direct caller symbols. Each expected caller includes an independently read source location. The pinned revisions preserve those labels.

The local run matched all nine labels with no missing or unexpected caller symbols. This establishes precision and recall for these queries. Repository-wide accuracy, runtime dispatch coverage, and arbitrary project performance require broader measurement.

## Reproduce

Install the Python package and trusted TypeScript compiler runtime first.

```sh
python benchmarks/fetch.py --directory /path/to/benchmark-checkouts
python benchmarks/run.py --repos-dir /path/to/benchmark-checkouts --output benchmark-results.json --reset-cache
```

Fetching creates new checkouts or verifies an existing checkout's revision. Existing checkouts at another revision are rejected. The benchmark reads third-party source without importing or running it.

`--reset-cache` clears the analyzer's source-index table for each benchmark root. Baseline snapshots remain available. Initial and warm timings measure indexing. Query timing measures first graph construction and caller traversal. Counters expose parser reuse, and warm results must preserve the original edge paths.

## Recorded local run

| Repository | Indexed modules | Initial index | Warm index | Labeled callers |
| --- | ---: | ---: | ---: | ---: |
| Flask | 24 | 1.5387 s | 0.4239 s | 4 |
| FastAPI | 1,219 | 65.5376 s | 12.6098 s | 4 |
| ts-extras | 49 | 0.9258 s | 0.0704 s | 1 |

The final v0.2 run used Python 3.11 on arm64 and overlapped with local Ollama inference. All three warm indexes reported zero successfully reparsed files. Raw source evidence, diagnostics, counters, pinned commits, and timings are saved in `results.json`. Timing depends on shared CPU/memory load, hardware, filesystem caching, and runtime versions.
