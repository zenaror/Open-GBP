/*
 * gbp_init_irq_probe.h — GBP-INIT-002: after the validated CONTROL
 * transform, is a PI HSP interrupt (IRQ 26) observed within a bounded
 * window once the PI mask is opened, and what does INTSR do around the
 * handler's write-1-to-clear?
 *
 * Normative description: docs/research/HARDWARE_TESTS.md (GBP-INIT-002),
 * docs/research/DEVLOG.md 2026-09-15 (design), docs/protocol/
 * INITIALIZATION.md §9 (rules R1–R8). Reference order followed: GBI's
 * (transform → IRQ_Request → __UnmaskIrq), with a one-shot self-masking
 * handler (gbp_irq_oneshot.h) instead of GBI's thread signal. GBI is an
 * independent mature implementation; the Nintendo Start-up Disc (the
 * official reference) unmasks before its device writes and is NOT what
 * this probe reproduces.
 *
 * Sequence (the order is mandatory and checked by the host mock):
 *   AR_INFO[5:3] := 3 → presence gate (must be PRESENT) → PI precondition
 *   (INTSR bit 13 == 0, INTMR bit 13 == 0, else abort — never adjust) →
 *   S0 → CONTROL shape (bit 0x10 set, bits 0x0C clear, unambiguous) →
 *   irq_install (previous handler kept) → CONTROL := (v & ~0x10) | 0x0C
 *   (GBI layout) → S1 (still masked) → t_unmask, __UnmaskIrq → wait for
 *   fired or T_MAX → __MaskIrq → S2 (INTSR sampled twice) → teardown:
 *   CONTROL := v → S3 → single INTSR W1C only if bit 13 is still set →
 *   previous handler back → mask state verified → AR_INFO → S4.
 * There is NO unmask before the transform (no idle-unmask stage).
 *
 * Writes: AR_INFO bits 3–5, TEST (handshake), CONTROL (transform +
 * restore), INTMR through libogc2's __MaskIrq/__UnmaskIrq only, INTSR
 * W1C 0x2000. Read only: the GBP IRQ block. Never touched: KEYPAD,
 * VIDEO, AUDIO, SIOCTL, SIODATA.
 *
 * T_MAX is an operational bound (screen and SD log must always happen),
 * not a property of the Game Boy Player: a timeout means "no IRQ 26
 * observed within T_MAX", nothing more.
 */
#ifndef OPENGBP_GBP_INIT_IRQ_PROBE_H
#define OPENGBP_GBP_INIT_IRQ_PROBE_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_transport.h"
#include "gbp_detect.h"
#include "../log/ringlog.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_INITIRQ_SNAPSHOTS 5   /* S0..S4 */

struct gbp_initirq_config {
    uint8_t patterns[4];
    unsigned npatterns;
    unsigned expansion_code;      /* AR_INFO bits 3-5 during the experiment (3) */
    uint8_t clear_mask;           /* 0x10 */
    uint8_t set_mask;             /* 0x0C */
    int require_idle_shape;       /* precondition: (v & clear_mask) != 0 && (v & set_mask) == 0 */
    uint32_t t_max_ticks;         /* wait bound after the unmask, in transport ticks */
    uint32_t t_max_ms;            /* the same bound in ms (log only) */
    uint32_t tb_hz;               /* ticks per second, for the µs conversion (0 = unknown) */
};

/* Defaults: patterns C3/3C/FF/00, code 3, transform (v & ~0x10) | 0x0C,
 * T_MAX 2000 ms at 40.5 MHz (81 000 000 ticks). */
void gbp_initirq_config_default(struct gbp_initirq_config *cfg);

struct gbp_initirq_snapshot {
    char id[4];                   /* "S0".."S4" */
    int taken;
    uint32_t ticks;
    uint32_t since_write;         /* ticks since the experimental CONTROL write (0 if before) */
    uint32_t since_unmask;        /* ticks since the unmask (0 if before) */
    int pi_ok;
    uint32_t intsr, intmr;
    int pi2_ok;                   /* S2 only: second INTSR/INTMR sample */
    uint32_t intsr2, intmr2;
    gbp_status control_rc, irq_rc, test_rc;
    int has_test;
    uint8_t control[GBP_BLOCK_SIZE];
    uint8_t irq[GBP_BLOCK_SIZE];
    uint8_t test[GBP_BLOCK_SIZE];
    uint8_t control_vote;         /* GBI semantic value */
    uint8_t control_b1f;          /* Start-up Disc semantic value (byte 0x1F) */
    uint16_t irq_disc;            /* bytes 0x1D/0x1F (Start-up Disc reading) */
    uint16_t irq_gbi;             /* GBI vote reading */
};

/* Experimental result. Restore results are reported separately
 * (restore_ok / restore_reason): a timeout is not a transport failure,
 * and a failed restore does not change what was observed. */
typedef enum {
    GBP_INITIRQ_OK_IRQ_OBSERVED = 0,     /* handler fired within T_MAX */
    GBP_INITIRQ_TIMEOUT_NO_IRQ_OBSERVED, /* no IRQ 26 observed within T_MAX (nothing more) */
    GBP_INITIRQ_ABORT_ARINFO,            /* AR_INFO unreadable / not settable */
    GBP_INITIRQ_ABORT_NOT_PRESENT,       /* verdict != PRESENT (absent, inconsistent, no data) */
    GBP_INITIRQ_ABORT_PI_PRECONDITION,   /* PI unreadable, INTMR bit 13 already enabled, or INTSR bit 13 set */
    GBP_INITIRQ_ABORT_CONTROL_READ,      /* CONTROL unreadable or ambiguous */
    GBP_INITIRQ_ABORT_CONTROL_SHAPE,     /* semantic value not in the required idle shape */
    GBP_INITIRQ_ABORT_HANDLER_INSTALL,   /* no IRQ path in the transport, or install failed */
    GBP_INITIRQ_ABORT_UNMASK,            /* unmask failed or INTMR bit 13 did not become 1 */
    GBP_INITIRQ_TRANSPORT_ERROR          /* a transfer failed after the handler was installed */
} gbp_initirq_status;

struct gbp_initirq_result {
    gbp_initirq_status status;
    const char *reason;
    int restore_ok;               /* 1 if every attempted restore succeeded */
    const char *restore_reason;   /* first restore failure, or "-" */
    /* teardown flags: what was changed and must be undone */
    int arinfo_changed, handler_installed, control_written, irq_unmasked, irq_masked_again, pi_ack_performed;
    /* AR_INFO */
    uint16_t arinfo_orig, arinfo_exp, arinfo_final;
    int arinfo_restored;          /* 1 ok, 0 failed, -1 not attempted */
    /* detection */
    struct gbp_handshake_result det;
    uint32_t base;
    /* PI precondition */
    int pi_pre_ok;
    uint32_t intsr_pre, intmr_pre;
    /* CONTROL */
    uint8_t control_orig, control_exp;
    uint8_t write_raw[GBP_BLOCK_SIZE], restore_raw[GBP_BLOCK_SIZE];
    gbp_status write_rc, restore_rc;
    int control_restored;         /* -1 not attempted, 1 readback vote == orig, 0 otherwise */
    /* handler */
    gbp_status install_rc;
    int old_handler_null;         /* 1 if the previous handler was NULL, 0 if not, -1 unknown */
    gbp_status handler_restore_rc;
    int handler_restored;         /* -1 not attempted, 1 ok, 0 failed */
    /* unmask / wait */
    uint32_t t_unmask, t_post_unmask;
    uint32_t intsr_pre_unmask, intmr_pre_unmask, intsr_post_unmask, intmr_post_unmask;
    int pi_pre_unmask_ok, pi_post_unmask_ok;
    gbp_status unmask_rc, mask_rc;
    uint32_t t_wait_end, wait_ticks;
    unsigned polls;
    int timed_out;
    /* handler record (copied while masked) */
    struct gbp_irq_record rec;
    int fired;
    uint32_t latency_ticks, latency_us;
    int unexpected_reentry;
    /* PI cleanup (teardown) */
    int cleanup_ack_performed;
    uint32_t cleanup_intsr_before, cleanup_intsr_after;
    gbp_status cleanup_rc;
    /* mask state at the end */
    uint32_t intmr_final;
    int mask_ok;                  /* -1 not checked, 1 INTMR bit 13 clear at the end, 0 not */
    /* snapshots */
    struct gbp_initirq_snapshot snap[GBP_INITIRQ_SNAPSHOTS];
    unsigned errors;              /* transport failures */
    int transport_ok;
};

/* Runs the experiment; always returns after the teardown. Returns 0 if
 * it completed (aborted or not), -1 only if AR_INFO could not be read. */
int gbp_initirq_probe_run(const struct gbp_transport *t, struct ringlog *log,
                          const struct gbp_initirq_config *cfg, struct gbp_initirq_result *res);

int gbp_initirq_summary(const struct gbp_initirq_result *res, char *dst, size_t cap);
const char *gbp_initirq_status_name(gbp_initirq_status s);

#ifdef __cplusplus
}
#endif
#endif
