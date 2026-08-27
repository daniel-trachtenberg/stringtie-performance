# StringTie performance project

This repository tracks an experimental effort to reduce StringTie runtime by at
least 2x without changing transcript reconstruction or abundance results.
Performance claims must compare the same workload, compiler, flags, thread
count, and machine and must pass the upstream regression suite.

## Quick start

```bash
./scripts/setup.sh
./scripts/build.sh release baseline
python3 scripts/benchmark.py \
  --binary baseline=build/baseline/stringtie \
  --manifest benchmarks/cases.json \
  --repetitions 7 \
  --output benchmark-results/baseline.json
```

`setup.sh` downloads the small upstream regression dataset through the
project's existing test runner. It does not download a production-size
benchmark. Put local, coordinate-sorted BAM/CRAM inputs under
`benchmarks/data/` (ignored by Git) and copy `benchmarks/cases.example.json` to
a separate manifest to describe them.

To compare two binaries while alternating their execution order:

```bash
python3 scripts/benchmark.py \
  --binary baseline=build/baseline/stringtie \
  --binary candidate=build/candidate/stringtie \
  --manifest benchmarks/cases.json \
  --repetitions 9 \
  --output benchmark-results/comparison.json
```

The runner writes normalized-output SHA-256 values and fails if binaries
produce different GTF content (comment lines beginning with `#` are ignored,
matching the upstream test policy). It reports median wall time and candidate
speedup for each case. Commit the small JSON result when it supports an
experiment; never commit sequencing data.

## Measurement protocol

1. Pin a baseline commit and record `git rev-parse HEAD`.
2. Use a release build for both revisions. Architecture-specific flags are
   allowed only when identical for both.
3. Use a dedicated machine with power connected and background work minimized.
4. Include short-read, guided, long-read, mixed-read, and pathological
   high-complexity splice-graph inputs. The bundled cases are correctness smoke
   tests, not sufficient evidence for a 2x claim.
5. Use at least one warmup and seven measured runs. Prefer the median and report
   dispersion. Repeat on a second machine before claiming a general speedup.
6. Run `make test` and verify cross-binary output hashes before accepting a
   result.

## Initial algorithm map

The main flow-related code is in `rlink.cpp`:

- `bfs` around line 7216 searches residual paths.
- `weight_bfs` around line 8805 applies node-rate constraints.
- `long_max_flow` around line 8864 builds dense `n x n` capacity/flow storage
  and repeatedly calls an Edmonds-Karp-like BFS.
- `push_max_flow`, `push_guide_maxflow`, `guidepushflow`, and
  `nascent2max_flow` implement specialized flow propagation for other modes.

The strongest first hypothesis is that complex long-read splice graphs pay for
dense matrix initialization and repeated allocation even though adjacency is
sparse. Validate that with a representative long-read profile before changing
the algorithm. Candidate experiments include sparse residual-edge storage,
reusing BFS scratch buffers, and replacing repeated full-vector initialization.
Each experiment should be isolated in its own branch and evaluated for output
equivalence before combining changes.

## Profiling on macOS

Build with release optimization and debug symbols (the default release target
uses `-g -O3`), then use Instruments' Time Profiler or `xctrace` on a large
case. Example:

```bash
xcrun xctrace record --template 'Time Profiler' \
  --output benchmark-results/stringtie.trace \
  --launch -- build/baseline/stringtie \
  -o /tmp/stringtie-profile.gtf benchmarks/data/sample.bam
```

Trace bundles are ignored and should not be committed. On Linux, use `perf
record`/`perf report` with the same optimized, symbol-bearing binary.

