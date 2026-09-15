#include "gbp_init_irq_probe.h"

#include <stdio.h>
#include <string.h>
#include "gbp_rawlog.h"

/* Defaults for the GameCube: 40.5 MHz time base, T_MAX 2000 ms. */
#define DEFAULT_TB_HZ 40500000u
#define DEFAULT_T_MAX_MS 2000u

void gbp_initirq_config_default(struct gbp_initirq_config *cfg)
{
    memset(cfg, 0, sizeof *cfg);
    cfg->patterns[0] = 0xC3;
    cfg->patterns[1] = 0x3C;
    cfg->patterns[2] = 0xFF;
    cfg->patterns[3] = 0x00;
    cfg->npatterns = 4;
    cfg->expansion_code = 3;
    cfg->clear_mask = 0x10;
    cfg->set_mask = 0x0C;
    cfg->require_idle_shape = 1;
    cfg->tb_hz = DEFAULT_TB_HZ;
    cfg->t_max_ms = DEFAULT_T_MAX_MS;
    cfg->t_max_ticks = (uint32_t)((DEFAULT_TB_HZ / 1000u) * DEFAULT_T_MAX_MS);
}

const char *gbp_initirq_status_name(gbp_initirq_status s)
{
    switch (s) {
    case GBP_INITIRQ_OK_IRQ_OBSERVED: return "ok_irq_observed";
    case GBP_INITIRQ_TIMEOUT_NO_IRQ_OBSERVED: return "timeout_no_irq_observed";
    case GBP_INITIRQ_ABORT_ARINFO: return "abort_arinfo";
    case GBP_INITIRQ_ABORT_NOT_PRESENT: return "abort_not_present";
    case GBP_INITIRQ_ABORT_PI_PRECONDITION: return "abort_pi_precondition";
    case GBP_INITIRQ_ABORT_CONTROL_READ: return "abort_control_read";
    case GBP_INITIRQ_ABORT_CONTROL_SHAPE: return "abort_control_shape";
    case GBP_INITIRQ_ABORT_HANDLER_INSTALL: return "abort_handler_install";
    case GBP_INITIRQ_ABORT_UNMASK: return "abort_unmask";
    case GBP_INITIRQ_TRANSPORT_ERROR: return "transport_error";
    default: return "?";
    }
}

static uint32_t now(const struct gbp_transport *t)
{
    return t->ticks ? t->ticks(t->ctx) : 0u;
}

static uint32_t ticks_to_us(const struct gbp_initirq_config *cfg, uint32_t ticks)
{
    if (!cfg->tb_hz) return 0u;
    return (uint32_t)(((uint64_t)ticks * 1000000u) / cfg->tb_hz);
}

static void restore_fail(struct gbp_initirq_result *res, const char *why)
{
    if (res->restore_ok) res->restore_reason = why;
    res->restore_ok = 0;
}

/* One snapshot: PI, CONTROL raw, IRQ raw (+ TEST raw, + second PI sample). */
static void snapshot(const struct gbp_transport *t, struct ringlog *log, struct gbp_initirq_result *res,
                     unsigned n, int with_test, int second_pi_sample, uint32_t write_ticks, uint32_t unmask_ticks)
{
    struct gbp_initirq_snapshot *s = &res->snap[n];
    char tag[8];

    snprintf(s->id, sizeof s->id, "S%u", n);
    snprintf(tag, sizeof tag, "tag=%s", s->id);
    s->taken = 1;
    s->ticks = now(t);
    s->since_write = write_ticks ? (uint32_t)(s->ticks - write_ticks) : 0u;
    s->since_unmask = unmask_ticks ? (uint32_t)(s->ticks - unmask_ticks) : 0u;
    ringlog_printf(log, "SNAP tag=%s ticks=%lu since_write=%lu since_unmask=%lu", s->id, (unsigned long)s->ticks,
                   (unsigned long)s->since_write, (unsigned long)s->since_unmask);
    s->pi_ok = gbp_rawlog_read_pi(t, log, tag, &s->intsr, &s->intmr);
    if (!s->pi_ok) res->errors++;
    if (second_pi_sample) {
        char tag2[8];
        snprintf(tag2, sizeof tag2, "tag=%sb", s->id);
        /* Two samples separated only by the bookkeeping of the first one:
         * no invented delay. */
        s->pi2_ok = gbp_rawlog_read_pi(t, log, tag2, &s->intsr2, &s->intmr2);
        if (!s->pi2_ok) res->errors++;
    }
    s->control_rc = gbp_rawlog_read_block(t, log, s->id, res->base, GBP_IDX_CONTROL, s->control, &res->errors);
    s->control_vote = gbp_majority_vote_byte(s->control);
    s->control_b1f = s->control[GBP_BLOCK_SIZE - 1u];
    s->irq_rc = gbp_rawlog_read_block(t, log, s->id, res->base, GBP_IDX_IRQ, s->irq, &res->errors);
    s->irq_disc = gbp_irq_value_disc(s->irq);
    s->irq_gbi = gbp_irq_value_gbi(s->irq);
    if (with_test) {
        s->has_test = 1;
        s->test_rc = gbp_rawlog_read_block(t, log, s->id, res->base, GBP_IDX_TEST, s->test, &res->errors);
    }
}

static gbp_status write_control_logged(const struct gbp_transport *t, struct ringlog *log, const char *tag,
                                       uint32_t base, uint8_t value, uint8_t raw_out[GBP_BLOCK_SIZE],
                                       struct gbp_initirq_result *res)
{
    struct gbp_xfer_info info;
    char hex[GBP_BLOCK_SIZE * 2 + 1];
    uint32_t addr = gbp_block_addr(base, GBP_IDX_CONTROL, 0);
    gbp_status rc;

    memset(&info, 0, sizeof info);
    memset(raw_out, value, GBP_BLOCK_SIZE);        /* GBI layout: byte replicated ×32 */
    rc = t->write_block(t->ctx, addr, raw_out, &info);
    if (rc != GBP_OK) res->errors++;
    ringlog_hex(hex, sizeof hex, raw_out, GBP_BLOCK_SIZE);
    ringlog_printf(log, "CTLW %s addr=%08lx semantic=%02x rc=%s ticks=%lu polls=%u dspcr=%04x layout=gbi-replicated data=%s",
                   tag, (unsigned long)addr, (unsigned)value, gbp_status_name(rc), (unsigned long)info.ticks,
                   (unsigned)info.polls, (unsigned)info.dma_status, hex);
    return rc;
}

static void copy_record(const struct gbp_transport *t, struct gbp_initirq_result *res)
{
    struct gbp_irq_record r;
    memset(&r, 0, sizeof r);
    if (t->irq_record && t->irq_record(t->ctx, &r) == GBP_OK) res->rec = r;
}

static void log_handler(struct ringlog *log, const struct gbp_initirq_config *cfg, struct gbp_initirq_result *res)
{
    const struct gbp_irq_record *r = &res->rec;
    res->fired = r->fired ? 1 : 0;
    res->unexpected_reentry = (r->count > 1u) ? 1 : 0;
    if (res->fired) {
        res->latency_ticks = (uint32_t)(r->t_entry - res->t_unmask);   /* wrap-safe */
        res->latency_us = ticks_to_us(cfg, res->latency_ticks);
    }
    ringlog_printf(log, "HANDLER fired=%lu count=%lu t_entry=%lu t_unmask=%lu latency_ticks=%lu latency_us=%lu reentry=%d",
                   (unsigned long)r->fired, (unsigned long)r->count, (unsigned long)r->t_entry,
                   (unsigned long)res->t_unmask, (unsigned long)res->latency_ticks, (unsigned long)res->latency_us,
                   res->unexpected_reentry);
    ringlog_printf(log, "HANDLERPI intsr_before_ack=%08lx intmr_at_entry=%08lx intsr_after_ack=%08lx intmr_after_mask=%08lx reentry_intsr=%08lx reentry_intmr=%08lx",
                   (unsigned long)r->intsr_before_ack, (unsigned long)r->intmr_at_entry,
                   (unsigned long)r->intsr_after_ack, (unsigned long)r->intmr_after_mask,
                   (unsigned long)r->reentry_intsr, (unsigned long)r->reentry_intmr);
}

/*
 * Idempotent teardown, run from every path (INITIALIZATION.md §9 R7):
 *   1. IRQ 26 masked (if the interrupt path was engaged)
 *   2. CONTROL back to the original semantic value (if written) → S3
 *   3. PI observed; 4. single INTSR W1C only if bit 13 is still set
 *   5. previous handler back; 6. mask state verified (expected: masked)
 *   7. AR_INFO back; 8. final snapshot S4 (if anything experimental ran)
 * No filesystem I/O happens here or before this returns.
 */
static void teardown(const struct gbp_transport *t, struct ringlog *log, const struct gbp_initirq_config *cfg,
                     struct gbp_initirq_result *res, uint32_t write_ticks)
{
    int engaged = (res->handler_installed || res->irq_unmasked) ? 1 : 0;
    uint32_t intsr = 0, intmr = 0;
    gbp_status rc;

    /* 1. mask, then copy the handler's record (only while masked) */
    if (engaged) {
        rc = t->irq_mask ? t->irq_mask(t->ctx) : GBP_ERR_BACKEND;
        ringlog_printf(log, "IRQ mask tag=TEARDOWN rc=%s", gbp_status_name(rc));
        if (rc == GBP_OK) res->irq_masked_again = 1; else { res->errors++; restore_fail(res, "mask_failed"); }
        copy_record(t, res);
        log_handler(log, cfg, res);
    }

    /* 2. CONTROL restore with the ORIGINAL semantic value, then S3 */
    if (res->control_written) {
        res->restore_rc = write_control_logged(t, log, "tag=RESTORE", res->base, res->control_orig, res->restore_raw, res);
        snapshot(t, log, res, 3, 0, 0, write_ticks, res->irq_unmasked ? res->t_unmask : 0u);
        res->control_restored = (res->restore_rc == GBP_OK && res->snap[3].control_rc == GBP_OK &&
                                 res->snap[3].control_vote == res->control_orig) ? 1 : 0;
        ringlog_printf(log, "CONTROL restore semantic=%02x readback_vote=%02x readback_b1f=%02x ok=%d",
                       (unsigned)res->control_orig, (unsigned)res->snap[3].control_vote,
                       (unsigned)res->snap[3].control_b1f, res->control_restored);
        if (!res->control_restored) restore_fail(res, "control_restore_failed");
    }

    /* 3./4. PI: a single W1C, only if bit 13 is still set, only while masked */
    if (engaged || res->control_written) {
        if (gbp_rawlog_read_pi(t, log, "tag=CLEANUPCHK", &intsr, &intmr)) {
            res->cleanup_intsr_before = intsr;
            if ((intsr & GBP_PI_HSP_BIT) && !(intmr & GBP_PI_HSP_BIT) && t->write_intsr) {
                res->cleanup_rc = t->write_intsr(t->ctx, GBP_PI_HSP_BIT);
                res->cleanup_ack_performed = 1;
                res->pi_ack_performed = 1;
                if (res->cleanup_rc != GBP_OK) res->errors++;
                if (!gbp_rawlog_read_pi(t, log, "tag=CLEANUP", &intsr, &intmr)) res->errors++;
                res->cleanup_intsr_after = intsr;
                ringlog_printf(log, "CLEANUP performed=1 value=%08lx rc=%s intsr_before=%08lx intsr_after=%08lx intsr13_after=%u",
                               (unsigned long)GBP_PI_HSP_BIT, gbp_status_name(res->cleanup_rc),
                               (unsigned long)res->cleanup_intsr_before, (unsigned long)res->cleanup_intsr_after,
                               (intsr & GBP_PI_HSP_BIT) ? 1u : 0u);
            } else {
                res->cleanup_intsr_after = intsr;
                ringlog_printf(log, "CLEANUP performed=0 intsr=%08lx intsr13=%u intmr13=%u",
                               (unsigned long)intsr, (intsr & GBP_PI_HSP_BIT) ? 1u : 0u,
                               (intmr & GBP_PI_HSP_BIT) ? 1u : 0u);
            }
        } else {
            res->errors++;
        }
    }

    /* 5. previous handler back (verbatim, NULL or not) */
    if (res->handler_installed) {
        res->handler_restore_rc = t->irq_restore ? t->irq_restore(t->ctx) : GBP_ERR_BACKEND;
        res->handler_restored = (res->handler_restore_rc == GBP_OK) ? 1 : 0;
        ringlog_printf(log, "IRQ restore rc=%s ok=%d old_handler=%s", gbp_status_name(res->handler_restore_rc),
                       res->handler_restored, res->old_handler_null == 1 ? "null" : res->old_handler_null == 0 ? "nonnull" : "?");
        if (res->handler_restored) res->handler_installed = 0;
        else { res->errors++; restore_fail(res, "handler_restore_failed"); }
    }

    /* 6. mask state: the original state was "masked" (precondition) */
    if (engaged) {
        int ok = 0;
        if (gbp_rawlog_read_pi(t, log, "tag=MASKCHK", &intsr, &intmr)) {
            ok = (intmr & GBP_PI_HSP_BIT) ? 0 : 1;
            if (!ok && t->irq_mask) {
                rc = t->irq_mask(t->ctx);
                ringlog_printf(log, "IRQ mask tag=RETRY rc=%s", gbp_status_name(rc));
                if (gbp_rawlog_read_pi(t, log, "tag=MASKCHK2", &intsr, &intmr)) ok = (intmr & GBP_PI_HSP_BIT) ? 0 : 1;
            }
            res->intmr_final = intmr;
        } else {
            res->errors++;
        }
        res->mask_ok = ok;
        ringlog_printf(log, "MASK final intmr=%08lx intmr13=%u orig_intmr13=0 ok=%d", (unsigned long)intmr,
                       (intmr & GBP_PI_HSP_BIT) ? 1u : 0u, ok);
        if (!ok) restore_fail(res, "mask_not_restored");
    }

    /* 7. AR_INFO back */
    if (res->arinfo_changed) {
        rc = t->write_arinfo(t->ctx, res->arinfo_orig);
        if (rc != GBP_OK || t->read_arinfo(t->ctx, &res->arinfo_final) != GBP_OK) {
            res->arinfo_final = 0xFFFF;
            res->errors++;
        }
        res->arinfo_restored = (res->arinfo_final == res->arinfo_orig) ? 1 : 0;
        ringlog_printf(log, "ARINFO restore value=%04x rc=%s readback=%04x ok=%d", (unsigned)res->arinfo_orig,
                       gbp_status_name(rc), (unsigned)res->arinfo_final, res->arinfo_restored);
        if (!res->arinfo_restored) restore_fail(res, "arinfo_restore_failed");
    } else {
        res->arinfo_final = res->arinfo_orig;
        res->arinfo_restored = 1;
    }

    /* 8. final snapshot, under the restored AR_INFO */
    if (engaged || res->control_written) {
        snapshot(t, log, res, 4, 0, 0, write_ticks, res->irq_unmasked ? res->t_unmask : 0u);
        ringlog_printf(log, "FINAL arinfo=%04x intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u control=%02x irq=%04x",
                       (unsigned)res->arinfo_final, (unsigned long)res->snap[4].intsr, (unsigned long)res->snap[4].intmr,
                       (res->snap[4].intsr & GBP_PI_HSP_BIT) ? 1u : 0u, (res->snap[4].intmr & GBP_PI_HSP_BIT) ? 1u : 0u,
                       (unsigned)res->snap[4].control_vote, (unsigned)res->snap[4].irq_disc);
    }
}

static void finish(const struct gbp_transport *t, struct ringlog *log, const struct gbp_initirq_config *cfg,
                   struct gbp_initirq_result *res, gbp_initirq_status st, const char *reason, uint32_t write_ticks)
{
    res->status = st;
    res->reason = reason;
    teardown(t, log, cfg, res, write_ticks);
    res->transport_ok = (res->errors == 0) ? 1 : 0;
    ringlog_printf(log, "INITIRQ end status=%s reason=%s restore=%s restore_reason=%s written=%d fired=%d count=%lu timed_out=%d "
                        "control_restored=%d handler_restored=%d mask_ok=%d arinfo_restored=%d cleanup=%d errors=%u transport_ok=%d",
                   gbp_initirq_status_name(st), reason, res->restore_ok ? "ok" : "error", res->restore_reason,
                   res->control_written, res->fired, (unsigned long)res->rec.count, res->timed_out,
                   res->control_restored, res->handler_restored, res->mask_ok, res->arinfo_restored,
                   res->cleanup_ack_performed, res->errors, res->transport_ok);
}

int gbp_initirq_probe_run(const struct gbp_transport *t, struct ringlog *log,
                          const struct gbp_initirq_config *cfg, struct gbp_initirq_result *res)
{
    uint16_t want;
    uint32_t write_ticks = 0;
    gbp_status rc;
    struct gbp_initirq_snapshot *s0;
    struct gbp_irq_record rec0;
    int old_null = -1;

    memset(res, 0, sizeof *res);
    res->restore_ok = 1;
    res->restore_reason = "-";
    res->control_restored = -1;
    res->handler_restored = -1;
    res->arinfo_restored = -1;
    res->mask_ok = -1;
    res->old_handler_null = -1;
    ringlog_printf(log, "INITIRQ start exp_code=%u clear=%02x set=%02x idle_shape=%d npatterns=%u t_max_ms=%lu t_max_ticks=%lu tb_hz=%lu",
                   cfg->expansion_code, (unsigned)cfg->clear_mask, (unsigned)cfg->set_mask, cfg->require_idle_shape,
                   cfg->npatterns, (unsigned long)cfg->t_max_ms, (unsigned long)cfg->t_max_ticks, (unsigned long)cfg->tb_hz);

    /* ---- 1. AR_INFO: bits 3-5 := expansion code (both references do this before the TEST handshake) ---- */
    if (t->read_arinfo(t->ctx, &res->arinfo_orig) != GBP_OK) {
        ringlog_printf(log, "ARINFO orig rc=fail");
        res->status = GBP_INITIRQ_ABORT_ARINFO;
        res->reason = "arinfo_unreadable";
        ringlog_printf(log, "INITIRQ end status=%s reason=%s", gbp_initirq_status_name(res->status), res->reason);
        return -1;
    }
    ringlog_printf(log, "ARINFO orig value=%04x size_code=%u exp_code=%u base=%08lx", (unsigned)res->arinfo_orig,
                   (unsigned)(res->arinfo_orig & 7u), (unsigned)((res->arinfo_orig >> 3) & 7u),
                   (unsigned long)gbp_internal_size_from_arinfo(res->arinfo_orig));
    want = gbp_arinfo_with_expansion(res->arinfo_orig, cfg->expansion_code);
    if (want != res->arinfo_orig) {
        rc = t->write_arinfo(t->ctx, want);
        res->arinfo_changed = 1;
        if (rc != GBP_OK || t->read_arinfo(t->ctx, &res->arinfo_exp) != GBP_OK || res->arinfo_exp != want) {
            res->errors++;
            ringlog_printf(log, "ARINFO exp wanted=%04x rc=%s readback=%04x", (unsigned)want, gbp_status_name(rc),
                           (unsigned)res->arinfo_exp);
            finish(t, log, cfg, res, GBP_INITIRQ_ABORT_ARINFO, "arinfo_not_settable", 0);
            return 0;
        }
    } else {
        res->arinfo_exp = res->arinfo_orig;
    }
    ringlog_printf(log, "ARINFO exp value=%04x exp_code=%u", (unsigned)res->arinfo_exp, (unsigned)((res->arinfo_exp >> 3) & 7u));
    res->base = gbp_internal_size_from_arinfo(res->arinfo_exp);

    /* ---- 2. presence gate (policy of gbp_detect.h) ---- */
    gbp_detect_handshake(t, log, "tag=DET", res->base, GBP_IDX_TEST, cfg->patterns, cfg->npatterns, &res->det);
    ringlog_printf(log, "DET verdict=%s run=%u transport_ok=%u vote_ok=%u b1_ok=%u all32_ok=%u",
                   gbp_verdict_name(res->det.verdict), res->det.run, res->det.transport_ok,
                   res->det.vote_ok, res->det.b1_ok, res->det.all32_ok);
    res->errors += res->det.failed;
    if (res->det.verdict != GBP_VERDICT_PRESENT) {
        finish(t, log, cfg, res, GBP_INITIRQ_ABORT_NOT_PRESENT, gbp_verdict_name(res->det.verdict), 0);
        return 0;
    }

    /* ---- 3. PI preconditions: read only; never adjust ---- */
    res->pi_pre_ok = gbp_rawlog_read_pi(t, log, "tag=PRE", &res->intsr_pre, &res->intmr_pre);
    if (!res->pi_pre_ok) {
        ringlog_printf(log, "PRECOND ok=0 reason=pi_unavailable");
        finish(t, log, cfg, res, GBP_INITIRQ_ABORT_PI_PRECONDITION, "pi_unavailable", 0);
        return 0;
    }
    if (res->intmr_pre & GBP_PI_HSP_BIT) {
        ringlog_printf(log, "PRECOND intsr13=%u intmr13=1 ok=0 reason=intmr13_unmasked",
                       (res->intsr_pre & GBP_PI_HSP_BIT) ? 1u : 0u);
        finish(t, log, cfg, res, GBP_INITIRQ_ABORT_PI_PRECONDITION, "intmr13_unmasked", 0);
        return 0;
    }
    if (res->intsr_pre & GBP_PI_HSP_BIT) {
        ringlog_printf(log, "PRECOND intsr13=1 intmr13=0 ok=0 reason=intsr13_set");
        finish(t, log, cfg, res, GBP_INITIRQ_ABORT_PI_PRECONDITION, "intsr13_set", 0);
        return 0;
    }
    ringlog_printf(log, "PRECOND intsr13=0 intmr13=0 irq_path=%d ok=1 reason=-", gbp_transport_has_irq_path(t));

    /* ---- 4. S0 + CONTROL baseline ---- */
    snapshot(t, log, res, 0, 1, 0, 0, 0);
    s0 = &res->snap[0];
    if (s0->control_rc != GBP_OK || !s0->pi_ok) {
        finish(t, log, cfg, res, GBP_INITIRQ_ABORT_CONTROL_READ, "s0_read_failed", 0);
        return 0;
    }
    if (s0->control_vote != s0->control_b1f) {
        ringlog_printf(log, "CONTROL ambiguous vote=%02x b1f=%02x", (unsigned)s0->control_vote, (unsigned)s0->control_b1f);
        finish(t, log, cfg, res, GBP_INITIRQ_ABORT_CONTROL_READ, "control_ambiguous", 0);
        return 0;
    }
    res->control_orig = s0->control_vote;
    res->control_exp = (uint8_t)((res->control_orig & (uint8_t)~cfg->clear_mask) | cfg->set_mask);
    ringlog_printf(log, "CONTROL semantic orig=%02x exp=%02x method=gbi-majority-vote transform=(v&~%02x)|%02x",
                   (unsigned)res->control_orig, (unsigned)res->control_exp, (unsigned)cfg->clear_mask, (unsigned)cfg->set_mask);
    if (cfg->require_idle_shape &&
        (((res->control_orig & cfg->clear_mask) == 0) || ((res->control_orig & cfg->set_mask) != 0))) {
        finish(t, log, cfg, res, GBP_INITIRQ_ABORT_CONTROL_SHAPE, "control_not_idle_shape", 0);
        return 0;
    }
    if (res->control_exp == res->control_orig) {
        finish(t, log, cfg, res, GBP_INITIRQ_ABORT_CONTROL_SHAPE, "transform_is_noop", 0);
        return 0;
    }

    /* ---- 5. handler first (R1): never a CONTROL write, never an unmask, without it ---- */
    if (!gbp_transport_has_irq_path(t)) {
        ringlog_printf(log, "IRQ install rc=unavailable");
        finish(t, log, cfg, res, GBP_INITIRQ_ABORT_HANDLER_INSTALL, "irq_ops_unavailable", 0);
        return 0;
    }
    res->install_rc = t->irq_install(t->ctx, &old_null);
    if (res->install_rc != GBP_OK) {
        res->errors++;
        ringlog_printf(log, "IRQ install rc=%s", gbp_status_name(res->install_rc));
        finish(t, log, cfg, res, GBP_INITIRQ_ABORT_HANDLER_INSTALL, "install_failed", 0);
        return 0;
    }
    res->handler_installed = 1;
    res->old_handler_null = old_null ? 1 : 0;
    ringlog_printf(log, "IRQ install rc=ok old_handler=%s", old_null ? "null" : "nonnull");

    /* ---- 6. experimental CONTROL write (validated transform, GBI layout), still masked ---- */
    res->write_rc = write_control_logged(t, log, "tag=EXP", res->base, res->control_exp, res->write_raw, res);
    write_ticks = now(t);
    res->control_written = 1;                    /* even on failure: the device may have taken it */
    if (res->write_rc != GBP_OK) {
        finish(t, log, cfg, res, GBP_INITIRQ_TRANSPORT_ERROR, "control_write_failed", write_ticks);
        return 0;
    }

    /* ---- 7. S1: masked snapshot after the transform ---- */
    snapshot(t, log, res, 1, 0, 0, write_ticks, 0);
    if (!res->snap[1].pi_ok || res->snap[1].control_rc != GBP_OK || res->snap[1].irq_rc != GBP_OK) {
        finish(t, log, cfg, res, GBP_INITIRQ_TRANSPORT_ERROR, "s1_read_failed", write_ticks);
        return 0;
    }

    /* ---- 8./9. t_unmask, unmask (values first, log afterwards — no formatting inside the window) ---- */
    res->pi_pre_unmask_ok = (t->read_pi(t->ctx, &res->intsr_pre_unmask, &res->intmr_pre_unmask) == GBP_OK) ? 1 : 0;
    res->t_unmask = now(t);
    res->unmask_rc = t->irq_unmask(t->ctx);
    res->irq_unmasked = 1;                       /* even on failure: the teardown masks anyway */
    res->t_post_unmask = now(t);
    res->pi_post_unmask_ok = (t->read_pi(t->ctx, &res->intsr_post_unmask, &res->intmr_post_unmask) == GBP_OK) ? 1 : 0;
    memset(&rec0, 0, sizeof rec0);
    t->irq_record(t->ctx, &rec0);
    ringlog_printf(log, "PI tag=UNMASKPRE rc=%s intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u",
                   res->pi_pre_unmask_ok ? "ok" : "fail", (unsigned long)res->intsr_pre_unmask,
                   (unsigned long)res->intmr_pre_unmask, (res->intsr_pre_unmask & GBP_PI_HSP_BIT) ? 1u : 0u,
                   (res->intmr_pre_unmask & GBP_PI_HSP_BIT) ? 1u : 0u);
    ringlog_printf(log, "UNMASK t_unmask=%lu rc=%s t_post=%lu dt_post=%lu", (unsigned long)res->t_unmask,
                   gbp_status_name(res->unmask_rc), (unsigned long)res->t_post_unmask,
                   (unsigned long)(uint32_t)(res->t_post_unmask - res->t_unmask));
    ringlog_printf(log, "PI tag=UNMASKPOST rc=%s intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u fired=%lu",
                   res->pi_post_unmask_ok ? "ok" : "fail", (unsigned long)res->intsr_post_unmask,
                   (unsigned long)res->intmr_post_unmask, (res->intsr_post_unmask & GBP_PI_HSP_BIT) ? 1u : 0u,
                   (res->intmr_post_unmask & GBP_PI_HSP_BIT) ? 1u : 0u, (unsigned long)rec0.fired);
    if (!res->pi_pre_unmask_ok || !res->pi_post_unmask_ok) res->errors++;
    if (res->unmask_rc != GBP_OK ||
        (res->pi_post_unmask_ok && !(res->intmr_post_unmask & GBP_PI_HSP_BIT) && rec0.count == 0)) {
        /* The unmask did not take effect (INTMR bit 13 still 0 and the
         * handler never ran): nothing can arrive; do not wait. */
        if (res->unmask_rc != GBP_OK) res->errors++;
        finish(t, log, cfg, res, GBP_INITIRQ_ABORT_UNMASK, "unmask_not_effective", write_ticks);
        return 0;
    }

    /* ---- 10. wait for the handler or the operational bound; no DMA in here ---- */
    {
        uint32_t tnow;
        for (;;) {
            struct gbp_irq_record r;
            memset(&r, 0, sizeof r);
            t->irq_record(t->ctx, &r);
            res->polls++;
            if (r.fired) break;
            tnow = now(t);
            if ((uint32_t)(tnow - res->t_unmask) >= cfg->t_max_ticks) { res->timed_out = 1; break; }
        }
    }
    res->t_wait_end = now(t);
    res->wait_ticks = (uint32_t)(res->t_wait_end - res->t_unmask);

    /* ---- 11. IRQ 26 masked again before anything else (idempotent with the handler's own mask) ---- */
    res->mask_rc = t->irq_mask(t->ctx);
    ringlog_printf(log, "IRQ mask tag=MAIN rc=%s", gbp_status_name(res->mask_rc));
    if (res->mask_rc == GBP_OK) res->irq_masked_again = 1; else { res->errors++; restore_fail(res, "mask_failed"); }
    ringlog_printf(log, "WAIT fired=%d timed_out=%d polls=%u wait_ticks=%lu wait_us=%lu t_max_ms=%lu t_max_ticks=%lu",
                   res->timed_out ? 0 : 1, res->timed_out, res->polls, (unsigned long)res->wait_ticks,
                   (unsigned long)ticks_to_us(cfg, res->wait_ticks), (unsigned long)cfg->t_max_ms,
                   (unsigned long)cfg->t_max_ticks);

    /* ---- 12. S2: PI sampled twice, CONTROL, IRQ (masked) ---- */
    snapshot(t, log, res, 2, 0, 1, write_ticks, res->t_unmask);
    if (!res->snap[2].pi_ok || res->snap[2].control_rc != GBP_OK || res->snap[2].irq_rc != GBP_OK) {
        finish(t, log, cfg, res, GBP_INITIRQ_TRANSPORT_ERROR, "s2_read_failed", write_ticks);
        return 0;
    }

    /* ---- 13.–18. teardown + end record ---- */
    copy_record(t, res);
    finish(t, log, cfg, res, res->rec.fired ? GBP_INITIRQ_OK_IRQ_OBSERVED : GBP_INITIRQ_TIMEOUT_NO_IRQ_OBSERVED,
           res->rec.fired ? "-" : "no_irq26_within_t_max", write_ticks);
    return 0;
}

int gbp_initirq_summary(const struct gbp_initirq_result *res, char *dst, size_t cap)
{
    const struct gbp_initirq_snapshot *s2 = &res->snap[2], *s3 = &res->snap[3];
    return snprintf(dst, cap,
                    "DONE status=%s reason=%s restore=%s restore_reason=%s verdict=%s det=%u/%u written=%d "
                    "fired=%d count=%lu timed_out=%d latency_ticks=%lu latency_us=%lu "
                    "intsr_before_ack=%08lx intsr_after_ack=%08lx intmr_after_mask=%08lx "
                    "s2_intsr13=%u,%u s3_intsr13=%u cleanup=%d reentry=%d "
                    "control_orig=%02x control_exp=%02x control_restored=%d handler_restored=%d mask_ok=%d "
                    "arinfo_restored=%d errors=%u transport_ok=%d",
                    gbp_initirq_status_name(res->status), res->reason ? res->reason : "-",
                    res->restore_ok ? "ok" : "error", res->restore_reason ? res->restore_reason : "-",
                    gbp_verdict_name(res->det.verdict), res->det.vote_ok, res->det.run, res->control_written,
                    res->fired, (unsigned long)res->rec.count, res->timed_out,
                    (unsigned long)res->latency_ticks, (unsigned long)res->latency_us,
                    (unsigned long)res->rec.intsr_before_ack, (unsigned long)res->rec.intsr_after_ack,
                    (unsigned long)res->rec.intmr_after_mask,
                    (s2->intsr & GBP_PI_HSP_BIT) ? 1u : 0u, (s2->intsr2 & GBP_PI_HSP_BIT) ? 1u : 0u,
                    (s3->intsr & GBP_PI_HSP_BIT) ? 1u : 0u, res->cleanup_ack_performed, res->unexpected_reentry,
                    (unsigned)res->control_orig, (unsigned)res->control_exp, res->control_restored,
                    res->handler_restored, res->mask_ok, res->arinfo_restored, res->errors, res->transport_ok);
}
