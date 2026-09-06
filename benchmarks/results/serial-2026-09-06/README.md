# Published serial benchmark evidence

The [recorded runs](report.json) measured **2.119x** speedup on the tiled
short-read fixture, with seven measured repetitions, one warmup per binary,
and separate one-OS-thread probes. All normalized GTF outputs matched.
See [build provenance](build-provenance.json) for source revisions, compiler
flags and the shared dependency-library hashes, and the
[full analysis](../../../SERIAL_OPTIMIZATION_REPORT.md) for limitations.

These JSON files preserve the original measurements and hashes, but replace
machine-local absolute paths with repository-relative paths. GTFs, logs,
sequencing input and compiled binaries are not committed. The source hashes
describe the measured snapshot; the provenance notes two subsequent
nonfunctional end-of-file whitespace cleanups.

## Rebuild a fair pair

From a fresh checkout of this commit, with the documented build prerequisites
installed, run the following from the repository root. The baseline worktree
directory must not already exist. Compilation can use multiple workers; the
two measured executables are built with `NOTHREADS`.

```sh
task_repo_root=$(pwd)
make clean NOTHREADS=1
make release NOTHREADS=1 -j4
mkdir -p build/serial-original build/serial-optimized
cp stringtie build/serial-optimized/stringtie

git worktree add --detach build/serial-baseline-src \
  6e129005a05909be2bcac56aa336d98c836ac3a0
git -C build/serial-baseline-src apply \
  "$task_repo_root/benchmarks/results/serial-2026-09-06/baseline-serial.patch"
make -C build/serial-baseline-src release NOTHREADS=1 -j4 \
  HTSLIB="$task_repo_root/htslib"
cp build/serial-baseline-src/stringtie build/serial-original/stringtie
```

The pinned baseline has the public v3.0.3 algorithm sources. Its other changes
are repository scaffolding and an ARM portability fix. The supplied patch
only defines the mutex needed to link upstream's existing serial code; it
does not start a thread. Setting `HTSLIB` shares the exact same prebuilt static
dependency archives with the candidate, rather than building different copies.
Do not rebuild or replace those archives between the two builds. Binary
hashes may differ across compiler versions, paths and hosts; compare source,
build settings, outputs and measurements rather than expecting identical
executable hashes on another computer.

Prepare the upstream test input with `./scripts/setup.sh` if it is absent.
Generate the same throughput fixture without changing its tiling parameters:

```sh
mkdir -p benchmarks/data
cc -O2 -Ihtslib -Ihtslib/xlibs/include benchmarks/tools/bam_tile.c \
  htslib/libhts.a htslib/xlibs/lib/libbz2.a \
  htslib/xlibs/lib/liblzma.a htslib/xlibs/lib/libdeflate.a \
  -lz -lm -pthread -o build/bam_tile
build/bam_tile tests/mix_short.bam \
  benchmarks/data/mix_short_tile_1024.bam 1024 40000 1000001

python3 scripts/benchmark_serial.py \
  --baseline build/serial-original/stringtie \
  --candidate build/serial-optimized/stringtie \
  --input benchmarks/data/mix_short_tile_1024.bam \
  --output-dir benchmark-results/serial-new-run \
  --repetitions 7 --warmups 1
```

Use a new output directory for each run. Input generation and compilation
must finish before timing. Match the recorded input SHA-256 for an exact
fixture reproduction; archive bytes can differ with different compression
library versions. This synthetic workload does not establish a universal
2x improvement on all RNA-seq data.
