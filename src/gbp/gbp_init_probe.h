/*
 * gbp_init_probe.h — GBP-INIT-001: observe the effect of GBI's CONTROL
 * transform `(v & ~0x10) | 0x0C` while the PI HSP interrupt is masked.
 *
 * Provenance (docs/protocol/INITIALIZATION.md §8): GBI Standard's worker
 * thread reads CONTROL (majority vote of the 32 bytes), writes
 * `(v & ~0x10) | 0x04 | 0x08` as a byte replicated over 32 bytes, and only
 * afterwards requests/unmasks PI interrupt 26. GBI is an independent
 * mature implementation, not official Nintendo software; the official
 * Start-up Disc performs the same bit changes in a different order and
 * layout and is NOT what this probe reproduces.
 *
 * The experiment is deliberately short and single-variable:
 *   S0 baseline  → write experimental CONTROL → S1, S2, S3 → write the
 *   ORIGINAL semantic value back → S4 → restore INTMR (if changed) and
 *   AR_INFO → S5.
 * Preconditions for the write: presence == PRESENT (gbp_detect policy),
 * PI registers readable, INTMR bit 13 clear (masked) — made so only by
 * clearing that single bit if needed —, CONTROL readable without
 * ambiguity (vote == byte 0x1F), bit 0x10 set and bits 0x0C clear in the
 * semantic value (the idle shape observed on hardware). Anything else
 * aborts before the write. The IRQ block is never written. No delays are
 * inserted (neither reference has one).
 */
#ifndef OPENGBP_GBP_INIT_PROBE_H
#define OPENGBP_GBP_INIT_PROBE_H

#include <stdint.h>
#include "gbp_transport.h"
#include "gbp_detect.h"
#include "../log/ringlog.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_INIT_SNAPSHOTS 6   /* S0..S5 */

struct gbp_init_config {
    uint8_t patterns[4];
    unsigned npatterns;
    unsigned expansion_code;      /* AR_INFO bits 3-5 during the experiment (3) */
    uint8_t clear_mask;           /* 0x10 */
    uint8_t set_mask;             /* 0x0C */
    int require_idle_shape;       /* precondition: (v & clear_mask) != 0 && (v & set_mask) == 0 */
};

void gbp_init_config_default(struct gbp_init_config *cfg);

struct gbp_init_snapshot {
    char id[4];                   /* "S0".."S5" */
    int taken;
    uint32_t ticks;               /* transport ticks at capture */
    uint32_t ticks_since_write;   /* 0 for S0 */
    int pi_ok;
    uint32_t intsr, intmr;
    gbp_status control_rc, irq_rc, test_rc;
    int has_test;
    uint8_t control[GBP_BLOCK_SIZE];
    uint8_t irq[GBP_BLOCK_SIZE];
    uint8_t test[GBP_BLOCK_SIZE];
    uint8_t control_vote;         /* GBI semantic value */
    uint8_t control_b1f;          /* Start-up Disc semantic value (byte 0x1F) */
    uint16_t irq_disc;            /* bytes 0x1D/0x1F, Start-up Disc reading (report only) */
};

typedef enum {
    GBP_INIT_OK = 0,
    GBP_INIT_ABORT_ARINFO,        /* AR_INFO unreadable / not settable */
    GBP_INIT_ABORT_NOT_PRESENT,   /* verdict != PRESENT */
    GBP_INIT_ABORT_PI,            /* PI registers unavailable or INTMR could not be masked */
    GBP_INIT_ABORT_CONTROL_READ,  /* CONTROL unreadable or ambiguous */
    GBP_INIT_ABORT_CONTROL_SHAPE, /* semantic value not in the required shape */
    GBP_INIT_ERROR_AFTER_WRITE    /* a transfer failed after the experimental write */
} gbp_init_status;

struct gbp_init_result {
    gbp_init_status status;
    const char *abort_reason;
    int control_written;          /* experimental write was issued */
    /* AR_INFO */
    uint16_t arinfo_orig, arinfo_exp, arinfo_final;
    int arinfo_changed, arinfo_restored;
    /* detection */
    struct gbp_handshake_result det;
    uint32_t base;
    /* PI */
    uint32_t intmr_orig, intmr_exp, intmr_final;
    int intmr_changed;            /* 1 if we cleared bit 13 */
    int intmr_restored;           /* 1 restored, 0 failed, -1 unchanged */
    /* CONTROL */
    uint8_t control_orig, control_exp;
    uint8_t write_raw[GBP_BLOCK_SIZE], restore_raw[GBP_BLOCK_SIZE];
    gbp_status write_rc, restore_rc;
    int control_restored;         /* -1 not attempted, 1 readback vote == orig, 0 otherwise */
    int transition_s1_s2;         /* 1 if S1 and S2 differ in CONTROL/IRQ/INTSR */
    struct gbp_init_snapshot snap[GBP_INIT_SNAPSHOTS];
    unsigned errors;
    int transport_ok;
};

/* Runs the experiment; always returns after attempting every restore
 * step that is still possible. Returns 0 if it completed (aborted or
 * not), -1 only if AR_INFO could not even be read. */
int gbp_init_probe_run(const struct gbp_transport *t, struct ringlog *log,
                       const struct gbp_init_config *cfg, struct gbp_init_result *res);

int gbp_init_summary(const struct gbp_init_result *res, char *dst, size_t cap);
const char *gbp_init_status_name(gbp_init_status s);

#ifdef __cplusplus
}
#endif
#endif
