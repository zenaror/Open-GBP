/*
 * gbp_replay.h — trace/replay backend.
 *
 * Answers transport calls from a recorded script, one line per operation,
 * in order:
 *
 *   A r <hex16>            read_arinfo  -> value (rc ok)
 *   A w <hex16>            write_arinfo -> expected value (mismatch = GBP_ERR_BACKEND)
 *   R <hex32addr> <rc> <64hex>    read_block  -> data, rc (rc: ok|timeout|busy|param|backend)
 *   W <hex32addr> <rc>            write_block -> rc (address must match)
 *   P r <hex32 intsr> <hex32 intmr>   read_pi -> values
 *   P w <hex32 intmr>             write_intmr -> expected value (mismatch = GBP_ERR_BACKEND)
 *   P a <hex32 value>             write_intsr (W1C acknowledge) -> expected value
 *   P p <hex32 intsr>             optional: the next poll_intsr returns this value; a
 *                                 poll_intsr call with no such line pending returns the
 *                                 INTSR of the last "P r"/"P p" line and consumes nothing
 *   T <ticks>                     next ticks() call returns this value (physical time base);
 *                                 ticks() calls not matched by a T line return the last
 *                                 value + 1 ("timeline mode", enabled by the first T line)
 *   I i <null|nonnull>            irq_install -> old_was_null
 *   I u <count> <fired> <t_entry> <intsr_before_ack> <intmr_at_entry>
 *       <intsr_after_ack> <intmr_after_mask> <reentry_intsr> <reentry_intmr>
 *       [<intsr_before_w1c> <t_second> <intsr_second> <intmr_second> <reentry_t>]
 *                                 irq_unmask; the handler record that the physical
 *                                 handler produced during the window (all zero when it
 *                                 never ran) becomes visible to irq_record afterwards;
 *                                 the optional five numbers are the extended handler's
 *                                 fields (GBP-INIT-003B logs; absent in older fixtures)
 *   I m                           irq_mask
 *   I r                           irq_restore
 *   I p <gen>                     optional (GBP-INIT-004): irq_prepare publishes generation
 *                                 <gen>; an irq_prepare call with no such line pending
 *                                 consumes nothing (older fixtures never carry one)
 *   B <hex32addr> <hex32len> <rc> [<hex32 crc32>]
 *                                 read_bulk (GBP-AV-SERVICE-001): one whole-block read of
 *                                 <len> bytes at <addr>; the bytes are NOT in the script —
 *                                 they come from the block source the harness attaches
 *                                 (gbp_replay.block_source, fed by the run's `-blocks.bin`
 *                                 sidecar, tools/avdump.py / src/gbp/gbp_avdump.h); with no
 *                                 source the buffer is zero-filled and `blocks_missing`
 *                                 counts it; a crc32 that does not match the bytes delivered
 *                                 counts in `block_crc_mismatches`. The operation is exposed
 *                                 only when the script contains a "B " line.
 * irq_record consumes no line; irq_record_slot returns the "I u" record of the
 * generation that was current when it was consumed (all zero for any other slot);
 * irq_multi_status reports the current generation and the entries consumed so far. The interrupt-path operations are exposed
 * only when the script contains an "I " line (physical logs of
 * GBP-INIT-002 and later); older fixtures keep the transport without an
 * interrupt path, and a probe that needs it stops at its install step.
 *   # comment / blank
 * ticks() returns 10 × operations consumed (no script line).
 *
 * tools/probelog.py can generate such a script from a device log
 * (captures/fixtures/, .gbpreplay files). When the script is exhausted every call
 * returns GBP_ERR_BACKEND and `exhausted` counts them.
 */
#ifndef OPENGBP_GBP_REPLAY_H
#define OPENGBP_GBP_REPLAY_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_transport.h"

#ifdef __cplusplus
extern "C" {
#endif

struct gbp_replay {
    const char *script;   /* NUL-terminated text, lines separated by '\n' */
    size_t pos;           /* current offset into script */
    unsigned step;        /* operations consumed */
    unsigned exhausted;   /* calls made after the script ended */
    unsigned mismatches;  /* calls whose kind/address differed from the script */
    uint16_t arinfo;      /* last value written/read, for convenience */
    int has_irq_ops;      /* script contains "I " lines: the interrupt path is replayed */
    int timeline;         /* script contains "T " lines: ticks() follows them */
    uint32_t last_ticks;  /* last value delivered by ticks() in timeline mode */
    unsigned tick_polls;  /* ticks() calls answered without a T line (timeline mode) */
    uint32_t poll_increment; /* ticks() advance per unmatched call in timeline mode (default 1) */
    uint32_t last_intsr;  /* INTSR of the last "P r" / "P p" line, for poll_intsr */
    int handler_installed;
    struct gbp_irq_record rec;   /* handler record after "I u" */
    uint32_t gen;                /* generation published by the last "I p" (0 after the install) */
    unsigned entries;            /* sum of the "I u" record counts since the install */
    struct gbp_irq_record slots[GBP_IRQ_MULTI_SLOTS];   /* the "I u" record of each generation */
    /* whole-block reads ("B" lines): the bytes come from the attached block source */
    int has_bulk_ops;            /* script contains "B " lines: read_bulk is exposed */
    uint32_t (*block_source)(void *ctx, uint32_t base, uint32_t aram_addr, uint32_t len, uint8_t *out);
    void *block_ctx;             /* returns the bytes copied (0 = unavailable) */
    unsigned bulk_reads;         /* "B" lines consumed */
    unsigned blocks_missing;     /* bulk reads answered with zeros (no source / no bytes) */
    unsigned block_crc_mismatches; /* bulk reads whose bytes did not match the script's crc32 */
};

void gbp_replay_init(struct gbp_replay *r, const char *script);
void gbp_replay_transport(struct gbp_replay *r, struct gbp_transport *t);

/* Parses one hex byte pair sequence; returns number of bytes decoded. */
size_t gbp_hex_decode(const char *hex, uint8_t *out, size_t cap);

#ifdef __cplusplus
}
#endif
#endif
