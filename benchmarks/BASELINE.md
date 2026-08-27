# Performance baseline

Baseline captured on 2026-08-26 PDT from commit
`6e129005a05909be2bcac56aa336d98c836ac3a0` (StringTie 3.0.3). The release
binary was freshly built with `-O3 -DNDEBUG` and has SHA-256
`bb05e66a36b2da0712b5bbdfa824f6c868f23d1ae0ab70bff0b956a76d3d9ae0`.
No algorithm source was changed before this measurement.

## Primary throughput baseline

The primary fixture is a deterministic 1,024-fold coordinate translation of
`tests/mix_short.bam`. It contains 9,836,544 mapped alignments in 1,024
independent bundles and is 608 MiB on this host. The fixture SHA-256 is
`9df7f162d14bcab93727b7ab31893ccdd92539d0d6f61ee4412cca721d61d3d8`.

| Threads | Median | Mean | p05-p95 | CV | 2x target |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 9.4583 s | 9.4766 s | 9.4020-9.5720 s | 0.73% | <=4.7291 s |
| 4 | 9.5424 s | 9.5455 s | 9.4017-9.6644 s | 1.08% | <=4.7712 s |

Each result uses one warmup followed by seven measured runs. The one-thread
result is the optimization baseline. Four threads were 0.89% slower, so this
fixture also exposes serial ingest, scheduling, and output work rather than
hiding it behind worker-count changes.

All repetitions produced a stable normalized GTF with SHA-256
`d2be13d11ea4ad96c3a0c73e5aa53ee340e468478d72f75943a33b54a61cb4c8`:
5,120 transcripts and 45,056 exons. One additional `/usr/bin/time -l` run
recorded 9.54 s real, 12.36 s user, 0.19 s system, 8,142,848 bytes maximum RSS,
157,795,267,900 retired instructions, and 38,633,764,294 elapsed cycles.

The fixture repeats biological graph shapes at different coordinates. It is a
stable whole-pipeline throughput and scheduling benchmark, but it does not
model a single unusually complex splice graph. A production-scale long-read
fixture is still needed before claiming a 2x network-flow improvement.

## Upstream correctness and smoke baseline

The freshly built binary matched all nine supplied expected GTFs after comment
lines were removed. The existing five-case harness was also run with three
warmups and 30 measured repetitions:

| Case | Median |
| --- | ---: |
| Short reads | 0.009693 s |
| Short guided | 0.018806 s |
| Long reads | 0.007748 s |
| Long guided | 0.309121 s |
| Mixed guided | 0.025199 s |

These fixtures are correctness smoke tests, not the primary timing evidence:
four finish in under 26 ms, and the 309 ms guided case is dominated in part by
reading an 11 MiB annotation.

## Reproduce

From the repository root on the same host/toolchain:

```sh
./scripts/build.sh release baseline-6e129005

clang -O2 -Ihtslib -Ihtslib/xlibs/include \
  benchmarks/tools/bam_tile.c \
  htslib/libhts.a htslib/xlibs/lib/libbz2.a \
  htslib/xlibs/lib/liblzma.a htslib/xlibs/lib/libdeflate.a \
  -lz -lm -lpthread -o build/bam_tile

build/bam_tile tests/mix_short.bam \
  benchmarks/data/mix_short_tile_1024.bam 1024 40000 1000001

python3 scripts/benchmark.py \
  --binary baseline_6e129005=build/baseline-6e129005/stringtie \
  --manifest benchmarks/scaled-cases.json \
  --data-dir benchmarks/data \
  --warmups 1 --repetitions 7 --seed 20260826 \
  --output benchmark-results/2026-08-26-baseline-6e129005-scaled.json
```

The raw scaled and smoke JSON files are retained locally under
`benchmark-results/` (ignored by Git). Comparable future medians should be
appended to `benchmarks/history.csv`; that file is the graph-ready history.
