#include "gbp_avsvc_probe.h"

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

void gbp_avsvc_config_timebase(struct gbp_avsvc_config *cfg, uint32_t tb_hz)
{
    gbp_initirqa_config_timebase(&cfg->a, tb_hz);
    cfg->t_delivery_ticks = (uint32_t)(((uint64_t)tb_hz * cfg->t_delivery_ms) / 1000u);
    cfg->t_next_cause_ticks = (uint32_t)(((uint64_t)tb_hz * cfg->t_next_cause_ms) / 1000u);
}

void gbp_avsvc_config_default(struct gbp_avsvc_config *cfg)
{
    memset(cfg, 0, sizeof *cfg);
    gbp_initirqa_config_default(&cfg->a);
    cfg->t_delivery_ms = DEFAULT_T_DELIVERY_MS;
    cfg->t_next_cause_ms = DEFAULT_T_NEXT_CAUSE_MS;
    cfg->ack_or = 0x8000;
    cfg->src_mask = 0x0555;
    cfg->av_mask = 0x0500;
    cfg->audio_src = GBP_AVBLOCK_AUDIO_SRC;
    cfg->video_src = GBP_AVBLOCK_VIDEO_SRC;
    cfg->audio_index = GBP_AVBLOCK_AUDIO_INDEX;
    cfg->video_index = GBP_AVBLOCK_VIDEO_INDEX;
    cfg->audio_len = GBP_AVBLOCK_AUDIO_LEN;
    cfg->video_len = GBP_AVBLOCK_VIDEO_LEN;
    cfg->odd_mask = 0x0AAA;
    cfg->bit15_mask = 0x8000;
    cfg->high_mask = 0x7000;
    gbp_avsvc_config_timebase(cfg, cfg->a.tb_hz);
}

const char *gbp_avsvc_status_name(gbp_avsvc_status s)
{
    switch (s) {
    case GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED: return "ok_service_rearm_cause_observed";
    case GBP_AVSVC_NO_NEXT_CAUSE_AFTER_SERVICE: return "no_next_cause_after_service";
    case GBP_AVSVC_SERVICE_COMPLETED_WITH_ERRORS: return "service_completed_with_errors";
    case GBP_AVSVC_NO_INITIAL_CAUSE: return "no_initial_cause";
    case GBP_AVSVC_FIRST_DELIVERY_TIMEOUT: return "first_delivery_timeout";
    case GBP_AVSVC_ABORT_STAGE_A: return "abort_stage_a";
    case GBP_AVSVC_ABORT_HANDLER_INSTALL: return "abort_handler_install";
    case GBP_AVSVC_ABORT_PRE_UNMASK_STATE: return "abort_pre_unmask_state";
    case GBP_AVSVC_ABORT_UNMASK: return "abort_unmask";
    case GBP_AVSVC_ABORT_BULK_UNAVAILABLE: return "abort_bulk_unavailable";
    case GBP_AVSVC_ABORT_PRESVC_STATE: return "abort_presvc_state";
    case GBP_AVSVC_ABORT_READ_INCONSISTENT: return "abort_read_inconsistent";
    case GBP_AVSVC_ABORT_TRANSPORT: return "abort_transport";
    case GBP_AVSVC_ACK_WRITE_FAILED: return "ack_write_failed";
    case GBP_AVSVC_REARM_WRITE_FAILED: return "rearm_write_failed";
    case GBP_AVSVC_AUDIO_DMA_BUSY: return "audio_dma_busy";
    case GBP_AVSVC_AUDIO_DMA_TIMEOUT: return "audio_dma_timeout";
    case GBP_AVSVC_AUDIO_DMA_ERROR: return "audio_dma_error";
    case GBP_AVSVC_VIDEO_DMA_BUSY: return "video_dma_busy";
    case GBP_AVSVC_VIDEO_DMA_TIMEOUT: return "video_dma_timeout";
    case GBP_AVSVC_VIDEO_DMA_ERROR: return "video_dma_error";
    case GBP_AVSVC_ANOMALY_REENTRY: return "anomaly_reentry";
    case GBP_AVSVC_ANOMALY_MASK_FAILURE: return "anomaly_mask_failure";
    case GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE: return "anomaly_unexpected_source";
    case GBP_AVSVC_ANOMALY_CONTROL_CHANGED: return "anomaly_control_changed";
    case GBP_AVSVC_ANOMALY_POSTACK_SHAPE: return "anomaly_postack_shape";
    case GBP_AVSVC_ANOMALY_PI_STICKY_AFTER_SERVICE: return "anomaly_pi_sticky_after_service";
    case GBP_AVSVC_ANOMALY_REARM_STATE: return "anomaly_rearm_state";
    default: return "?";
    }
}

/* hardware observation / transport error / DMA error / protocol anomaly / precondition abort */
const char *gbp_avsvc_status_class(gbp_avsvc_status s)
{
    switch (s) {
    case GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED: return "ok";
    case GBP_AVSVC_NO_NEXT_CAUSE_AFTER_SERVICE:
    case GBP_AVSVC_NO_INITIAL_CAUSE:
    case GBP_AVSVC_FIRST_DELIVERY_TIMEOUT: return "observation";
    case GBP_AVSVC_SERVICE_COMPLETED_WITH_ERRORS: return "errors";
    case GBP_AVSVC_ABORT_STAGE_A:
    case GBP_AVSVC_ABORT_HANDLER_INSTALL:
    case GBP_AVSVC_ABORT_PRE_UNMASK_STATE:
    case GBP_AVSVC_ABORT_UNMASK:
    case GBP_AVSVC_ABORT_BULK_UNAVAILABLE:
    case GBP_AVSVC_ABORT_PRESVC_STATE:
    case GBP_AVSVC_ABORT_READ_INCONSISTENT: return "abort";
    case GBP_AVSVC_ABORT_TRANSPORT:
    case GBP_AVSVC_ACK_WRITE_FAILED:
    case GBP_AVSVC_REARM_WRITE_FAILED: return "transport";
    case GBP_AVSVC_AUDIO_DMA_BUSY:
    case GBP_AVSVC_AUDIO_DMA_TIMEOUT:
    case GBP_AVSVC_AUDIO_DMA_ERROR:
    case GBP_AVSVC_VIDEO_DMA_BUSY:
    case GBP_AVSVC_VIDEO_DMA_TIMEOUT:
    case GBP_AVSVC_VIDEO_DMA_ERROR: return "dma";
    default: return "anomaly";
    }
}

const char *gbp_avsvc_rearmpost_name(int outcome)
{
    switch (outcome) {
    case GBP_AVSVC_REARMPOST_A_QUIET: return "A_quiet";
    case GBP_AVSVC_REARMPOST_B_LATCHED: return "B_latched";
    case GBP_AVSVC_REARMPOST_C_SOURCE_BEFORE_PI: return "C_source_before_pi";
    case GBP_AVSVC_REARMPOST_D_UNEXPECTED: return "D_unexpected";
    case GBP_AVSVC_REARMPOST_E_INVALID: return "E_invalid";
    case GBP_AVSVC_REARMPOST_F_INCONSISTENT: return "F_inconsistent";
    default: return "-";
    }
}

/* ---- run context ---------------------------------------------------- */
struct run_ctx {
    const struct gbp_transport *t;
    struct ringlog *log;
    const struct gbp_avsvc_config *cfg;
    struct gbp_avsvc_result *res;
};

static void restore_fail(struct gbp_avsvc_result *res, const char *why)
{
    if (res->restore_ok) res->restore_reason = why;
    res->restore_ok = 0;
}

static const char *old_handler_name(const struct gbp_irq_handler_state *h)
{
    return h->old_handler_null == 1 ? "null" : h->old_handler_null == 0 ? "nonnull" : "?";
}

static void note_control(struct gbp_avsvc_result *res, const struct gbp_initirqa_snapshot *s)
{
    if (s->control_rc == GBP_OK && (s->control_vote != res->a.control_exp || s->control_vote != s->control_b1f)) res->control_ok = 0;
}

/* ---- teardown hook: handler restore + mask verification, between the PI step and AR_INFO ---- */
static void teardown_hook(void *arg)
{
    struct run_ctx *x = (struct run_ctx *)arg;
    struct gbp_avsvc_result *res = x->res;
    int engaged = (res->h.handler_was_installed || res->unmasks) ? 1 : 0;
    const char *fail = gbp_irq_service_teardown_hook(x->t, x->log, &res->h, engaged, &res->a.errors);
    if (fail) restore_fail(res, fail);
}

/* ---- the teardown for every path after the 003A stage (CPU masked, at most one PI W1C) ---- */
static void teardown_av(struct run_ctx *x, const char *variant)
{
    struct gbp_avsvc_result *res = x->res;
    struct gbp_initirqa_teardown_opts opts;
    res->teardown_variant = variant;
    ringlog_printf(x->log, "TEARDOWNAV variant=%s deliveries=%u drained=%u/%u acks=%u rearms=%u/%u next_cause=%d unmasks=%u",
                   variant, res->deliveries, res->drains_completed, res->drains_selected, res->acks,
                   res->rearm_completed, res->rearm_attempted, res->next_cause_found, res->unmasks);
    opts.pi_cleanup_allowed = 1;                 /* the teardown's own budget: one W1C at most */
    opts.pre_arinfo_hook = teardown_hook;
    opts.hook_ctx = x;
    opts.pi_policy = res->unmasks ? "unmasked_once" : "never_unmasked";
    gbp_initirqa_teardown(x->t, x->log, &x->cfg->a, &res->a, &opts);
    if (res->a.pi_cleanup_performed) res->teardown_w1c = 1;
    res->pi_sticky_final = bit13(res->a.cleanup_intsr_after) ? 1 : 0;
    if (!res->a.restore_ok && res->restore_ok) restore_fail(res, res->a.restore_reason);
}

/* Writes issued whose completion the transport did not report: the stage's five, the ACK, the re-arm. */
static unsigned count_uncertain_av(const struct gbp_avsvc_result *res)
{
    const struct gbp_regwrite_result *w[7];
    unsigned i, n = 0;
    w[0] = &res->a.w_ctl_exp; w[1] = &res->a.w_a1; w[2] = &res->a.w_a2; w[3] = &res->a.w_stop; w[4] = &res->a.w_ctl_restore;
    w[5] = &res->k.w_ack; w[6] = &res->w_rearm;
    for (i = 0; i < 7; i++) if (w[i]->attempted && !w[i]->completed) n++;
    return n;
}

static void end_records(struct run_ctx *x)
{
    struct gbp_avsvc_result *res = x->res;
    res->uncertain_writes = count_uncertain_av(res);
    res->errors = res->a.errors;
    res->transport_ok = (res->errors == 0) ? 1 : 0;
    res->power_cycle_required = res->a.power_cycle_required;
    /* block summaries: computed only now, after the teardown (outside the timed region); the buffers are only read */
    gbp_avblock_summarize(&res->audio);
    gbp_avblock_summarize(&res->video);
    ringlog_printf(x->log, "AVSVC end status=%s class=%s reason=%s restore=%s restore_reason=%s teardown=%s power_cycle_required=%d errors=%u transport_ok=%d",
                   res->status_name, res->status_class, res->reason, res->restore_ok ? "ok" : "error", res->restore_reason,
                   res->teardown_variant ? res->teardown_variant : "-", res->power_cycle_required, res->errors, res->transport_ok);
    gbp_initirqa_log_summary_records(x->log, &res->a);
    ringlog_printf(x->log, "SERVICE pass pending=%04x drain=%04x selected=%u attempted=%u completed=%u drain_uncertain=%d ack=%d/%d ack_value=%04x source_after_ack=%04x",
                   (unsigned)res->pending_irq, (unsigned)res->drain_mask, res->drains_selected, res->drains_attempted, res->drains_completed,
                   res->drain_uncertain, res->k.w_ack.attempted, res->k.w_ack.completed, (unsigned)res->k.ack_value, (unsigned)res->source_after_ack);
    ringlog_printf(x->log, "SERVICE rearm relatch_postdrain=%d relatch_postack=%d pi_clean=%d pi_sticky=%d rearm=%d/%d rearmpost=%s next_cause=%d immediate=%d timed_out=%d",
                   res->relatch_postdrain, res->relatch_postack, res->pi_clean, res->pi_sticky, res->rearm_attempted, res->rearm_completed,
                   gbp_avsvc_rearmpost_name(res->rearmpost_outcome), res->next_cause_found, res->next_cause_immediate, res->next_cause_timed_out);
    ringlog_printf(x->log, "COUNTERS unmasks=%u deliveries=%u acks=%u rearms=%u next_causes=%u unexpected=%04x site=%s isr_w1c=%u main_w1c=%u teardown_w1c=%u w1c_total=%u control_ok=%d uncertain=%u",
                   res->unmasks, res->deliveries, res->acks, res->rearm_completed, res->next_cause_found, (unsigned)res->unexpected,
                   res->unexpected_site, res->isr_w1c, res->main_w1c, res->teardown_w1c, res->isr_w1c + res->main_w1c + res->teardown_w1c,
                   res->control_ok, res->uncertain_writes);
    gbp_avblock_log_summary(x->log, &res->audio);
    gbp_avblock_log_summary(x->log, &res->video);
    ringlog_printf(x->log, "TIMING cause_to_isr=%lu/%luus isr_to_presvc=%lu presvc_to_ack=%lu service=%lu/%luus ack_to_postack=%lu postack_to_rearm=%lu rearm_to_next_cause=%lu/%luus",
                   (unsigned long)res->dt_cause_to_isr, (unsigned long)ticks_to_us(x->cfg->a.tb_hz, res->dt_cause_to_isr),
                   (unsigned long)res->dt_isr_to_presvc, (unsigned long)res->dt_presvc_to_ack, (unsigned long)res->dt_service,
                   (unsigned long)ticks_to_us(x->cfg->a.tb_hz, res->dt_service), (unsigned long)res->dt_ack_to_postack,
                   (unsigned long)res->dt_postack_to_rearm, (unsigned long)res->dt_rearm_to_next_cause,
                   (unsigned long)ticks_to_us(x->cfg->a.tb_hz, res->dt_rearm_to_next_cause));
    ringlog_printf(x->log, "RESTOREAV handler_installed=%d handler_restored=%d old_handler=%s mask_ok=%d intmr_final=%08lx pi_sticky_final=%d unmasked=%d masked_again=%d",
                   res->h.handler_was_installed, res->h.handler_restored, old_handler_name(&res->h), res->h.mask_ok,
                   (unsigned long)res->h.intmr_final, res->pi_sticky_final, res->d.irq_unmasked, res->d.irq_masked_again);
}

static void set_status(struct gbp_avsvc_result *res, gbp_avsvc_status st, const char *reason)
{
    res->status = st;
    res->status_name = gbp_avsvc_status_name(st);
    res->status_class = gbp_avsvc_status_class(st);
    res->reason = reason;
}

static void finish(struct run_ctx *x, gbp_avsvc_status st, const char *reason, const char *variant)
{
    set_status(x->res, st, reason);
    teardown_av(x, variant);
    end_records(x);
}

/* ---- snapshot checks shared by PRESVC / POSTDRAIN / POSTACK / REARMPOST ----
 * Returns 0 and the abort (status, reason, site) when a mandatory check fails:
 * reads ok, Disc == GBI, CONTROL unchanged, INTMR bit 13 = 0 in both samples,
 * no source outside AV. The AV bits are never a requirement here. */
static int common_checks(struct run_ctx *x, const struct gbp_initirqa_snapshot *s, const char *site,
                         gbp_avsvc_status *st, const char **reason)
{
    struct gbp_avsvc_result *res = x->res;
    const struct gbp_avsvc_config *cfg = x->cfg;
    uint16_t unexpected;
    note_control(res, s);
    if (!s->pi_ok || s->control_rc != GBP_OK || s->irq_rc != GBP_OK) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "%s_read_failed", site);
        *st = GBP_AVSVC_ABORT_TRANSPORT; *reason = res->reason_buf; return 0;
    }
    if (s->irq_disc != s->irq_gbi) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "%s_semantic_disagree", site);
        *st = GBP_AVSVC_ABORT_READ_INCONSISTENT; *reason = res->reason_buf; return 0;
    }
    if (s->control_vote != res->a.control_exp || s->control_vote != s->control_b1f) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "control_changed_%s", site);
        *st = GBP_AVSVC_ANOMALY_CONTROL_CHANGED; *reason = res->reason_buf; return 0;
    }
    if (bit13(s->intmr) || (s->pi2_ok && bit13(s->intmr2))) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "intmr13_set_%s", site);
        *st = GBP_AVSVC_ANOMALY_MASK_FAILURE; *reason = res->reason_buf; return 0;
    }
    unexpected = (uint16_t)(s->irq_gbi & cfg->src_mask & (uint16_t)~cfg->av_mask);
    if (unexpected) {
        res->unexpected = unexpected;
        res->unexpected_site = site;
        snprintf(res->reason_buf, sizeof res->reason_buf, "unexpected_source_%s", site);
        *st = GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE; *reason = res->reason_buf; return 0;
    }
    return 1;
}

static void log_service_snapshot(struct run_ctx *x, const char *kind, const struct gbp_initirqa_snapshot *s, uint16_t src_mask, uint16_t av_mask)
{
    ringlog_printf(x->log, "%s t=%lu intsr13=%u,%u intmr13=%u,%u control=%02x irq=%04x/%04x src=%04x av=%04x unexpected=%04x odd=%04x bit15=%u high=%04x",
                   kind, (unsigned long)s->ticks, bit13(s->intsr), bit13(s->intsr2), bit13(s->intmr), bit13(s->intmr2),
                   (unsigned)s->control_vote, (unsigned)s->irq_gbi, (unsigned)s->irq_disc, (unsigned)(s->irq_gbi & src_mask),
                   (unsigned)(s->irq_gbi & av_mask), (unsigned)(s->irq_gbi & src_mask & (uint16_t)~av_mask),
                   (unsigned)(s->irq_gbi & x->cfg->odd_mask), (unsigned)((s->irq_gbi & x->cfg->bit15_mask) ? 1u : 0u),
                   (unsigned)(s->irq_gbi & x->cfg->high_mask));
}

static gbp_avsvc_status dma_status(int is_audio, gbp_status rc)
{
    if (rc == GBP_ERR_BUSY) return is_audio ? GBP_AVSVC_AUDIO_DMA_BUSY : GBP_AVSVC_VIDEO_DMA_BUSY;
    if (rc == GBP_ERR_TIMEOUT) return is_audio ? GBP_AVSVC_AUDIO_DMA_TIMEOUT : GBP_AVSVC_VIDEO_DMA_TIMEOUT;
    return is_audio ? GBP_AVSVC_AUDIO_DMA_ERROR : GBP_AVSVC_VIDEO_DMA_ERROR;
}

/* The wait for the next cause after the re-arm (outcome A or C): INTSR polled while masked,
 * bounded by t_next_cause_ticks since t_rearm, no formatting per poll. On INTSR bit 13 the
 * NEXTCAUSE snapshot is taken at the poll's own time-base value (one read, as the 003A EVENT). */
static int wait_next_cause(struct run_ctx *x, uint32_t *t_end)
{
    struct gbp_avsvc_result *res = x->res;
    uint32_t tnow, intsr;
    for (;;) {
        tnow = now(x->t);
        if (x->t->poll_intsr(x->t->ctx, &intsr) == GBP_OK) {
            res->next_cause_polls++;
            if (intsr & GBP_PI_HSP_BIT) {
                gbp_initirqa_snapshot_take_at(x->t, &res->a, &res->nextcause, "NEXTCAUSE", 0, 1, tnow, intsr, res->next_cause_polls);
                *t_end = tnow;
                return 1;
            }
        } else {
            res->a.poll_errors++;
        }
        if ((uint32_t)(tnow - res->t_rearm) >= x->cfg->t_next_cause_ticks) { *t_end = tnow; return 0; }
    }
}

int gbp_avsvc_probe_run(const struct gbp_transport *t, struct ringlog *log,
                        const struct gbp_avsvc_config *cfg, struct gbp_avsvc_result *res)
{
    struct run_ctx xs, *x = &xs;
    gbp_initirqa_cause_rc crc;
    const struct gbp_initirqa_snapshot *ev;
    struct gbp_irq_record rec0;
    gbp_avsvc_status st;
    const char *why = "-";
    int old_null = -1;

    xs.t = t; xs.log = log; xs.cfg = cfg; xs.res = res;
    memset(res, 0, sizeof *res);
    res->restore_ok = 1;
    res->restore_reason = "-";
    res->reason = "-";
    res->status_name = "-";
    res->status_class = "-";
    res->preunmask_reason = "-";
    res->presvc_reason = "-";
    res->postack_reason = "-";
    res->unexpected_site = "-";
    res->control_ok = 1;
    gbp_irq_service_handler_init(&res->h);
    gbp_irq_service_delivery_init(&res->d);
    gbp_irq_service_ack_init(&res->k);
    gbp_avblock_init(&res->audio, "audio", cfg->audio_index, cfg->audio_src, cfg->audio_buf, cfg->audio_cap, cfg->audio_len);
    gbp_avblock_init(&res->video, "video", cfg->video_index, cfg->video_src, cfg->video_buf, cfg->video_cap, cfg->video_len);
    /* pre-fill outside the timed region: a known state, never reported as block content (present = attempted) */
    if (cfg->audio_buf && cfg->audio_cap) memset(cfg->audio_buf, 0, cfg->audio_cap);
    if (cfg->video_buf && cfg->video_cap) memset(cfg->video_buf, 0, cfg->video_cap);

    ringlog_printf(log, "AVSVC start t_delivery_ms=%lu t_delivery_ticks=%lu t_next_cause_ms=%lu t_next_cause_ticks=%lu ack_or=%04x src_mask=%04x av_mask=%04x odd_mask=%04x bit15_mask=%04x high_mask=%04x",
                   (unsigned long)cfg->t_delivery_ms, (unsigned long)cfg->t_delivery_ticks, (unsigned long)cfg->t_next_cause_ms,
                   (unsigned long)cfg->t_next_cause_ticks, (unsigned)cfg->ack_or, (unsigned)cfg->src_mask, (unsigned)cfg->av_mask,
                   (unsigned)cfg->odd_mask, (unsigned)cfg->bit15_mask, (unsigned)cfg->high_mask);
    ringlog_printf(log, "AVSVC blocks audio_idx=%x audio_len=%04lx audio_src=%04x video_idx=%x video_len=%04lx video_src=%04x order=audio_then_video prefill=00 bulk_read=%d",
                   cfg->audio_index, (unsigned long)cfg->audio_len, (unsigned)cfg->audio_src, cfg->video_index, (unsigned long)cfg->video_len,
                   (unsigned)cfg->video_src, gbp_transport_has_bulk_read(t));
    ringlog_printf(log, "AVSVC policy handler=003b_ext_installed_once deliveries=1 snapshot=PRESVC_authoritative drain=selected_by_snapshot ack=pending|%04x_from_PRESVC",
                   (unsigned)cfg->ack_or);
    ringlog_printf(log, "AVSVC policy2 postack=no_source_requirement rearm=irq_zero_after_pi_clean next_cause=observed_never_delivered w1c_budget=isr1_main1_nextcause0_teardown1");

    /* ---- 1. the GBP-INIT-003A sequence, verbatim, PI masked, no handler ---- */
    crc = gbp_initirqa_run_cause(t, log, &cfg->a, &res->a);
    if (crc == GBP_INITIRQA_CAUSE_ABORTED) {
        res->stage_a_aborted = 1;
        res->status = GBP_AVSVC_ABORT_STAGE_A;
        res->status_name = gbp_initirqa_status_name(res->a.status);
        res->status_class = gbp_avsvc_status_class(GBP_AVSVC_ABORT_STAGE_A);
        res->reason = res->a.reason ? res->a.reason : "-";
        res->teardown_variant = "stage_a";
        if (!res->a.restore_ok) restore_fail(res, res->a.restore_reason);
        end_records(x);
        return 0;
    }
    if (crc == GBP_INITIRQA_CAUSE_NOT_OBSERVED) {
        finish(x, GBP_AVSVC_NO_INITIAL_CAUSE, "no_intsr13_within_t_max", "S2_before_unmask");
        return 0;
    }

    /* ---- 2. the cause is latched at the PI: record it, touch nothing ---- */
    ev = &res->a.snap[GBP_INITIRQA_SNAP_EVENT];
    res->t_cause = ev->taken ? ev->ticks : res->a.t_first_intsr13;
    res->cause_irq = ev->irq_gbi;
    ringlog_printf(log, "CAUSE t_event=%lu since_a2=%lu intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u control=%02x irq=%04x/%04x av=%04x unexpected=%04x",
                   (unsigned long)res->t_cause, (unsigned long)ev->since_a2, (unsigned long)ev->intsr, (unsigned long)ev->intmr,
                   bit13(ev->intsr), bit13(ev->intmr), (unsigned)ev->control_vote, (unsigned)ev->irq_gbi, (unsigned)ev->irq_disc,
                   (unsigned)(ev->irq_gbi & cfg->av_mask), (unsigned)(ev->irq_gbi & cfg->src_mask & (uint16_t)~cfg->av_mask));

    /* ---- 3. the 003B extended one-shot handler, installed once (after the cause); previous handler kept ---- */
    res->h.irq_path_available = gbp_transport_has_irq_path(t);
    if (!res->h.irq_path_available) {
        ringlog_printf(log, "IRQ install rc=unavailable");
        finish(x, GBP_AVSVC_ABORT_HANDLER_INSTALL, "irq_ops_unavailable", "S2_before_unmask");
        return 0;
    }
    res->h.install_rc = t->irq_install(t->ctx, &old_null);
    if (res->h.install_rc != GBP_OK) {
        res->a.errors++;
        ringlog_printf(log, "IRQ install rc=%s", gbp_status_name(res->h.install_rc));
        finish(x, GBP_AVSVC_ABORT_HANDLER_INSTALL, "install_failed", "S2_before_unmask");
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

    /* ---- 4. PREUNMASK: the 003B preconditions + the AV rule (no unmask otherwise) ---- */
    gbp_initirqa_snapshot_take(t, &res->a, &res->preunmask, "PREUNMASK", 0, 1);
    gbp_initirqa_snapshot_log(log, &res->a, &res->preunmask);
    note_control(res, &res->preunmask);
    res->preunmask_ok = gbp_irq_service_preunmask_check(&res->preunmask, res->a.control_exp, cfg->src_mask, cfg->odd_mask,
                                                        cfg->bit15_mask, cfg->high_mask, res->h.install_count, res->h.install_fired, &why);
    if (res->preunmask_ok) {
        uint16_t unexpected = (uint16_t)(res->preunmask.irq_gbi & cfg->src_mask & (uint16_t)~cfg->av_mask);
        if (unexpected) { res->preunmask_ok = 0; why = "unexpected_source"; res->unexpected = unexpected; res->unexpected_site = "PREUNMASK"; }
        else if ((res->preunmask.irq_gbi & cfg->av_mask) == 0) { res->preunmask_ok = 0; why = "no_av_source"; }
    }
    res->preunmask_reason = why;
    gbp_irq_service_log_preunmask(log, "", &res->preunmask, res->preunmask_ok, why, cfg->src_mask, cfg->odd_mask, cfg->bit15_mask);
    ringlog_printf(log, "PREUNMASKAV av=%04x unexpected=%04x t_cause=%lu ok=%d", (unsigned)(res->preunmask.irq_gbi & cfg->av_mask),
                   (unsigned)(res->preunmask.irq_gbi & cfg->src_mask & (uint16_t)~cfg->av_mask), (unsigned long)res->t_cause, res->preunmask_ok);
    if (!res->preunmask_ok) {
        if (res->unexpected) finish(x, GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE, "unexpected_source_PREUNMASK", "S2_before_unmask");
        else if (strcmp(why, "control_changed") == 0) finish(x, GBP_AVSVC_ANOMALY_CONTROL_CHANGED, "control_changed_PREUNMASK", "S2_before_unmask");
        else finish(x, GBP_AVSVC_ABORT_PRE_UNMASK_STATE, why, "S2_before_unmask");
        return 0;
    }

    /* ---- 5. the ONE unmask, the delivery, the main re-mask, the record (gbp_irq_service; 003B verbatim) ---- */
    res->unmasks = 1;
    gbp_irq_service_deliver(t, log, cfg->a.tb_hz, cfg->t_delivery_ms, cfg->t_delivery_ticks, -1, "", "", &res->d, &res->a.errors);
    if (res->d.mask_rc != GBP_OK) restore_fail(res, "mask_failed");
    if (!res->d.fired) {
        int never_opened = (res->d.unmask_rc != GBP_OK) ||
                           (res->d.pi_post_unmask_ok && !bit13(res->d.intmr_post_unmask) && res->d.rec.count == 0);
        if (res->d.unmask_rc != GBP_OK) res->a.errors++;
        finish(x, never_opened ? GBP_AVSVC_ABORT_UNMASK : GBP_AVSVC_FIRST_DELIVERY_TIMEOUT,
               never_opened ? "unmask_not_effective" : "no_delivery_within_t_delivery", "S3_service_aborted");
        return 0;
    }
    res->deliveries = 1;
    res->isr_w1c = 1;                            /* the first entry performs the body's single W1C */
    res->dt_cause_to_isr = (uint32_t)(res->d.rec.t_entry - res->t_cause);
    if (res->d.reentry) { finish(x, GBP_AVSVC_ANOMALY_REENTRY, "handler_entered_more_than_once", "S3_service_aborted"); return 0; }
    if (res->d.main_mask_ok != 1) { finish(x, GBP_AVSVC_ANOMALY_MASK_FAILURE, "intmr13_still_set_after_remask", "S3_service_aborted"); return 0; }
    res->delivered = 1;

    /* ---- 6. PRESVC: the authoritative snapshot of this service pass ---- */
    gbp_initirqa_snapshot_take(t, &res->a, &res->presvc, "PRESVC", 0, 1);
    gbp_initirqa_snapshot_log(log, &res->a, &res->presvc);
    log_service_snapshot(x, "PRESVC", &res->presvc, cfg->src_mask, cfg->av_mask);
    res->dt_isr_to_presvc = (uint32_t)(res->presvc.ticks - res->d.rec.t_entry);
    if (!common_checks(x, &res->presvc, "PRESVC", &st, &why)) { res->presvc_reason = why; finish(x, st, why, "S3_service_aborted"); return 0; }
    if ((res->presvc.irq_gbi & cfg->av_mask) == 0) { res->presvc_reason = "no_av_source"; finish(x, GBP_AVSVC_ABORT_PRESVC_STATE, "no_av_source_PRESVC", "S3_service_aborted"); return 0; }
    if ((res->presvc.irq_gbi & cfg->odd_mask) != 0 || (res->presvc.irq_gbi & cfg->bit15_mask) != 0 || (res->presvc.irq_gbi & cfg->high_mask) != 0) {
        res->presvc_reason = "irq_shape";
        finish(x, GBP_AVSVC_ABORT_PRESVC_STATE, "irq_shape_PRESVC", "S3_service_aborted");
        return 0;
    }
    res->presvc_ok = 1;
    res->pending_irq = res->presvc.irq_gbi;                       /* authoritative from here on */
    res->drain_mask = (uint16_t)(res->pending_irq & cfg->av_mask);
    res->audio.selected = (res->drain_mask & cfg->audio_src) ? 1 : 0;
    res->video.selected = (res->drain_mask & cfg->video_src) ? 1 : 0;
    res->audio.addr = gbp_block_addr(res->a.base, res->audio.index, 0);   /* known now, whether or not the block is read */
    res->video.addr = gbp_block_addr(res->a.base, res->video.index, 0);
    res->drains_selected = (unsigned)res->audio.selected + (unsigned)res->video.selected;
    ringlog_printf(log, "SVC start pending=%04x drain=%04x audio=%d video=%d order=audio_then_video ack_value=%04x ack_source=PRESVC t=%lu",
                   (unsigned)res->pending_irq, (unsigned)res->drain_mask, res->audio.selected, res->video.selected,
                   (unsigned)(res->pending_irq | cfg->ack_or), (unsigned long)res->presvc.ticks);
    if (!gbp_transport_has_bulk_read(t)) {
        ringlog_printf(log, "SVC abort reason=bulk_read_unavailable");
        finish(x, GBP_AVSVC_ABORT_BULK_UNAVAILABLE, "bulk_read_unavailable", "S3_service_aborted");
        return 0;
    }

    /* ---- 7. the drains: AUDIO then VIDEO, one whole-block DMA each, nothing formatted until both are done ---- */
    if (res->audio.selected) {
        res->drains_attempted++;
        gbp_avblock_read(t, res->a.base, &res->audio, &res->a.errors);
        if (res->audio.completed) res->drains_completed++;
        res->t_service_end = res->audio.t_end;
    }
    if (res->video.selected && (!res->audio.selected || res->audio.completed)) {
        res->drains_attempted++;
        gbp_avblock_read(t, res->a.base, &res->video, &res->a.errors);
        if (res->video.completed) res->drains_completed++;
        res->t_service_end = res->video.t_end;
    }
    gbp_avblock_log_read(log, "AUDIOREAD", &res->audio);
    gbp_avblock_log_read(log, "VIDEOREAD", &res->video);
    if (res->t_service_end) res->dt_service = (uint32_t)(res->t_service_end - res->presvc.ticks);
    ringlog_printf(log, "SVCEND drain=%04x selected=%u attempted=%u completed=%u ok=%d t_end=%lu dt_service=%lu audio_rc=%s video_rc=%s",
                   (unsigned)res->drain_mask, res->drains_selected, res->drains_attempted, res->drains_completed,
                   (res->drains_completed == res->drains_selected) ? 1 : 0, (unsigned long)res->t_service_end, (unsigned long)res->dt_service,
                   res->audio.attempted ? gbp_status_name(res->audio.rc) : "-", res->video.attempted ? gbp_status_name(res->video.rc) : "-");
    if (res->audio.selected && !res->audio.completed) {
        res->drain_uncertain = (res->audio.rc == GBP_ERR_TIMEOUT) ? 1 : 0;
        finish(x, dma_status(1, res->audio.rc), "audio_read_failed", "S3_dma_failed");
        return 0;
    }
    if (res->video.selected && !res->video.completed) {
        res->drain_uncertain = (res->video.rc == GBP_ERR_TIMEOUT) ? 1 : 0;
        finish(x, dma_status(0, res->video.rc), "video_read_failed", "S3_dma_failed");
        return 0;
    }

    /* ---- 8. POSTDRAIN: observation only (the ACK value stays the PRESVC one) ---- */
    gbp_initirqa_snapshot_take(t, &res->a, &res->postdrain, "POSTDRAIN", 0, 1);
    gbp_initirqa_snapshot_log(log, &res->a, &res->postdrain);
    log_service_snapshot(x, "POSTDRAIN", &res->postdrain, cfg->src_mask, cfg->av_mask);
    res->relatch_postdrain = (bit13(res->postdrain.intsr) || (res->postdrain.pi2_ok && bit13(res->postdrain.intsr2))) ? 1 : 0;
    ringlog_printf(log, "POSTDRAIN observation_only=1 relatch=%d av_after_drain=%04x pending_kept=%04x", res->relatch_postdrain,
                   (unsigned)(res->postdrain.irq_gbi & cfg->av_mask), (unsigned)res->pending_irq);
    if (!common_checks(x, &res->postdrain, "POSTDRAIN", &st, &why)) { finish(x, st, why, "S3_service_aborted"); return 0; }
    res->postdrain_ok = 1;

    /* ---- 9. ACK := pending_irq | 0x8000 (the PRESVC value), POSTACK, the single main W1C (gbp_irq_service) ---- */
    gbp_irq_service_ack_write_postack(t, log, &res->a, res->pending_irq, cfg->ack_or, cfg->src_mask, "", "POSTACK", "tag=ACK", "",
                                      &res->k, &res->a.errors);
    res->dt_presvc_to_ack = (uint32_t)(res->k.w_ack.t_after - res->presvc.ticks);
    if (res->k.main_pi_w1c) { res->main_w1c = 1; if (res->k.main_w1c_rc != GBP_OK) restore_fail(res, "main_pi_w1c_failed"); }
    if (!res->k.w_ack.completed) {
        finish(x, GBP_AVSVC_ACK_WRITE_FAILED, "ack_write_failed", "S4_ack_failed");
        return 0;
    }
    res->acks = 1;
    res->acked = 1;
    res->dt_ack_to_postack = (uint32_t)(res->k.postack.ticks - res->k.w_ack.t_after);

    /* ---- 10. POSTACK: no source requirement; shape, CONTROL, mask, agreement, unexpected are mandatory ---- */
    res->relatch_postack = bit13(res->k.postack.intsr) ? 1 : 0;
    res->source_after_ack = (uint16_t)(res->k.postack.irq_gbi & cfg->av_mask);
    log_service_snapshot(x, "POSTACKAV", &res->k.postack, cfg->src_mask, cfg->av_mask);
    if (!common_checks(x, &res->k.postack, "POSTACK", &st, &why)) { res->postack_reason = why; finish(x, st, why, "S3_service_aborted"); return 0; }
    if ((res->k.postack.irq_gbi & cfg->odd_mask) != 0 || (res->k.postack.irq_gbi & cfg->bit15_mask) == 0 || (res->k.postack.irq_gbi & cfg->high_mask) != 0) {
        res->postack_reason = "postack_shape";
        finish(x, GBP_AVSVC_ANOMALY_POSTACK_SHAPE, "postack_shape", "S3_service_aborted");
        return 0;
    }
    res->postack_ok = 1;
    ringlog_printf(log, "POSTACKAV boundary=%s source_after_ack=%04x relatch=%d main_w1c=%d requirement=none", res->source_after_ack ? "pending_av" : "clean",
                   (unsigned)res->source_after_ack, res->relatch_postack, res->k.main_pi_w1c);

    /* ---- 11. PI clean before the re-arm (the POSTACK W1C, if any, was the single main W1C) ---- */
    if (res->k.main_pi_w1c) { res->pi_clean_intsr = res->k.main_w1c_intsr_after; res->pi_clean_intmr = res->k.main_w1c_intmr_after; }
    else { res->pi_clean_intsr = res->k.postack.pi2_ok ? res->k.postack.intsr2 : res->k.postack.intsr; res->pi_clean_intmr = res->k.postack.pi2_ok ? res->k.postack.intmr2 : res->k.postack.intmr; }
    res->pi_clean = (!bit13(res->pi_clean_intsr) && !bit13(res->pi_clean_intmr)) ? 1 : 0;
    res->pi_sticky = res->k.main_w1c_sticky;
    ringlog_printf(log, "PICLEAN intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u main_w1c=%d sticky=%d ok=%d",
                   (unsigned long)res->pi_clean_intsr, (unsigned long)res->pi_clean_intmr, bit13(res->pi_clean_intsr),
                   bit13(res->pi_clean_intmr), res->k.main_pi_w1c, res->pi_sticky, res->pi_clean);
    if (!res->pi_clean) {
        if (res->pi_sticky) finish(x, GBP_AVSVC_ANOMALY_PI_STICKY_AFTER_SERVICE, "pi_sticky_after_service", "S3_pi_sticky");
        else finish(x, GBP_AVSVC_ANOMALY_MASK_FAILURE, "pi_not_clean_after_ack", "S3_pi_sticky");
        return 0;
    }

    /* ---- 12. REARM: IRQ := 0x0000 (GBI's end-of-pass write), CPU still masked ---- */
    res->t_rearm = now(t);
    res->rearm_before = res->k.postack.irq_gbi;
    ringlog_printf(log, "REARM t_rearm=%lu before=%04x value=0000 layout=gbi-u16-replicated after=drain_ack_pi_clean",
                   (unsigned long)res->t_rearm, (unsigned)res->rearm_before);
    res->rearm_attempted = 1;
    res->a.irq_writes_attempted++;
    res->a.power_cycle_required = 1;
    gbp_regwrite_irq_u16(t, "tag=REARM", res->a.base, res->rearm_before, 0x0000, &res->w_rearm, &res->a.errors);
    if (res->w_rearm.completed) { res->rearm_completed = 1; res->a.irq_writes_completed++; }
    gbp_regwrite_log(log, &res->w_rearm);
    res->dt_postack_to_rearm = (uint32_t)(res->t_rearm - res->k.postack.ticks);
    if (!res->rearm_completed) {
        finish(x, GBP_AVSVC_REARM_WRITE_FAILED, "rearm_write_failed", "S4_rearm_failed");
        return 0;
    }

    /* ---- 13. REARMPOST: the state right after the re-arm (no W1C here, ever) ---- */
    gbp_initirqa_snapshot_take(t, &res->a, &res->rearmpost, "REARMPOST", 0, 1);
    gbp_initirqa_snapshot_log(log, &res->a, &res->rearmpost);
    {
        const struct gbp_initirqa_snapshot *s = &res->rearmpost;
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
        note_control(res, s);
        res->rearmpost_ok = (reads_ok && control_ok && masked && agree && shape_ok) ? 1 : 0;
        if (!reads_ok) res->rearmpost_outcome = GBP_AVSVC_REARMPOST_NONE;
        else if (!shape_ok) res->rearmpost_outcome = GBP_AVSVC_REARMPOST_E_INVALID;
        else if (unexpected) res->rearmpost_outcome = GBP_AVSVC_REARMPOST_D_UNEXPECTED;
        else if (src == 0 && !latched && !latched_first) res->rearmpost_outcome = GBP_AVSVC_REARMPOST_A_QUIET;
        else if (av && latched) res->rearmpost_outcome = GBP_AVSVC_REARMPOST_B_LATCHED;
        else if (av && !latched && !latched_first) res->rearmpost_outcome = GBP_AVSVC_REARMPOST_C_SOURCE_BEFORE_PI;
        else res->rearmpost_outcome = GBP_AVSVC_REARMPOST_F_INCONSISTENT;
        ringlog_printf(log, "REARMPOST t=%lu since_rearm=%lu intsr13=%u,%u intmr13=%u,%u control=%02x irq=%04x/%04x src=%04x av=%04x unexpected=%04x odd=%04x bit15=%u high=%04x outcome=%s ok=%d",
                       (unsigned long)s->ticks, (unsigned long)(uint32_t)(s->ticks - res->t_rearm), bit13(s->intsr), bit13(s->intsr2),
                       bit13(s->intmr), bit13(s->intmr2), (unsigned)s->control_vote, (unsigned)s->irq_gbi, (unsigned)s->irq_disc,
                       (unsigned)src, (unsigned)av, (unsigned)unexpected, (unsigned)(s->irq_gbi & cfg->odd_mask),
                       (unsigned)((s->irq_gbi & cfg->bit15_mask) ? 1u : 0u), (unsigned)(s->irq_gbi & cfg->high_mask),
                       gbp_avsvc_rearmpost_name(res->rearmpost_outcome), res->rearmpost_ok);
        if (!reads_ok) { finish(x, GBP_AVSVC_ABORT_TRANSPORT, "rearmpost_read_failed", "S4C_rearmpost_invalid"); return 0; }
        if (!agree) { finish(x, GBP_AVSVC_ABORT_READ_INCONSISTENT, "rearmpost_semantic_disagree", "S4C_rearmpost_invalid"); return 0; }
        if (!control_ok) { finish(x, GBP_AVSVC_ANOMALY_CONTROL_CHANGED, "control_changed_REARMPOST", "S4C_rearmpost_invalid"); return 0; }
        if (!masked) { finish(x, GBP_AVSVC_ANOMALY_MASK_FAILURE, "intmr13_set_REARMPOST", "S4C_rearmpost_invalid"); return 0; }
        if (res->rearmpost_outcome == GBP_AVSVC_REARMPOST_E_INVALID) { finish(x, GBP_AVSVC_ANOMALY_REARM_STATE, "rearm_state_invalid", "S4C_rearmpost_invalid"); return 0; }
        if (res->rearmpost_outcome == GBP_AVSVC_REARMPOST_D_UNEXPECTED) {
            res->unexpected = unexpected; res->unexpected_site = "REARMPOST";
            finish(x, GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE, "unexpected_source_REARMPOST", "S4C_rearmpost_invalid"); return 0;
        }
        if (res->rearmpost_outcome == GBP_AVSVC_REARMPOST_F_INCONSISTENT) { finish(x, GBP_AVSVC_ANOMALY_REARM_STATE, "rearmpost_pi_without_source", "S4C_rearmpost_invalid"); return 0; }

        /* ---- 14. NEXTCAUSE: observed while masked, never delivered ---- */
        if (res->rearmpost_outcome == GBP_AVSVC_REARMPOST_B_LATCHED) {
            res->next_cause_found = 1;
            res->next_cause_immediate = 1;
            res->t_next_cause = s->ticks;
            res->next_cause_irq = s->irq_gbi;
            res->next_cause_intsr = s->pi2_ok ? s->intsr2 : s->intsr;
            res->dt_rearm_to_next_cause = (uint32_t)(s->ticks - res->t_rearm);
            ringlog_printf(log, "NEXTCAUSE found=1 immediate=1 t_next_cause=%lu since_rearm=%lu intsr=%08lx control=%02x irq=%04x/%04x av=%04x unexpected=0000 polls=0 delivered=0",
                           (unsigned long)res->t_next_cause, (unsigned long)res->dt_rearm_to_next_cause, (unsigned long)res->next_cause_intsr,
                           (unsigned)s->control_vote, (unsigned)s->irq_gbi, (unsigned)s->irq_disc, (unsigned)av);
        } else {
            uint32_t t_end = 0;
            int found = wait_next_cause(x, &t_end);
            if (!found) {
                res->next_cause_timed_out = 1;
                ringlog_printf(log, "NEXTCAUSE found=0 timed_out=1 t_end=%lu since_rearm=%lu polls=%u rearmpost=%s t_next_cause_ticks=%lu",
                               (unsigned long)t_end, (unsigned long)(uint32_t)(t_end - res->t_rearm), res->next_cause_polls,
                               gbp_avsvc_rearmpost_name(res->rearmpost_outcome), (unsigned long)cfg->t_next_cause_ticks);
                finish(x, GBP_AVSVC_NO_NEXT_CAUSE_AFTER_SERVICE, "no_next_cause_within_bound", "S4A_rearmed_no_next_cause");
                return 0;
            }
            {
                const struct gbp_initirqa_snapshot *q = &res->nextcause;
                uint16_t qsrc = (uint16_t)(q->irq_gbi & cfg->src_mask);
                uint16_t qav = (uint16_t)(q->irq_gbi & cfg->av_mask);
                uint16_t qunexpected = (uint16_t)(qsrc & (uint16_t)~cfg->av_mask);
                gbp_initirqa_snapshot_log(log, &res->a, q);
                note_control(res, q);
                res->t_next_cause = q->ticks;
                res->next_cause_irq = q->irq_gbi;
                res->next_cause_intsr = q->poll_intsr;
                res->dt_rearm_to_next_cause = (uint32_t)(q->ticks - res->t_rearm);
                ringlog_printf(log, "NEXTCAUSE found=1 immediate=0 t_next_cause=%lu since_rearm=%lu intsr=%08lx control=%02x irq=%04x/%04x av=%04x unexpected=%04x polls=%u delivered=0",
                               (unsigned long)res->t_next_cause, (unsigned long)res->dt_rearm_to_next_cause, (unsigned long)res->next_cause_intsr,
                               (unsigned)q->control_vote, (unsigned)q->irq_gbi, (unsigned)q->irq_disc, (unsigned)qav, (unsigned)qunexpected, res->next_cause_polls);
                if (q->irq_rc != GBP_OK || q->control_rc != GBP_OK || !q->pi_ok) { finish(x, GBP_AVSVC_ABORT_TRANSPORT, "nextcause_read_failed", "S4B_next_cause_latched"); return 0; }
                if (q->irq_disc != q->irq_gbi) { finish(x, GBP_AVSVC_ABORT_READ_INCONSISTENT, "nextcause_semantic_disagree", "S4B_next_cause_latched"); return 0; }
                if (qunexpected) {
                    res->unexpected = qunexpected; res->unexpected_site = "NEXTCAUSE";
                    finish(x, GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE, "unexpected_source_NEXTCAUSE", "S4B_next_cause_latched"); return 0;
                }
                if (!qav) { finish(x, GBP_AVSVC_ANOMALY_REARM_STATE, "nextcause_pi_without_source", "S4B_next_cause_latched"); return 0; }
                res->next_cause_found = 1;
            }
        }
    }

    /* ---- 15. the next cause stays latched (never delivered); teardown with the CPU masked ---- */
    set_status(res, GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED, "-");
    teardown_av(x, "S4B_next_cause_latched");
    {
        unsigned uncertain = count_uncertain_av(res);
        int chain = (res->deliveries == 1 && res->d.reentry == 0 && res->presvc_ok && res->drains_completed == res->drains_selected &&
                     res->drains_selected >= 1 && res->acked && res->postack_ok && res->pi_clean && res->rearm_completed &&
                     res->next_cause_found && res->unexpected == 0 && res->drain_uncertain == 0) ? 1 : 0;
        if (!chain || res->pi_sticky || uncertain || res->a.errors || !res->control_ok || !res->restore_ok)
            set_status(res, GBP_AVSVC_SERVICE_COMPLETED_WITH_ERRORS,
                       !chain ? "chain_incomplete" : res->pi_sticky ? "pi_sticky" : uncertain ? "uncertain_write" : !res->restore_ok ? res->restore_reason :
                       !res->control_ok ? "control_changed" : "transport_errors");
    }
    end_records(x);
    return 0;
}

int gbp_avsvc_summary(const struct gbp_avsvc_result *res, char *dst, size_t cap)
{
    const struct gbp_initirqa_result *a = &res->a;
    return snprintf(dst, cap,
                    "DONE status=%s class=%s reason=%s restore=%s restore_reason=%s teardown=%s verdict=%s det=%u/%u written=%d "
                    "irq_attempted=%u irq_completed=%u ctl_exp=%d/%d a1=%d/%d a2=%d/%d ack=%d/%d rearm=%d/%d stop=%d/%d ctl_restore=%d/%d uncertain=%u "
                    "cause=%d t_event=%lu handler=%d old=%s unmasked=%d fired=%d count=%lu latency_ticks=%lu "
                    "pending=%04x drain=%04x drains=%u/%u/%u audio=%s/%04lx video=%s/%04lx drain_uncertain=%d ack_value=%04x postack_irq=%04x source_after_ack=%04x "
                    "relatch=%d/%d main_w1c=%d pi_clean=%d sticky=%d rearmpost=%s next_cause=%d immediate=%d dt_next=%lu "
                    "unexpected=%04x site=%s isr_w1c=%u teardown_w1c=%u control_ok=%d pi_sticky_final=%d "
                    "control_restore_ok=%d irq_stop_write_ok=%d stop_post=%04x pi_cleanup=%d handler_restored=%d mask_ok=%d "
                    "arinfo_restore_ok=%d power_cycle_required=%d errors=%u transport_ok=%d",
                    res->status_name, res->status_class, res->reason ? res->reason : "-", res->restore_ok ? "ok" : "error",
                    res->restore_reason ? res->restore_reason : "-", res->teardown_variant ? res->teardown_variant : "-",
                    gbp_verdict_name(a->det.verdict), a->det.vote_ok, a->det.run, a->control_written,
                    a->irq_writes_attempted, a->irq_writes_completed,
                    a->w_ctl_exp.attempted, a->w_ctl_exp.completed, a->w_a1.attempted, a->w_a1.completed, a->w_a2.attempted, a->w_a2.completed,
                    res->k.w_ack.attempted, res->k.w_ack.completed, res->rearm_attempted, res->rearm_completed,
                    a->w_stop.attempted, a->w_stop.completed, a->w_ctl_restore.attempted, a->w_ctl_restore.completed, res->uncertain_writes,
                    a->intsr13_seen, (unsigned long)a->t_first_intsr13, res->h.handler_was_installed, old_handler_name(&res->h),
                    res->d.irq_unmasked, res->d.fired, (unsigned long)res->d.rec.count, (unsigned long)res->d.latency_ticks,
                    (unsigned)res->pending_irq, (unsigned)res->drain_mask, res->drains_selected, res->drains_attempted, res->drains_completed,
                    res->audio.attempted ? gbp_status_name(res->audio.rc) : "-", (unsigned long)(res->audio.summarized ? res->audio.crc32 & 0xFFFFu : 0u),
                    res->video.attempted ? gbp_status_name(res->video.rc) : "-", (unsigned long)(res->video.summarized ? res->video.crc32 & 0xFFFFu : 0u),
                    res->drain_uncertain, (unsigned)res->k.ack_value, (unsigned)res->k.postack.irq_gbi, (unsigned)res->source_after_ack,
                    res->relatch_postdrain, res->relatch_postack, res->k.main_pi_w1c, res->pi_clean, res->pi_sticky,
                    gbp_avsvc_rearmpost_name(res->rearmpost_outcome), res->next_cause_found, res->next_cause_immediate,
                    (unsigned long)res->dt_rearm_to_next_cause,
                    (unsigned)res->unexpected, res->unexpected_site ? res->unexpected_site : "-", res->isr_w1c, res->teardown_w1c, res->control_ok,
                    res->pi_sticky_final, a->control_restore_ok, a->irq_stop_write_ok, (unsigned)a->irq_stop_post.gbi, a->pi_cleanup_performed,
                    res->h.handler_restored, res->h.mask_ok, a->arinfo_restore_ok,
                    res->power_cycle_required, res->errors, res->transport_ok);
}

int gbp_avsvc_dump_info(const struct gbp_avsvc_result *res, uint32_t tb_hz, const char *test_id,
                        const char *build_id, const char *app, const char *commit, struct gbp_avdump_info *info)
{
    memset(info, 0, sizeof *info);
    info->version = (uint16_t)GBP_AVDUMP_VERSION;
    if (res->audio.attempted) info->flags |= GBP_AVDUMP_FLAG_AUDIO_PRESENT;
    if (res->audio.completed) info->flags |= GBP_AVDUMP_FLAG_AUDIO_VALID;
    if (res->video.attempted) info->flags |= GBP_AVDUMP_FLAG_VIDEO_PRESENT;
    if (res->video.completed) info->flags |= GBP_AVDUMP_FLAG_VIDEO_VALID;
    info->pending_irq = res->pending_irq;
    info->drain_mask = res->drain_mask;
    info->audio_len = res->audio.attempted ? res->audio.len : 0u;   /* absent = nothing stored */
    info->video_len = res->video.attempted ? res->video.len : 0u;
    info->audio_rc = (uint32_t)res->audio.rc;
    info->video_rc = (uint32_t)res->video.rc;
    info->audio_wait_ticks = res->audio.info.ticks;
    info->video_wait_ticks = res->video.info.ticks;
    info->audio_dt_ticks = res->audio.attempted ? (uint32_t)(res->audio.t_end - res->audio.t_start) : 0u;
    info->video_dt_ticks = res->video.attempted ? (uint32_t)(res->video.t_end - res->video.t_start) : 0u;
    info->tb_hz = tb_hz;
    info->audio_index = res->audio.index;
    info->video_index = res->video.index;
    return gbp_avdump_set_identity(info, test_id, build_id, app, commit);
}
