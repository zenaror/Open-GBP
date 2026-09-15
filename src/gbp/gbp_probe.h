/*
 * gbp_probe.h — GBP-PROBE-001 logic: read-only presence probe with the
 * AR_INFO expansion-code A/B experiment (docs/research/HARDWARE_TESTS.md).
 *
 * The logic is hardware-independent: it drives a gbp_transport and writes
 * every observation as one text record into a ringlog. Interpretation
 * (match/mismatch) is *also* recorded but never replaces the raw block.
 *
 * Writes performed on the GBP side: only 32-byte blocks to index 0 (TEST),
 * filled with one of the configured pattern bytes.  Writes on the
 * GameCube side: AR_INFO (0xCC005012) bits 3-5 only, restored at the end.
 */
#ifndef OPENGBP_GBP_PROBE_H
#define OPENGBP_GBP_PROBE_H

#include <stdint.h>
#include "gbp_transport.h"
#include "gbp_detect.h"
#include "../log/ringlog.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_PROBE_MAX_PATTERNS 8
#define GBP_PROBE_MAX_INDICES 8
#define GBP_PROBE_MODES 2   /* A = original AR_INFO, B = expansion code forced */

struct gbp_probe_config {
    uint8_t patterns[GBP_PROBE_MAX_PATTERNS];
    unsigned npatterns;
    unsigned indices[GBP_PROBE_MAX_INDICES];   /* blocks to dump raw, e.g. {0x0,0x4,0xD} */
    unsigned nindices;
    unsigned expansion_code;                   /* MODE B value for AR_INFO bits 3-5 (3) */
    int run_mode_b;                            /* 0 = only MODE A */
    int handshake_index;                       /* block index used for the handshake (0 = TEST) */
};

/* Default = exactly GBP-PROBE-001 as specified. */
void gbp_probe_config_default(struct gbp_probe_config *cfg);

struct gbp_probe_mode_result {
    uint16_t arinfo_before;     /* AR_INFO read at the start of the mode */
    uint16_t arinfo_after;      /* AR_INFO read at the end of the mode */
    uint32_t base;              /* internal ARAM size used for addressing */
    unsigned reads_ok;          /* raw block reads that completed */
    unsigned reads_failed;
    unsigned tests_run;         /* handshake patterns attempted */
    unsigned tests_transport_ok;/* handshakes whose write and read both completed */
    unsigned tests_match_all;   /* all 32 bytes == ~pattern (probe-0001 heuristic, reporting only) */
    unsigned tests_match_1f;    /* byte 0x1F == ~pattern (reporting only) */
    unsigned tests_match_b1;    /* Start-up Disc criterion: byte 1 == ~pattern */
    unsigned tests_match_vote;  /* GBI criterion: majority-vote byte == ~pattern */
    unsigned tests_failed;      /* write or read did not complete */
    gbp_verdict verdict;        /* gbp_presence_verdict() over this mode's handshakes */
    uint8_t raw[GBP_PROBE_MAX_INDICES][GBP_BLOCK_SIZE]; /* last raw dump per index */
    gbp_status raw_rc[GBP_PROBE_MAX_INDICES];
};

struct gbp_probe_result {
    uint16_t arinfo_orig;
    uint16_t arinfo_final;      /* read back after restore */
    int arinfo_changed;         /* 1 if MODE B wrote AR_INFO */
    int arinfo_restored;        /* 1 if final == orig (or never changed) */
    int arinfo_rc;              /* first non-OK status of an AR_INFO access, else 0 */
    struct gbp_probe_mode_result mode[GBP_PROBE_MODES];
    unsigned modes_run;
    unsigned errors;            /* total non-OK transfers */
    /* present[m] = 1 iff mode[m].verdict == GBP_VERDICT_PRESENT (policy of
     * gbp_detect.h: every handshake completed and passed both official
     * criteria). Transport success alone never sets it. */
    int present[GBP_PROBE_MODES];
    int transport_ok;           /* 1 iff every transfer of the run completed */
};

/* Runs the probe. Returns 0 if the sequence completed (whatever the
 * device answered), -1 if AR_INFO could not even be read. */
int gbp_probe_run(const struct gbp_transport *t, struct ringlog *log,
                  const struct gbp_probe_config *cfg, struct gbp_probe_result *res);

/* One-line machine-readable summary, e.g. for USB Gecko:
 * "DONE modes=2 a_present=1 b_present=1 errors=0 changed=1 restored=1 ..." */
int gbp_probe_summary(const struct gbp_probe_result *res, char *dst, size_t cap);

#ifdef __cplusplus
}
#endif
#endif
