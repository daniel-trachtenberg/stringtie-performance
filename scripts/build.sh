#!/usr/bin/env bash
set -euo pipefail

mode=${1:-release}
label=${2:-$mode}
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

if command -v getconf >/dev/null 2>&1; then
  jobs=$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)
fi
if [[ -z "${jobs:-}" ]] && command -v sysctl >/dev/null 2>&1; then
  jobs=$(sysctl -n hw.logicalcpu 2>/dev/null || true)
fi
jobs=${jobs:-4}

mkdir -p "$root/build/$label"
make -C "$root" clean

case "$mode" in
  release)
    make -C "$root" -j"$jobs" release
    ;;
  native)
    CXXFLAGS="-g -O3 -march=native" make -C "$root" -j"$jobs" release
    ;;
  *)
    echo "Usage: $0 [release|native] [output-label]" >&2
    exit 2
    ;;
esac

cp "$root/stringtie" "$root/build/$label/stringtie"
"$root/build/$label/stringtie" --version

