#include "gbp_initirqb_probe.h"

#include <stdio.h>
#include <string.h>
#include "gbp_rawlog.h"

#define DEFAULT_T_DELIVERY_MS 100u

void gbp_initirqb_config_timebase(struct gbp_initirqb_config *cfg, uint32_t tb_hz)
{
    gbp_initirqa_config_timebase(&cfg->a, tb_hz);
    cfg->t_delivery_ticks = (uint32_t)(((uint64_t)tb_hz * cfg->t_delivery_ms) / 1000u);
}

void gbp_initirqb_config_default(struct gbp_initirqb_config *cfg)
{
    memset(cfg, 0, sizeof *cfg);
    gbp_initirqa_config_default(&cfg->a);
    cfg->t_delivery_ms = DEFAULT_T_DELIVERY_MS;
    cfg->ack_or = 0x8000;
    cfg->src_mask = 0x0555;
    cfg->odd_mask = 0x0AAA;
    cfg->bit15_mask = 0x8000;
    cfg->high_mask = 0x7000;
    gbp_initirqb_config_timebase(cfg, cfg->a.tb_hz);
}

const char *gbp_initirqb_status_name(gbp_initirqb_status s)
{
    switch (s) {
    case GBP_INITIRQB_OK_DELIVERY_OBSERVED: return "ok_delivery_observed";
    case GBP_INITIRQB_DELIVERY_TIMEOUT: return "delivery_timeout";
    case GBP_INITIRQB_NO_CAUSE_WITHIN_TMAX: return "no_cause_within_tmax";
    case GBP_INITIRQB_ABORT_STAGE_A: return "abort_stage_a";
    case GBP_INITIRQB_ABORT_HANDLER_INSTALL: return "abort_handler_install";
    case GBP_INITIRQB_ABORT_PRE_UNMASK_STATE: return "abort_pre_unmask_state";
    case GBP_INITIRQB_ABORT_UNMASK: return "abort_unmask";
    case GBP_INITIRQB_ANOMALY_REENTRY: return "anomaly_reentry";
    case GBP_INITIRQB_ANOMALY_MASK_FAILURE: return "anomaly_mask_failure";
    default: return "?";
    }
}

static uint32_t now(const struct gbp_transport *t)
{
    return t->ticks ? t->ticks(t->ctx) : 0u;
}

static uint32_t ticks_to_us(const struct gbp_initirqb_config *cfg, uint32_t ticks)
{
    if (!cfg->a.tb_hz) return 0u;
    return (uint32_t)(((uint64_t)ticks * 1000000u) / cfg->a.tb_hz);
}

static unsigned bit13(uint32_t v)
{
    return (v & GBP_PI_HSP_BIT) ? 1u : 0u;
}

static void restore_fail(struct gbp_initirqb_result *res, const char *why)
{
    if (res->restore_ok) res->restore_reason = why;
    res->restore_ok = 0;
}

/* ---- teardown hook: handler restore + mask verification, between the PI step and AR_INFO ---- */
struct hook_ctx {
    const struct gbp_transport *t;
    struct ringlog *log;
    struct gbp_initirqb_result *res;
};

static void teardown_hook(void *arg)
{
    struct hook_ctx *h = (struct hook_ctx *)arg;
    const struct gbp_transport *t = h->t;
    struct ringlog *log = h->log;
    struct gbp_initirqb_result *res = h->res;
    int engaged = (res->handler_was_installed || res->irq_unmasked) ? 1 : 0;
    uint32_t intsr = 0, intmr = 0;
    gbp_status rc;

    /* 1. previous handler back, verbatim (NULL or not) */
    if (res->handler_installed) {
        res->handler_restore_rc = t->irq_restore ? t->irq_restore(t->ctx) : GBP_ERR_BACKEND;
        res->handler_restored = (res->handler_restore_rc == GBP_OK) ? 1 : 0;
        ringlog_printf(log, "IRQ restore rc=%s ok=%d old_handler=%s", gbp_status_name(res->handler_restore_rc),
                       res->handler_restored, res->old_handler_null == 1 ? "null" : res->old_handler_null == 0 ? "nonnull" : "?");
        if (res->handler_restored) res->handler_installed = 0;
        else { res->a.errors++; restore_fail(res, "handler_restore_failed"); }
    }
    /* 2. mask state: the original state was "masked" (precondition) */
    if (engaged) {
        int ok = 0;
        if (gbp_rawlog_read_pi(t, log, "tag=MASKCHK", &intsr, &intmr)) {
            ok = bit13(intmr) ? 0 : 1;
            if (!ok && t->irq_mask) {
                rc = t->irq_mask(t->ctx);
                ringlog_printf(log, "IRQ mask tag=RETRY rc=%s", gbp_status_name(rc));
                if (gbp_rawlog_read_pi(t, log, "tag=MASKCHK2", &intsr, &intmr)) ok = bit13(intmr) ? 0 : 1;
            }
            res->intmr_final = intmr;
        } else {
            res->a.errors++;
        }
        res->mask_ok = ok;
        ringlog_printf(log, "MASK final intmr=%08lx intmr13=%u orig_intmr13=0 ok=%d", (unsigned long)intmr, bit13(intmr), ok);
        if (!ok) restore_fail(res, "mask_not_restored");
    }
}

/* ---- the teardown for every path after the 003A stage ---- */
static void teardown_b(const struct gbp_transport *t, struct ringlog *log, const struct gbp_initirqb_config *cfg,
                       struct gbp_initirqb_result *res)
{
    struct gbp_initirqa_teardown_opts opts;
    struct hook_ctx h;
    h.t = t; h.log = log; h.res = res;
    opts.pi_cleanup_allowed = res->main_pi_w1c ? 0 : 1;      /* the main-loop W1C budget: one per run */
    opts.pre_arinfo_hook = teardown_hook;
    opts.hook_ctx = &h;
    opts.pi_policy = res->irq_unmasked ? "unmasked_once" : "never_unmasked";   /* the run's real policy (label defect of initirqb-0001 fixed) */
    gbp_initirqa_teardown(t, log, &cfg->a, &res->a, &opts);
    if (res->a.pi_cleanup_performed) {
        res->main_pi_w1c = 1;
        res->main_pi_w1c_site = "CLEANUP";
        res->main_w1c_rc = res->a.cleanup_rc;
        res->main_w1c_intsr_before = res->a.cleanup_intsr_before;
        res->main_w1c_intsr_after = res->a.cleanup_intsr_after;
        res->main_w1c_sticky = res->a.pi_cleanup_sticky;
    }
    res->pi_sticky_final = (res->a.cleanup_intsr_after & GBP_PI_HSP_BIT) ? 1 : 0;
    if (!res->a.restore_ok && res->restore_ok) restore_fail(res, res->a.restore_reason);
}

static void log_handler(struct ringlog *log, const struct gbp_initirqb_config *cfg, struct gbp_initirqb_result *res)
{
    const struct gbp_irq_record *r = &res->rec;
    res->fired = r->fired ? 1 : 0;
    res->reentry = (r->count > 1u) ? 1 : 0;
    if (res->fired) {
        res->latency_ticks = (uint32_t)(r->t_entry - res->t_unmask);   /* wrap-safe; never from t_post_unmask */
        res->latency_us = ticks_to_us(cfg, res->latency_ticks);
    }
    ringlog_printf(log, "HANDLER fired=%lu count=%lu t_entry=%lu t_unmask=%lu latency_ticks=%lu latency_us=%lu reentry=%d",
                   (unsigned long)r->fired, (unsigned long)r->count, (unsigned long)r->t_entry,
                   (unsigned long)res->t_unmask, (unsigned long)res->latency_ticks, (unsigned long)res->latency_us, res->reentry);
    ringlog_printf(log, "HANDLERPI intsr_at_entry=%08lx intmr_at_entry=%08lx intmr_after_mask=%08lx intsr_before_w1c=%08lx intsr_after_w1c=%08lx reentry_intsr=%08lx reentry_intmr=%08lx",
                   (unsigned long)r->intsr_before_ack, (unsigned long)r->intmr_at_entry, (unsigned long)r->intmr_after_mask,
                   (unsigned long)r->intsr_before_w1c, (unsigned long)r->intsr_after_ack,
                   (unsigned long)r->reentry_intsr, (unsigned long)r->reentry_intmr);
    ringlog_printf(log, "HANDLERPI2 t_second=%lu dt_second=%lu intsr_second=%08lx intmr_second=%08lx reentry_t=%lu",
                   (unsigned long)r->t_second, (unsigned long)(uint32_t)(r->t_second - r->t_entry),
                   (unsigned long)r->intsr_second, (unsigned long)r->intmr_second, (unsigned long)r->reentry_t);
}

static void log_delivery(struct ringlog *log, const struct gbp_initirqb_result *res)
{
    const struct gbp_irq_record *r = &res->rec;
    ringlog_printf(log, "DELIVERY fired=%d count=%lu latency_ticks=%lu latency_us=%lu intsr13_entry=%u intmr13_entry=%u intmr13_after_mask=%u intsr13_before_w1c=%u intsr13_after_w1c=%u intsr13_second=%u intmr13_second=%u main_mask_ok=%d reentry=%d",
                   res->fired, (unsigned long)r->count, (unsigned long)res->latency_ticks, (unsigned long)res->latency_us,
                   bit13(r->intsr_before_ack), bit13(r->intmr_at_entry), bit13(r->intmr_after_mask), bit13(r->intsr_before_w1c),
                   bit13(r->intsr_after_ack), bit13(r->intsr_second), bit13(r->intmr_second), res->main_mask_ok, res->reentry);
}

static void end_records(struct ringlog *log, struct gbp_initirqb_result *res)
{
    res->uncertain_writes = res->a.uncertain_writes + ((res->w_ack.attempted && !res->w_ack.completed) ? 1u : 0u);
    res->errors = res->a.errors;
    res->transport_ok = (res->errors == 0) ? 1 : 0;
    res->power_cycle_required = res->a.power_cycle_required;
    ringlog_printf(log, "INITIRQB end status=%s reason=%s restore=%s restore_reason=%s power_cycle_required=%d errors=%u transport_ok=%d",
                   res->status_name, res->reason, res->restore_ok ? "ok" : "error", res->restore_reason,
                   res->power_cycle_required, res->errors, res->transport_ok);
    gbp_initirqa_log_summary_records(log, &res->a);
    ringlog_printf(log, "ACKS ack=%d/%d ack_value=%04x irq_pending=%04x skipped=%d reason=%s isr_pi_w1c=%d main_pi_w1c=%d site=%s sticky=%d uncertain=%u",
                   res->w_ack.attempted, res->w_ack.completed, (unsigned)res->ack_value, (unsigned)res->irq_pending,
                   res->ack_skipped, res->ack_skip_reason, res->fired, res->main_pi_w1c, res->main_pi_w1c_site,
                   res->main_w1c_sticky, res->uncertain_writes);
    ringlog_printf(log, "RESTOREB handler_installed=%d handler_restored=%d old_handler=%s mask_ok=%d intmr_final=%08lx pi_sticky_final=%d unmasked=%d masked_again=%d",
                   res->handler_was_installed, res->handler_restored,
                   res->old_handler_null == 1 ? "null" : res->old_handler_null == 0 ? "nonnull" : "?",
                   res->mask_ok, (unsigned long)res->intmr_final, res->pi_sticky_final, res->irq_unmasked, res->irq_masked_again);
}

static void finish(const struct gbp_transport *t, struct ringlog *log, const struct gbp_initirqb_config *cfg,
                   struct gbp_initirqb_result *res, gbp_initirqb_status st, const char *reason, int do_teardown)
{
    res->status = st;
    res->status_name = gbp_initirqb_status_name(st);
    res->reason = reason;
    if (do_teardown) teardown_b(t, log, cfg, res);
    end_records(log, res);
}

/* PREUNMASK preconditions (docs: HARDWARE_TESTS.md planned entry) */
static int preunmask_check(const struct gbp_initirqb_config *cfg, struct gbp_initirqb_result *res, const char **why)
{
    const struct gbp_initirqa_snapshot *s = &res->preunmask;
    if (!s->pi_ok || s->control_rc != GBP_OK || s->irq_rc != GBP_OK) { *why = "read_failed"; return 0; }
    if (res->install_count || res->install_fired) { *why = "record_not_clear"; return 0; }
    if (!bit13(s->intsr) || (s->pi2_ok && !bit13(s->intsr2))) { *why = "cause_lost"; return 0; }
    if (bit13(s->intmr) || (s->pi2_ok && bit13(s->intmr2))) { *why = "intmr13_unmasked"; return 0; }
    if (s->control_vote != res->a.control_exp || s->control_vote != s->control_b1f) { *why = "control_changed"; return 0; }
    if (s->irq_disc != s->irq_gbi) { *why = "semantic_disagree"; return 0; }
    if ((s->irq_gbi & cfg->src_mask) == 0 || (s->irq_gbi & cfg->odd_mask) != 0 ||
        (s->irq_gbi & cfg->bit15_mask) != 0 || (s->irq_gbi & cfg->high_mask) != 0) { *why = "irq_state_unexpected"; return 0; }
    *why = "-";
    return 1;
}

int gbp_initirqb_probe_run(const struct gbp_transport *t, struct ringlog *log,
                           const struct gbp_initirqb_config *cfg, struct gbp_initirqb_result *res)
{
    gbp_initirqa_cause_rc crc;
    const struct gbp_initirqa_snapshot *ev;
    const char *why = "-";
    int old_null = -1;
    struct gbp_irq_record rec0;
    uint32_t intsr = 0, intmr = 0;

    memset(res, 0, sizeof *res);
    res->restore_ok = 1;
    res->restore_reason = "-";
    res->reason = "-";
    res->status_name = "-";
    res->preunmask_reason = "-";
    res->ack_skip_reason = "-";
    res->main_pi_w1c_site = "-";
    res->old_handler_null = -1;
    res->handler_restored = -1;
    res->main_mask_ok = -1;
    res->mask_ok = -1;
    ringlog_printf(log, "INITIRQB start t_delivery_ms=%lu t_delivery_ticks=%lu ack_or=%04x src_mask=%04x odd_mask=%04x bit15_mask=%04x high_mask=%04x install_point=after_latched_cause",
                   (unsigned long)cfg->t_delivery_ms, (unsigned long)cfg->t_delivery_ticks, (unsigned)cfg->ack_or,
                   (unsigned)cfg->src_mask, (unsigned)cfg->odd_mask, (unsigned)cfg->bit15_mask, (unsigned)cfg->high_mask);

    /* ---- 1. the GBP-INIT-003A sequence, verbatim, PI masked, no handler ---- */
    crc = gbp_initirqa_run_cause(t, log, &cfg->a, &res->a);
    if (crc == GBP_INITIRQA_CAUSE_ABORTED) {
        /* the stage tore down and wrote its own end records; nothing of 003B ran */
        res->stage_a_aborted = 1;
        res->status = GBP_INITIRQB_ABORT_STAGE_A;
        res->status_name = gbp_initirqa_status_name(res->a.status);
        res->reason = res->a.reason ? res->a.reason : "-";
        if (!res->a.restore_ok) restore_fail(res, res->a.restore_reason);
        end_records(log, res);
        return 0;
    }
    if (crc == GBP_INITIRQA_CAUSE_NOT_OBSERVED) {
        finish(t, log, cfg, res, GBP_INITIRQB_NO_CAUSE_WITHIN_TMAX, "no_intsr13_within_t_max", 1);
        return 0;
    }

    /* ---- 2. the cause is latched at the PI: record it, touch nothing ---- */
    ev = &res->a.snap[GBP_INITIRQA_SNAP_EVENT];
    if (ev->taken) {
        ringlog_printf(log, "CAUSE t_event=%lu since_a2=%lu intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u control=%02x irq=%04x",
                       (unsigned long)ev->ticks, (unsigned long)ev->since_a2, (unsigned long)ev->intsr, (unsigned long)ev->intmr,
                       bit13(ev->intsr), bit13(ev->intmr), (unsigned)ev->control_vote, (unsigned)ev->irq_gbi);
    } else {
        ringlog_printf(log, "CAUSE t_first_intsr13=%lu phase=%s (seen by a snapshot, no EVENT slot)",
                       (unsigned long)res->a.t_first_intsr13, res->a.first_intsr13_phase);
    }

    /* ---- 3. handler installed only now (point B); previous handler kept ---- */
    res->irq_path_available = gbp_transport_has_irq_path(t);
    if (!res->irq_path_available) {
        ringlog_printf(log, "IRQ install rc=unavailable");
        finish(t, log, cfg, res, GBP_INITIRQB_ABORT_HANDLER_INSTALL, "irq_ops_unavailable", 1);
        return 0;
    }
    res->install_rc = t->irq_install(t->ctx, &old_null);
    if (res->install_rc != GBP_OK) {
        res->a.errors++;
        ringlog_printf(log, "IRQ install rc=%s", gbp_status_name(res->install_rc));
        finish(t, log, cfg, res, GBP_INITIRQB_ABORT_HANDLER_INSTALL, "install_failed", 1);
        return 0;
    }
    res->handler_installed = 1;
    res->handler_was_installed = 1;
    res->old_handler_null = old_null ? 1 : 0;
    memset(&rec0, 0, sizeof rec0);
    t->irq_record(t->ctx, &rec0);                /* the install clears the record: count 0, fired 0 expected */
    res->install_count = rec0.count;
    res->install_fired = rec0.fired;
    ringlog_printf(log, "IRQ install rc=ok old_handler=%s record_count=%lu record_fired=%lu", old_null ? "null" : "nonnull",
                   (unsigned long)rec0.count, (unsigned long)rec0.fired);

    /* ---- 4. PREUNMASK: the state must still be the one the cause was latched in ---- */
    gbp_initirqa_snapshot_take(t, &res->a, &res->preunmask, "PREUNMASK", 0, 1);
    gbp_initirqa_snapshot_log(log, &res->a, &res->preunmask);
    res->preunmask_ok = preunmask_check(cfg, res, &why);
    res->preunmask_reason = why;
    ringlog_printf(log, "PREUNMASK ok=%d reason=%s intsr13=%u,%u intmr13=%u,%u control=%02x irq=%04x/%04x src=%04x odd=%04x bit15=%u",
                   res->preunmask_ok, why, bit13(res->preunmask.intsr), bit13(res->preunmask.intsr2),
                   bit13(res->preunmask.intmr), bit13(res->preunmask.intmr2), (unsigned)res->preunmask.control_vote,
                   (unsigned)res->preunmask.irq_gbi, (unsigned)res->preunmask.irq_disc,
                   (unsigned)(res->preunmask.irq_gbi & cfg->src_mask), (unsigned)(res->preunmask.irq_gbi & cfg->odd_mask),
                   (unsigned)((res->preunmask.irq_gbi & cfg->bit15_mask) ? 1u : 0u));
    if (!res->preunmask_ok) {
        finish(t, log, cfg, res, GBP_INITIRQB_ABORT_PRE_UNMASK_STATE, why, 1);
        return 0;
    }

    /* ---- 5. one unmask; values first, formatting afterwards ---- */
    res->pi_pre_unmask_ok = (t->read_pi(t->ctx, &res->intsr_pre_unmask, &res->intmr_pre_unmask) == GBP_OK) ? 1 : 0;
    res->t_unmask = now(t);
    res->unmask_rc = t->irq_unmask(t->ctx);
    res->irq_unmasked = 1;                       /* even on failure: the teardown re-masks anyway */
    res->t_post_unmask = now(t);                 /* the handler may already have run inside __UnmaskIrq */
    res->pi_post_unmask_ok = (t->read_pi(t->ctx, &res->intsr_post_unmask, &res->intmr_post_unmask) == GBP_OK) ? 1 : 0;
    memset(&rec0, 0, sizeof rec0);
    t->irq_record(t->ctx, &rec0);
    ringlog_printf(log, "PI tag=UNMASKPRE rc=%s intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u",
                   res->pi_pre_unmask_ok ? "ok" : "fail", (unsigned long)res->intsr_pre_unmask, (unsigned long)res->intmr_pre_unmask,
                   bit13(res->intsr_pre_unmask), bit13(res->intmr_pre_unmask));
    ringlog_printf(log, "UNMASK t_unmask=%lu rc=%s t_post=%lu dt_post=%lu", (unsigned long)res->t_unmask,
                   gbp_status_name(res->unmask_rc), (unsigned long)res->t_post_unmask,
                   (unsigned long)(uint32_t)(res->t_post_unmask - res->t_unmask));
    ringlog_printf(log, "PI tag=UNMASKPOST rc=%s intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u fired=%lu",
                   res->pi_post_unmask_ok ? "ok" : "fail", (unsigned long)res->intsr_post_unmask, (unsigned long)res->intmr_post_unmask,
                   bit13(res->intsr_post_unmask), bit13(res->intmr_post_unmask), (unsigned long)rec0.fired);
    if (!res->pi_pre_unmask_ok || !res->pi_post_unmask_ok) res->a.errors++;

    /* ---- 6. wait for the handler or the operational bound; no DMA, no formatting in here ---- */
    {
        uint32_t tnow;
        for (;;) {
            struct gbp_irq_record r;
            memset(&r, 0, sizeof r);
            t->irq_record(t->ctx, &r);
            res->polls++;
            if (r.fired) break;
            tnow = now(t);
            if ((uint32_t)(tnow - res->t_unmask) >= cfg->t_delivery_ticks) { res->timed_out = 1; break; }
        }
    }
    res->t_wait_end = now(t);
    res->wait_ticks = (uint32_t)(res->t_wait_end - res->t_unmask);

    /* ---- 7. IRQ 26 masked again by the main loop (idempotent with the handler's own mask), then verified ---- */
    res->mask_rc = t->irq_mask(t->ctx);
    ringlog_printf(log, "IRQ mask tag=MAIN rc=%s", gbp_status_name(res->mask_rc));
    if (res->mask_rc == GBP_OK) res->irq_masked_again = 1; else { res->a.errors++; restore_fail(res, "mask_failed"); }
    ringlog_printf(log, "WAIT fired=%d timed_out=%d polls=%u wait_ticks=%lu wait_us=%lu t_delivery_ms=%lu t_delivery_ticks=%lu",
                   res->timed_out ? 0 : 1, res->timed_out, res->polls, (unsigned long)res->wait_ticks,
                   (unsigned long)ticks_to_us(cfg, res->wait_ticks), (unsigned long)cfg->t_delivery_ms, (unsigned long)cfg->t_delivery_ticks);
    if (gbp_rawlog_read_pi(t, log, "tag=REMASKCHK", &intsr, &intmr)) {
        res->intsr_remask = intsr; res->intmr_remask = intmr;
        res->main_mask_ok = bit13(intmr) ? 0 : 1;
        if (!res->main_mask_ok) {
            gbp_status rc = t->irq_mask(t->ctx);
            res->remask_retry = 1;
            ringlog_printf(log, "IRQ mask tag=RETRY rc=%s", gbp_status_name(rc));
            if (gbp_rawlog_read_pi(t, log, "tag=REMASKCHK2", &intsr, &intmr)) { res->intsr_remask = intsr; res->intmr_remask = intmr; res->main_mask_ok = bit13(intmr) ? 0 : 1; }
        }
    } else {
        res->a.errors++;
    }

    /* ---- 8. the record, copied only now (masked); formatted here, outside the handler ---- */
    memset(&res->rec, 0, sizeof res->rec);
    t->irq_record(t->ctx, &res->rec);
    log_handler(log, cfg, res);
    log_delivery(log, res);

    if (!res->fired) {
        /* nothing delivered: was the mask ever opened? UNMASKPOST shows INTMR right after the call */
        int never_opened = (res->unmask_rc != GBP_OK) ||
                           (res->pi_post_unmask_ok && !bit13(res->intmr_post_unmask) && res->rec.count == 0);
        if (res->unmask_rc != GBP_OK) res->a.errors++;
        finish(t, log, cfg, res, never_opened ? GBP_INITIRQB_ABORT_UNMASK : GBP_INITIRQB_DELIVERY_TIMEOUT,
               never_opened ? "unmask_not_effective" : "no_delivery_within_t_delivery", 1);
        return 0;
    }
    if (res->reentry) {
        finish(t, log, cfg, res, GBP_INITIRQB_ANOMALY_REENTRY, "handler_entered_more_than_once", 1);
        return 0;
    }
    if (res->main_mask_ok != 1) {
        finish(t, log, cfg, res, GBP_INITIRQB_ANOMALY_MASK_FAILURE, "intmr13_still_set_after_remask", 1);
        return 0;
    }

    /* ---- 9. PREACK: the device has not been acknowledged; PI, CONTROL, IRQ as they are now ---- */
    gbp_initirqa_snapshot_take(t, &res->a, &res->preack, "PREACK", 0, 1);
    gbp_initirqa_snapshot_log(log, &res->a, &res->preack);
    ringlog_printf(log, "PREACK intsr13=%u,%u intmr13=%u control=%02x irq=%04x/%04x src_pending=%04x",
                   bit13(res->preack.intsr), bit13(res->preack.intsr2), bit13(res->preack.intmr),
                   (unsigned)res->preack.control_vote, (unsigned)res->preack.irq_gbi, (unsigned)res->preack.irq_disc,
                   (unsigned)(res->preack.irq_gbi & cfg->src_mask));

    /* ---- 10. device ACK: IRQ := read | 0x8000 (GBI's form; A1's physically validated write), derived from the read ---- */
    if (res->preack.irq_rc != GBP_OK) {
        res->ack_skipped = 1; res->ack_skip_reason = "irq_read_failed";
    } else if (res->preack.irq_disc != res->preack.irq_gbi) {
        res->ack_skipped = 1; res->ack_skip_reason = "semantic_disagree";
    } else {
        res->irq_pending = res->preack.irq_gbi;
        res->ack_value = (uint16_t)(res->irq_pending | cfg->ack_or);
        ringlog_printf(log, "ACK before=%04x ack_or=%04x ack_value=%04x formula=read|ack_or", (unsigned)res->irq_pending,
                       (unsigned)cfg->ack_or, (unsigned)res->ack_value);
        res->a.irq_writes_attempted++;              /* before the transport call, as in 003A */
        res->a.power_cycle_required = 1;
        gbp_regwrite_irq_u16(t, "tag=ACK", res->a.base, res->irq_pending, res->ack_value, &res->w_ack, &res->a.errors);
        if (res->w_ack.completed) res->a.irq_writes_completed++;
        gbp_regwrite_log(log, &res->w_ack);
    }
    if (res->ack_skipped) ringlog_printf(log, "ACK skipped=1 reason=%s", res->ack_skip_reason);

    /* ---- 11. POSTACK ---- */
    gbp_initirqa_snapshot_take(t, &res->a, &res->postack, "POSTACK", 0, 1);
    gbp_initirqa_snapshot_log(log, &res->a, &res->postack);
    ringlog_printf(log, "POSTACK intsr13=%u,%u intmr13=%u control=%02x irq=%04x/%04x src_pending=%04x bit15=%u ack=%d/%d",
                   bit13(res->postack.intsr), bit13(res->postack.intsr2), bit13(res->postack.intmr),
                   (unsigned)res->postack.control_vote, (unsigned)res->postack.irq_gbi, (unsigned)res->postack.irq_disc,
                   (unsigned)(res->postack.irq_gbi & cfg->src_mask), (unsigned)((res->postack.irq_gbi & cfg->bit15_mask) ? 1u : 0u),
                   res->w_ack.attempted, res->w_ack.completed);

    /* ---- 12. main-loop PI W1C: at most one per run, here only if bit 13 reads 1 while masked ---- */
    if (res->postack.pi_ok && bit13(res->postack.intsr) && !bit13(res->postack.intmr) && t->write_intsr && !res->main_pi_w1c) {
        res->main_pi_w1c = 1;
        res->main_pi_w1c_site = "POSTACK";
        res->main_w1c_intsr_before = res->postack.intsr;
        ringlog_printf(log, "MAINPICLEANUP site=POSTACK performed=1 value=%08lx", (unsigned long)GBP_PI_HSP_BIT);
        res->main_w1c_rc = t->write_intsr(t->ctx, GBP_PI_HSP_BIT);
        if (res->main_w1c_rc != GBP_OK) { res->a.errors++; restore_fail(res, "main_pi_w1c_failed"); }
        if (!gbp_rawlog_read_pi(t, log, "tag=MAINCLEANUP", &intsr, &intmr)) res->a.errors++;
        res->main_w1c_intsr_after = intsr;
        res->main_w1c_sticky = bit13(intsr) ? 1 : 0;
        ringlog_printf(log, "MAINPICLEANUP result rc=%s intsr_before=%08lx intsr_after=%08lx intsr13_after=%u sticky=%d",
                       gbp_status_name(res->main_w1c_rc), (unsigned long)res->main_w1c_intsr_before,
                       (unsigned long)res->main_w1c_intsr_after, bit13(intsr), res->main_w1c_sticky);
    } else {
        ringlog_printf(log, "MAINPICLEANUP site=POSTACK performed=0 intsr13=%u intmr13=%u", bit13(res->postack.intsr), bit13(res->postack.intmr));
    }

    /* ---- 13. teardown: CONTROL restore, stop word, PI (budget), handler restore, mask check, AR_INFO, FINAL ---- */
    finish(t, log, cfg, res, GBP_INITIRQB_OK_DELIVERY_OBSERVED, "-", 1);
    return 0;
}

int gbp_initirqb_summary(const struct gbp_initirqb_result *res, char *dst, size_t cap)
{
    const struct gbp_initirqa_result *a = &res->a;
    const struct gbp_irq_record *r = &res->rec;
    return snprintf(dst, cap,
                    "DONE status=%s reason=%s restore=%s restore_reason=%s verdict=%s det=%u/%u written=%d "
                    "irq_attempted=%u irq_completed=%u ctl_exp=%d/%d a1=%d/%d a2=%d/%d ack=%d/%d stop=%d/%d ctl_restore=%d/%d uncertain=%u "
                    "cause=%d t_event=%lu handler=%d old=%s preunmask=%d/%s unmasked=%d fired=%d count=%lu latency_ticks=%lu latency_us=%lu "
                    "intsr13_entry=%u intmr13_entry=%u intmr13_after_mask=%u intsr13_after_w1c=%u intsr13_second=%u "
                    "preack_irq=%04x ack_value=%04x postack_irq=%04x postack_intsr13=%u main_pi_w1c=%d site=%s sticky=%d "
                    "control_restore_ok=%d irq_stop_write_ok=%d stop_post=%04x pi_cleanup=%d handler_restored=%d mask_ok=%d arinfo_restore_ok=%d "
                    "power_cycle_required=%d errors=%u transport_ok=%d",
                    res->status_name, res->reason ? res->reason : "-", res->restore_ok ? "ok" : "error",
                    res->restore_reason ? res->restore_reason : "-", gbp_verdict_name(a->det.verdict), a->det.vote_ok, a->det.run,
                    a->control_written, a->irq_writes_attempted, a->irq_writes_completed,
                    a->w_ctl_exp.attempted, a->w_ctl_exp.completed, a->w_a1.attempted, a->w_a1.completed, a->w_a2.attempted, a->w_a2.completed,
                    res->w_ack.attempted, res->w_ack.completed, a->w_stop.attempted, a->w_stop.completed,
                    a->w_ctl_restore.attempted, a->w_ctl_restore.completed, res->uncertain_writes,
                    a->intsr13_seen, (unsigned long)a->t_first_intsr13, res->handler_was_installed,
                    res->old_handler_null == 1 ? "null" : res->old_handler_null == 0 ? "nonnull" : "?",
                    res->preunmask_ok, res->preunmask_reason ? res->preunmask_reason : "-", res->irq_unmasked, res->fired,
                    (unsigned long)r->count, (unsigned long)res->latency_ticks, (unsigned long)res->latency_us,
                    bit13(r->intsr_before_ack), bit13(r->intmr_at_entry), bit13(r->intmr_after_mask), bit13(r->intsr_after_ack), bit13(r->intsr_second),
                    (unsigned)res->preack.irq_gbi, (unsigned)res->ack_value, (unsigned)res->postack.irq_gbi, bit13(res->postack.intsr),
                    res->main_pi_w1c, res->main_pi_w1c_site ? res->main_pi_w1c_site : "-", res->main_w1c_sticky,
                    a->control_restore_ok, a->irq_stop_write_ok, (unsigned)a->irq_stop_post.gbi, a->pi_cleanup_performed,
                    res->handler_restored, res->mask_ok, a->arinfo_restore_ok,
                    res->power_cycle_required, res->errors, res->transport_ok);
}
