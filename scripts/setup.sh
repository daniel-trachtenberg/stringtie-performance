#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
"$root/scripts/build.sh" release baseline
make -C "$root" test

echo
echo "Environment ready. Baseline binary: build/baseline/stringtie"
echo "Next: python3 scripts/benchmark.py --binary baseline=build/baseline/stringtie --manifest benchmarks/cases.json"

