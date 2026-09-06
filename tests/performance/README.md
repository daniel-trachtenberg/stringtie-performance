# Serial optimization correctness tests

Run these commands from the repository root. These are correctness tests, not
timing benchmarks. Keep assertions enabled: **do not add `-DNDEBUG`**.

The commands below were validated with Apple Clang on macOS. They instrument
the changed C++ implementations with AddressSanitizer and UndefinedBehaviorSanitizer.
The auxiliary-tag test links the normally built bundled HTSlib; it does not
rebuild HTSlib itself with sanitizers.

Prepare the bundled libraries if they have not already been built:

```sh
make ./htslib/libhts.a
mkdir -p build/serial-tests
```

Compile the four tests:

```sh
c++ -std=c++11 -O1 -g -fno-exceptions -fno-rtti \
  -fsanitize=address,undefined -I. -Igclib -Ihtslib \
  tests/performance/aux_equivalence.cpp \
  gclib/GSam.cpp gclib/GBase.cpp gclib/GStr.cpp gclib/gdna.cpp \
  htslib/libhts.a htslib/xlibs/lib/libbz2.a \
  htslib/xlibs/lib/liblzma.a htslib/xlibs/lib/libdeflate.a -lz \
  -o build/serial-tests/aux_equivalence

c++ -std=c++11 -O1 -g -fno-exceptions -fno-rtti \
  -fsanitize=address,undefined -I. -Igclib -Ihtslib \
  tests/performance/pair_equivalence.cpp gclib/GBase.cpp gclib/GStr.cpp \
  -o build/serial-tests/pair_equivalence

c++ -std=c++11 -O1 -g -fno-exceptions -fno-rtti \
  -fsanitize=address,undefined -I. -Igclib -Ihtslib \
  tests/performance/pool_lifecycle.cpp \
  gclib/GBase.cpp gclib/GStr.cpp gclib/gff.cpp gclib/gdna.cpp \
  gclib/GFaSeqGet.cpp gclib/GFastaIndex.cpp \
  -o build/serial-tests/pool_lifecycle

c++ -std=c++11 -O1 -g -fno-exceptions -fno-rtti \
  -fsanitize=address,undefined -I. -Igclib -Ihtslib \
  tests/performance/bitvec_equivalence.cpp gclib/GBase.cpp \
  -o build/serial-tests/bitvec_equivalence
```

On Linux, append `-pthread -lm` to the auxiliary-tag link command if required by
the bundled HTSlib build. Run the tests with sanitizer failures made fatal:

```sh
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 build/serial-tests/aux_equivalence
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 build/serial-tests/pair_equivalence
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 build/serial-tests/pool_lifecycle
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 build/serial-tests/bitvec_equivalence
```

Leak detection is disabled because LeakSanitizer is unavailable on the tested
macOS host. It can be enabled on supported hosts. These results establish no
ASan/UBSan error in the exercised code; they do not constitute a leak-detector run.

## Contracts checked

| Test | Contract and expected completed checks |
| --- | --- |
| `aux_equivalence.cpp` | 20,300 comparisons: general tag lookup pointer/`errno` equivalence with HTSlib; typed assembly accessor value equivalence with the general APIs; duplicate tags, unknown tags, scalar/string/array payloads, every truncation of the fixture, selected corruptions, repeated lookups, and strand interpretation. The new enum accessors intentionally do not define `errno`; existing string-tag APIs retain their behavior. |
| `pair_equivalence.cpp` | 62,025 differential/ownership checks against the original string-key `GHash<int>`: 10,000 initial random keys, table growth, 100,000 randomized operations, first-value retention on duplicate insertion, lookup-and-removal, reinsertion, clearing, and copied ownership of temporary read names. Signed position/hit extrema are tested with noncolliding names. Production callers use positive mapped positions; arbitrary negative positions can make the former string representation ambiguous. |
| `pool_lifecycle.cpp` | 40,000 populated/reset read lifecycles across assembly and merge modes: complete field reset, shared junction-pointer lifetime, transcript-info ownership, vector capacity cutoff, and the 4,096-object retention limit. |
| `bitvec_equivalence.cpp` | 301,088 vector pairs, four equivalence assertions per pair: allocation-free containment versus the previous intersection/equality expression, in-place union versus allocating union, and logical contents after reserve/clear/resize, including empty and unequal-sized vectors. |

The benchmark harness has separate Python checks for output normalization,
failure reporting, stale-output rejection, resource recording, alternating run
order, and rejection of additional process threads:

```sh
python3 -m unittest discover -s tests/performance -p 'test_*.py'
```

End-to-end GTF comparisons and runtime measurements are separate requirements.
Use `scripts/benchmark_serial.py` with both programs built using `NOTHREADS`;
`-p 1` alone does not enforce one operating-system thread. Keep compilation and
these tests idle while collecting timing results.
