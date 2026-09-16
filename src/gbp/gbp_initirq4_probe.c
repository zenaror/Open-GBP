#include "gbp_initirq4_probe.h"

#include <stdio.h>
#include <string.h>
#include "gbp_rawlog.h"

#define DEFAULT_T_DELIVERY_MS   100u
#define DEFAULT_T_NEXT_CAUSE_MS 500u

static unsigned bit13(uint32_t v)
{
    return (v & GBP_PI_HSP_BIT) ? 1u : 0u;
}

static uint32_t now(const struct gbp_transport *t)
{
    return t->ticks ? t->ticks(t->ctx) : 0u;
}

static uint32_t ticks_to_us(uint32_t tb_hz, uint32_t ticks)
{
    if (!tb_hz) return 0u;
    return (uint32_t)(((uint64_t)ticks * 1000000u) / tb_hz);
}

void gbp_initirq4_config_timebase(struct gbp_initirq4_config *cfg, uint32_t tb_hz)
{
    gbp_initirqa_config_timebase(&cfg->a, tb_hz);
    cfg->t_delivery_ticks = (uint32_t)(((uint64_t)tb_hz * cfg->t_delivery_ms) / 1000u);
    cfg->t_next_cause_ticks = (uint32_t)(((uint64_t)tb_hz * cfg->t_next_cause_ms) / 1000u);
}

void gbp_initirq4_config_default(struct gbp_initirq4_config *cfg)
{
    memset(cfg, 0, sizeof *cfg);
    gbp_initirqa_config_default(&cfg->a);
    cfg->t_delivery_ms = DEFAULT_T_DELIVERY_MS;
    cfg->t_next_cause_ms = DEFAULT_T_NEXT_CAUSE_MS;
    cfg->ack_or = 0x8000;
    cfg->src_mask = 0x0555;
    cfg->av_mask = 0x0500;
    cfg->odd_mask = 0x0AAA;
    cfg->bit15_mask = 0x8000;
    cfg->high_mask = 0x7000;
    cfg->max_cycles = GBP_INITIRQ4_MAX_CYCLES;
    cfg->max_rearms = GBP_INITIRQ4_MAX_REARMS;
    gbp_initirq4_config_timebase(cfg, cfg->a.tb_hz);
}

const char *gbp_initirq4_status_name(gbp_initirq4_status s)
{
    switch (s) {
    case GBP_INITIRQ4_OK_CYCLES_COMPLETED: return "ok_cycles_completed";
    case GBP_INITIRQ4_CYCLES_COMPLETED_WITH_ERRORS: return "cycles_completed_with_errors";
    case GBP_INITIRQ4_NO_INITIAL_CAUSE: return "no_initial_cause";
    case GBP_INITIRQ4_NO_NEXT_CAUSE: return "no_next_cause";
    case GBP_INITIRQ4_DELIVERY_TIMEOUT: return "delivery_timeout";
    case GBP_INITIRQ4_ABORT_STAGE_A: return "abort_stage_a";
    case GBP_INITIRQ4_ABORT_HANDLER_INSTALL: return "abort_handler_install";
    case GBP_INITIRQ4_ABORT_PRE_UNMASK_STATE: return "abort_pre_unmask_state";
    case GBP_INITIRQ4_ABORT_UNMASK: return "abort_unmask";
    case GBP_INITIRQ4_ABORT_READ_INCONSISTENT: return "abort_read_inconsistent";
    case GBP_INITIRQ4_ABORT_TRANSPORT: return "abort_transport";
    case GBP_INITIRQ4_ANOMALY_REENTRY: return "anomaly_reentry";
    case GBP_INITIRQ4_ANOMALY_GENERATION: return "anomaly_generation";
    case GBP_INITIRQ4_ANOMALY_MASK_FAILURE: return "anomaly_mask_failure";
    case GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE: return "anomaly_unexpected_source";
    case GBP_INITIRQ4_ANOMALY_SOURCE_LOST_BEFORE_ACK: return "anomaly_source_lost_before_ack";
    case GBP_INITIRQ4_ANOMALY_SOURCE_NOT_CLEARED: return "anomaly_source_not_cleared";
    case GBP_INITIRQ4_ANOMALY_PI_STICKY_AFTER_ACK: return "anomaly_pi_sticky_after_ack";
    case GBP_INITIRQ4_ANOMALY_REARM_STATE: return "anomaly_rearm_state";
    case GBP_INITIRQ4_ANOMALY_CONTROL_CHANGED: return "anomaly_control_changed";
    default: return "?";
    }
}

const char *gbp_initirq4_rearmpost_name(int outcome)
{
    switch (outcome) {
    case GBP_INITIRQ4_REARMPOST_A_QUIET: return "A_quiet";
    case GBP_INITIRQ4_REARMPOST_B_LATCHED: return "B_latched";
    case GBP_INITIRQ4_REARMPOST_C_SOURCE_BEFORE_PI: return "C_source_before_pi";
    case GBP_INITIRQ4_REARMPOST_D_UNEXPECTED: return "D_unexpected";
    case GBP_INITIRQ4_REARMPOST_E_INVALID: return "E_invalid";
    case GBP_INITIRQ4_REARMPOST_F_INCONSISTENT: return "F_inconsistent";
    default: return "-";
    }
}

/* ---- run context ---------------------------------------------------- */
struct run_ctx {
    const struct gbp_transport *t;
    struct ringlog *log;
    const struct gbp_initirq4_config *cfg;
    struct gbp_initirq4_result *res;
};

static void restore_fail(struct gbp_initirq4_result *res, const char *why)
{
    if (res->restore_ok) res->restore_reason = why;
    res->restore_ok = 0;
}

static const char *old_handler_name(const struct gbp_irq_handler_state *h)
{
    return h->old_handler_null == 1 ? "null" : h->old_handler_null == 0 ? "nonnull" : "?";
}

/* ---- teardown hook: handler restore + mask verification, between the PI step and AR_INFO ---- */
static void teardown_hook(void *arg)
{
    struct run_ctx *x = (struct run_ctx *)arg;
    struct gbp_initirq4_result *res = x->res;
    int engaged = (res->h.handler_was_installed || res->unmasks) ? 1 : 0;
    const char *fail = gbp_irq_service_teardown_hook(x->t, x->log, &res->h, engaged, &res->a.errors);
    if (fail) restore_fail(res, fail);
}

/* ---- the teardown for every path after the 003A stage (CPU masked, at most one PI W1C) ---- */
static void teardown4(struct run_ctx *x, const char *variant)
{
    struct gbp_initirq4_result *res = x->res;
    struct gbp_initirqa_teardown_opts opts;
    res->teardown_variant = variant;
    ringlog_printf(x->log, "TEARDOWN4 variant=%s cycles_started=%u cycles_completed=%u rearms=%u/%u deliveries=%u acks=%u unmasks=%u",
                   variant, res->cycles_started, res->completed_cycles, res->rearms_attempted, res->rearms_completed,
                   res->deliveries, res->acks, res->unmasks);
    opts.pi_cleanup_allowed = 1;                 /* the teardown's own budget: one W1C at most, whatever the cycles spent */
    opts.pre_arinfo_hook = teardown_hook;
    opts.hook_ctx = x;
    opts.pi_policy = res->unmasks ? "unmasked_per_cycle" : "never_unmasked";
    gbp_initirqa_teardown(x->t, x->log, &x->cfg->a, &res->a, &opts);
    if (res->a.pi_cleanup_performed) res->teardown_w1c = 1;
    res->pi_sticky_final = bit13(res->a.cleanup_intsr_after) ? 1 : 0;
    if (!res->a.restore_ok && res->restore_ok) restore_fail(res, res->a.restore_reason);
}

static void cycle_end_records(struct run_ctx *x, const struct gbp_initirq4_cycle *c)
{
    const struct gbp_irq_record *r = &c->d.rec;
    ringlog_printf(x->log, "CYCLE n=%u end cause=%d t_cause=%lu immediate=%d prepared=%d preunmask=%d/%s unmasked=%d fired=%d count=%lu latency_ticks=%lu delivered=%d",
                   c->index, c->cause_ready, (unsigned long)c->t_cause, c->cause_immediate, c->prepared, c->preunmask_ok,
                   c->preunmask_reason ? c->preunmask_reason : "-", c->d.irq_unmasked, c->d.fired, (unsigned long)r->count,
                   (unsigned long)c->d.latency_ticks, c->delivered);
    ringlog_printf(x->log, "CYCLE n=%u ack=%d/%d ack_value=%04x pending=%04x skipped=%d reason=%s postack_irq=%04x main_w1c=%d sticky=%d unexpected=%04x site=%s boundary=%d",
                   c->index, c->k.w_ack.attempted, c->k.w_ack.completed, (unsigned)c->k.ack_value, (unsigned)c->k.irq_pending,
                   c->k.ack_skipped, c->k.ack_skip_reason ? c->k.ack_skip_reason : "-", (unsigned)c->k.postack.irq_gbi,
                   c->k.main_pi_w1c, c->k.main_w1c_sticky, (unsigned)c->unexpected, c->unexpected_site ? c->unexpected_site : "-",
                   c->boundary_ok);
    ringlog_printf(x->log, "CYCLE n=%u rearm=%d/%d t_rearm=%lu rearmpost=%s rearmpost_ok=%d rearmpost_irq=%04x next_cause_polls=%u next_cause_timed_out=%d",
                   c->index, c->rearm_attempted, c->rearm_completed, (unsigned long)c->t_rearm,
                   gbp_initirq4_rearmpost_name(c->rearmpost_outcome), c->rearmpost_ok, (unsigned)c->rearmpost.irq_gbi,
                   c->cause_polls, c->cause_timed_out);
    ringlog_printf(x->log, "TIMING n=%u cause_to_isr=%lu/%luus isr_second=%lu isr_to_preack=%lu ack_to_postack=%lu postack_to_rearm=%lu rearm_to_next_cause=%lu/%luus",
                   c->index, (unsigned long)c->dt_cause_to_isr, (unsigned long)ticks_to_us(x->cfg->a.tb_hz, c->dt_cause_to_isr),
                   (unsigned long)c->dt_isr_second, (unsigned long)c->dt_isr_to_preack, (unsigned long)c->dt_ack_to_postack,
                   (unsigned long)c->dt_postack_to_rearm, (unsigned long)c->dt_rearm_to_next_cause,
                   (unsigned long)ticks_to_us(x->cfg->a.tb_hz, c->dt_rearm_to_next_cause));
}

/* Writes that were issued but whose completion the transport did not report
 * (device state uncertain): the 003A stage's five, the ACK and the re-arm of every cycle. */
static unsigned count_uncertain4(const struct gbp_initirq4_result *res)
{
    const struct gbp_regwrite_result *w[5];
    unsigned i, n = 0;
    w[0] = &res->a.w_ctl_exp; w[1] = &res->a.w_a1; w[2] = &res->a.w_a2; w[3] = &res->a.w_stop; w[4] = &res->a.w_ctl_restore;
    for (i = 0; i < 5; i++) if (w[i]->attempted && !w[i]->completed) n++;
    for (i = 0; i < GBP_INITIRQ4_MAX_CYCLES; i++) {
        const struct gbp_initirq4_cycle *c = &res->cycles[i];
        if (c->k.w_ack.attempted && !c->k.w_ack.completed) n++;
        if (c->w_rearm.attempted && !c->w_rearm.completed) n++;
    }
    return n;
}

static void end_records(struct run_ctx *x)
{
    struct gbp_initirq4_result *res = x->res;
    unsigned i;
    res->uncertain_writes = count_uncertain4(res);
    res->errors = res->a.errors;
    res->transport_ok = (res->errors == 0) ? 1 : 0;
    res->power_cycle_required = res->a.power_cycle_required;
    if (res->h.handler_was_installed && x->t->irq_multi_status) x->t->irq_multi_status(x->t->ctx, &res->multi_final);
    res->entries_total = res->multi_final.entries_total;
    res->generation_errors = res->multi_final.generation_errors;
    ringlog_printf(x->log, "INITIRQ4 end status=%s reason=%s restore=%s restore_reason=%s teardown=%s power_cycle_required=%d errors=%u transport_ok=%d",
                   res->status_name, res->reason, res->restore_ok ? "ok" : "error", res->restore_reason,
                   res->teardown_variant ? res->teardown_variant : "-", res->power_cycle_required, res->errors, res->transport_ok);
    gbp_initirqa_log_summary_records(x->log, &res->a);
    ringlog_printf(x->log, "CYCLES requested=%u completed=%u causes=%u deliveries=%u acks=%u rearms=%u next_causes=%u reentry=%u unexpected=%u timeouts=%u isr_w1c=%u main_w1c=%u teardown_w1c=%u",
                   res->cycles_requested, res->completed_cycles, res->causes, res->deliveries, res->acks, res->rearms_completed,
                   res->next_causes, res->reentries, res->unexpected_sources, res->timeouts, res->isr_w1c, res->main_w1c, res->teardown_w1c);
    for (i = 0; i < GBP_INITIRQ4_MAX_CYCLES; i++) if (res->cycles[i].started) cycle_end_records(x, &res->cycles[i]);
    ringlog_printf(x->log, "MULTI expected_gen=%lu entries_total=%lu generation_errors=%lu anomaly_count=%lu anomaly_fired=%lu unmasks=%u",
                   (unsigned long)res->multi_final.expected_gen, (unsigned long)res->multi_final.entries_total,
                   (unsigned long)res->multi_final.generation_errors, (unsigned long)res->multi_final.anomaly.count,
                   (unsigned long)res->multi_final.anomaly.fired, res->unmasks);
    ringlog_printf(x->log, "RESTORE4 handler_installed=%d handler_restored=%d old_handler=%s mask_ok=%d intmr_final=%08lx pi_sticky_final=%d control_ok=%d uncertain=%u",
                   res->h.handler_was_installed, res->h.handler_restored, old_handler_name(&res->h), res->h.mask_ok,
                   (unsigned long)res->h.intmr_final, res->pi_sticky_final, res->control_ok, res->uncertain_writes);
}

static void set_status(struct gbp_initirq4_result *res, gbp_initirq4_status st, const char *reason)
{
    res->status = st;
    res->status_name = gbp_initirq4_status_name(st);
    res->reason = reason;
}

static const char *cycle_reason(struct gbp_initirq4_result *res, const char *what, unsigned n)
{
    snprintf(res->reason_buf, sizeof res->reason_buf, "%s_cycle_%u", what, n);
    return res->reason_buf;
}

static void finish(struct run_ctx *x, gbp_initirq4_status st, const char *reason, const char *variant)
{
    set_status(x->res, st, reason);
    teardown4(x, variant);
    end_records(x);
}

/* ---- per-cycle helpers ------------------------------------------------ */
static void cycle_tags(struct gbp_initirq4_cycle *c, unsigned n)
{
    c->index = n;
    snprintf(c->tag_preunmask, sizeof c->tag_preunmask, "PREUNMASK-%u", n);
    snprintf(c->tag_preack, sizeof c->tag_preack, "PREACK-%u", n);
    snprintf(c->tag_postack, sizeof c->tag_postack, "POSTACK-%u", n);
    snprintf(c->tag_ack, sizeof c->tag_ack, "tag=ACK-%u", n);
    snprintf(c->tag_rearm, sizeof c->tag_rearm, "tag=REARM-%u", n);
    snprintf(c->tag_rearmpost, sizeof c->tag_rearmpost, "REARMPOST-%u", n);
    snprintf(c->tag_nextcause, sizeof c->tag_nextcause, "NEXTCAUSE-%u", n);
    snprintf(c->nfield, sizeof c->nfield, " n=%u", n);
    snprintf(c->sfx, sizeof c->sfx, "-%u", n);
}

static void note_control(struct gbp_initirq4_result *res, const struct gbp_initirqa_snapshot *s)
{
    if (s->control_rc == GBP_OK && (s->control_vote != res->a.control_exp || s->control_vote != s->control_b1f)) res->control_ok = 0;
}

static void read_multi(struct run_ctx *x, struct gbp_irq_multi_status *m)
{
    memset(m, 0, sizeof *m);
    x->t->irq_multi_status(x->t->ctx, m);
}

/* The wait for the next cause after a re-arm (outcome A or C): INTSR polled while masked,
 * bounded by t_next_cause_ticks since t_rearm, no formatting per poll. On INTSR bit 13 the
 * NEXTCAUSE snapshot is taken at the poll's own time base value (one read, as the 003A EVENT). */
static int wait_next_cause(struct run_ctx *x, struct gbp_initirq4_cycle *c, struct gbp_initirq4_cycle *nx, uint32_t *t_end)
{
    uint32_t tnow, intsr;
    for (;;) {
        tnow = now(x->t);
        if (x->t->poll_intsr(x->t->ctx, &intsr) == GBP_OK) {
            c->cause_polls++;
            if (intsr & GBP_PI_HSP_BIT) {
                gbp_initirqa_snapshot_take_at(x->t, &x->res->a, &nx->nextcause, c->tag_nextcause, 0, 1, tnow, intsr, c->cause_polls);
                *t_end = tnow;
                return 1;
            }
        } else {
            x->res->a.poll_errors++;
        }
        if ((uint32_t)(tnow - c->t_rearm) >= x->cfg->t_next_cause_ticks) { *t_end = tnow; return 0; }
    }
}

int gbp_initirq4_probe_run(const struct gbp_transport *t, struct ringlog *log,
                           const struct gbp_initirq4_config *cfg, struct gbp_initirq4_result *res)
{
    struct run_ctx xs, *x = &xs;
    gbp_initirqa_cause_rc crc;
    const struct gbp_initirqa_snapshot *ev;
    struct gbp_irq_record rec0;
    struct gbp_irq_multi_status m0;
    int old_null = -1;
    unsigned n, i;

    xs.t = t; xs.log = log; xs.cfg = cfg; xs.res = res;
    memset(res, 0, sizeof *res);
    res->restore_ok = 1;
    res->restore_reason = "-";
    res->reason = "-";
    res->status_name = "-";
    res->control_ok = 1;
    res->cycles_requested = cfg->max_cycles;
    gbp_irq_service_handler_init(&res->h);
    for (i = 0; i < GBP_INITIRQ4_MAX_CYCLES; i++) {
        struct gbp_initirq4_cycle *c = &res->cycles[i];
        cycle_tags(c, i);
        gbp_irq_service_delivery_init(&c->d);
        gbp_irq_service_ack_init(&c->k);
        c->preunmask_reason = "-";
        c->unexpected_site = "-";
    }
    ringlog_printf(log, "INITIRQ4 start max_cycles=%u max_rearms=%u t_delivery_ms=%lu t_delivery_ticks=%lu t_next_cause_ms=%lu t_next_cause_ticks=%lu ack_or=%04x src_mask=%04x av_mask=%04x odd_mask=%04x bit15_mask=%04x high_mask=%04x",
                   cfg->max_cycles, cfg->max_rearms, (unsigned long)cfg->t_delivery_ms, (unsigned long)cfg->t_delivery_ticks,
                   (unsigned long)cfg->t_next_cause_ms, (unsigned long)cfg->t_next_cause_ticks, (unsigned)cfg->ack_or,
                   (unsigned)cfg->src_mask, (unsigned)cfg->av_mask, (unsigned)cfg->odd_mask, (unsigned)cfg->bit15_mask, (unsigned)cfg->high_mask);
    ringlog_printf(log, "INITIRQ4 policy handler=installed_once control=written_once_never_per_cycle rearm=irq_zero_after_clean_boundary_only ack=read_or_%04x_av_only w1c_budget=isr1_main1_rearmpost0_teardown1",
                   (unsigned)cfg->ack_or);

    /* ---- 1. the GBP-INIT-003A sequence, verbatim, PI masked, no handler ---- */
    crc = gbp_initirqa_run_cause(t, log, &cfg->a, &res->a);
    if (crc == GBP_INITIRQA_CAUSE_ABORTED) {
        res->stage_a_aborted = 1;
        res->status = GBP_INITIRQ4_ABORT_STAGE_A;
        res->status_name = gbp_initirqa_status_name(res->a.status);
        res->reason = res->a.reason ? res->a.reason : "-";
        res->teardown_variant = "stage_a";
        if (!res->a.restore_ok) restore_fail(res, res->a.restore_reason);
        end_records(x);
        return 0;
    }
    if (crc == GBP_INITIRQA_CAUSE_NOT_OBSERVED) {
        finish(x, GBP_INITIRQ4_NO_INITIAL_CAUSE, "no_intsr13_within_t_max", "S2_before_unmask");
        return 0;
    }

    /* ---- 2. the first cause is latched at the PI: record it, touch nothing ---- */
    ev = &res->a.snap[GBP_INITIRQA_SNAP_EVENT];
    res->causes = 1;
    {
        struct gbp_initirq4_cycle *c0 = &res->cycles[0];
        c0->cause_ready = 1;
        c0->t_cause = ev->taken ? ev->ticks : res->a.t_first_intsr13;
        c0->cause_irq = ev->irq_gbi;
        c0->cause_intsr = ev->poll_intsr;
        ringlog_printf(log, "CAUSE n=0 t_cause=%lu since_a2=%lu intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u control=%02x irq=%04x/%04x av=%04x unexpected=%04x",
                       (unsigned long)c0->t_cause, (unsigned long)ev->since_a2, (unsigned long)ev->intsr, (unsigned long)ev->intmr,
                       bit13(ev->intsr), bit13(ev->intmr), (unsigned)ev->control_vote, (unsigned)ev->irq_gbi, (unsigned)ev->irq_disc,
                       (unsigned)(ev->irq_gbi & cfg->av_mask), (unsigned)(ev->irq_gbi & cfg->src_mask & (uint16_t)~cfg->av_mask));
    }

    /* ---- 3. the handler, installed once (point B: after the cause); previous handler kept ---- */
    res->h.irq_path_available = gbp_transport_has_irq_multi_path(t);
    if (!res->h.irq_path_available) {
        ringlog_printf(log, "IRQ install rc=unavailable multi_path=%d", gbp_transport_has_irq_path(t));
        finish(x, GBP_INITIRQ4_ABORT_HANDLER_INSTALL, "irq_multi_ops_unavailable", "S2_before_unmask");
        return 0;
    }
    res->h.install_rc = t->irq_install(t->ctx, &old_null);
    if (res->h.install_rc != GBP_OK) {
        res->a.errors++;
        ringlog_printf(log, "IRQ install rc=%s", gbp_status_name(res->h.install_rc));
        finish(x, GBP_INITIRQ4_ABORT_HANDLER_INSTALL, "install_failed", "S2_before_unmask");
        return 0;
    }
    res->h.handler_installed = 1;
    res->h.handler_was_installed = 1;
    res->h.old_handler_null = old_null ? 1 : 0;
    memset(&rec0, 0, sizeof rec0);
    t->irq_record_slot(t->ctx, 0, &rec0);        /* the install clears every slot: count 0, fired 0 expected */
    res->h.install_count = rec0.count;
    res->h.install_fired = rec0.fired;
    read_multi(x, &m0);
    ringlog_printf(log, "IRQ install rc=ok old_handler=%s record_count=%lu record_fired=%lu", old_null ? "null" : "nonnull",
                   (unsigned long)rec0.count, (unsigned long)rec0.fired);
    ringlog_printf(log, "MULTI install expected_gen=%lu entries_total=%lu generation_errors=%lu anomaly_count=%lu anomaly_fired=%lu slots=%u",
                   (unsigned long)m0.expected_gen, (unsigned long)m0.entries_total, (unsigned long)m0.generation_errors,
                   (unsigned long)m0.anomaly.count, (unsigned long)m0.anomaly.fired, (unsigned)GBP_IRQ_MULTI_SLOTS);

    /* ---- 4. the cycles ---- */
    for (n = 0; n < cfg->max_cycles && n < GBP_INITIRQ4_MAX_CYCLES; n++) {
        struct gbp_initirq4_cycle *c = &res->cycles[n];
        struct gbp_initirq4_cycle *prev = n ? &res->cycles[n - 1] : 0;
        struct gbp_initirq4_cycle *nx = (n + 1 < GBP_INITIRQ4_MAX_CYCLES) ? &res->cycles[n + 1] : 0;
        const char *why = "-";
        const char *before_unmask = n ? "S4B_next_cause_latched" : "S2_before_unmask";
        uint32_t evidence_intmr;
        int last_cycle = (n + 1 >= cfg->max_cycles) ? 1 : 0;

        c->started = 1;
        res->cycles_started = n + 1;
        ringlog_printf(log, "CYCLE n=%u start t_cause=%lu cause_irq=%04x immediate=%d", n, (unsigned long)c->t_cause,
                       (unsigned)c->cause_irq, c->cause_immediate);

        /* ---- PREPARE: publish generation n, only with INTMR bit 13 = 0 (last PI evidence) ---- */
        evidence_intmr = n == 0 ? ev->intmr : (c->cause_immediate ? prev->rearmpost.intmr2 : c->nextcause.intmr2);
        c->prepare_intmr = evidence_intmr;
        if (bit13(evidence_intmr)) {
            ringlog_printf(log, "PREPARE n=%u gen=%u rc=skipped intmr13=1", n, n);
            finish(x, GBP_INITIRQ4_ANOMALY_MASK_FAILURE, cycle_reason(res, "intmr13_set_before_prepare", n), before_unmask);
            return 0;
        }
        c->prepare_rc = t->irq_prepare(t->ctx, n);
        c->prepared = (c->prepare_rc == GBP_OK) ? 1 : 0;
        memset(&c->slot_before, 0, sizeof c->slot_before);
        t->irq_record_slot(t->ctx, n, &c->slot_before);
        read_multi(x, &c->multi_before);
        ringlog_printf(log, "PREPARE n=%u gen=%u rc=%s intmr13=%u expected_gen=%lu entries_total=%lu generation_errors=%lu slot_count=%lu slot_fired=%lu",
                       n, n, gbp_status_name(c->prepare_rc), bit13(evidence_intmr), (unsigned long)c->multi_before.expected_gen,
                       (unsigned long)c->multi_before.entries_total, (unsigned long)c->multi_before.generation_errors,
                       (unsigned long)c->slot_before.count, (unsigned long)c->slot_before.fired);
        if (!c->prepared) {
            res->a.errors++;
            finish(x, GBP_INITIRQ4_ABORT_HANDLER_INSTALL, cycle_reason(res, "prepare_failed", n), before_unmask);
            return 0;
        }
        if (c->slot_before.count || c->slot_before.fired) {
            /* n = 0: the install precondition of 003B (record not clean); n > 0: an entry landed in a future slot */
            if (n == 0) finish(x, GBP_INITIRQ4_ABORT_PRE_UNMASK_STATE, "record_not_clear", before_unmask);
            else finish(x, GBP_INITIRQ4_ANOMALY_GENERATION, cycle_reason(res, "slot_not_clean", n), before_unmask);
            return 0;
        }
        if (c->multi_before.expected_gen != n || c->multi_before.generation_errors || c->multi_before.entries_total != res->deliveries) {
            finish(x, GBP_INITIRQ4_ANOMALY_GENERATION, cycle_reason(res, "generation_mismatch", n), before_unmask);
            return 0;
        }

        /* ---- PREUNMASK-n: the 003B preconditions + the AV rule + the causal boundary ---- */
        gbp_initirqa_snapshot_take(t, &res->a, &c->preunmask, c->tag_preunmask, 0, 1);
        gbp_initirqa_snapshot_log(log, &res->a, &c->preunmask);
        note_control(res, &c->preunmask);
        c->preunmask_ok = gbp_irq_service_preunmask_check(&c->preunmask, res->a.control_exp, cfg->src_mask, cfg->odd_mask,
                                                          cfg->bit15_mask, cfg->high_mask, c->slot_before.count, c->slot_before.fired, &why);
        if (c->preunmask_ok) {
            uint16_t unexpected = (uint16_t)(c->preunmask.irq_gbi & cfg->src_mask & (uint16_t)~cfg->av_mask);
            if (unexpected) { c->preunmask_ok = 0; why = "unexpected_source"; c->unexpected = unexpected; c->unexpected_site = "PREUNMASK"; }
            else if ((c->preunmask.irq_gbi & cfg->av_mask) == 0) { c->preunmask_ok = 0; why = "no_av_source"; }
            else if (prev && (int32_t)(c->t_cause - prev->t_rearm) <= 0) { c->preunmask_ok = 0; why = "cause_not_after_rearm"; }
        }
        c->preunmask_reason = why;
        gbp_irq_service_log_preunmask(log, c->nfield, &c->preunmask, c->preunmask_ok, why, cfg->src_mask, cfg->odd_mask, cfg->bit15_mask);
        ringlog_printf(log, "PREUNMASK4 n=%u av=%04x unexpected=%04x expected_gen=%lu slot_clean=%d t_cause=%lu since_rearm=%lu ok=%d",
                       n, (unsigned)(c->preunmask.irq_gbi & cfg->av_mask), (unsigned)(c->preunmask.irq_gbi & cfg->src_mask & (uint16_t)~cfg->av_mask),
                       (unsigned long)c->multi_before.expected_gen, (c->slot_before.count || c->slot_before.fired) ? 0 : 1,
                       (unsigned long)c->t_cause, (unsigned long)c->since_rearm, c->preunmask_ok);
        if (!c->preunmask_ok) {
            if (c->unexpected) { res->unexpected_sources++; finish(x, GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE, cycle_reason(res, "unexpected_source", n), before_unmask); }
            else if (strcmp(why, "control_changed") == 0) finish(x, GBP_INITIRQ4_ANOMALY_CONTROL_CHANGED, cycle_reason(res, "control_changed_preunmask", n), before_unmask);
            else finish(x, GBP_INITIRQ4_ABORT_PRE_UNMASK_STATE, why, before_unmask);
            return 0;
        }

        /* ---- UNMASK-n / delivery / main re-mask / record (gbp_irq_service) ---- */
        res->unmasks++;
        gbp_irq_service_deliver(t, log, cfg->a.tb_hz, cfg->t_delivery_ms, cfg->t_delivery_ticks, (int)n, c->nfield, c->sfx, &c->d, &res->a.errors);
        if (c->d.mask_rc != GBP_OK) restore_fail(res, "mask_failed");
        read_multi(x, &c->multi_after);
        ringlog_printf(log, "HANDLER4 n=%u expected_gen=%lu entries_total=%lu generation_errors=%lu anomaly_count=%lu anomaly_fired=%lu deliveries_before=%u",
                       n, (unsigned long)c->multi_after.expected_gen, (unsigned long)c->multi_after.entries_total,
                       (unsigned long)c->multi_after.generation_errors, (unsigned long)c->multi_after.anomaly.count,
                       (unsigned long)c->multi_after.anomaly.fired, res->deliveries);
        if (c->multi_after.generation_errors) res->generation_errors = c->multi_after.generation_errors;
        if (!c->d.fired) {
            int never_opened = (c->d.unmask_rc != GBP_OK) ||
                               (c->d.pi_post_unmask_ok && !bit13(c->d.intmr_post_unmask) && c->d.rec.count == 0 &&
                                c->multi_after.entries_total == res->deliveries);
            if (c->d.unmask_rc != GBP_OK) res->a.errors++;
            if (never_opened) { finish(x, GBP_INITIRQ4_ABORT_UNMASK, cycle_reason(res, "unmask_not_effective", n), "S3_cycle_aborted"); return 0; }
            if (c->multi_after.generation_errors) { finish(x, GBP_INITIRQ4_ANOMALY_GENERATION, cycle_reason(res, "generation_out_of_range", n), "S3_cycle_aborted"); return 0; }
            if (c->multi_after.entries_total != res->deliveries) { res->reentries++; finish(x, GBP_INITIRQ4_ANOMALY_REENTRY, cycle_reason(res, "entry_outside_slot", n), "S3_cycle_aborted"); return 0; }
            res->timeouts++;
            finish(x, GBP_INITIRQ4_DELIVERY_TIMEOUT, cycle_reason(res, "delivery_timeout", n), "S3_cycle_aborted");
            return 0;
        }
        res->deliveries++;
        res->isr_w1c++;                              /* the first entry of a slot performs the body's single W1C */
        c->dt_cause_to_isr = (uint32_t)(c->d.rec.t_entry - c->t_cause);
        c->dt_isr_second = (uint32_t)(c->d.rec.t_second - c->d.rec.t_entry);
        if (c->d.reentry) { res->reentries++; finish(x, GBP_INITIRQ4_ANOMALY_REENTRY, cycle_reason(res, "reentry", n), "S3_cycle_aborted"); return 0; }
        if (c->multi_after.generation_errors) { finish(x, GBP_INITIRQ4_ANOMALY_GENERATION, cycle_reason(res, "generation_out_of_range", n), "S3_cycle_aborted"); return 0; }
        if (c->multi_after.entries_total != res->deliveries) { res->reentries++; finish(x, GBP_INITIRQ4_ANOMALY_REENTRY, cycle_reason(res, "entry_outside_slot", n), "S3_cycle_aborted"); return 0; }
        if (c->d.main_mask_ok != 1) { finish(x, GBP_INITIRQ4_ANOMALY_MASK_FAILURE, cycle_reason(res, "intmr13_still_set_after_remask", n), "S3_cycle_aborted"); return 0; }
        c->delivered = 1;

        /* ---- PREACK-n / ACK-n / POSTACK-n / the cycle's single main W1C (gbp_irq_service) ---- */
        gbp_irq_service_ack(t, log, &res->a, cfg->ack_or, cfg->src_mask, cfg->av_mask, 1, 1, res->a.control_exp,
                            c->nfield, c->tag_preack, c->tag_postack, c->tag_ack, c->sfx, &c->k, &res->a.errors);
        note_control(res, &c->k.preack);
        note_control(res, &c->k.postack);
        c->dt_isr_to_preack = (uint32_t)(c->k.preack.ticks - c->d.rec.t_entry);
        if (c->k.main_pi_w1c) { res->main_w1c++; if (c->k.main_w1c_rc != GBP_OK) restore_fail(res, "main_pi_w1c_failed"); }
        if (c->k.ack_skipped) {
            const char *r = c->k.ack_skip_reason;
            if (strcmp(r, "unexpected_source") == 0) { c->unexpected = c->k.unexpected; c->unexpected_site = "PREACK"; res->unexpected_sources++;
                finish(x, GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE, cycle_reason(res, "unexpected_source", n), "S3_cycle_aborted"); }
            else if (strcmp(r, "source_lost") == 0) { c->source_lost = 1; finish(x, GBP_INITIRQ4_ANOMALY_SOURCE_LOST_BEFORE_ACK, cycle_reason(res, "source_lost_before_ack", n), "S3_cycle_aborted"); }
            else if (strcmp(r, "control_changed") == 0) finish(x, GBP_INITIRQ4_ANOMALY_CONTROL_CHANGED, cycle_reason(res, "control_changed_preack", n), "S3_cycle_aborted");
            else if (strcmp(r, "intmr13_set") == 0) finish(x, GBP_INITIRQ4_ANOMALY_MASK_FAILURE, cycle_reason(res, "intmr13_set_preack", n), "S3_cycle_aborted");
            else if (strcmp(r, "semantic_disagree") == 0) finish(x, GBP_INITIRQ4_ABORT_READ_INCONSISTENT, cycle_reason(res, "preack_semantic_disagree", n), "S3_cycle_aborted");
            else finish(x, GBP_INITIRQ4_ABORT_TRANSPORT, cycle_reason(res, "preack_read_failed", n), "S3_cycle_aborted");
            return 0;
        }
        if (!c->k.w_ack.completed) {
            finish(x, GBP_INITIRQ4_ABORT_TRANSPORT, cycle_reason(res, "ack_write_failed", n), "S3_cycle_aborted");
            return 0;
        }
        res->acks++;
        c->acked = 1;
        c->dt_ack_to_postack = (uint32_t)(c->k.postack.ticks - c->k.w_ack.t_after);

        /* ---- POSTACK-n: the clean boundary before any re-arm ---- */
        if (!c->k.postack.pi_ok || c->k.postack.control_rc != GBP_OK || c->k.postack.irq_rc != GBP_OK) {
            finish(x, GBP_INITIRQ4_ABORT_TRANSPORT, cycle_reason(res, "postack_read_failed", n), "S3_cycle_aborted"); return 0;
        }
        if (c->k.postack.irq_disc != c->k.postack.irq_gbi) {
            finish(x, GBP_INITIRQ4_ABORT_READ_INCONSISTENT, cycle_reason(res, "postack_semantic_disagree", n), "S3_cycle_aborted"); return 0;
        }
        if (c->k.postack.control_vote != res->a.control_exp || c->k.postack.control_vote != c->k.postack.control_b1f) {
            finish(x, GBP_INITIRQ4_ANOMALY_CONTROL_CHANGED, cycle_reason(res, "control_changed_postack", n), "S3_cycle_aborted"); return 0;
        }
        if (bit13(c->k.postack.intmr) || (c->k.postack.pi2_ok && bit13(c->k.postack.intmr2))) {
            finish(x, GBP_INITIRQ4_ANOMALY_MASK_FAILURE, cycle_reason(res, "intmr13_set_postack", n), "S3_cycle_aborted"); return 0;
        }
        if (c->k.postack.irq_gbi & cfg->src_mask) {
            uint16_t unexpected = (uint16_t)(c->k.postack.irq_gbi & cfg->src_mask & (uint16_t)~cfg->av_mask);
            if (unexpected) { c->unexpected = unexpected; c->unexpected_site = "POSTACK"; res->unexpected_sources++;
                finish(x, GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE, cycle_reason(res, "unexpected_source", n), "S3_cycle_aborted"); }
            else { c->source_not_cleared = 1; finish(x, GBP_INITIRQ4_ANOMALY_SOURCE_NOT_CLEARED, cycle_reason(res, "source_pending_after_ack", n), "S3_cycle_aborted"); }
            return 0;
        }
        /* PI clean: the POSTACK W1C (if any) is the cycle's one main W1C; its re-read must show bit 13 clear */
        if (c->k.main_pi_w1c) { c->pi_clean_intsr = c->k.main_w1c_intsr_after; c->pi_clean_intmr = c->k.main_w1c_intmr_after; }
        else { c->pi_clean_intsr = c->k.postack.pi2_ok ? c->k.postack.intsr2 : c->k.postack.intsr; c->pi_clean_intmr = c->k.postack.pi2_ok ? c->k.postack.intmr2 : c->k.postack.intmr; }
        c->pi_clean = (!bit13(c->pi_clean_intsr) && !bit13(c->pi_clean_intmr)) ? 1 : 0;
        c->pi_sticky = c->k.main_w1c_sticky;
        ringlog_printf(log, "PICLEAN n=%u intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u main_w1c=%d sticky=%d ok=%d",
                       n, (unsigned long)c->pi_clean_intsr, (unsigned long)c->pi_clean_intmr, bit13(c->pi_clean_intsr),
                       bit13(c->pi_clean_intmr), c->k.main_pi_w1c, c->pi_sticky, c->pi_clean);
        if (!c->pi_clean) {
            if (c->pi_sticky) finish(x, GBP_INITIRQ4_ANOMALY_PI_STICKY_AFTER_ACK, cycle_reason(res, "pi_sticky_after_ack", n), "S3_cycle_aborted");
            else finish(x, GBP_INITIRQ4_ANOMALY_MASK_FAILURE, cycle_reason(res, "pi_not_clean_after_ack", n), "S3_cycle_aborted");
            return 0;
        }
        c->boundary_ok = 1;
        res->completed_cycles++;
        ringlog_printf(log, "BOUNDARY n=%u ok=1 completed_cycles=%u deliveries=%u acks=%u main_w1c=%u", n, res->completed_cycles,
                       res->deliveries, res->acks, res->main_w1c);

        if (last_cycle || n >= cfg->max_rearms || !nx) break;   /* the final cycle: no re-arm, teardown with the CPU masked */

        /* ---- REARM-n: IRQ := 0x0000 (GBI's end-of-pass write), only after the clean boundary ---- */
        c->t_rearm = now(t);
        c->rearm_before = c->k.postack.irq_gbi;
        ringlog_printf(log, "REARM n=%u t_rearm=%lu before=%04x value=0000 layout=gbi-u16-replicated after=clean_boundary", n,
                       (unsigned long)c->t_rearm, (unsigned)c->rearm_before);
        c->rearm_attempted = 1;
        res->rearms_attempted++;
        res->a.irq_writes_attempted++;
        res->a.power_cycle_required = 1;
        gbp_regwrite_irq_u16(t, c->tag_rearm, res->a.base, c->rearm_before, 0x0000, &c->w_rearm, &res->a.errors);
        if (c->w_rearm.completed) { c->rearm_completed = 1; res->rearms_completed++; res->a.irq_writes_completed++; }
        gbp_regwrite_log(log, &c->w_rearm);
        c->dt_postack_to_rearm = (uint32_t)(c->t_rearm - c->k.postack.ticks);
        if (!c->rearm_completed) {
            finish(x, GBP_INITIRQ4_ABORT_TRANSPORT, cycle_reason(res, "rearm_write_failed", n), "S4_rearm_failed");
            return 0;
        }

        /* ---- REARMPOST-n: the state right after the re-arm (no W1C here, ever) ---- */
        gbp_initirqa_snapshot_take(t, &res->a, &c->rearmpost, c->tag_rearmpost, 0, 1);
        gbp_initirqa_snapshot_log(log, &res->a, &c->rearmpost);
        note_control(res, &c->rearmpost);
        {
            const struct gbp_initirqa_snapshot *s = &c->rearmpost;
            uint16_t src = (uint16_t)(s->irq_gbi & cfg->src_mask);
            uint16_t av = (uint16_t)(s->irq_gbi & cfg->av_mask);
            uint16_t unexpected = (uint16_t)(src & (uint16_t)~cfg->av_mask);
            unsigned latched = s->pi2_ok ? bit13(s->intsr2) : bit13(s->intsr);
            unsigned latched_first = bit13(s->intsr);
            int shape_ok = ((s->irq_gbi & cfg->odd_mask) == 0 && (s->irq_gbi & cfg->bit15_mask) == 0 && (s->irq_gbi & cfg->high_mask) == 0) ? 1 : 0;
            int reads_ok = (s->pi_ok && s->control_rc == GBP_OK && s->irq_rc == GBP_OK) ? 1 : 0;
            int control_ok = (s->control_rc == GBP_OK && s->control_vote == res->a.control_exp && s->control_vote == s->control_b1f) ? 1 : 0;
            int masked = (!bit13(s->intmr) && !(s->pi2_ok && bit13(s->intmr2))) ? 1 : 0;
            int agree = (s->irq_disc == s->irq_gbi) ? 1 : 0;
            c->rearmpost_ok = (reads_ok && control_ok && masked && agree && shape_ok) ? 1 : 0;
            if (!reads_ok) c->rearmpost_outcome = GBP_INITIRQ4_REARMPOST_NONE;
            else if (!shape_ok) c->rearmpost_outcome = GBP_INITIRQ4_REARMPOST_E_INVALID;
            else if (unexpected) c->rearmpost_outcome = GBP_INITIRQ4_REARMPOST_D_UNEXPECTED;
            else if (src == 0 && !latched && !latched_first) c->rearmpost_outcome = GBP_INITIRQ4_REARMPOST_A_QUIET;
            else if (av && latched) c->rearmpost_outcome = GBP_INITIRQ4_REARMPOST_B_LATCHED;
            else if (av && !latched && !latched_first) c->rearmpost_outcome = GBP_INITIRQ4_REARMPOST_C_SOURCE_BEFORE_PI;
            else c->rearmpost_outcome = GBP_INITIRQ4_REARMPOST_F_INCONSISTENT;
            ringlog_printf(log, "REARMPOST n=%u t=%lu since_rearm=%lu intsr13=%u,%u intmr13=%u,%u control=%02x irq=%04x/%04x src=%04x av=%04x unexpected=%04x odd=%04x bit15=%u high=%04x outcome=%s ok=%d",
                           n, (unsigned long)s->ticks, (unsigned long)(uint32_t)(s->ticks - c->t_rearm), bit13(s->intsr), bit13(s->intsr2),
                           bit13(s->intmr), bit13(s->intmr2), (unsigned)s->control_vote, (unsigned)s->irq_gbi, (unsigned)s->irq_disc,
                           (unsigned)src, (unsigned)av, (unsigned)unexpected, (unsigned)(s->irq_gbi & cfg->odd_mask),
                           (unsigned)((s->irq_gbi & cfg->bit15_mask) ? 1u : 0u), (unsigned)(s->irq_gbi & cfg->high_mask),
                           gbp_initirq4_rearmpost_name(c->rearmpost_outcome), c->rearmpost_ok);
            if (!reads_ok) { finish(x, GBP_INITIRQ4_ABORT_TRANSPORT, cycle_reason(res, "rearmpost_read_failed", n), "S4C_rearmpost_invalid"); return 0; }
            if (!agree) { finish(x, GBP_INITIRQ4_ABORT_READ_INCONSISTENT, cycle_reason(res, "rearmpost_semantic_disagree", n), "S4C_rearmpost_invalid"); return 0; }
            if (!control_ok) { finish(x, GBP_INITIRQ4_ANOMALY_CONTROL_CHANGED, cycle_reason(res, "control_changed_rearmpost", n), "S4C_rearmpost_invalid"); return 0; }
            if (!masked) { finish(x, GBP_INITIRQ4_ANOMALY_MASK_FAILURE, cycle_reason(res, "intmr13_set_rearmpost", n), "S4C_rearmpost_invalid"); return 0; }
            if (c->rearmpost_outcome == GBP_INITIRQ4_REARMPOST_E_INVALID) { finish(x, GBP_INITIRQ4_ANOMALY_REARM_STATE, cycle_reason(res, "rearm_state_invalid", n), "S4C_rearmpost_invalid"); return 0; }
            if (c->rearmpost_outcome == GBP_INITIRQ4_REARMPOST_D_UNEXPECTED) {
                c->unexpected = unexpected; c->unexpected_site = "REARMPOST"; res->unexpected_sources++;
                finish(x, GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE, cycle_reason(res, "unexpected_source", n), "S4C_rearmpost_invalid"); return 0;
            }
            if (c->rearmpost_outcome == GBP_INITIRQ4_REARMPOST_F_INCONSISTENT) { finish(x, GBP_INITIRQ4_ANOMALY_REARM_STATE, cycle_reason(res, "rearmpost_pi_without_source", n), "S4C_rearmpost_invalid"); return 0; }

            /* ---- NEXTCAUSE-n ---- */
            if (c->rearmpost_outcome == GBP_INITIRQ4_REARMPOST_B_LATCHED) {
                nx->cause_ready = 1;
                nx->cause_immediate = 1;
                nx->t_cause = s->ticks;
                nx->cause_irq = s->irq_gbi;
                nx->cause_intsr = s->pi2_ok ? s->intsr2 : s->intsr;
                nx->since_rearm = (uint32_t)(s->ticks - c->t_rearm);
                nx->since_prev_cause = (uint32_t)(s->ticks - c->t_cause);
                c->dt_rearm_to_next_cause = nx->since_rearm;
                res->next_causes++;
                res->causes++;
                ringlog_printf(log, "NEXTCAUSE n=%u found=1 immediate=1 t_next_cause=%lu since_rearm=%lu since_prev_cause=%lu intsr=%08lx control=%02x irq=%04x/%04x av=%04x unexpected=0000 polls=0",
                               n, (unsigned long)nx->t_cause, (unsigned long)nx->since_rearm, (unsigned long)nx->since_prev_cause,
                               (unsigned long)nx->cause_intsr, (unsigned)s->control_vote, (unsigned)s->irq_gbi, (unsigned)s->irq_disc, (unsigned)av);
            } else {
                uint32_t t_end = 0;
                int found = wait_next_cause(x, c, nx, &t_end);
                if (!found) {
                    c->cause_timed_out = 1;
                    ringlog_printf(log, "NEXTCAUSE n=%u found=0 timed_out=1 t_end=%lu since_rearm=%lu polls=%u rearmpost=%s t_next_cause_ticks=%lu",
                                   n, (unsigned long)t_end, (unsigned long)(uint32_t)(t_end - c->t_rearm), c->cause_polls,
                                   gbp_initirq4_rearmpost_name(c->rearmpost_outcome), (unsigned long)cfg->t_next_cause_ticks);
                    finish(x, GBP_INITIRQ4_NO_NEXT_CAUSE, cycle_reason(res, "no_next_cause", n), "S4A_rearmed_no_next_cause");
                    return 0;
                }
                {
                    const struct gbp_initirqa_snapshot *q = &nx->nextcause;
                    uint16_t qsrc = (uint16_t)(q->irq_gbi & cfg->src_mask);
                    uint16_t qav = (uint16_t)(q->irq_gbi & cfg->av_mask);
                    uint16_t qunexpected = (uint16_t)(qsrc & (uint16_t)~cfg->av_mask);
                    gbp_initirqa_snapshot_log(log, &res->a, q);
                    note_control(res, q);
                    nx->t_cause = q->ticks;
                    nx->cause_irq = q->irq_gbi;
                    nx->cause_intsr = q->poll_intsr;
                    nx->since_rearm = (uint32_t)(q->ticks - c->t_rearm);
                    nx->since_prev_cause = (uint32_t)(q->ticks - c->t_cause);
                    c->dt_rearm_to_next_cause = nx->since_rearm;
                    ringlog_printf(log, "NEXTCAUSE n=%u found=1 immediate=0 t_next_cause=%lu since_rearm=%lu since_prev_cause=%lu intsr=%08lx control=%02x irq=%04x/%04x av=%04x unexpected=%04x polls=%u",
                                   n, (unsigned long)nx->t_cause, (unsigned long)nx->since_rearm, (unsigned long)nx->since_prev_cause,
                                   (unsigned long)nx->cause_intsr, (unsigned)q->control_vote, (unsigned)q->irq_gbi, (unsigned)q->irq_disc,
                                   (unsigned)qav, (unsigned)qunexpected, c->cause_polls);
                    if (q->irq_rc != GBP_OK || q->control_rc != GBP_OK || !q->pi_ok) { finish(x, GBP_INITIRQ4_ABORT_TRANSPORT, cycle_reason(res, "nextcause_read_failed", n), "S4B_next_cause_latched"); return 0; }
                    if (q->irq_disc != q->irq_gbi) { finish(x, GBP_INITIRQ4_ABORT_READ_INCONSISTENT, cycle_reason(res, "nextcause_semantic_disagree", n), "S4B_next_cause_latched"); return 0; }
                    if (qunexpected) {
                        c->unexpected = qunexpected; c->unexpected_site = "NEXTCAUSE"; res->unexpected_sources++;
                        finish(x, GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE, cycle_reason(res, "unexpected_source", n), "S4B_next_cause_latched"); return 0;
                    }
                    if (!qav) { finish(x, GBP_INITIRQ4_ANOMALY_REARM_STATE, cycle_reason(res, "nextcause_pi_without_source", n), "S4B_next_cause_latched"); return 0; }
                    nx->cause_ready = 1;
                    res->next_causes++;
                    res->causes++;
                }
            }
        }
    }

    /* ---- 5. every cycle completed: no re-arm after the last one; teardown with the CPU masked ---- */
    set_status(res, GBP_INITIRQ4_OK_CYCLES_COMPLETED, "-");
    teardown4(x, "final_cycle");
    {
        int all = (res->cycles_requested == cfg->max_cycles && res->completed_cycles == cfg->max_cycles &&
                   res->deliveries == cfg->max_cycles && res->acks == cfg->max_cycles &&
                   res->rearms_completed == cfg->max_rearms && res->next_causes == cfg->max_rearms &&
                   res->unexpected_sources == 0 && res->reentries == 0 && res->generation_errors == 0) ? 1 : 0;
        unsigned uncertain = count_uncertain4(res);
        int sticky = 0;
        for (i = 0; i < GBP_INITIRQ4_MAX_CYCLES; i++) if (res->cycles[i].pi_sticky) sticky = 1;
        if (!all || sticky || uncertain || res->a.errors || !res->control_ok || !res->restore_ok)
            set_status(res, GBP_INITIRQ4_CYCLES_COMPLETED_WITH_ERRORS,
                       !all ? "counters_incomplete" : sticky ? "pi_sticky" : uncertain ? "uncertain_write" : !res->restore_ok ? res->restore_reason :
                       !res->control_ok ? "control_changed" : "transport_errors");
    }
    end_records(x);
    return 0;
}

int gbp_initirq4_summary(const struct gbp_initirq4_result *res, char *dst, size_t cap)
{
    const struct gbp_initirqa_result *a = &res->a;
    return snprintf(dst, cap,
                    "DONE status=%s reason=%s restore=%s restore_reason=%s teardown=%s verdict=%s det=%u/%u written=%d "
                    "irq_attempted=%u irq_completed=%u ctl_exp=%d/%d a1=%d/%d a2=%d/%d stop=%d/%d ctl_restore=%d/%d uncertain=%u "
                    "cause=%d t_event=%lu handler=%d old=%s cycles=%u/%u completed=%u deliveries=%u acks=%u rearms=%u/%u next_causes=%u "
                    "unexpected=%u reentry=%u timeouts=%u gen_errors=%u entries=%u isr_w1c=%u main_w1c=%u teardown_w1c=%u control_ok=%d "
                    "pi_sticky_final=%d control_restore_ok=%d irq_stop_write_ok=%d stop_post=%04x pi_cleanup=%d handler_restored=%d mask_ok=%d "
                    "arinfo_restore_ok=%d power_cycle_required=%d errors=%u transport_ok=%d",
                    res->status_name, res->reason ? res->reason : "-", res->restore_ok ? "ok" : "error",
                    res->restore_reason ? res->restore_reason : "-", res->teardown_variant ? res->teardown_variant : "-",
                    gbp_verdict_name(a->det.verdict), a->det.vote_ok, a->det.run, a->control_written,
                    a->irq_writes_attempted, a->irq_writes_completed,
                    a->w_ctl_exp.attempted, a->w_ctl_exp.completed, a->w_a1.attempted, a->w_a1.completed, a->w_a2.attempted, a->w_a2.completed,
                    a->w_stop.attempted, a->w_stop.completed, a->w_ctl_restore.attempted, a->w_ctl_restore.completed, res->uncertain_writes,
                    a->intsr13_seen, (unsigned long)a->t_first_intsr13, res->h.handler_was_installed, old_handler_name(&res->h),
                    res->cycles_started, res->cycles_requested, res->completed_cycles, res->deliveries, res->acks,
                    res->rearms_completed, res->rearms_attempted, res->next_causes,
                    res->unexpected_sources, res->reentries, res->timeouts, res->generation_errors, res->entries_total,
                    res->isr_w1c, res->main_w1c, res->teardown_w1c, res->control_ok,
                    res->pi_sticky_final, a->control_restore_ok, a->irq_stop_write_ok, (unsigned)a->irq_stop_post.gbi, a->pi_cleanup_performed,
                    res->h.handler_restored, res->h.mask_ok, a->arinfo_restore_ok,
                    res->power_cycle_required, res->errors, res->transport_ok);
}
