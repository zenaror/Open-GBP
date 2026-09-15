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
 *                                 irq_unmask; the handler record that the physical
 *                                 handler produced during the window (all zero when it
 *                                 never ran) becomes visible to irq_record afterwards
 *   I m                           irq_mask
 *   I r                           irq_restore
 * irq_record consumes no line. The interrupt-path operations are exposed
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
};

void gbp_replay_init(struct gbp_replay *r, const char *script);
void gbp_replay_transport(struct gbp_replay *r, struct gbp_transport *t);

/* Parses one hex byte pair sequence; returns number of bytes decoded. */
size_t gbp_hex_decode(const char *hex, uint8_t *out, size_t cap);

#ifdef __cplusplus
}
#endif
#endif
