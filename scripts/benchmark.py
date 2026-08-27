#!/usr/bin/env python3
"""Reproducible, dependency-free StringTie wall-time benchmark runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def normalized_bytes(path: Path) -> bytes:
    with path.open("rb") as handle:
        return b"".join(line for line in handle if not line.startswith(b"#"))


def digest(path: Path) -> str:
    return hashlib.sha256(normalized_bytes(path)).hexdigest()


def parse_binary(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("binary must be LABEL=PATH")
    label, raw_path = value.split("=", 1)
    path = Path(raw_path).expanduser().resolve()
    if not label or not path.is_file():
        raise argparse.ArgumentTypeError(f"invalid binary: {value}")
    return label, path


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", action="append", required=True, type=parse_binary)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("tests"))
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=20260826)
    args = parser.parse_args()

    if args.repetitions < 1 or args.warmups < 0:
        parser.error("repetitions must be positive and warmups non-negative")

    manifest_path = args.manifest.resolve()
    data_dir = args.data_dir.resolve()
    cases = json.loads(manifest_path.read_text())["cases"]
    binaries = dict(args.binary)
    if len(binaries) != len(args.binary):
        parser.error("binary labels must be unique")

    results: dict[str, object] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machine": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "manifest": str(manifest_path),
        "data_dir": str(data_dir),
        "warmups": args.warmups,
        "repetitions": args.repetitions,
        "binaries": {label: str(path) for label, path in binaries.items()},
        "cases": {},
    }
    rng = random.Random(args.seed)

    with tempfile.TemporaryDirectory(prefix="stringtie-bench-") as tmp:
        tmp_dir = Path(tmp)
        for case in cases:
            name = case["name"]
            measurements = {label: [] for label in binaries}
            hashes: dict[str, str] = {}
            expected_raw = case.get("expected")
            expected = None
            if expected_raw:
                expected = Path(expected_raw.format(data=str(data_dir))).resolve()
                if not expected.is_file():
                    raise FileNotFoundError(f"missing expected output for {name}: {expected}")
                expected_hash = digest(expected)
            else:
                expected_hash = None

            for iteration in range(args.warmups + args.repetitions):
                order = list(binaries.items())
                rng.shuffle(order)
                for label, binary in order:
                    output = tmp_dir / f"{name}-{label}.gtf"
                    rendered = [
                        token.format(data=str(data_dir), output=str(output))
                        for token in case["args"]
                    ]
                    started = time.perf_counter()
                    proc = subprocess.run(
                        [str(binary), *rendered],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    elapsed = time.perf_counter() - started
                    if proc.returncode != 0:
                        raise RuntimeError(
                            f"{name}/{label} exited {proc.returncode}: {proc.stderr[-2000:]}"
                        )
                    output_hash = digest(output)
                    hashes[label] = output_hash
                    if expected_hash and output_hash != expected_hash:
                        raise RuntimeError(f"{name}/{label} output differs from expected GTF")
                    if iteration >= args.warmups:
                        measurements[label].append(elapsed)

            if len(set(hashes.values())) != 1:
                raise RuntimeError(f"{name}: binaries produced different GTF output")

            case_result: dict[str, object] = {"output_sha256": next(iter(hashes.values())), "runs": {}}
            for label, values in measurements.items():
                case_result["runs"][label] = {
                    "seconds": values,
                    "median_seconds": statistics.median(values),
                    "mean_seconds": statistics.mean(values),
                    "p05_seconds": percentile(values, 0.05),
                    "p95_seconds": percentile(values, 0.95),
                }
            first_label = next(iter(binaries))
            baseline = statistics.median(measurements[first_label])
            case_result["speedup_vs_first"] = {
                label: baseline / statistics.median(values)
                for label, values in measurements.items()
            }
            results["cases"][name] = case_result
            summary = ", ".join(
                f"{label}={statistics.median(values):.6f}s"
                for label, values in measurements.items()
            )
            print(f"{name}: {summary}")

    encoded = json.dumps(results, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
        print(f"wrote {args.output}")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

