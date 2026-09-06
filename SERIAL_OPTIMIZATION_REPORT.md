# Single-thread StringTie optimization audit

## Scope and acceptance rule

Compare the public StringTie **v3.0.3** implementation with this fork on the
same compressed, coordinate-sorted BAM. Both must use **one operating-system
thread**, identical release flags and dependency libraries. A speedup counts
only if every reconstructed GTF record, including abundance fields and record
order, matches. Only command/version comment lines beginning with `#` are removed.

The earlier approximately 2.57x demonstration was **not a valid serial result**:
`-p 1` meant two OS threads in upstream, and the fork implicitly added a BGZF
decompression worker plus an I/O thread. That implicit worker setup has now
been removed. Both reported benchmark binaries use `make release NOTHREADS=1`.
The normal threaded build still has a reader plus assembly workers; `-p 1`
alone is not a substitute for a serial build.

## What changed

| Area | Implemented optimization | Equivalence constraint |
|---|---|---|
| Fragment-to-graph construction (`rlink.cpp`) | Reuse bundle-local graph/node vectors and bitsets; replace a per-read visited-node hash with dense generation stamps | Same node visitation and coverage-update order; clear marks on generation wrap |
| Bitset compatibility (`gclib/GBitVec.h`, `rlink.cpp`) | Allocation-free subset predicate and in-place unions instead of temporary intersections/unions | Match the original zero-extended word semantics, including unequal lengths |
| BAM auxiliary tags (`gclib/GSam.cpp`, `gclib/GSam.h`) | Bounds-checked one-pass scalar/string scan, plus typed assembly accessors that avoid repeated tag-name dispatch and unused `errno` bookkeeping | Preserve returned values, duplicate-tag behavior, missing/wrong-type values and malformed-input fallback; general string-tag APIs retain their error behavior |
| Mate pairing (`read_pair_index.h`) | Exact structured name/position/hit keys, cached hashes, combined lookup/removal | Retain first insertion on duplicates; compare full names, not just hashes; preserve pairing/count order |
| Alignment allocation (`bundle.h`, `rlink.cpp`) | Recycle up to 4,096 small alignment objects per bundle, keeping vector capacity; look up junctions before allocating | Reset every field; preserve transcript-info ownership and non-owning junction pointers; do not pool oversized vectors |

These are algorithmic/data-structure and implementation optimizations. There
are no additional worker threads, looser filtering thresholds, approximate
flow computations, fast-math flags, pre-decompression, or cached transcript
results. Reused buffers hold fresh data for each read or bundle; repeated genomic
tiles are still independently processed.

The build now tracks transitive header dependencies, which matters when
changing shared structure layouts. The upstream shell regression runner also
now exits unsuccessfully on an execution failure or output mismatch instead
of printing an error and continuing.

## Paper-to-code findings

The original method repeatedly selects a compatible high-coverage path,
quantifies it using a generalized flow network with bias multipliers, then
subtracts assigned fragment abundance. Altering path choices or floating-point
update order can alter later reconstructions, even if a replacement solver
finds a mathematically equivalent maximum-flow value. This is why the changes
above preserve traversal and abundance arithmetic. See the [2015 paper,
including Online Methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC4643835/).

StringTie2 already introduced collapsing equivalent alignments and representing
actual graph nodes/edges with compact bit vectors. Those are not new contributions
of this fork; this work makes their implementation cheaper. See the [2019
StringTie2 paper and Methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC6912988/).

The serial profile of the pre-change fork contained 726 snapshots. Approximately
33% were in fetching/decoding BAM records (26% in DEFLATE), 33% in bundle
assembly/output/cleanup, 17% in `processRead`, and 11% at the strand/tag lookup
site. These are rough sampling estimates, not exact phase timings. Short-read
`push_max_flow` appeared in only about six snapshots; dense `long_max_flow`
did not appear. A flow-solver replacement alone therefore could not deliver
2x end-to-end on this workload.

For a future **long-read, complex-splice-graph** workload, `long_max_flow`
remains a strong target: replace dense capacity/flow matrices with sparse
residual edges and reuse BFS scratch. Initialization/storage could move from
O(V²) to O(V+E), while retaining sorted neighbor order and the same augmenting
paths. This remains a proposal, not an implemented or measured speedup.
Read-to-graph mapping memoization and reusable junction-support scratch are
also follow-on candidates, excluded from the measured build here.

## Workload and limitations

The existing short-read throughput fixture is
`benchmarks/data/mix_short_tile_1024.bam`: **9,836,544 alignments**, generated
from 1,024 coordinate-translated independent copies of the upstream
`tests/mix_short.bam` fixture.

Input SHA-256:
`9df7f162d14bcab93727b7ab31893ccdd92539d0d6f61ee4412cca721d61d3d8`.

Expected normalized GTF SHA-256:
`d2be13d11ea4ad96c3a0c73e5aa53ee340e468478d72f75943a33b54a61cb4c8`.

This demonstrates throughput on this particular synthetic, short-read fixture.
It does **not** establish a universal 2x speedup, nor a 2x long-read flow-solver
improvement. Output equality establishes unchanged results on tested inputs,
not a proof for all possible datasets. Production short/long/mixed-read data,
complex loci, and a second machine are needed for broader claims.

The alignment-object pool is bounded, but the retained `readlist` pointer-array
capacity can follow the largest bundle encountered. Report memory alongside
time rather than assuming the memory tradeoff is zero.

## Re-run the strict comparison

For a new checkout, first follow the
[baseline/candidate build and fixture recipe](benchmarks/results/serial-2026-09-06/README.md).

The prepared binaries are local, ignored artifacts. From the repository root:

```sh
python3 scripts/benchmark_serial.py \
  --baseline build/serial-original/stringtie \
  --candidate build/serial-optimized/stringtie \
  --input benchmarks/data/mix_short_tile_1024.bam \
  --output-dir benchmark-results/serial-new-run \
  --repetitions 7 --warmups 1
```

Choose a new output directory each time. The harness refuses existing
directories, failed/empty runs and differing GTFs. It logs binary/input hashes,
commands, execution order, wall/user/system time and peak RSS. It alternates
the first binary in each paired repetition, with a recorded seed.

Thread verification is performed in separate untimed probes using the OS task
API (macOS) or `/proc/PID/task` (Linux). Every observed count must be one.
Sampling alone cannot exclude extremely short-lived threads, so it accompanies
the source-audited `NOTHREADS` build and disabled BGZF worker setup; it is not
a resource sandbox. No profiling or concurrent compilation runs during timing.

When rebuilding, clean C++ objects before switching thread or optimization
flags; dependency tracking does not detect changed flags:

```sh
make clean NOTHREADS=1
make release NOTHREADS=1 -j4
```

`-j4` parallelizes **compilation only**, not the measured program. Do not use
the bare `make nothreads` target for performance comparisons: it need not select
release optimization. The public source needs the same small serial-link
compatibility fix (`printCovMutex` definition), described in build provenance.
Do not label a build of the current checkout as an upstream baseline.

## Correctness validation

Both serial binaries pass all nine upstream expected-GTF cases: short reads,
super-reads, guided short reads, long reads with/without guides, mixed reads
with/without guides, and the two nascent modes. The upstream test runner also
passes with its failure reporting fixed.

Additional ASan/UBSan tests cover 20,300 auxiliary-tag comparisons, 62,025
mate-index differential/ownership checks, 40,000 pooled alignment lifecycles,
and 301,088 bit-vector pairs with four equivalence checks each. Six Python
tests exercise benchmark failure detection and accounting. See
[test commands and contracts](tests/performance/README.md).

## Recorded timing results

The first seven-repetition validation measured **11.756856 s** upstream versus
**5.592657 s** optimized: **2.102x**, with one observed OS thread in each binary
and all 18 outputs matching (probes, warmups and measured runs). Raw evidence:
`benchmark-results/serial-2026-09-06/report.json`.

The final clean-rebuilt comparison uses **byte-identical dependency libraries**
for both programs, Apple Clang 21.0.0, `-O3`, and `-DNOTHREADS` on an Apple M1 Max.
Seven paired measured repetitions followed one warmup per binary and separate
thread probes:

| Metric | Original v3.0.3 | Optimized |
|---|---:|---:|
| Median wall time | 11.763609 s | 5.550278 s |
| Wall-time range | 11.667007–11.794881 s | 5.531622–5.595550 s |
| Median CPU time (user + system) | 11.697892 s | 5.524253 s |
| Median peak RSS | 7,471,104 bytes | 7,176,192 bytes |
| Observed OS threads | 1 | 1 |

**Wall-time speedup: 2.119x (52.82% less time). CPU-time speedup: 2.118x.**
Every individual paired speedup exceeded 2.10x. All 18 GTF outputs matched.
The thread probes recorded 3,933 original-process and 1,885 candidate-process
observations, each with exactly one thread.

Raw evidence and source/build provenance are in
`benchmark-results/serial-shared-libs-2026-09-06/`. Use this final comparison
for the presentation. The 2x goal is met **on this benchmark**, subject to the
workload/generalization limits above.

The small [run report](benchmarks/results/serial-2026-09-06/report.json) and
[build provenance](benchmarks/results/serial-2026-09-06/build-provenance.json)
are also committed for GitHub review, with local absolute paths replaced by
repository-relative paths. Large data, GTF output files and binaries remain local.
