#include "gbp_video_probe.h"

#include <stdio.h>
#include <string.h>
#include "gbp_rawlog.h"

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

static uint32_t ms_to_ticks(uint32_t tb_hz, uint32_t ms)
{
    return (uint32_t)(((uint64_t)tb_hz * ms) / 1000u);
}

void gbp_video_config_timebase(struct gbp_video_config *cfg, uint32_t tb_hz)
{
    gbp_initirqa_config_timebase(&cfg->a, tb_hz);
    cfg->t_delivery_ticks = ms_to_ticks(tb_hz, cfg->t_delivery_ms);
    cfg->t_next_cause_ticks = ms_to_ticks(tb_hz, cfg->t_next_cause_ms);
    cfg->admission_budget_ticks = ms_to_ticks(tb_hz, cfg->admission_budget_ms);
}

void gbp_video_config_default(struct gbp_video_config *cfg)
{
    memset(cfg, 0, sizeof *cfg);
    gbp_initirqa_config_default(&cfg->a);
    cfg->t_delivery_ms = GBP_AVSEQ_T_DELIVERY_MS;
    cfg->t_next_cause_ms = GBP_AVSEQ_T_NEXT_CAUSE_MS;
    cfg->admission_budget_ms = GBP_AVSEQ_ADMISSION_BUDGET_MS;
    cfg->target_video_blocks = GBP_AVSEQ_TARGET_VIDEO_BLOCKS;
    cfg->max_deliveries = GBP_AVSEQ_MAX_DELIVERIES;
    cfg->verify_cycles = GBP_AVSEQ_VERIFY_CYCLES;
    cfg->ack_or = 0x8000;
    cfg->src_mask = 0x0555;
    cfg->av_mask = 0x0500;
    cfg->audio_src = GBP_AVSEQ_AUDIO_SRC;
    cfg->video_src = GBP_AVSEQ_VIDEO_SRC;
    cfg->audio_index = GBP_AVSEQ_AUDIO_INDEX;
    cfg->video_index = GBP_AVSEQ_VIDEO_INDEX;
    cfg->audio_len = GBP_AVSEQ_AUDIO_BLOCK_SIZE;
    cfg->video_len = GBP_AVSEQ_VIDEO_BLOCK_SIZE;
    cfg->odd_mask = 0x0AAA;
    cfg->bit15_mask = 0x8000;
    cfg->high_mask = 0x7000;
    gbp_video_config_timebase(cfg, cfg->a.tb_hz);
}

const char *gbp_video_status_name(gbp_video_status s)
{
    switch (s) {
    case GBP_VIDEO_OK_SEQUENCE_CAPTURE: return "ok_video_sequence_capture";
    case GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP: return "ok_target_not_reached_delivery_cap";
    case GBP_VIDEO_OK_TARGET_NOT_REACHED_RUNTIME_CAP: return "ok_target_not_reached_runtime_cap";
    case GBP_VIDEO_OBSERVATION_NO_NEXT_CAUSE: return "observation_no_next_cause";
    case GBP_VIDEO_CAPTURE_COMPLETED_WITH_ERRORS: return "capture_completed_with_errors";
    case GBP_VIDEO_NO_INITIAL_CAUSE: return "no_initial_cause";
    case GBP_VIDEO_FIRST_DELIVERY_TIMEOUT: return "first_delivery_timeout";
    case GBP_VIDEO_ABORT_STAGE_A: return "abort_stage_a";
    case GBP_VIDEO_ABORT_HANDLER_INSTALL: return "abort_handler_install";
    case GBP_VIDEO_ABORT_PRE_UNMASK_STATE: return "abort_pre_unmask_state";
    case GBP_VIDEO_ABORT_UNMASK: return "abort_unmask";
    case GBP_VIDEO_ABORT_BULK_UNAVAILABLE: return "abort_bulk_unavailable";
    case GBP_VIDEO_ABORT_RESET_UNAVAILABLE: return "abort_reset_unavailable";
    case GBP_VIDEO_ABORT_STORE_UNAVAILABLE: return "abort_store_unavailable";
    case GBP_VIDEO_ABORT_PRESVC_STATE: return "abort_presvc_state";
    case GBP_VIDEO_ABORT_READ_INCONSISTENT: return "abort_read_inconsistent";
    case GBP_VIDEO_ABORT_TRANSPORT: return "abort_transport";
    case GBP_VIDEO_ABORT_CAPACITY: return "abort_capacity";
    case GBP_VIDEO_ACK_WRITE_FAILED: return "ack_write_failed";
    case GBP_VIDEO_REARM_WRITE_FAILED: return "rearm_write_failed";
    case GBP_VIDEO_AUDIO_DMA_BUSY: return "audio_dma_busy";
    case GBP_VIDEO_AUDIO_DMA_TIMEOUT: return "audio_dma_timeout";
    case GBP_VIDEO_AUDIO_DMA_ERROR: return "audio_dma_error";
    case GBP_VIDEO_VIDEO_DMA_BUSY: return "video_dma_busy";
    case GBP_VIDEO_VIDEO_DMA_TIMEOUT: return "video_dma_timeout";
    case GBP_VIDEO_VIDEO_DMA_ERROR: return "video_dma_error";
    case GBP_VIDEO_ANOMALY_REENTRY: return "anomaly_reentry";
    case GBP_VIDEO_ANOMALY_MISSED_ENTRY: return "anomaly_missed_entry";
    case GBP_VIDEO_ANOMALY_ISR_STATE: return "anomaly_isr_state";
    case GBP_VIDEO_ANOMALY_RECORD_NOT_CLEAR: return "anomaly_record_not_clear";
    case GBP_VIDEO_ANOMALY_MASK_FAILURE: return "anomaly_mask_failure";
    case GBP_VIDEO_ANOMALY_UNEXPECTED_SOURCE: return "anomaly_unexpected_source";
    case GBP_VIDEO_ANOMALY_CAUSE_WITHOUT_SOURCE: return "anomaly_cause_without_source";
    case GBP_VIDEO_ANOMALY_CONTROL_CHANGED: return "anomaly_control_changed";
    case GBP_VIDEO_ANOMALY_POSTACK_SHAPE: return "anomaly_postack_shape";
    case GBP_VIDEO_ANOMALY_PI_STICKY: return "anomaly_pi_sticky";
    case GBP_VIDEO_ANOMALY_REARM_STATE: return "anomaly_rearm_state";
    default: return "?";
    }
}

const char *gbp_video_status_class(gbp_video_status s)
{
    switch (s) {
    case GBP_VIDEO_OK_SEQUENCE_CAPTURE:
    case GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP:
    case GBP_VIDEO_OK_TARGET_NOT_REACHED_RUNTIME_CAP: return "ok";
    case GBP_VIDEO_OBSERVATION_NO_NEXT_CAUSE:
    case GBP_VIDEO_NO_INITIAL_CAUSE:
    case GBP_VIDEO_FIRST_DELIVERY_TIMEOUT: return "observation";
    case GBP_VIDEO_CAPTURE_COMPLETED_WITH_ERRORS: return "errors";
    case GBP_VIDEO_ABORT_STAGE_A:
    case GBP_VIDEO_ABORT_HANDLER_INSTALL:
    case GBP_VIDEO_ABORT_PRE_UNMASK_STATE:
    case GBP_VIDEO_ABORT_UNMASK:
    case GBP_VIDEO_ABORT_BULK_UNAVAILABLE:
    case GBP_VIDEO_ABORT_RESET_UNAVAILABLE:
    case GBP_VIDEO_ABORT_STORE_UNAVAILABLE:
    case GBP_VIDEO_ABORT_PRESVC_STATE:
    case GBP_VIDEO_ABORT_READ_INCONSISTENT:
    case GBP_VIDEO_ABORT_CAPACITY: return "abort";
    case GBP_VIDEO_ABORT_TRANSPORT:
    case GBP_VIDEO_ACK_WRITE_FAILED:
    case GBP_VIDEO_REARM_WRITE_FAILED: return "transport";
    case GBP_VIDEO_AUDIO_DMA_BUSY:
    case GBP_VIDEO_AUDIO_DMA_TIMEOUT:
    case GBP_VIDEO_AUDIO_DMA_ERROR:
    case GBP_VIDEO_VIDEO_DMA_BUSY:
    case GBP_VIDEO_VIDEO_DMA_TIMEOUT:
    case GBP_VIDEO_VIDEO_DMA_ERROR: return "dma";
    default: return "anomaly";
    }
}

/* ---- run context ---------------------------------------------------- */
struct run_ctx {
    const struct gbp_transport *t;
    struct ringlog *log;
    const struct gbp_video_config *cfg;
    struct gbp_video_result *res;
    struct gbp_avseq_store *store;
    uint32_t audio_addr, video_addr, irq_addr;
};

static void restore_fail(struct gbp_video_result *res, const char *why)
{
    if (res->restore_ok) res->restore_reason = why;
    res->restore_ok = 0;
}

static const char *old_handler_name(const struct gbp_irq_handler_state *h)
{
    return h->old_handler_null == 1 ? "null" : h->old_handler_null == 0 ? "nonnull" : "?";
}

static void note_control(struct gbp_video_result *res, const struct gbp_initirqa_snapshot *s)
{
    if (s->control_rc == GBP_OK && (s->control_vote != res->a.control_exp || s->control_vote != s->control_b1f)) res->control_ok = 0;
}

static void set_status(struct gbp_video_result *res, gbp_video_status st, const char *reason)
{
    res->status = st;
    res->status_name = gbp_video_status_name(st);
    res->status_class = gbp_video_status_class(st);
    res->reason = reason;
}

static void service_failed(struct gbp_video_result *res, const char *reason)
{
    if (res->service_ok) res->service_reason = reason;
    res->service_ok = 0;
}

/* wrap-safe remaining admission budget at time t (0 once the deadline passed; "unlimited" before the first unmask) */
static uint32_t remaining_at(const struct gbp_video_result *res, uint32_t t)
{
    uint32_t d;
    if (!res->deadline_armed) return 0xFFFFFFFFu;
    d = (uint32_t)(res->admission_deadline - t);
    if ((int32_t)d <= 0) return 0u;
    return d;
}

/* ---- teardown hook: handler restore + mask verification, between the PI step and AR_INFO ---- */
static void teardown_hook(void *arg)
{
    struct run_ctx *x = (struct run_ctx *)arg;
    struct gbp_video_result *res = x->res;
    int engaged = (res->h.handler_was_installed || res->unmasks) ? 1 : 0;
    const char *fail = gbp_irq_service_teardown_hook(x->t, x->log, &res->h, engaged, &res->a.errors);
    if (fail) restore_fail(res, fail);
}

static void log_lean_cycles(struct run_ctx *x);

/* ---- the teardown for every path after the 003A stage (CPU masked, at most one PI W1C) ---- */
static void teardown_video(struct run_ctx *x, const char *variant)
{
    struct gbp_video_result *res = x->res;
    struct gbp_initirqa_teardown_opts opts;
    res->teardown_variant = variant;
    /* the lean cycles' compact records first (chronological order for the log and for a replay fixture), then the teardown */
    log_lean_cycles(x);
    ringlog_printf(x->log, "TEARDOWNVIDEO variant=%s capture=%s deliveries=%u video=%u/%u audio=%u/%u acks=%u rearms=%u next_cause_at_end=%d unmasks=%u",
                   variant, gbp_avseq_end_name(res->capture), res->deliveries, res->video_completed, res->video_blocks,
                   res->audio_completed, res->audio_drains, res->acks, res->rearms, res->next_cause_at_end, res->unmasks);
    opts.pi_cleanup_allowed = 1;                 /* the teardown's own budget: one W1C at most */
    opts.pre_arinfo_hook = teardown_hook;
    opts.hook_ctx = x;
    opts.pi_policy = res->unmasks ? "unmasked_per_cycle" : "never_unmasked";
    gbp_initirqa_teardown(x->t, x->log, &x->cfg->a, &res->a, &opts);
    if (res->a.pi_cleanup_performed) res->teardown_w1c = 1;
    res->pi_sticky_final = bit13(res->a.cleanup_intsr_after) ? 1 : 0;
    if (!res->a.restore_ok && res->restore_ok) restore_fail(res, res->a.restore_reason);
}

/* Writes issued whose completion the transport did not report: the stage's five plus the per-cycle ACK / re-arm counted as they happen. */
static unsigned count_uncertain_stage(const struct gbp_video_result *res)
{
    const struct gbp_regwrite_result *w[5];
    unsigned i, n = 0;
    w[0] = &res->a.w_ctl_exp; w[1] = &res->a.w_a1; w[2] = &res->a.w_a2; w[3] = &res->a.w_stop; w[4] = &res->a.w_ctl_restore;
    for (i = 0; i < 5; i++) if (w[i]->attempted && !w[i]->completed) n++;
    return n;
}

static void end_records(struct run_ctx *x)
{
    struct gbp_video_result *res = x->res;
    struct gbp_avseq_store *s = x->store;
    unsigned i;
    res->uncertain_writes += count_uncertain_stage(res);
    res->errors = res->a.errors;
    res->transport_ok = (res->errors == 0) ? 1 : 0;
    res->power_cycle_required = res->a.power_cycle_required;
    ringlog_printf(x->log, "VIDEO end status=%s class=%s reason=%s restore=%s restore_reason=%s teardown=%s power_cycle_required=%d errors=%u transport_ok=%d",
                   res->status_name, res->status_class, res->reason, res->restore_ok ? "ok" : "error", res->restore_reason,
                   res->teardown_variant ? res->teardown_variant : "-", res->power_cycle_required, res->errors, res->transport_ok);
    gbp_initirqa_log_summary_records(x->log, &res->a);
    if (s) {
        for (i = 0; i < s->vblocks_n; i++) gbp_avseq_log_vblock(x->log, &s->vblocks[i]);
        for (i = 0; i < s->ablocks_n; i++) gbp_avseq_log_ablock(x->log, &s->ablocks[i]);
        gbp_avseq_log_boundaries(x->log, "gbi", &res->b_gbi);
        gbp_avseq_log_boundaries(x->log, "disc", &res->b_disc);
    }
    ringlog_printf(x->log, "ADMISSION t0=%lu budget_ticks=%lu deadline=%lu armed=%d admissions=%u refusals=%u last_refusal=%s target=%u max_deliveries=%u verify_cycles=%u",
                   (unsigned long)res->t0, (unsigned long)x->cfg->admission_budget_ticks, (unsigned long)res->admission_deadline, res->deadline_armed,
                   res->admissions, res->refusals, res->refusal, x->cfg->target_video_blocks, x->cfg->max_deliveries, x->cfg->verify_cycles);
    ringlog_printf(x->log, "MATRIX service=%s service_reason=%s capture=%s deliveries=%u video=%u/%u audio=%u/%u audio_raw=%u next_cause_at_end=%d boundaries_gbi=%u boundaries_disc=%u complete_gbi=%d complete_disc=%d reference_content=offline restore=%s",
                   res->service_ok ? "ok" : "failed", res->service_reason, gbp_avseq_end_name(res->capture), res->deliveries,
                   res->video_completed, res->video_blocks, res->audio_completed, res->audio_drains, s ? gbp_avseq_audio_raw_count(s) : 0u,
                   res->next_cause_at_end, res->b_gbi.count, res->b_disc.count, res->b_gbi.complete_interval, res->b_disc.complete_interval,
                   res->restore_ok ? "ok" : "failed");
    ringlog_printf(x->log, "COUNTERS unmasks=%u deliveries=%u acks=%u rearms=%u lean=%u verify=%u unexpected=%04x site=%s cycle=%u isr_w1c=%u main_w1c=%u teardown_w1c=%u w1c_total=%u control_ok=%d uncertain=%u",
                   res->unmasks, res->deliveries, res->acks, res->rearms, res->lean_cycles, res->verify_cycles_done, (unsigned)res->unexpected,
                   res->unexpected_site, res->unexpected_cycle, res->isr_w1c, res->main_w1c, res->teardown_w1c,
                   res->isr_w1c + res->main_w1c + res->teardown_w1c, res->control_ok, res->uncertain_writes);
    ringlog_printf(x->log, "TIMING first_cause_to_isr=%lu/%luus t0=%lu deadline=%lu",
                   (unsigned long)res->dt_cause_to_isr_first, (unsigned long)ticks_to_us(x->cfg->a.tb_hz, res->dt_cause_to_isr_first),
                   (unsigned long)res->t0, (unsigned long)res->admission_deadline);
    ringlog_printf(x->log, "RESTOREVIDEO handler_installed=%d handler_restored=%d old_handler=%s mask_ok=%d intmr_final=%08lx pi_sticky_final=%d unmasks=%u",
                   res->h.handler_was_installed, res->h.handler_restored, old_handler_name(&res->h), res->h.mask_ok,
                   (unsigned long)res->h.intmr_final, res->pi_sticky_final, res->unmasks);
}

/* the summaries that need the raw buffers (read-only), then the boundaries */
static void summarize(struct run_ctx *x)
{
    struct gbp_avseq_store *s = x->store;
    unsigned i;
    if (!s) return;
    gbp_avseq_summarize(s);
    for (i = 0; i < s->ablocks_n; i++) {
        const struct gbp_avseq_ablock *a = &s->ablocks[i];
        if (a->summarized && a->cycle < s->cycles_n) s->cycles[a->cycle].audio_crc32 = a->crc32;
    }
    gbp_avseq_boundaries(s, 0, &x->res->b_gbi);
    gbp_avseq_boundaries(s, 1, &x->res->b_disc);
}

static void log_lean_cycles(struct run_ctx *x)
{
    struct gbp_avseq_store *s = x->store;
    unsigned i;
    if (!s) return;
    for (i = 0; i < s->cycles_n; i++) {
        if (s->cycles[i].verify) continue;                 /* verify cycles logged their lines inline */
        gbp_avseq_log_cycle(x->log, &s->cycles[i], x->audio_addr, x->video_addr);
    }
}

static void finish(struct run_ctx *x, gbp_video_status st, const char *reason, const char *variant, int capture)
{
    set_status(x->res, st, reason);
    if (capture) x->res->capture = capture;
    if (x->res->capture == GBP_AVSEQ_END_EARLY_FAILURE || (st != GBP_VIDEO_OK_SEQUENCE_CAPTURE && st != GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP &&
        st != GBP_VIDEO_OK_TARGET_NOT_REACHED_RUNTIME_CAP && st != GBP_VIDEO_OBSERVATION_NO_NEXT_CAUSE)) service_failed(x->res, reason);
    summarize(x);
    teardown_video(x, variant);
    end_records(x);
}

/* ---- snapshot checks shared by PRESVC / POSTDRAIN / POSTACK / REARMPOST of the verify cycles (as GBP-AV-SERVICE-001) ---- */
static int common_checks(struct run_ctx *x, const struct gbp_initirqa_snapshot *s, const char *site, unsigned n,
                         gbp_video_status *st, const char **reason)
{
    struct gbp_video_result *res = x->res;
    const struct gbp_video_config *cfg = x->cfg;
    uint16_t unexpected;
    note_control(res, s);
    if (!s->pi_ok || s->control_rc != GBP_OK || s->irq_rc != GBP_OK) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "%s_read_failed_cycle_%u", site, n);
        *st = GBP_VIDEO_ABORT_TRANSPORT; *reason = res->reason_buf; return 0;
    }
    if (s->irq_disc != s->irq_gbi) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "%s_semantic_disagree_cycle_%u", site, n);
        *st = GBP_VIDEO_ABORT_READ_INCONSISTENT; *reason = res->reason_buf; return 0;
    }
    if (s->control_vote != res->a.control_exp || s->control_vote != s->control_b1f) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "control_changed_%s_cycle_%u", site, n);
        *st = GBP_VIDEO_ANOMALY_CONTROL_CHANGED; *reason = res->reason_buf; return 0;
    }
    if (bit13(s->intmr) || (s->pi2_ok && bit13(s->intmr2))) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "intmr13_set_%s_cycle_%u", site, n);
        *st = GBP_VIDEO_ANOMALY_MASK_FAILURE; *reason = res->reason_buf; return 0;
    }
    unexpected = (uint16_t)(s->irq_gbi & cfg->src_mask & (uint16_t)~cfg->av_mask);
    if (unexpected) {
        res->unexpected = unexpected;
        res->unexpected_site = site;
        res->unexpected_cycle = n;
        snprintf(res->reason_buf, sizeof res->reason_buf, "unexpected_source_%s_cycle_%u", site, n);
        *st = GBP_VIDEO_ANOMALY_UNEXPECTED_SOURCE; *reason = res->reason_buf; return 0;
    }
    return 1;
}

static void log_service_snapshot(struct run_ctx *x, const char *kind, unsigned n, const struct gbp_initirqa_snapshot *s)
{
    const struct gbp_video_config *cfg = x->cfg;
    ringlog_printf(x->log, "%s n=%u t=%lu intsr13=%u,%u intmr13=%u,%u control=%02x irq=%04x/%04x src=%04x av=%04x unexpected=%04x odd=%04x bit15=%u high=%04x",
                   kind, n, (unsigned long)s->ticks, bit13(s->intsr), bit13(s->intsr2), bit13(s->intmr), bit13(s->intmr2),
                   (unsigned)s->control_vote, (unsigned)s->irq_gbi, (unsigned)s->irq_disc, (unsigned)(s->irq_gbi & cfg->src_mask),
                   (unsigned)(s->irq_gbi & cfg->av_mask), (unsigned)(s->irq_gbi & cfg->src_mask & (uint16_t)~cfg->av_mask),
                   (unsigned)(s->irq_gbi & cfg->odd_mask), (unsigned)((s->irq_gbi & cfg->bit15_mask) ? 1u : 0u),
                   (unsigned)(s->irq_gbi & cfg->high_mask));
}

static gbp_video_status dma_status(int is_audio, gbp_status rc)
{
    if (rc == GBP_ERR_BUSY) return is_audio ? GBP_VIDEO_AUDIO_DMA_BUSY : GBP_VIDEO_VIDEO_DMA_BUSY;
    if (rc == GBP_ERR_TIMEOUT) return is_audio ? GBP_VIDEO_AUDIO_DMA_TIMEOUT : GBP_VIDEO_VIDEO_DMA_TIMEOUT;
    return is_audio ? GBP_VIDEO_AUDIO_DMA_ERROR : GBP_VIDEO_VIDEO_DMA_ERROR;
}

/* the per-cycle names of the verify-cycle records (the snapshot keeps the pointer) */
static void cycle_names(struct gbp_video_result *res, unsigned n)
{
    snprintf(res->id_presvc, sizeof res->id_presvc, "PRESVC-%u", n);
    snprintf(res->id_postdrain, sizeof res->id_postdrain, "POSTDRAIN-%u", n);
    snprintf(res->id_postack, sizeof res->id_postack, "POSTACK-%u", n);
    snprintf(res->id_rearmpost, sizeof res->id_rearmpost, "REARMPOST-%u", n);
    snprintf(res->tag_ack, sizeof res->tag_ack, "tag=ACK-%u", n);
    snprintf(res->tag_rearm, sizeof res->tag_rearm, "tag=REARM-%u", n);
    snprintf(res->nfield, sizeof res->nfield, " n=%u", n);
    snprintf(res->sfx, sizeof res->sfx, "-%u", n);
}

/* copies the delivery values into the compact record */
static void record_delivery(struct gbp_avseq_cycle *c, const struct gbp_irq_delivery *d)
{
    const struct gbp_irq_record *r = &d->rec;
    c->intsr_pre = d->intsr_pre_unmask; c->intmr_pre = d->intmr_pre_unmask;
    c->t_unmask = d->t_unmask; c->t_post_unmask = d->t_post_unmask;
    c->intsr_post = d->intsr_post_unmask; c->intmr_post = d->intmr_post_unmask;
    c->rec0_fired = d->rec0_fired;
    c->wait_polls = d->polls; c->timed_out = (uint8_t)(d->timed_out ? 1u : 0u); c->t_wait_end = d->t_wait_end;
    c->intsr_remask = d->intsr_remask_first; c->intmr_remask = d->intmr_remask_first;
    c->remask_retry = (uint8_t)(d->remask_retry ? 1u : 0u); c->mask_ok = (uint8_t)(d->main_mask_ok == 1 ? 1u : 0u);
    c->isr_fired = (uint8_t)(r->fired ? 1u : 0u); c->isr_count = (uint8_t)(r->count > 255u ? 255u : r->count);
    c->isr_reentry = (uint8_t)(d->reentry ? 1u : 0u);
    c->t_entry = r->t_entry; c->latency = d->latency_ticks;
    c->intsr_entry = r->intsr_before_ack; c->intmr_entry = r->intmr_at_entry; c->intsr_after_w1c = r->intsr_after_ack;
    c->intmr_after_mask = r->intmr_after_mask; c->intsr_before_w1c = r->intsr_before_w1c;
    c->t_second = r->t_second; c->intsr_second = r->intsr_second; c->intmr_second = r->intmr_second;
    c->reentry_t = r->reentry_t; c->reentry_intsr = r->reentry_intsr; c->reentry_intmr = r->reentry_intmr;
}

/* WAIT_NEXT: the masked read-only poll for the next cause, bounded by min(T_NEXT_CAUSE, remaining budget);
 * a single read when no budget is left. Nothing is written to the PI here. */
static void wait_next(struct run_ctx *x, struct gbp_avseq_cycle *c, uint32_t t_ref)
{
    const struct gbp_transport *t = x->t;
    struct gbp_video_result *res = x->res;
    uint32_t remaining = remaining_at(res, t_ref);
    uint32_t bound = x->cfg->t_next_cause_ticks;
    uint32_t intsr = 0;
    if (remaining == 0u) {
        if (t->poll_intsr(t->ctx, &intsr) != GBP_OK) res->a.poll_errors++;
        c->next_polls = 1;
        c->intsr_next = intsr;
        c->t_next = t_ref;
        c->next_observed = (uint8_t)bit13(intsr);
        c->next_ended_by = (uint8_t)(c->next_observed ? GBP_AVSEQ_NEXT_CAUSE : GBP_AVSEQ_NEXT_SINGLE_READ);
        return;
    }
    if (remaining < bound) bound = remaining;
    for (;;) {
        uint32_t tnow = now(t);
        if (t->poll_intsr(t->ctx, &intsr) == GBP_OK) {
            c->next_polls++;
            if (intsr & GBP_PI_HSP_BIT) {
                c->next_observed = 1; c->next_ended_by = GBP_AVSEQ_NEXT_CAUSE; c->t_next = tnow; c->intsr_next = intsr;
                return;
            }
        } else {
            res->a.poll_errors++;
        }
        if ((uint32_t)(tnow - t_ref) >= bound) {
            c->t_next = tnow; c->intsr_next = intsr;
            c->next_ended_by = (uint8_t)((bound < x->cfg->t_next_cause_ticks) ? GBP_AVSEQ_NEXT_DEADLINE : GBP_AVSEQ_NEXT_TIMEOUT);
            return;
        }
    }
}

int gbp_video_probe_run(const struct gbp_transport *t, struct ringlog *log,
                        const struct gbp_video_config *cfg, struct gbp_video_result *res)
{
    struct run_ctx xs, *x = &xs;
    struct gbp_avseq_store *store = cfg->store;
    gbp_initirqa_cause_rc crc;
    const struct gbp_initirqa_snapshot *ev;
    struct gbp_irq_record rec0;
    gbp_video_status st;
    const char *why = "-";
    int old_null = -1;
    uint32_t t_cause_next = 0;
    unsigned n;

    xs.t = t; xs.log = log; xs.cfg = cfg; xs.res = res; xs.store = store;
    xs.audio_addr = xs.video_addr = xs.irq_addr = 0;
    memset(res, 0, sizeof *res);
    res->store = store;
    res->restore_ok = 1;
    res->restore_reason = "-";
    res->reason = "-";
    res->status_name = "-";
    res->status_class = "-";
    res->preunmask_reason = "-";
    res->unexpected_site = "-";
    res->service_reason = "-";
    res->service_ok = 1;
    res->control_ok = 1;
    res->refusal = "-";
    gbp_irq_service_handler_init(&res->h);
    gbp_irq_service_delivery_init(&res->d);
    gbp_irq_service_ack_init(&res->k);

    ringlog_printf(log, "VIDEO start target=%u max_deliveries=%u verify_cycles=%u budget_ms=%lu budget_ticks=%lu t_delivery_ms=%lu t_delivery_ticks=%lu t_next_cause_ms=%lu t_next_cause_ticks=%lu",
                   cfg->target_video_blocks, cfg->max_deliveries, cfg->verify_cycles, (unsigned long)cfg->admission_budget_ms,
                   (unsigned long)cfg->admission_budget_ticks, (unsigned long)cfg->t_delivery_ms, (unsigned long)cfg->t_delivery_ticks,
                   (unsigned long)cfg->t_next_cause_ms, (unsigned long)cfg->t_next_cause_ticks);
    ringlog_printf(log, "VIDEO masks ack_or=%04x src_mask=%04x av_mask=%04x odd_mask=%04x bit15_mask=%04x high_mask=%04x",
                   (unsigned)cfg->ack_or, (unsigned)cfg->src_mask, (unsigned)cfg->av_mask, (unsigned)cfg->odd_mask,
                   (unsigned)cfg->bit15_mask, (unsigned)cfg->high_mask);
    ringlog_printf(log, "VIDEO blocks audio_idx=%x audio_len=%04lx audio_src=%04x video_idx=%x video_len=%04lx video_src=%04x order=audio_then_video video_slots=%u audio_raw_slots=%u prefill=00 bulk_read=%d reset_op=%d",
                   cfg->audio_index, (unsigned long)cfg->audio_len, (unsigned)cfg->audio_src, cfg->video_index, (unsigned long)cfg->video_len,
                   (unsigned)cfg->video_src, (unsigned)GBP_AVSEQ_MAX_VIDEO_BLOCKS, (unsigned)GBP_AVSEQ_AUDIO_RAW_SLOTS,
                   gbp_transport_has_bulk_read(t), gbp_transport_has_irq_reset(t));
    ringlog_printf(log, "VIDEO policy handler=003b_ext_installed_once record=reset_under_mask_before_each_unmask snapshot=READ_authoritative drain=selected_by_snapshot ack=pending|%04x",
                   (unsigned)cfg->ack_or);
    ringlog_printf(log, "VIDEO policy2 admission=before_unmask cycle=transactional wait_next=masked_poll w1c_budget=isr1_main1_teardown1 predicates=gbi_and_disc content=offline_only");

    if (!store || !store->video_raw || !store->audio_raw || store->video_raw_cap < GBP_AVSEQ_VIDEO_RAW_BYTES || store->audio_raw_cap < GBP_AVSEQ_AUDIO_RAW_BYTES ||
        cfg->target_video_blocks > GBP_AVSEQ_MAX_VIDEO_BLOCKS || cfg->max_deliveries > GBP_AVSEQ_MAX_DELIVERIES) {
        set_status(res, GBP_VIDEO_ABORT_STORE_UNAVAILABLE, "store_or_bounds_invalid");
        res->capture = GBP_AVSEQ_END_EARLY_FAILURE;
        service_failed(res, "store_or_bounds_invalid");
        res->teardown_variant = "none";
        ringlog_printf(log, "VIDEO abort reason=store_or_bounds_invalid");
        end_records(x);
        return 0;
    }
    /* known state of every raw slot before the run, outside the timed region; never reported as block content */
    memset(store->video_raw, 0, GBP_AVSEQ_VIDEO_RAW_BYTES);
    memset(store->audio_raw, 0, GBP_AVSEQ_AUDIO_RAW_BYTES);
    {
        uint8_t *vr = store->video_raw; uint32_t vc = store->video_raw_cap; uint8_t *ar = store->audio_raw; uint32_t ac = store->audio_raw_cap;
        gbp_avseq_store_init(store, vr, vc, ar, ac);
    }

    /* ---- 1. the GBP-INIT-003A sequence, verbatim, PI masked, no handler ---- */
    crc = gbp_initirqa_run_cause(t, log, &cfg->a, &res->a);
    if (crc == GBP_INITIRQA_CAUSE_ABORTED) {
        res->stage_a_aborted = 1;
        res->status = GBP_VIDEO_ABORT_STAGE_A;
        res->status_name = gbp_initirqa_status_name(res->a.status);
        res->status_class = gbp_video_status_class(GBP_VIDEO_ABORT_STAGE_A);
        res->reason = res->a.reason ? res->a.reason : "-";
        res->teardown_variant = "stage_a";
        res->capture = GBP_AVSEQ_END_EARLY_FAILURE;
        service_failed(res, res->reason);
        if (!res->a.restore_ok) restore_fail(res, res->a.restore_reason);
        end_records(x);
        return 0;
    }
    xs.irq_addr = gbp_block_addr(res->a.base, GBP_IDX_IRQ, 0);
    xs.audio_addr = gbp_block_addr(res->a.base, cfg->audio_index, 0);
    xs.video_addr = gbp_block_addr(res->a.base, cfg->video_index, 0);
    if (crc == GBP_INITIRQA_CAUSE_NOT_OBSERVED) {
        finish(x, GBP_VIDEO_NO_INITIAL_CAUSE, "no_intsr13_within_t_max", "S2_before_unmask", GBP_AVSEQ_END_EARLY_FAILURE);
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

    /* ---- 3. the 003B extended one-shot handler, installed ONCE; previous handler kept ---- */
    res->h.irq_path_available = gbp_transport_has_irq_path(t);
    if (!res->h.irq_path_available) {
        ringlog_printf(log, "IRQ install rc=unavailable");
        finish(x, GBP_VIDEO_ABORT_HANDLER_INSTALL, "irq_ops_unavailable", "S2_before_unmask", GBP_AVSEQ_END_EARLY_FAILURE);
        return 0;
    }
    if (!gbp_transport_has_bulk_read(t)) {
        ringlog_printf(log, "VIDEO abort reason=bulk_read_unavailable");
        finish(x, GBP_VIDEO_ABORT_BULK_UNAVAILABLE, "bulk_read_unavailable", "S2_before_unmask", GBP_AVSEQ_END_EARLY_FAILURE);
        return 0;
    }
    if (!gbp_transport_has_irq_reset(t)) {
        ringlog_printf(log, "VIDEO abort reason=record_reset_unavailable");
        finish(x, GBP_VIDEO_ABORT_RESET_UNAVAILABLE, "record_reset_unavailable", "S2_before_unmask", GBP_AVSEQ_END_EARLY_FAILURE);
        return 0;
    }
    res->h.install_rc = t->irq_install(t->ctx, &old_null);
    if (res->h.install_rc != GBP_OK) {
        res->a.errors++;
        ringlog_printf(log, "IRQ install rc=%s", gbp_status_name(res->h.install_rc));
        finish(x, GBP_VIDEO_ABORT_HANDLER_INSTALL, "install_failed", "S2_before_unmask", GBP_AVSEQ_END_EARLY_FAILURE);
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
        if (res->unexpected) finish(x, GBP_VIDEO_ANOMALY_UNEXPECTED_SOURCE, "unexpected_source_PREUNMASK", "S2_before_unmask", GBP_AVSEQ_END_EARLY_FAILURE);
        else if (strcmp(why, "control_changed") == 0) finish(x, GBP_VIDEO_ANOMALY_CONTROL_CHANGED, "control_changed_PREUNMASK", "S2_before_unmask", GBP_AVSEQ_END_EARLY_FAILURE);
        else finish(x, GBP_VIDEO_ABORT_PRE_UNMASK_STATE, why, "S2_before_unmask", GBP_AVSEQ_END_EARLY_FAILURE);
        return 0;
    }

    /* ---- 5. the service loop ---- */
    t_cause_next = res->t_cause;
    for (n = 0; ; n++) {
        struct gbp_avseq_cycle *c;
        int verify = (n < cfg->verify_cycles) ? 1 : 0;
        uint16_t pending;
        uint32_t t_ref, t_adm = 0;

        /* ---- CHECK_ADMISSION (every cycle after the first: the first enters from the validated initialization).
         * Evaluated BEFORE the cycle record is bound, so a full table ends the loop as a cap, never as a failure. ---- */
        if (n > 0) {
            uint32_t remaining;
            t_adm = now(t);
            remaining = remaining_at(res, t_adm);
            if (store->vblocks_n >= cfg->target_video_blocks) res->refusal = "target_reached";
            else if (res->deliveries >= cfg->max_deliveries || n >= GBP_AVSEQ_MAX_DELIVERIES) res->refusal = "delivery_cap";
            else if (remaining == 0u) res->refusal = "runtime_cap";
            else res->refusal = "-";
            if (strcmp(res->refusal, "-") != 0) {
                res->refusals++;
                res->next_cause_at_end = 1;              /* the cause found by the previous WAIT_NEXT stays latched for the teardown */
                if (verify) ringlog_printf(log, "ADMIT n=%u t_adm=%lu refused=%s remaining=%lu deliveries=%u video=%u", n, (unsigned long)t_adm,
                                           res->refusal, (unsigned long)remaining, res->deliveries, store->vblocks_n);
                if (strcmp(res->refusal, "target_reached") == 0) finish(x, GBP_VIDEO_OK_SEQUENCE_CAPTURE, "-", "S5_capture_end", GBP_AVSEQ_END_TARGET_REACHED);
                else if (strcmp(res->refusal, "delivery_cap") == 0) finish(x, GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP, "-", "S5_capture_end", GBP_AVSEQ_END_DELIVERY_CAP);
                else finish(x, GBP_VIDEO_OK_TARGET_NOT_REACHED_RUNTIME_CAP, "-", "S5_capture_end", GBP_AVSEQ_END_RUNTIME_CAP);
                goto completed;
            }
            res->admissions++;
        }
        c = &store->cycles[n];
        gbp_avseq_cycle_init(c, n);
        c->verify = (uint8_t)verify;
        c->t_cause = t_cause_next;
        c->t_adm = t_adm;
        cycle_names(res, n);
        if (n > 0) {
            uint32_t remaining = remaining_at(res, t_adm);
            /* ---- PREPARE: the record back to zero (memory only), INTMR bit 13 read 0, the record read 0/0; no PI write ---- */
            {
                gbp_status rc = t->irq_record_reset(t->ctx);
                uint32_t intsr = 0, intmr = 0;
                struct gbp_irq_record rr;
                c->prep_rc = (uint8_t)rc;
                if (rc != GBP_OK) { res->a.errors++; if (verify) ringlog_printf(log, "PREPARE n=%u reset_rc=%s", n, gbp_status_name(rc)); finish(x, GBP_VIDEO_ANOMALY_RECORD_NOT_CLEAR, "record_reset_refused", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
                if (t->read_pi(t->ctx, &intsr, &intmr) != GBP_OK) { res->a.errors++; finish(x, GBP_VIDEO_ABORT_TRANSPORT, "prepare_pi_read_failed", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
                c->intsr_prep = intsr; c->intmr_prep = intmr;
                memset(&rr, 0, sizeof rr);
                t->irq_record(t->ctx, &rr);
                if (verify) ringlog_printf(log, "ADMIT n=%u t_adm=%lu remaining=%lu deliveries=%u video=%u prep_intsr=%08lx prep_intmr=%08lx record=%lu/%lu",
                                           n, (unsigned long)c->t_adm, (unsigned long)remaining, res->deliveries, store->vblocks_n,
                                           (unsigned long)intsr, (unsigned long)intmr, (unsigned long)rr.count, (unsigned long)rr.fired);
                if (bit13(intmr)) { finish(x, GBP_VIDEO_ANOMALY_MASK_FAILURE, "intmr13_set_before_unmask", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
                if (rr.count || rr.fired) { finish(x, GBP_VIDEO_ANOMALY_RECORD_NOT_CLEAR, "record_not_clear_before_unmask", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
                if (!bit13(intsr)) { finish(x, GBP_VIDEO_ANOMALY_REARM_STATE, "no_cause_latched_at_admission", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            }
        } else {
            res->admissions++;
            c->intsr_prep = res->preunmask.intsr; c->intmr_prep = res->preunmask.intmr;
        }

        /* ---- UNMASK + CONFIRM: the ONE unmask of the cycle, the delivery, the main re-mask, the record ---- */
        gbp_irq_service_delivery_init(&res->d);
        gbp_irq_service_deliver_quiet(t, cfg->a.tb_hz, cfg->t_delivery_ticks, -1, &res->d, &res->a.errors);
        if (verify) gbp_irq_service_deliver_log(log, cfg->a.tb_hz, cfg->t_delivery_ms, cfg->t_delivery_ticks, res->nfield, res->sfx, &res->d);
        res->unmasks++;
        if (n == 0) { res->t0 = res->d.t_unmask; res->admission_deadline = res->t0 + cfg->admission_budget_ticks; res->deadline_armed = 1; }
        record_delivery(c, &res->d);
        if (res->d.mask_rc != GBP_OK) restore_fail(res, "mask_failed");
        if (!res->d.fired) {
            int never_opened = (res->d.unmask_rc != GBP_OK) ||
                               (res->d.pi_post_unmask_ok && !bit13(res->d.intmr_post_unmask) && res->d.rec.count == 0);
            if (res->d.unmask_rc != GBP_OK) res->a.errors++;
            store->cycles_n = n + 1u;
            if (n == 0) finish(x, never_opened ? GBP_VIDEO_ABORT_UNMASK : GBP_VIDEO_FIRST_DELIVERY_TIMEOUT,
                               never_opened ? "unmask_not_effective" : "no_delivery_within_t_delivery", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE);
            else finish(x, GBP_VIDEO_ANOMALY_MISSED_ENTRY, "no_handler_entry_after_unmask", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE);
            return 0;
        }
        store->cycles_n = n + 1u;
        res->deliveries++;
        res->isr_w1c++;                          /* the first entry performs the body's single W1C */
        if (n == 0) res->dt_cause_to_isr_first = (uint32_t)(res->d.rec.t_entry - res->t_cause);
        if (res->d.reentry) { finish(x, GBP_VIDEO_ANOMALY_REENTRY, "handler_entered_more_than_once", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
        if (res->d.rec.count != 1u || !bit13(res->d.rec.intsr_before_ack) || !bit13(res->d.rec.intmr_at_entry) ||
            bit13(res->d.rec.intmr_after_mask) || bit13(res->d.rec.intsr_after_ack)) {
            finish(x, GBP_VIDEO_ANOMALY_ISR_STATE, "handler_record_state_unexpected", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0;
        }
        if (res->d.main_mask_ok != 1) { finish(x, GBP_VIDEO_ANOMALY_MASK_FAILURE, "intmr13_still_set_after_remask", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
        c->admitted = 1;                          /* from here on the cycle is transactional */

        /* ---- READ: the authoritative snapshot of this cycle (ONE IRQ read; verify cycles take the AVSVC snapshot) ---- */
        if (verify) {
            gbp_initirqa_snapshot_take(t, &res->a, &res->presvc, res->id_presvc, 0, 1);
            gbp_initirqa_snapshot_log(log, &res->a, &res->presvc);
            log_service_snapshot(x, "PRESVC", n, &res->presvc);
            c->t_read = res->presvc.ticks;
            memcpy(c->irq_raw, res->presvc.irq, GBP_BLOCK_SIZE);
            c->irq_info = res->presvc.irq_info;
            c->irq_rc = res->presvc.irq_rc;
            c->irq_disc = res->presvc.irq_disc; c->irq_gbi = res->presvc.irq_gbi;
            if (!common_checks(x, &res->presvc, "PRESVC", n, &st, &why)) { finish(x, st, why, "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            pending = res->presvc.irq_gbi;
        } else {
            memset(&c->irq_info, 0, sizeof c->irq_info);
            c->irq_rc = t->read_block(t->ctx, xs.irq_addr, c->irq_raw, &c->irq_info);
            c->t_read = now(t);
            if (c->irq_rc != GBP_OK) { res->a.errors++; snprintf(res->reason_buf, sizeof res->reason_buf, "READ_failed_cycle_%u", n); finish(x, GBP_VIDEO_ABORT_TRANSPORT, res->reason_buf, "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            c->irq_disc = gbp_irq_value_disc(c->irq_raw);
            c->irq_gbi = gbp_irq_value_gbi(c->irq_raw);
            if (c->irq_disc != c->irq_gbi) { snprintf(res->reason_buf, sizeof res->reason_buf, "READ_semantic_disagree_cycle_%u", n); finish(x, GBP_VIDEO_ABORT_READ_INCONSISTENT, res->reason_buf, "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            pending = c->irq_gbi;
            {
                uint16_t unexpected = (uint16_t)(pending & cfg->src_mask & (uint16_t)~cfg->av_mask);
                if (unexpected) {
                    res->unexpected = unexpected; res->unexpected_site = "READ"; res->unexpected_cycle = n;
                    snprintf(res->reason_buf, sizeof res->reason_buf, "unexpected_source_READ_cycle_%u", n);
                    finish(x, GBP_VIDEO_ANOMALY_UNEXPECTED_SOURCE, res->reason_buf, "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0;
                }
            }
        }
        c->pending = pending;
        c->irq_byte0 = c->irq_raw[0];
        c->irq_off2_g0 = c->irq_raw[2];
        if ((pending & cfg->av_mask) == 0) { snprintf(res->reason_buf, sizeof res->reason_buf, "cause_without_av_source_cycle_%u", n); finish(x, GBP_VIDEO_ANOMALY_CAUSE_WITHOUT_SOURCE, res->reason_buf, "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
        if ((pending & cfg->odd_mask) != 0 || (pending & cfg->bit15_mask) != 0 || (pending & cfg->high_mask) != 0) {
            snprintf(res->reason_buf, sizeof res->reason_buf, "irq_shape_READ_cycle_%u", n);
            finish(x, GBP_VIDEO_ABORT_PRESVC_STATE, res->reason_buf, "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0;
        }
        c->audio_selected = (uint8_t)((pending & cfg->audio_src) ? 1u : 0u);
        c->video_selected = (uint8_t)((pending & cfg->video_src) ? 1u : 0u);
        c->ack_value = (uint16_t)(pending | cfg->ack_or);
        if (verify) ringlog_printf(log, "SVC n=%u pending=%04x audio=%u video=%u order=audio_then_video ack_value=%04x t=%lu", n, (unsigned)pending,
                                   c->audio_selected, c->video_selected, (unsigned)c->ack_value, (unsigned long)c->t_read);

        /* ---- AUDIO: one whole-block DMA into the next raw slot (first 8) or the ping-pong pair ---- */
        if (c->audio_selected) {
            unsigned raw_slot = 0;
            uint8_t *buf = gbp_avseq_audio_target(store, &raw_slot);
            struct gbp_avseq_ablock *a;
            if (!buf) { finish(x, GBP_VIDEO_ABORT_CAPACITY, "audio_slot_unavailable", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            gbp_avblock_init(&res->audio, "audio", cfg->audio_index, cfg->audio_src, buf, GBP_AVSEQ_AUDIO_BLOCK_SIZE, cfg->audio_len);
            res->audio.selected = 1;
            res->audio_drains++;
            c->audio_attempted = 1;                  /* set before the transport call, as gbp_avblock_read does */
            gbp_avblock_read(t, res->a.base, &res->audio, &res->a.errors);
            a = gbp_avseq_audio_commit(store, n, raw_slot, res->audio.rc, &res->audio.info, res->audio.t_start, res->audio.t_end);
            c->audio_completed = (uint8_t)(res->audio.completed ? 1u : 0u);
            c->audio_rc = (uint8_t)res->audio.rc;
            c->t_audio_start = res->audio.t_start; c->t_audio_end = res->audio.t_end;
            c->audio_wait = res->audio.info.ticks; c->audio_polls = res->audio.info.polls;
            c->audio_slot = (a && a->completed) ? a->slot : GBP_AVSEQ_SLOT_NONE;
            if (res->audio.completed) res->audio_completed++;
            if (verify) gbp_avblock_log_read(log, "AUDIOREAD", &res->audio);
            if (!res->audio.completed) {
                if (res->audio.rc == GBP_ERR_TIMEOUT) res->uncertain_writes += 0;   /* a drain is a read: the device state is not written */
                snprintf(res->reason_buf, sizeof res->reason_buf, "audio_read_failed_cycle_%u", n);
                finish(x, dma_status(1, res->audio.rc), res->reason_buf, "S3_dma_failed", GBP_AVSEQ_END_EARLY_FAILURE);   /* no VIDEO, no ACK, no re-arm */
                return 0;
            }
        }

        /* ---- VIDEO: one whole-block DMA into the next slot of the contiguous buffer (bounds checked first) ---- */
        if (c->video_selected) {
            uint8_t *buf = gbp_avseq_video_target(store);
            struct gbp_avseq_vblock *v;
            if (!buf) { finish(x, GBP_VIDEO_ABORT_CAPACITY, "video_slot_unavailable", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            gbp_avblock_init(&res->video, "video", cfg->video_index, cfg->video_src, buf, GBP_AVSEQ_VIDEO_BLOCK_SIZE, cfg->video_len);
            res->video.selected = 1;
            res->video_blocks++;
            c->video_attempted = 1;
            gbp_avblock_read(t, res->a.base, &res->video, &res->a.errors);
            v = gbp_avseq_video_commit(store, n, pending, res->video.rc, &res->video.info, res->video.t_start, res->video.t_end);
            c->video_completed = (uint8_t)(res->video.completed ? 1u : 0u);
            c->video_rc = (uint8_t)res->video.rc;
            c->video_seq = v ? v->seq : (uint16_t)GBP_AVSEQ_VIDEO_SEQ_NONE;
            c->t_video_start = res->video.t_start; c->t_video_end = res->video.t_end;
            c->video_wait = res->video.info.ticks; c->video_polls = res->video.info.polls;
            if (res->video.completed) res->video_completed++;
            if (verify) gbp_avblock_log_read(log, "VIDEOREAD", &res->video);
            if (!res->video.completed) {
                snprintf(res->reason_buf, sizeof res->reason_buf, "video_read_failed_cycle_%u", n);
                finish(x, dma_status(0, res->video.rc), res->reason_buf, "S3_dma_failed", GBP_AVSEQ_END_EARLY_FAILURE);   /* no ACK, no re-arm */
                return 0;
            }
        }

        /* ---- POSTDRAIN (verify cycles only): observation, never changes pending / the ACK ---- */
        if (verify) {
            gbp_initirqa_snapshot_take(t, &res->a, &res->postdrain, res->id_postdrain, 0, 1);
            gbp_initirqa_snapshot_log(log, &res->a, &res->postdrain);
            log_service_snapshot(x, "POSTDRAIN", n, &res->postdrain);
            c->relatch_postdrain = (uint8_t)((bit13(res->postdrain.intsr) || (res->postdrain.pi2_ok && bit13(res->postdrain.intsr2))) ? 1u : 0u);
            if (!common_checks(x, &res->postdrain, "POSTDRAIN", n, &st, &why)) { finish(x, st, why, "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
        }

        /* ---- ACK := pending | 0x8000 (the READ value), then PI clean (<= 1 main W1C) ---- */
        c->ack_attempted = 1;
        if (verify) {
            gbp_irq_service_ack_init(&res->k);
            gbp_irq_service_ack_write_postack(t, log, &res->a, pending, cfg->ack_or, cfg->src_mask, res->nfield, res->id_postack, res->tag_ack, res->sfx,
                                              &res->k, &res->a.errors);
            res->w_ack = res->k.w_ack;
        } else {
            res->a.irq_writes_attempted++;
            res->a.power_cycle_required = 1;
            gbp_regwrite_irq_u16(t, "tag=ACK", res->a.base, pending, c->ack_value, &res->w_ack, &res->a.errors);
            if (res->w_ack.completed) res->a.irq_writes_completed++;
        }
        c->ack_completed = (uint8_t)(res->w_ack.completed ? 1u : 0u);
        c->t_ack_after = res->w_ack.t_after;
        if (!res->w_ack.completed) {
            res->uncertain_writes++;
            finish(x, GBP_VIDEO_ACK_WRITE_FAILED, "ack_write_failed", "S4_ack_failed", GBP_AVSEQ_END_EARLY_FAILURE);
            return 0;
        }
        res->acks++;
        if (verify) {
            const struct gbp_initirqa_snapshot *ps = &res->k.postack;
            c->relatch_postack = (uint8_t)(bit13(ps->intsr) ? 1u : 0u);
            log_service_snapshot(x, "POSTACKAV", n, ps);
            if (!common_checks(x, ps, "POSTACK", n, &st, &why)) { finish(x, st, why, "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            if ((ps->irq_gbi & cfg->odd_mask) != 0 || (ps->irq_gbi & cfg->bit15_mask) == 0 || (ps->irq_gbi & cfg->high_mask) != 0) {
                snprintf(res->reason_buf, sizeof res->reason_buf, "postack_shape_cycle_%u", n);
                finish(x, GBP_VIDEO_ANOMALY_POSTACK_SHAPE, res->reason_buf, "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0;
            }
            if (res->k.main_pi_w1c) { c->main_w1c = 1; res->main_w1c++; if (res->k.main_w1c_rc != GBP_OK) restore_fail(res, "main_pi_w1c_failed"); }
            c->intsr_postack = ps->intsr; c->intmr_postack = ps->intmr;
            if (res->k.main_pi_w1c) { c->intsr_after_main_w1c = res->k.main_w1c_intsr_after; c->pi_sticky = (uint8_t)(res->k.main_w1c_sticky ? 1u : 0u); }
            else c->intsr_after_main_w1c = ps->pi2_ok ? ps->intsr2 : ps->intsr;
            {
                uint32_t pi_intmr = res->k.main_pi_w1c ? res->k.main_w1c_intmr_after : (ps->pi2_ok ? ps->intmr2 : ps->intmr);
                ringlog_printf(log, "PICLEAN n=%u intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u main_w1c=%u sticky=%u", n,
                               (unsigned long)c->intsr_after_main_w1c, (unsigned long)pi_intmr, bit13(c->intsr_after_main_w1c), bit13(pi_intmr),
                               (unsigned)c->main_w1c, (unsigned)c->pi_sticky);
                if (bit13(pi_intmr)) { finish(x, GBP_VIDEO_ANOMALY_MASK_FAILURE, "intmr13_set_PICLEAN", "S3_pi_sticky", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            }
            if (bit13(c->intsr_after_main_w1c)) {
                c->pi_sticky = 1;
                finish(x, GBP_VIDEO_ANOMALY_PI_STICKY, "pi_sticky_after_ack", "S3_pi_sticky", GBP_AVSEQ_END_EARLY_FAILURE); return 0;
            }
        } else {
            uint32_t intsr = 0, intmr = 0;
            if (t->read_pi(t->ctx, &intsr, &intmr) != GBP_OK) { res->a.errors++; finish(x, GBP_VIDEO_ABORT_TRANSPORT, "piclean_read_failed", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            c->intsr_postack = intsr; c->intmr_postack = intmr;
            c->intsr_after_main_w1c = intsr;
            if (bit13(intmr)) { finish(x, GBP_VIDEO_ANOMALY_MASK_FAILURE, "intmr13_set_PICLEAN", "S3_pi_sticky", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            if (bit13(intsr)) {
                c->relatch_postack = 1;
                if (!t->write_intsr) { c->pi_sticky = 1; finish(x, GBP_VIDEO_ANOMALY_PI_STICKY, "pi_set_after_ack_no_w1c_op", "S3_pi_sticky", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
                c->main_w1c = 1;
                res->main_w1c++;
                if (t->write_intsr(t->ctx, GBP_PI_HSP_BIT) != GBP_OK) { res->a.errors++; restore_fail(res, "main_pi_w1c_failed"); }
                if (t->read_pi(t->ctx, &intsr, &intmr) != GBP_OK) { res->a.errors++; finish(x, GBP_VIDEO_ABORT_TRANSPORT, "piclean_reread_failed", "S3_service_aborted", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
                c->intsr_after_main_w1c = intsr;
                if (bit13(intsr)) { c->pi_sticky = 1; finish(x, GBP_VIDEO_ANOMALY_PI_STICKY, "pi_sticky_after_ack", "S3_pi_sticky", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
                if (bit13(intmr)) { finish(x, GBP_VIDEO_ANOMALY_MASK_FAILURE, "intmr13_set_PICLEAN", "S3_pi_sticky", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            }
        }

        /* ---- REARM: IRQ := 0x0000 (GBI's end-of-pass write), CPU masked, PI clean verified above ---- */
        c->t_rearm = now(t);
        if (verify) ringlog_printf(log, "REARM n=%u t_rearm=%lu before=%04x value=0000 layout=gbi-u16-replicated after=drain_ack_pi_clean", n,
                                   (unsigned long)c->t_rearm, (unsigned)(verify ? res->k.postack.irq_gbi : c->ack_value));
        c->rearm_attempted = 1;
        res->a.irq_writes_attempted++;
        res->a.power_cycle_required = 1;
        gbp_regwrite_irq_u16(t, verify ? res->tag_rearm : "tag=REARM", res->a.base, verify ? res->k.postack.irq_gbi : c->ack_value, 0x0000, &res->w_rearm, &res->a.errors);
        if (res->w_rearm.completed) { c->rearm_completed = 1; res->a.irq_writes_completed++; res->rearms++; }
        c->t_rearm_after = res->w_rearm.t_after;
        if (verify) gbp_regwrite_log(log, &res->w_rearm);
        if (!res->w_rearm.completed) {
            res->uncertain_writes++;
            finish(x, GBP_VIDEO_REARM_WRITE_FAILED, "rearm_write_failed", "S4_rearm_failed", GBP_AVSEQ_END_EARLY_FAILURE);
            return 0;
        }
        t_ref = c->t_rearm_after;

        /* ---- REARMPOST (verify cycles): the state right after the re-arm, classified as GBP-AV-SERVICE-001 ---- */
        if (verify) {
            const struct gbp_initirqa_snapshot *s;
            uint16_t src, av, unexpected;
            unsigned latched, latched_first;
            int shape_ok, reads_ok, control_ok, masked, agree, outcome;
            gbp_initirqa_snapshot_take(t, &res->a, &res->rearmpost, res->id_rearmpost, 0, 1);
            gbp_initirqa_snapshot_log(log, &res->a, &res->rearmpost);
            s = &res->rearmpost;
            src = (uint16_t)(s->irq_gbi & cfg->src_mask);
            av = (uint16_t)(s->irq_gbi & cfg->av_mask);
            unexpected = (uint16_t)(src & (uint16_t)~cfg->av_mask);
            latched = s->pi2_ok ? bit13(s->intsr2) : bit13(s->intsr);
            latched_first = bit13(s->intsr);
            shape_ok = ((s->irq_gbi & cfg->odd_mask) == 0 && (s->irq_gbi & cfg->bit15_mask) == 0 && (s->irq_gbi & cfg->high_mask) == 0) ? 1 : 0;
            reads_ok = (s->pi_ok && s->control_rc == GBP_OK && s->irq_rc == GBP_OK) ? 1 : 0;
            control_ok = (s->control_rc == GBP_OK && s->control_vote == res->a.control_exp && s->control_vote == s->control_b1f) ? 1 : 0;
            masked = (!bit13(s->intmr) && !(s->pi2_ok && bit13(s->intmr2))) ? 1 : 0;
            agree = (s->irq_disc == s->irq_gbi) ? 1 : 0;
            note_control(res, s);
            if (!reads_ok) outcome = 0;
            else if (!shape_ok) outcome = 5;
            else if (unexpected) outcome = 4;
            else if (src == 0 && !latched && !latched_first) outcome = 1;
            else if (av && latched) outcome = 2;
            else if (av && !latched && !latched_first) outcome = 3;
            else outcome = 6;
            ringlog_printf(log, "REARMPOST n=%u t=%lu since_rearm=%lu intsr13=%u,%u intmr13=%u,%u control=%02x irq=%04x/%04x src=%04x av=%04x unexpected=%04x odd=%04x bit15=%u high=%04x outcome=%s",
                           n, (unsigned long)s->ticks, (unsigned long)(uint32_t)(s->ticks - c->t_rearm), bit13(s->intsr), bit13(s->intsr2),
                           bit13(s->intmr), bit13(s->intmr2), (unsigned)s->control_vote, (unsigned)s->irq_gbi, (unsigned)s->irq_disc,
                           (unsigned)src, (unsigned)av, (unsigned)unexpected, (unsigned)(s->irq_gbi & cfg->odd_mask),
                           (unsigned)((s->irq_gbi & cfg->bit15_mask) ? 1u : 0u), (unsigned)(s->irq_gbi & cfg->high_mask),
                           outcome == 1 ? "A_quiet" : outcome == 2 ? "B_latched" : outcome == 3 ? "C_source_before_pi" : outcome == 4 ? "D_unexpected" :
                           outcome == 5 ? "E_invalid" : outcome == 6 ? "F_inconsistent" : "-");
            if (!reads_ok) { finish(x, GBP_VIDEO_ABORT_TRANSPORT, "rearmpost_read_failed", "S4C_rearmpost_invalid", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            if (!agree) { finish(x, GBP_VIDEO_ABORT_READ_INCONSISTENT, "rearmpost_semantic_disagree", "S4C_rearmpost_invalid", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            if (!control_ok) { finish(x, GBP_VIDEO_ANOMALY_CONTROL_CHANGED, "control_changed_REARMPOST", "S4C_rearmpost_invalid", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            if (!masked) { finish(x, GBP_VIDEO_ANOMALY_MASK_FAILURE, "intmr13_set_REARMPOST", "S4C_rearmpost_invalid", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            if (outcome == 5) { finish(x, GBP_VIDEO_ANOMALY_REARM_STATE, "rearm_state_invalid", "S4C_rearmpost_invalid", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            if (outcome == 4) {
                res->unexpected = unexpected; res->unexpected_site = "REARMPOST"; res->unexpected_cycle = n;
                finish(x, GBP_VIDEO_ANOMALY_UNEXPECTED_SOURCE, "unexpected_source_REARMPOST", "S4C_rearmpost_invalid", GBP_AVSEQ_END_EARLY_FAILURE); return 0;
            }
            if (outcome == 6) { finish(x, GBP_VIDEO_ANOMALY_REARM_STATE, "rearmpost_pi_without_source", "S4C_rearmpost_invalid", GBP_AVSEQ_END_EARLY_FAILURE); return 0; }
            c->next_pending = s->irq_gbi;
            t_ref = s->ticks;
            if (outcome == 2) {
                c->next_observed = 1; c->next_ended_by = GBP_AVSEQ_NEXT_CAUSE; c->t_next = s->ticks;
                c->intsr_next = s->pi2_ok ? s->intsr2 : s->intsr;
            }
        }

        /* ---- WAIT_NEXT: masked, read-only, min(T_NEXT_CAUSE, remaining budget); the cause stays latched ---- */
        if (!c->next_observed) wait_next(x, c, t_ref);
        if (verify) {
            ringlog_printf(log, "NEXT n=%u observed=%u ended_by=%s t_next=%lu since_rearm=%lu intsr=%08lx polls=%lu delivered=0", n, (unsigned)c->next_observed,
                           gbp_avseq_next_end_name(c->next_ended_by), (unsigned long)c->t_next, (unsigned long)(uint32_t)(c->t_next - c->t_rearm),
                           (unsigned long)c->intsr_next, (unsigned long)c->next_polls);
            gbp_avseq_log_cycle(log, c, xs.audio_addr, xs.video_addr);
            res->verify_cycles_done++;
        } else {
            res->lean_cycles++;
        }
        if (c->next_ended_by == GBP_AVSEQ_NEXT_CAUSE) { t_cause_next = c->t_next; continue; }
        if (c->next_ended_by == GBP_AVSEQ_NEXT_TIMEOUT) {
            c->end_reason = GBP_AVSEQ_END_NO_NEXT_CAUSE;
            finish(x, GBP_VIDEO_OBSERVATION_NO_NEXT_CAUSE, "no_next_cause_within_bound", "S5_capture_end", GBP_AVSEQ_END_NO_NEXT_CAUSE);
            goto completed;
        }
        /* the admission deadline arrived during the wait (or no budget was left): runtime cap, nothing fabricated */
        c->end_reason = GBP_AVSEQ_END_RUNTIME_CAP;
        res->next_cause_at_end = c->next_observed ? 1 : 0;
        res->refusal = "runtime_cap";
        res->refusals++;
        finish(x, GBP_VIDEO_OK_TARGET_NOT_REACHED_RUNTIME_CAP, "-", "S5_capture_end", GBP_AVSEQ_END_RUNTIME_CAP);
        goto completed;
    }

completed:
    {
        gbp_video_status st2 = res->status;
        if ((st2 == GBP_VIDEO_OK_SEQUENCE_CAPTURE || st2 == GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP || st2 == GBP_VIDEO_OK_TARGET_NOT_REACHED_RUNTIME_CAP) &&
            (res->pi_sticky_final || res->uncertain_writes || res->a.errors || !res->control_ok || !res->restore_ok)) {
            set_status(res, GBP_VIDEO_CAPTURE_COMPLETED_WITH_ERRORS,
                       res->pi_sticky_final ? "pi_sticky" : res->uncertain_writes ? "uncertain_write" : !res->restore_ok ? res->restore_reason :
                       !res->control_ok ? "control_changed" : "transport_errors");
            /* the VIDEO end record already went out with the ok status: append the re-classification explicitly */
            ringlog_printf(log, "VIDEO reclassified status=%s reason=%s", res->status_name, res->reason);
        }
    }
    return 0;
}

int gbp_video_summary(const struct gbp_video_result *res, char *dst, size_t cap)
{
    const struct gbp_initirqa_result *a = &res->a;
    const struct gbp_avseq_store *s = res->store;
    return snprintf(dst, cap,
                    "DONE status=%s class=%s reason=%s restore=%s restore_reason=%s teardown=%s verdict=%s det=%u/%u written=%d "
                    "irq_attempted=%u irq_completed=%u uncertain=%u service=%s service_reason=%s capture=%s deliveries=%u video=%u/%u audio=%u/%u audio_raw=%u "
                    "next_cause_at_end=%d boundaries_gbi=%u boundaries_disc=%u complete_gbi=%d complete_disc=%d reference_content=offline "
                    "cause=%d t_event=%lu handler=%d old=%s unmasks=%u lean=%u verify=%u t0=%lu deadline=%lu refusal=%s "
                    "unexpected=%04x site=%s isr_w1c=%u main_w1c=%u teardown_w1c=%u control_ok=%d pi_sticky_final=%d "
                    "control_restore_ok=%d irq_stop_write_ok=%d stop_post=%04x pi_cleanup=%d handler_restored=%d mask_ok=%d "
                    "arinfo_restore_ok=%d power_cycle_required=%d errors=%u transport_ok=%d",
                    res->status_name, res->status_class, res->reason ? res->reason : "-", res->restore_ok ? "ok" : "error",
                    res->restore_reason ? res->restore_reason : "-", res->teardown_variant ? res->teardown_variant : "-",
                    gbp_verdict_name(a->det.verdict), a->det.vote_ok, a->det.run, a->control_written,
                    a->irq_writes_attempted, a->irq_writes_completed, res->uncertain_writes,
                    res->service_ok ? "ok" : "failed", res->service_reason ? res->service_reason : "-", gbp_avseq_end_name(res->capture),
                    res->deliveries, res->video_completed, res->video_blocks, res->audio_completed, res->audio_drains, s ? gbp_avseq_audio_raw_count(s) : 0u,
                    res->next_cause_at_end, res->b_gbi.count, res->b_disc.count, res->b_gbi.complete_interval, res->b_disc.complete_interval,
                    a->intsr13_seen, (unsigned long)a->t_first_intsr13, res->h.handler_was_installed, old_handler_name(&res->h),
                    res->unmasks, res->lean_cycles, res->verify_cycles_done, (unsigned long)res->t0, (unsigned long)res->admission_deadline, res->refusal,
                    (unsigned)res->unexpected, res->unexpected_site ? res->unexpected_site : "-", res->isr_w1c, res->main_w1c, res->teardown_w1c,
                    res->control_ok, res->pi_sticky_final, a->control_restore_ok, a->irq_stop_write_ok, (unsigned)a->irq_stop_post.gbi,
                    a->pi_cleanup_performed, res->h.handler_restored, res->h.mask_ok, a->arinfo_restore_ok,
                    res->power_cycle_required, res->errors, res->transport_ok);
}

int gbp_video_dump_info(const struct gbp_video_result *res, uint32_t tb_hz, const char *test_id,
                        const char *build_id, const char *app, const char *commit, struct gbp_avseqdump_info *info)
{
    memset(info, 0, sizeof *info);
    info->version = (uint16_t)GBP_AVSEQDUMP_VERSION;
    if (res->service_ok) info->flags |= GBP_AVSEQDUMP_FLAG_SERVICE_OK;
    if (res->restore_ok) info->flags |= GBP_AVSEQDUMP_FLAG_RESTORE_OK;
    if (res->next_cause_at_end) info->flags |= GBP_AVSEQDUMP_FLAG_NEXT_CAUSE_AT_END;
    if (res->capture == GBP_AVSEQ_END_EARLY_FAILURE) info->flags |= GBP_AVSEQDUMP_FLAG_PARTIAL;
    if (res->stage_a_aborted) info->flags |= GBP_AVSEQDUMP_FLAG_STAGE_A_ABORTED;
    info->tb_hz = tb_hz;
    info->capture_result = (uint16_t)res->capture;
    info->status_code = (uint16_t)res->status;
    info->end_reason = (uint16_t)((res->store && res->store->cycles_n) ? res->store->cycles[res->store->cycles_n - 1u].end_reason : 0u);
    info->target_video_blocks = GBP_AVSEQ_TARGET_VIDEO_BLOCKS;
    info->max_deliveries = GBP_AVSEQ_MAX_DELIVERIES;
    info->t0 = res->t0;
    info->admission_deadline = res->admission_deadline;
    info->admission_budget_ticks = (uint32_t)(res->admission_deadline - res->t0);
    info->boundaries_gbi = res->b_gbi.count;
    info->boundaries_disc = res->b_disc.count;
    return gbp_avseqdump_set_identity(info, test_id, build_id, app, commit);
}
