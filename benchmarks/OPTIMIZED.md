# First optimization checkpoint

This checkpoint was measured on 2026-08-26 PDT from the working tree based on
commit `6e129005a05909be2bcac56aa336d98c836ac3a0`. The final release binary has
SHA-256 `0feea73105222509181f68abdf8af913d697dbb1c03319cda61bb7cce2fa2052`.

## Result

The benchmark runner randomly interleaved the frozen baseline and optimized
binaries for one warmup plus seven measured repetitions. Both used `-p 1` on
the 9,836,544-alignment scaled short-read fixture described in `BASELINE.md`.

| Binary | Median | Mean | p05-p95 |
| --- | ---: | ---: | ---: |
| Baseline | 9.6382 s | 9.6363 s | 9.5909-9.6795 s |
| Optimized | 3.8352 s | 3.8289 s | 3.7611-3.9029 s |

The paired median speedup is **2.513x**. The optimized median is below the
original 4.7291-second 2x target. Every run produced normalized GTF SHA-256
`d2be13d11ea4ad96c3a0c73e5aa53ee340e468478d72f75943a33b54a61cb4c8`.

One additional `/usr/bin/time -l` comparison measured 12.39 s user + 0.21 s
system for the baseline and 9.08 s user + 0.50 s system for the optimized
binary. Retired instructions fell from 157,970,904,845 to 103,515,411,723.
Maximum RSS was effectively unchanged (9.03 MB versus 9.14 MB).

The optimized single-input path configures one HTSlib BGZF decompression worker;
HTSlib also owns an internal ordered-I/O coordination thread. Together with
StringTie's existing producer and bundle worker, a `-p 1` run can therefore have
four OS threads. BGZF threading is disabled for multi-input and `NOTHREADS`
builds. Thus the wall-time result includes both less CPU work and deliberate
decode/assembly overlap.

## Changes represented

- Bypass the multi-input merge heap for a single alignment input and reuse the
  reader-owned BAM record.
- Retain exon and junction-vector capacity while refilling that record.
- Validate and cache StringTie's frequently queried BAM auxiliary tags in one
  pass per alignment.
- Replace `sprintf` in integer `GStr::append` overloads with bounded decimal
  conversion.
- Pipeline ordered BGZF decompression with producer-side alignment handling.
- Add the missing `tmerge.h` dependency for safe incremental builds.

## Correctness gate

The final binary matched all nine supplied expected outputs after comment-line
normalization: short reads, short plus super-reads, guided short, long, guided
long, mixed, guided mixed, `-N`, and nascent-guided modes. The multi-input mixed
tests exercise the unchanged merge-heap path. Integer formatting was also
checked at zero and every signed/unsigned 32-bit and 64-bit endpoint.

Raw result files are retained locally under `benchmark-results/` (ignored by
Git). `history.csv` contains the baseline and this checkpoint in a graph-ready
format.
