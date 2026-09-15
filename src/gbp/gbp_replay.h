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
};

void gbp_replay_init(struct gbp_replay *r, const char *script);
void gbp_replay_transport(struct gbp_replay *r, struct gbp_transport *t);

/* Parses one hex byte pair sequence; returns number of bytes decoded. */
size_t gbp_hex_decode(const char *hex, uint8_t *out, size_t cap);

#ifdef __cplusplus
}
#endif
#endif
