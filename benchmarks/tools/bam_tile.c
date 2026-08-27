#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "htslib/hts.h"
#include "htslib/sam.h"

static void fail(const char *message, const char *path) {
    if (path)
        fprintf(stderr, "bam_tile: %s: %s\n", message, path);
    else
        fprintf(stderr, "bam_tile: %s\n", message);
    exit(1);
}

static int64_t parse_positive_i64(const char *text, const char *name) {
    char *end = NULL;
    errno = 0;
    long long value = strtoll(text, &end, 10);
    if (errno || !end || *end || value <= 0) {
        fprintf(stderr, "bam_tile: invalid %s: %s\n", name, text);
        exit(2);
    }
    return (int64_t)value;
}

int main(int argc, char **argv) {
    if (argc != 6) {
        fprintf(stderr,
                "Usage: bam_tile IN.bam OUT.bam COPIES STRIDE BASE_START_1BASED\n");
        return 2;
    }

    const char *input = argv[1];
    const char *output = argv[2];
    const int64_t copies = parse_positive_i64(argv[3], "copies");
    const int64_t stride = parse_positive_i64(argv[4], "stride");
    const int64_t base0 = parse_positive_i64(argv[5], "base start") - 1;

    samFile *in = sam_open(input, "r");
    if (!in)
        fail("cannot open input", input);
    sam_hdr_t *header = sam_hdr_read(in);
    if (!header)
        fail("cannot read header", input);
    bam1_t *record = bam_init1();
    if (!record)
        fail("cannot allocate record", NULL);

    int32_t target_tid = -1;
    int32_t previous_tid = -1;
    int64_t previous_position = -1;
    int64_t minimum_position = INT64_MAX;
    int64_t maximum_end = -1;
    int64_t source_records = 0;
    int read_status;

    while ((read_status = sam_read1(in, header, record)) >= 0) {
        /* StringTie ignores unmapped records, so the throughput fixture does too. */
        if (record->core.flag & BAM_FUNMAP)
            continue;
        if (target_tid < 0)
            target_tid = record->core.tid;
        if (record->core.tid != target_tid)
            fail("input must have mapped records on exactly one reference", input);
        if (previous_tid > record->core.tid ||
            (previous_tid == record->core.tid &&
             previous_position > record->core.pos))
            fail("input is not coordinate sorted", input);
        previous_tid = record->core.tid;
        previous_position = record->core.pos;
        if (record->core.pos < minimum_position)
            minimum_position = record->core.pos;
        int64_t end = bam_endpos(record);
        if (end > maximum_end)
            maximum_end = end;
        source_records++;
    }
    if (read_status < -1)
        fail("error reading input", input);
    if (target_tid < 0 || source_records == 0)
        fail("no mapped records", input);
    if (sam_close(in) < 0)
        fail("error closing input", input);

    const int64_t source_span = maximum_end - minimum_position;
    if (stride <= source_span)
        fail("stride must exceed source alignment span", NULL);
    const int64_t target_length = sam_hdr_tid2len(header, target_tid);
    const int64_t final_end = base0 + (copies - 1) * stride + source_span;
    if (base0 < 0 || final_end > target_length) {
        fprintf(stderr,
                "bam_tile: output exceeds %s length (%" PRId64
                "): final end=%" PRId64 "\n",
                sam_hdr_tid2name(header, target_tid), target_length, final_end);
        return 2;
    }

    samFile *out = sam_open(output, "wb");
    if (!out)
        fail("cannot open output", output);
    if (sam_hdr_write(out, header) < 0)
        fail("cannot write header", output);

    int64_t written = 0;
    for (int64_t copy = 0; copy < copies; ++copy) {
        in = sam_open(input, "r");
        if (!in)
            fail("cannot reopen input", input);
        sam_hdr_t *copy_header = sam_hdr_read(in);
        if (!copy_header)
            fail("cannot reread header", input);
        const int64_t delta = base0 + copy * stride - minimum_position;
        while ((read_status = sam_read1(in, copy_header, record)) >= 0) {
            if (record->core.flag & BAM_FUNMAP)
                continue;
            record->core.pos += delta;
            if (record->core.mtid == target_tid && record->core.mpos >= 0)
                record->core.mpos += delta;
            if (sam_write1(out, header, record) < 0)
                fail("cannot write record", output);
            written++;
        }
        if (read_status < -1)
            fail("error rereading input", input);
        sam_hdr_destroy(copy_header);
        if (sam_close(in) < 0)
            fail("error closing input copy", input);
    }
    if (sam_close(out) < 0)
        fail("error closing output", output);

    bam_destroy1(record);

    /* Indexing and a complete readback validate structure, count, and ordering. */
    if (sam_index_build3(output, NULL, 0, 1) != 0)
        fail("index build failed (invalid or unsorted BAM)", output);

    in = sam_open(output, "r");
    if (!in)
        fail("cannot reopen output", output);
    sam_hdr_t *output_header = sam_hdr_read(in);
    if (!output_header)
        fail("cannot reread output header", output);
    record = bam_init1();
    previous_tid = -1;
    previous_position = -1;
    int64_t verified = 0;
    while ((read_status = sam_read1(in, output_header, record)) >= 0) {
        if (record->core.flag & BAM_FUNMAP)
            continue;
        if (previous_tid > record->core.tid ||
            (previous_tid == record->core.tid &&
             previous_position > record->core.pos))
            fail("generated BAM is not coordinate sorted", output);
        previous_tid = record->core.tid;
        previous_position = record->core.pos;
        verified++;
    }
    if (read_status < -1)
        fail("error validating output", output);
    if (verified != written)
        fail("record count mismatch after validation", output);

    printf("source_records=%" PRId64 " copies=%" PRId64
           " output_records=%" PRId64 " reference=%s source_span=%" PRId64
           " stride=%" PRId64 " first_pos=%" PRId64
           " final_end=%" PRId64 "\n",
           source_records, copies, written,
           sam_hdr_tid2name(header, target_tid), source_span, stride, base0 + 1,
           final_end);

    bam_destroy1(record);
    sam_hdr_destroy(output_header);
    sam_close(in);
    sam_hdr_destroy(header);
    return 0;
}
