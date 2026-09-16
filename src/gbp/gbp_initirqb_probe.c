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
    struct gbp_initirqb_result *res = h->res;
    int engaged = (res->h.handler_was_installed || res->d.irq_unmasked) ? 1 : 0;
    const char *fail = gbp_irq_service_teardown_hook(h->t, h->log, &res->h, engaged, &res->a.errors);
    if (fail) restore_fail(res, fail);
}

/* ---- the teardown for every path after the 003A stage ---- */
static void teardown_b(const struct gbp_transport *t, struct ringlog *log, const struct gbp_initirqb_config *cfg,
                       struct gbp_initirqb_result *res)
{
    struct gbp_initirqa_teardown_opts opts;
    struct hook_ctx h;
    h.t = t; h.log = log; h.res = res;
    opts.pi_cleanup_allowed = res->k.main_pi_w1c ? 0 : 1;    /* the main-loop W1C budget: one per run */
    opts.pre_arinfo_hook = teardown_hook;
    opts.hook_ctx = &h;
    opts.pi_policy = res->d.irq_unmasked ? "unmasked_once" : "never_unmasked";   /* the run's real policy (label defect of initirqb-0001 fixed) */
    gbp_initirqa_teardown(t, log, &cfg->a, &res->a, &opts);
    if (res->a.pi_cleanup_performed) {
        res->k.main_pi_w1c = 1;
        res->k.main_pi_w1c_site = "CLEANUP";
        res->k.main_w1c_rc = res->a.cleanup_rc;
        res->k.main_w1c_intsr_before = res->a.cleanup_intsr_before;
        res->k.main_w1c_intsr_after = res->a.cleanup_intsr_after;
        res->k.main_w1c_sticky = res->a.pi_cleanup_sticky;
    }
    res->pi_sticky_final = (res->a.cleanup_intsr_after & GBP_PI_HSP_BIT) ? 1 : 0;
    if (!res->a.restore_ok && res->restore_ok) restore_fail(res, res->a.restore_reason);
}

static void end_records(struct ringlog *log, struct gbp_initirqb_result *res)
{
    res->uncertain_writes = res->a.uncertain_writes + ((res->k.w_ack.attempted && !res->k.w_ack.completed) ? 1u : 0u);
    res->errors = res->a.errors;
    res->transport_ok = (res->errors == 0) ? 1 : 0;
    res->power_cycle_required = res->a.power_cycle_required;
    ringlog_printf(log, "INITIRQB end status=%s reason=%s restore=%s restore_reason=%s power_cycle_required=%d errors=%u transport_ok=%d",
                   res->status_name, res->reason, res->restore_ok ? "ok" : "error", res->restore_reason,
                   res->power_cycle_required, res->errors, res->transport_ok);
    gbp_initirqa_log_summary_records(log, &res->a);
    ringlog_printf(log, "ACKS ack=%d/%d ack_value=%04x irq_pending=%04x skipped=%d reason=%s isr_pi_w1c=%d main_pi_w1c=%d site=%s sticky=%d uncertain=%u",
                   res->k.w_ack.attempted, res->k.w_ack.completed, (unsigned)res->k.ack_value, (unsigned)res->k.irq_pending,
                   res->k.ack_skipped, res->k.ack_skip_reason, res->d.fired, res->k.main_pi_w1c, res->k.main_pi_w1c_site,
                   res->k.main_w1c_sticky, res->uncertain_writes);
    ringlog_printf(log, "RESTOREB handler_installed=%d handler_restored=%d old_handler=%s mask_ok=%d intmr_final=%08lx pi_sticky_final=%d unmasked=%d masked_again=%d",
                   res->h.handler_was_installed, res->h.handler_restored,
                   res->h.old_handler_null == 1 ? "null" : res->h.old_handler_null == 0 ? "nonnull" : "?",
                   res->h.mask_ok, (unsigned long)res->h.intmr_final, res->pi_sticky_final, res->d.irq_unmasked, res->d.irq_masked_again);
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

int gbp_initirqb_probe_run(const struct gbp_transport *t, struct ringlog *log,
                           const struct gbp_initirqb_config *cfg, struct gbp_initirqb_result *res)
{
    gbp_initirqa_cause_rc crc;
    const struct gbp_initirqa_snapshot *ev;
    const char *why = "-";
    int old_null = -1;
    struct gbp_irq_record rec0;

    memset(res, 0, sizeof *res);
    res->restore_ok = 1;
    res->restore_reason = "-";
    res->reason = "-";
    res->status_name = "-";
    res->preunmask_reason = "-";
    gbp_irq_service_handler_init(&res->h);
    gbp_irq_service_delivery_init(&res->d);
    gbp_irq_service_ack_init(&res->k);
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
    res->h.irq_path_available = gbp_transport_has_irq_path(t);
    if (!res->h.irq_path_available) {
        ringlog_printf(log, "IRQ install rc=unavailable");
        finish(t, log, cfg, res, GBP_INITIRQB_ABORT_HANDLER_INSTALL, "irq_ops_unavailable", 1);
        return 0;
    }
    res->h.install_rc = t->irq_install(t->ctx, &old_null);
    if (res->h.install_rc != GBP_OK) {
        res->a.errors++;
        ringlog_printf(log, "IRQ install rc=%s", gbp_status_name(res->h.install_rc));
        finish(t, log, cfg, res, GBP_INITIRQB_ABORT_HANDLER_INSTALL, "install_failed", 1);
        return 0;
    }
    res->h.handler_installed = 1;
    res->h.handler_was_installed = 1;
    res->h.old_handler_null = old_null ? 1 : 0;
    memset(&rec0, 0, sizeof rec0);
    t->irq_record(t->ctx, &rec0);                /* the install clears the record: count 0, fired 0 expected */
    res->h.install_count = rec0.count;
    res->h.install_fired = rec0.fired;
    ringlog_printf(log, "IRQ install rc=ok old_handler=%s record_count=%lu record_fired=%lu", old_null ? "null" : "nonnull",
                   (unsigned long)rec0.count, (unsigned long)rec0.fired);

    /* ---- 4. PREUNMASK: the state must still be the one the cause was latched in ---- */
    gbp_initirqa_snapshot_take(t, &res->a, &res->preunmask, "PREUNMASK", 0, 1);
    gbp_initirqa_snapshot_log(log, &res->a, &res->preunmask);
    res->preunmask_ok = gbp_irq_service_preunmask_check(&res->preunmask, res->a.control_exp, cfg->src_mask, cfg->odd_mask,
                                                        cfg->bit15_mask, cfg->high_mask, res->h.install_count, res->h.install_fired, &why);
    res->preunmask_reason = why;
    gbp_irq_service_log_preunmask(log, "", &res->preunmask, res->preunmask_ok, why, cfg->src_mask, cfg->odd_mask, cfg->bit15_mask);
    if (!res->preunmask_ok) {
        finish(t, log, cfg, res, GBP_INITIRQB_ABORT_PRE_UNMASK_STATE, why, 1);
        return 0;
    }

    /* ---- 5.–8. one unmask, the wait, the main re-mask, the record (gbp_irq_service) ---- */
    gbp_irq_service_deliver(t, log, cfg->a.tb_hz, cfg->t_delivery_ms, cfg->t_delivery_ticks, -1, "", "", &res->d, &res->a.errors);
    if (res->d.mask_rc != GBP_OK) restore_fail(res, "mask_failed");

    if (!res->d.fired) {
        /* nothing delivered: was the mask ever opened? UNMASKPOST shows INTMR right after the call */
        int never_opened = (res->d.unmask_rc != GBP_OK) ||
                           (res->d.pi_post_unmask_ok && !bit13(res->d.intmr_post_unmask) && res->d.rec.count == 0);
        if (res->d.unmask_rc != GBP_OK) res->a.errors++;
        finish(t, log, cfg, res, never_opened ? GBP_INITIRQB_ABORT_UNMASK : GBP_INITIRQB_DELIVERY_TIMEOUT,
               never_opened ? "unmask_not_effective" : "no_delivery_within_t_delivery", 1);
        return 0;
    }
    if (res->d.reentry) {
        finish(t, log, cfg, res, GBP_INITIRQB_ANOMALY_REENTRY, "handler_entered_more_than_once", 1);
        return 0;
    }
    if (res->d.main_mask_ok != 1) {
        finish(t, log, cfg, res, GBP_INITIRQB_ANOMALY_MASK_FAILURE, "intmr13_still_set_after_remask", 1);
        return 0;
    }

    /* ---- 9.–12. PREACK, device ACK (read | 0x8000), POSTACK, main-loop W1C budget (gbp_irq_service) ---- */
    gbp_irq_service_ack(t, log, &res->a, cfg->ack_or, cfg->src_mask, cfg->src_mask, 0, 0, 0, "", "PREACK", "POSTACK", "tag=ACK", "",
                        &res->k, &res->a.errors);
    if (res->k.main_pi_w1c && res->k.main_w1c_rc != GBP_OK) restore_fail(res, "main_pi_w1c_failed");

    /* ---- 13. teardown: CONTROL restore, stop word, PI (budget), handler restore, mask check, AR_INFO, FINAL ---- */
    finish(t, log, cfg, res, GBP_INITIRQB_OK_DELIVERY_OBSERVED, "-", 1);
    return 0;
}

int gbp_initirqb_summary(const struct gbp_initirqb_result *res, char *dst, size_t cap)
{
    const struct gbp_initirqa_result *a = &res->a;
    const struct gbp_irq_record *r = &res->d.rec;
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
                    res->k.w_ack.attempted, res->k.w_ack.completed, a->w_stop.attempted, a->w_stop.completed,
                    a->w_ctl_restore.attempted, a->w_ctl_restore.completed, res->uncertain_writes,
                    a->intsr13_seen, (unsigned long)a->t_first_intsr13, res->h.handler_was_installed,
                    res->h.old_handler_null == 1 ? "null" : res->h.old_handler_null == 0 ? "nonnull" : "?",
                    res->preunmask_ok, res->preunmask_reason ? res->preunmask_reason : "-", res->d.irq_unmasked, res->d.fired,
                    (unsigned long)r->count, (unsigned long)res->d.latency_ticks, (unsigned long)res->d.latency_us,
                    bit13(r->intsr_before_ack), bit13(r->intmr_at_entry), bit13(r->intmr_after_mask), bit13(r->intsr_after_ack), bit13(r->intsr_second),
                    (unsigned)res->k.preack.irq_gbi, (unsigned)res->k.ack_value, (unsigned)res->k.postack.irq_gbi, bit13(res->k.postack.intsr),
                    res->k.main_pi_w1c, res->k.main_pi_w1c_site ? res->k.main_pi_w1c_site : "-", res->k.main_w1c_sticky,
                    a->control_restore_ok, a->irq_stop_write_ok, (unsigned)a->irq_stop_post.gbi, a->pi_cleanup_performed,
                    res->h.handler_restored, res->h.mask_ok, a->arinfo_restore_ok,
                    res->power_cycle_required, res->errors, res->transport_ok);
}
