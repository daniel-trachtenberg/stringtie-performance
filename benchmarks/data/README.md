# Local benchmark data

Place representative coordinate-sorted BAM/CRAM inputs here. All files in this
directory except this README and `.gitkeep` are ignored by Git to avoid
accidentally publishing large or sensitive genomic data.

Use public, redistributable datasets where possible and document accession,
download command, checksum, aligner, reference build, and preprocessing in the
benchmark result or experiment notes.

The checked-in `benchmarks/tools/bam_tile.c` utility can generate the synthetic
throughput fixture described in `benchmarks/BASELINE.md` from the public test
input. It translates one coordinate-sorted, single-contig locus into separated
copies, builds a BAI, and performs a full count/order validation. It intentionally
omits unmapped records and does not rewrite coordinate-bearing auxiliary tags
such as `SA` or `XA`; use it only with inputs for which those limitations are
irrelevant. The output must fit inside the contig length declared by the input
header.
