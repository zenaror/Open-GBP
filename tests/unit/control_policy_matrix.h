/*
 * control_policy_matrix.h -- Issue #145 (Phase 7's E2): the SAME matrix, run through every probe family that has a
 * CONTROL guard, against the mock's SYNTHETIC device. Included by each family's own unit test (which supplies CHECK,
 * the mock setup and the run function); nothing here is physical evidence.
 *
 *   for every bit b of the byte and every snapshot kind the family has:
 *     b = 0x01  the run PROCEEDS as the unchanged run does, control_ok stays 1, the tolerance is COUNTED and the
 *               CONTROLTOL record is in the log;
 *     b != 0x01 the guard TRIPS exactly as it did before the policy (the family's own reason string);
 *   the restore read-back: 0x01 accepted (and counted), the seven others fail the restore;
 *   and one combined case: 0x01 plus one strict bit trips (the tolerance never masks a second difference).
 *
 * THE KINDS: PREUNMASK (the device's byte at the pre-unmask snapshot), POSTACK and REARMPOST (the byte changes by
 * itself after the Nth IRQ write), RESTORE (the device holds a flipped bit only after the restore write), and PREACK
 * (the byte changes by itself when the Nth delivery is made, so the PREACK snapshot is the first to see it; only a
 * family whose ack path reaches gbp_irq_service_ack with require_control has it). A family that has no such kind passes
 * 0 for it. PRESVC and POSTDRAIN share one check function with POSTACK in avsvc, video and initirq4 (common_checks), so
 * the POSTACK kind is their kind; vstate's PRESVC is reached through the REARMPOST kind (its next check after the
 * re-arm). THE NEGATIVE REQUIREMENTS are asserted in every run of the matrix, tolerated or not: two CONTROL writes
 * and no more, the last of them the ORIGINAL byte, the same IRQ writes as the unchanged run, and power_cycle_required.
 */
#ifndef OPENGBP_TESTS_CONTROL_POLICY_MATRIX_H
#define OPENGBP_TESTS_CONTROL_POLICY_MATRIX_H

#include <string.h>

struct cp_result {
    int changed;                       /* the run ended on the family's CONTROL-changed anomaly */
    const char *reason;                /* the family's reason string (may be NULL) */
    int status;                        /* the family's status enum, compared with the baseline's */
    int control_ok;                    /* the family's control_ok flag */
    int ack_skipped_control;           /* the family's ack was SKIPPED because CONTROL changed (the PREACK guard) */
    const struct gbp_initirqa_result *a;
};

struct cp_family {
    const char *name;
    void (*setup)(struct gbp_mock *m);
    void (*run)(struct gbp_mock *m, struct ringlog *rl, struct cp_result *out);
    unsigned w_postack, w_rearm;       /* IRQ-write number after which CONTROL changes (0 = the family has no such kind) */
    unsigned w_preack_delivery;        /* delivery number after which CONTROL changes, seen first at PREACK (0 = no such kind) */
    const char *reason_preunmask, *reason_postack, *reason_rearm;   /* substrings of the strict reason */
};

static int cp_has_line(const struct ringlog *rl, const char *needle)
{
    size_t i;
    for (i = 0; i < rl->count; i++) if (strstr(ringlog_line(rl, i), needle)) return 1;
    return 0;
}

static int cp_reason_has(const struct cp_result *r, const char *needle)
{
    return r->reason && needle && strstr(r->reason, needle) != NULL;
}

static void cp_run_matrix(const struct cp_family *f)
{
    struct gbp_mock m;
    struct ringlog rl;
    struct cp_result base, r;
    uint8_t exp, orig;
    unsigned b, kind, base_cw, base_irqw;
    static const char *const KIND[5] = { "PREUNMASK", "POSTACK", "REARMPOST", "RESTORE", "PREACK" };

    printf("-- Issue #145 (%s): CONTROL bit 0x01 tolerated, the seven others strict, at every snapshot kind\n", f->name);
    f->setup(&m);
    f->run(&m, &rl, &base);
    CHECK(base.changed == 0);
    CHECK(base.control_ok == 1);
    CHECK(base.a->control_tol_n == 0u);            /* a run that never exercised the tolerance says nothing about it */
    CHECK(!cp_has_line(&rl, "CONTROLTOL"));
    exp = base.a->control_exp;
    orig = base.a->control_orig;
    base_cw = m.control_writes;
    base_irqw = base.a->irq_writes_attempted;
    CHECK(base_cw == 2u);                          /* the transform and the restore: never a third CONTROL write */
    CHECK(m.last_control_write == orig);
    CHECK(base.a->power_cycle_required == 1);

    for (kind = 0; kind < 5u; kind++) {
        for (b = 0; b < 8u; b++) {
            const uint8_t bit = (uint8_t)(1u << b);
            const uint8_t v = (uint8_t)(exp ^ bit);
            const char *want = kind == 0 ? f->reason_preunmask : kind == 1 ? f->reason_postack : f->reason_rearm;
            if (kind == 1 && !f->w_postack) continue;
            if (kind == 2 && !f->w_rearm) continue;
            if (kind == 4 && !f->w_preack_delivery) continue;
            f->setup(&m);
            if (kind == 0) m.control_on_install = v;
            else if (kind == 1) { m.control_change_after_irq_write = f->w_postack; m.control_change_value = v; }
            else if (kind == 2) { m.control_change_after_irq_write = f->w_rearm; m.control_change_value = v; }
            else if (kind == 3) { m.control_dev_xor = bit; m.control_dev_xor_from_write = 2u; }
            else { m.control_change_on_delivery = f->w_preack_delivery; m.control_change_on_delivery_value = v; }
            f->run(&m, &rl, &r);
            /* the negative requirements, in EVERY run of the matrix, tolerated or tripped: the runtime writes CONTROL twice (the
             * transform, then the ORIGINAL byte back), never anything else, and the power-cycle rule is still armed */
            CHECK(m.control_writes == base_cw);
            CHECK(m.last_control_write == orig);
            CHECK(r.a->power_cycle_required == 1);
            if (kind == 4u) {
                /* PREACK: bit 0x01 lets the ack proceed and is counted; a strict bit SKIPS the ack (control_changed) */
                if (bit == 0x01u) {
                    CHECK(r.ack_skipped_control == 0);
                    CHECK(r.control_ok == 1);
                    CHECK(r.a->control_tol_n > 0u);
                    CHECK(cp_has_line(&rl, "CONTROLTOL"));
                    CHECK(r.a->irq_writes_attempted == base_irqw);
                } else {
                    CHECK(r.ack_skipped_control == 1);
                    CHECK(r.a->irq_writes_attempted < base_irqw);    /* the ack write never happened */
                }
                continue;
            }
            if (kind < 3u) {
                if (bit == 0x01u) {
                    if (!(r.changed == 0 && r.control_ok == 1 && r.status == base.status && r.a->control_tol_n > 0u &&
                          cp_has_line(&rl, "CONTROLTOL")))
                        fprintf(stderr, "  [%s %s bit 0x%02x: changed=%d control_ok=%d status=%d/%d tol_n=%u]\n", f->name, KIND[kind],
                                bit, r.changed, r.control_ok, r.status, base.status, (unsigned)r.a->control_tol_n);
                    CHECK(r.changed == 0);
                    CHECK(r.control_ok == 1);
                    CHECK(r.status == base.status);
                    CHECK(r.a->control_tol_n > 0u);
                    CHECK(r.a->control_tol_first_vote == v);
                    CHECK(r.a->control_tol_first_exp == exp);
                    CHECK(cp_has_line(&rl, "CONTROLTOL"));
                    CHECK(r.a->irq_writes_attempted == base_irqw);      /* a tolerated run makes the same IRQ writes */
                    CHECK(r.a->control_tol_first_site[0] != '\0');      /* the record says WHERE it was first found */
                    if (kind == 0u) CHECK(strstr(r.a->control_tol_first_site, "PREUNMASK") != NULL);
                } else {
                    if (!(r.changed == 1 && cp_reason_has(&r, want)))
                        fprintf(stderr, "  [%s %s bit 0x%02x: changed=%d reason=%s status=%d]\n", f->name, KIND[kind], bit, r.changed,
                                r.reason ? r.reason : "(null)", r.status);
                    CHECK(r.changed == 1);
                    CHECK(cp_reason_has(&r, want));
                    CHECK(r.control_ok == 0);
                    CHECK(r.a->control_tol_n == 0u);   /* a strict trip is not a tolerated comparison */
                }
            } else {
                /* the restore: the guards saw the exact byte; only the read-back sees the flipped bit */
                CHECK(r.changed == 0);
                if (bit == 0x01u) {
                    CHECK(r.a->control_restore_ok == 1);
                    CHECK(r.a->control_tol_restore == 1);
                    CHECK(r.a->control_tol_n > 0u);
                    CHECK(cp_has_line(&rl, "CONTROLTOL"));
                    CHECK(cp_has_line(&rl, "restore=1"));
                } else {
                    CHECK(r.a->control_restore_ok == 0);
                    CHECK(r.a->restore_reason && strcmp(r.a->restore_reason, "control_restore_failed") == 0);
                    CHECK(r.a->control_tol_restore == 0);
                }
            }
        }
    }

    /* the tolerance never hides a second difference: bit 0x01 AND a strict bit at the pre-unmask snapshot trips */
    for (b = 1; b < 8u; b++) {
        f->setup(&m);
        m.control_on_install = (uint8_t)(exp ^ 0x01u ^ (1u << b));
        f->run(&m, &rl, &r);
        CHECK(r.changed == 1);
        CHECK(cp_reason_has(&r, f->reason_preunmask));
    }
}

#endif
