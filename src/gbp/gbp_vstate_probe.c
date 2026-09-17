#include "gbp_vstate_probe.h"

#include <stdio.h>
#include <string.h>
#include "gbp_rawlog.h"

typedef char gbp_vstate_cycle_size_check[(sizeof(struct gbp_vstate_cycle) == GBP_VSTATE_CYC_REC) ? 1 : -1];

static unsigned bit13(uint32_t v) { return (v & GBP_PI_HSP_BIT) ? 1u : 0u; }
static uint32_t now32(const struct gbp_transport *t) { return t->ticks ? t->ticks(t->ctx) : 0u; }
static uint64_t now64(const struct gbp_transport *t) { return t->ticks64 ? t->ticks64(t->ctx) : 0u; }

static uint32_t ms_to_ticks(uint32_t tb_hz, uint32_t ms)
{
    return (uint32_t)(((uint64_t)tb_hz * ms) / 1000u);
}

void gbp_vstate_config_timebase(struct gbp_vstate_config *cfg, uint32_t tb_hz)
{
    gbp_initirqa_config_timebase(&cfg->a, tb_hz);
    cfg->t_delivery_ticks = ms_to_ticks(tb_hz, cfg->t_delivery_ms);
    cfg->t_next_cause_ticks = ms_to_ticks(tb_hz, cfg->t_next_cause_ms);
    cfg->min_valid_observation_ticks = gbp_time64_from_seconds(tb_hz, cfg->min_valid_observation_s);
    cfg->hard_wallclock_ticks = gbp_time64_from_seconds(tb_hz, cfg->hard_wallclock_s);
}

void gbp_vstate_config_default(struct gbp_vstate_config *cfg)
{
    memset(cfg, 0, sizeof *cfg);
    gbp_initirqa_config_default(&cfg->a);
    cfg->t_delivery_ms = GBP_VSTATE_T_DELIVERY_MS;
    cfg->t_next_cause_ms = GBP_VSTATE_T_NEXT_CAUSE_MS;
    cfg->max_deliveries = GBP_VSTATE_MAX_DELIVERIES;
    cfg->verify_cycles = GBP_VSTATE_VERIFY_CYCLES;
    cfg->min_valid_observation_s = GBP_VSTATE_MIN_VALID_OBSERVATION_SECONDS;
    cfg->hard_wallclock_s = GBP_VSTATE_HARD_WALLCLOCK_LIMIT_SECONDS;
    cfg->ack_or = 0x8000;
    cfg->src_mask = 0x0555;
    cfg->av_mask = 0x0500;
    cfg->audio_src = GBP_VSTATE_AUDIO_SRC;
    cfg->video_src = GBP_VSTATE_VIDEO_SRC;
    cfg->audio_index = GBP_VSTATE_AUDIO_INDEX;
    cfg->video_index = GBP_VSTATE_VIDEO_INDEX;
    cfg->audio_len = GBP_VSTATE_AUDIO_BLOCK_SIZE;
    cfg->video_len = GBP_VSTATE_VIDEO_BLOCK_SIZE;
    cfg->odd_mask = 0x0AAA;
    cfg->bit15_mask = 0x8000;
    cfg->high_mask = 0x7000;
    gbp_vstate_config_timebase(cfg, cfg->a.tb_hz);
}

const char *gbp_vstate_status_name(gbp_vstate_status s)
{
    switch (s) {
    case GBP_VSTATE_OK_STRUCTURED_CHANGE_OBSERVED: return "ok_structured_change_observed";
    case GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL: return "ok_no_change_nominal_interval";
    case GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE: return "ok_no_change_inconclusive";
    case GBP_VSTATE_OBSERVATION_NO_NEXT_CAUSE: return "observation_no_next_cause";
    case GBP_VSTATE_CAPTURE_COMPLETED_WITH_ERRORS: return "capture_completed_with_errors";
    case GBP_VSTATE_NO_INITIAL_CAUSE: return "no_initial_cause";
    case GBP_VSTATE_FIRST_DELIVERY_TIMEOUT: return "first_delivery_timeout";
    case GBP_VSTATE_ABORT_STAGE_A: return "abort_stage_a";
    case GBP_VSTATE_ABORT_HANDLER_INSTALL: return "abort_handler_install";
    case GBP_VSTATE_ABORT_PRE_UNMASK_STATE: return "abort_pre_unmask_state";
    case GBP_VSTATE_ABORT_UNMASK: return "abort_unmask";
    case GBP_VSTATE_ABORT_BULK_UNAVAILABLE: return "abort_bulk_unavailable";
    case GBP_VSTATE_ABORT_RESET_UNAVAILABLE: return "abort_reset_unavailable";
    case GBP_VSTATE_ABORT_TIME64_UNAVAILABLE: return "abort_time64_unavailable";
    case GBP_VSTATE_ABORT_STORE_UNAVAILABLE: return "abort_store_unavailable";
    case GBP_VSTATE_ABORT_PRESVC_STATE: return "abort_presvc_state";
    case GBP_VSTATE_ABORT_READ_INCONSISTENT: return "abort_read_inconsistent";
    case GBP_VSTATE_ABORT_TRANSPORT: return "abort_transport";
    case GBP_VSTATE_ABORT_CAPACITY: return "abort_capacity";
    case GBP_VSTATE_ACK_WRITE_FAILED: return "ack_write_failed";
    case GBP_VSTATE_REARM_WRITE_FAILED: return "rearm_write_failed";
    case GBP_VSTATE_AUDIO_DMA_BUSY: return "audio_dma_busy";
    case GBP_VSTATE_AUDIO_DMA_TIMEOUT: return "audio_dma_timeout";
    case GBP_VSTATE_AUDIO_DMA_ERROR: return "audio_dma_error";
    case GBP_VSTATE_VIDEO_DMA_BUSY: return "video_dma_busy";
    case GBP_VSTATE_VIDEO_DMA_TIMEOUT: return "video_dma_timeout";
    case GBP_VSTATE_VIDEO_DMA_ERROR: return "video_dma_error";
    case GBP_VSTATE_ANOMALY_REENTRY: return "anomaly_reentry";
    case GBP_VSTATE_ANOMALY_MISSED_ENTRY: return "anomaly_missed_entry";
    case GBP_VSTATE_ANOMALY_ISR_STATE: return "anomaly_isr_state";
    case GBP_VSTATE_ANOMALY_RECORD_NOT_CLEAR: return "anomaly_record_not_clear";
    case GBP_VSTATE_ANOMALY_MASK_FAILURE: return "anomaly_mask_failure";
    case GBP_VSTATE_ANOMALY_UNEXPECTED_SOURCE: return "anomaly_unexpected_source";
    case GBP_VSTATE_ANOMALY_CAUSE_WITHOUT_SOURCE: return "anomaly_cause_without_source";
    case GBP_VSTATE_ANOMALY_CONTROL_CHANGED: return "anomaly_control_changed";
    case GBP_VSTATE_ANOMALY_POSTACK_SHAPE: return "anomaly_postack_shape";
    case GBP_VSTATE_ANOMALY_PI_STICKY: return "anomaly_pi_sticky";
    case GBP_VSTATE_ANOMALY_REARM_STATE: return "anomaly_rearm_state";
    default: return "?";
    }
}

const char *gbp_vstate_status_class(gbp_vstate_status s)
{
    switch (s) {
    case GBP_VSTATE_OK_STRUCTURED_CHANGE_OBSERVED:
    case GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL:
    case GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE: return "ok";
    case GBP_VSTATE_OBSERVATION_NO_NEXT_CAUSE:
    case GBP_VSTATE_NO_INITIAL_CAUSE:
    case GBP_VSTATE_FIRST_DELIVERY_TIMEOUT: return "observation";
    case GBP_VSTATE_CAPTURE_COMPLETED_WITH_ERRORS: return "errors";
    case GBP_VSTATE_ABORT_STAGE_A:
    case GBP_VSTATE_ABORT_HANDLER_INSTALL:
    case GBP_VSTATE_ABORT_PRE_UNMASK_STATE:
    case GBP_VSTATE_ABORT_UNMASK:
    case GBP_VSTATE_ABORT_BULK_UNAVAILABLE:
    case GBP_VSTATE_ABORT_RESET_UNAVAILABLE:
    case GBP_VSTATE_ABORT_TIME64_UNAVAILABLE:
    case GBP_VSTATE_ABORT_STORE_UNAVAILABLE:
    case GBP_VSTATE_ABORT_PRESVC_STATE:
    case GBP_VSTATE_ABORT_READ_INCONSISTENT:
    case GBP_VSTATE_ABORT_CAPACITY: return "abort";
    case GBP_VSTATE_ABORT_TRANSPORT:
    case GBP_VSTATE_ACK_WRITE_FAILED:
    case GBP_VSTATE_REARM_WRITE_FAILED: return "transport";
    case GBP_VSTATE_AUDIO_DMA_BUSY:
    case GBP_VSTATE_AUDIO_DMA_TIMEOUT:
    case GBP_VSTATE_AUDIO_DMA_ERROR:
    case GBP_VSTATE_VIDEO_DMA_BUSY:
    case GBP_VSTATE_VIDEO_DMA_TIMEOUT:
    case GBP_VSTATE_VIDEO_DMA_ERROR: return "dma";
    default: return "anomaly";
    }
}

const char *gbp_vstate_stop_name(int stop)
{
    switch (stop) {
    case GBP_VSTATE_STOP_NOMINAL_NEGATIVE: return "nominal_negative";
    case GBP_VSTATE_STOP_FRAME_STORE_CAP: return "frame_store_cap";
    case GBP_VSTATE_STOP_EVENT_STORE_CAP: return "event_store_cap";
    case GBP_VSTATE_STOP_SAFETY_BUDGET: return "safety_budget";
    case GBP_VSTATE_STOP_DELIVERY_CAP: return "delivery_cap";
    case GBP_VSTATE_STOP_NO_NEXT_CAUSE: return "no_next_cause";
    case GBP_VSTATE_STOP_FAILURE: return "failure";
    default: return "none";
    }
}

/*
 * The main status, exactly as §20 defines it, from the matrix and nothing
 * else. The classification keys on valid_observation_elapsed, NEVER on which
 * cap fired: a safety stop before the target is `ok_no_change_inconclusive`,
 * never `nominal_negative`.
 */
gbp_vstate_status gbp_vstate_main_status(const struct gbp_vstate_result *res)
{
    const struct gbp_vstate *st = res->st;
    if (!res->service_ok) return res->status;
    if (st && st->episode_count > 0u) return GBP_VSTATE_OK_STRUCTURED_CHANGE_OBSERVED;
    if (res->stop == GBP_VSTATE_STOP_NOMINAL_NEGATIVE) return GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL;
    if (res->stop == GBP_VSTATE_STOP_NO_NEXT_CAUSE) return GBP_VSTATE_OBSERVATION_NO_NEXT_CAUSE;
    return GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE;
}

/* ---- run context ---------------------------------------------------- */
struct run_ctx {
    const struct gbp_transport *t;
    struct ringlog *log;
    const struct gbp_vstate_config *cfg;
    struct gbp_vstate_result *res;
    struct gbp_vstate *st;
    uint32_t audio_addr, video_addr, irq_addr;
    int teardown_done;
};

static void restore_fail(struct gbp_vstate_result *res, const char *why)
{
    if (res->restore_ok) res->restore_reason = why;
    res->restore_ok = 0;
}

static const char *old_handler_name(const struct gbp_irq_handler_state *h)
{
    return h->old_handler_null == 1 ? "null" : h->old_handler_null == 0 ? "nonnull" : "?";
}

static void note_control(struct gbp_vstate_result *res, const struct gbp_initirqa_snapshot *s)
{
    if (s->control_rc == GBP_OK && (s->control_vote != res->a.control_exp || s->control_vote != s->control_b1f)) res->control_ok = 0;
}

static void set_status(struct gbp_vstate_result *res, gbp_vstate_status st, const char *reason)
{
    res->status = st;
    res->status_name = gbp_vstate_status_name(st);
    res->status_class = gbp_vstate_status_class(st);
    res->reason = reason;
}

static void service_failed(struct gbp_vstate_result *res, const char *reason)
{
    if (res->service_ok) res->service_reason = reason;
    res->service_ok = 0;
}

/* Every u32 counter that accumulates over the run goes through this: it ends
 * the run rather than wrapping (§14). */
static void bump(struct gbp_vstate_result *res, uint32_t *c)
{
    if (*c == 0xFFFFFFFFu) { res->counter_overflow++; return; }
    (*c)++;
}

/* ---- bounded cycle records ------------------------------------------ */
static void cycle_record(struct run_ctx *x, const struct gbp_vstate_cycle *c, unsigned kind)
{
    struct gbp_vstate_result *res = x->res;
    const struct gbp_vstate_config *cfg = x->cfg;
    struct gbp_vstate_cycle *dst = 0;
    switch (kind) {
    case GBP_VSTATE_CYC_KIND_FIRST:
        if (cfg->cyc_first && res->cyc_first_n < GBP_VSTATE_CYC_FIRST) dst = &cfg->cyc_first[res->cyc_first_n++];
        break;
    case GBP_VSTATE_CYC_KIND_LAST:
        /* a true ring: the last eight cycles of a run of hundreds of thousands */
        if (cfg->cyc_last) {
            dst = &cfg->cyc_last[res->cyc_last_next];
            res->cyc_last_next = (res->cyc_last_next + 1u) % GBP_VSTATE_CYC_LAST;
            if (res->cyc_last_n < GBP_VSTATE_CYC_LAST) res->cyc_last_n++;
        }
        break;
    case GBP_VSTATE_CYC_KIND_ANOMALY:
        if (cfg->cyc_anomaly && res->cyc_anomaly_n < GBP_VSTATE_CYC_ANOMALY) dst = &cfg->cyc_anomaly[res->cyc_anomaly_n++];
        break;
    default:
        if (cfg->cyc_episode && res->cyc_episode_n < GBP_VSTATE_CYC_EPISODE) dst = &cfg->cyc_episode[res->cyc_episode_n++];
        break;
    }
    if (!dst) return;
    *dst = *c;
    dst->kind = (uint16_t)kind;
}

/* ---- teardown -------------------------------------------------------- */
static void teardown_hook(void *arg)
{
    struct run_ctx *x = (struct run_ctx *)arg;
    struct gbp_vstate_result *res = x->res;
    int engaged = (res->h.handler_was_installed || res->unmasks) ? 1 : 0;
    const char *fail = gbp_irq_service_teardown_hook(x->t, x->log, &res->h, engaged, &res->a.errors);
    if (fail) restore_fail(res, fail);
}

/*
 * THE HARDWARE TEARDOWN, AND NOTHING ELSE. No summary, no checksum, no
 * boundary list, no textual record of the captured data runs before it.
 * GBP-VIDEO-001 summarised first and put 64.99 ms between the last
 * observation and the CONTROL restore; that ordering is corrected here.
 * The one line written before the writes is a fixed-size status line that
 * reads no store.
 */
static void teardown_hardware(struct run_ctx *x, const char *variant)
{
    struct gbp_vstate_result *res = x->res;
    struct gbp_initirqa_teardown_opts opts;
    if (x->teardown_done) return;
    x->teardown_done = 1;
    res->teardown_variant = variant;
    res->t_teardown_begin = now64(x->t);
    gbp_vstate_event(x->st, res->t_teardown_begin, GBP_VSTATE_EV_TEARDOWN_BEGIN, res->deliveries, (uint32_t)res->stop, 0u, 0u);
    /* NOTHING is formatted here. GBP-VIDEO-001 put 64.99 ms of summarising between its last
     * observation and the CONTROL restore; this probe adds not even one log line. Between the stop
     * decision and the first teardown write there are only scalar assignments, two time-base reads
     * and two fixed-size event records. The status line moved below, after the hardware is safe. */
    opts.pi_cleanup_allowed = 1;
    opts.pre_arinfo_hook = teardown_hook;
    opts.hook_ctx = x;
    opts.pi_policy = res->unmasks ? "unmasked_per_cycle" : "never_unmasked";
    gbp_initirqa_teardown(x->t, x->log, &x->cfg->a, &res->a, &opts);
    if (res->a.pi_cleanup_performed) res->teardown_w1c = 1;
    res->pi_sticky_final = bit13(res->a.cleanup_intsr_after) ? 1 : 0;
    if (!res->a.restore_ok && res->restore_ok) restore_fail(res, res->a.restore_reason);
    res->t_teardown_end = now64(x->t);
    gbp_vstate_event(x->st, res->t_teardown_end, GBP_VSTATE_EV_TEARDOWN_END, res->a.pi_cleanup_performed ? 1u : 0u,
                     res->restore_ok ? 1u : 0u, 0u, 0u);
    ringlog_printf(x->log, "TEARDOWNVSTATE variant=%s stop=%s deliveries=%lu video=%lu acks=%lu rearms=%lu unmasks=%lu next_cause_at_end=%d",
                   variant, gbp_vstate_stop_name(res->stop), (unsigned long)res->deliveries, (unsigned long)res->video_completed,
                   (unsigned long)res->acks, (unsigned long)res->rearms, (unsigned long)res->unmasks, res->next_cause_at_end);
}

static unsigned count_uncertain_stage(const struct gbp_vstate_result *res)
{
    const struct gbp_regwrite_result *w[5];
    unsigned i, n = 0;
    w[0] = &res->a.w_ctl_exp; w[1] = &res->a.w_a1; w[2] = &res->a.w_a2; w[3] = &res->a.w_stop; w[4] = &res->a.w_ctl_restore;
    for (i = 0; i < 5; i++) if (w[i]->attempted && !w[i]->completed) n++;
    return n;
}

/* ---- reporting, only ever AFTER the teardown ------------------------- */
static void log_cycles(struct ringlog *log, const char *tag, const struct gbp_vstate_cycle *c, uint32_t n)
{
    uint32_t i;
    for (i = 0; i < n; i++) {
        const struct gbp_vstate_cycle *v = &c[i];
        ringlog_printf(log, "%s i=%lu n=%lu f=%lu blk=%lu pend=%04x ack=%04x a=%u/%u v=%u/%u w1c=%u isr=%u/%u next=%u lat=%lu aw=%lu vw=%lu sig=%lu",
                       tag, (unsigned long)i, (unsigned long)v->index, (unsigned long)v->frame_index,
                       (unsigned long)v->block_in_frame, (unsigned)v->pending, (unsigned)v->ack_value,
                       v->audio_selected, v->audio_completed, v->video_selected, v->video_completed,
                       v->main_w1c, v->isr_count, v->isr_reentry, v->next_observed,
                       (unsigned long)v->latency_ticks, (unsigned long)v->audio_wait, (unsigned long)v->video_wait,
                       (unsigned long)v->sig_ticks);
        ringlog_printf(log, "%sT i=%lu cause=%llx unmask=%llx entry=%llx read=%llx ack=%llx rearm=%llx next=%llx pi=%08lx/%08lx/%08lx/%08lx rc=%08lx",
                       tag, (unsigned long)i, (unsigned long long)v->t_cause, (unsigned long long)v->t_unmask,
                       (unsigned long long)v->t_entry, (unsigned long long)v->t_read, (unsigned long long)v->t_ack,
                       (unsigned long long)v->t_rearm, (unsigned long long)v->t_next,
                       (unsigned long)v->intsr_entry, (unsigned long)v->intsr_after_w1c,
                       (unsigned long)v->intsr_postack, (unsigned long)v->intsr_next, (unsigned long)v->rc);
    }
}

void gbp_vstate_report(struct ringlog *log, const struct gbp_vstate_config *cfg, struct gbp_vstate_result *res)
{
    struct gbp_vstate *st = res->st;
    uint32_t tb = cfg->a.tb_hz;
    unsigned i;

    res->uncertain_writes += count_uncertain_stage(res);
    res->errors = res->a.errors;
    res->transport_ok = (res->errors == 0u) ? 1 : 0;
    res->power_cycle_required = res->a.power_cycle_required;
    res->tb_hz = tb;
    if (st) {
        res->valid_observation_elapsed = st->valid_observation_elapsed;
        if (st->baseline_valid) res->baseline_elapsed = gbp_time64_delta(res->t_capture_start, st->t_baseline_valid);
    }
    /* A derived interval is only real when BOTH of its endpoints are. The capture clock starts at
     * the first admitted unmask; on a path that never reached one, t_capture_start is unset and
     * the elapsed value is 0 — never the absolute time base read back as a duration. The safety
     * epoch is always a real reading (the stage's start when no CONTROL write was made, with
     * epoch_ok = -1 saying so), so its interval needs no such guard. */
    res->capture_elapsed = res->t_capture_start ? gbp_time64_delta(res->t_capture_start, res->t_stop) : 0u;
    res->safety_elapsed = gbp_time64_delta(res->t_control_transform, res->t_stop);

    ringlog_printf(log, "VSTATE end status=%s class=%s reason=%s stop=%s restore=%s restore_reason=%s teardown=%s power_cycle_required=%d errors=%lu transport_ok=%d",
                   res->status_name, res->status_class, res->reason, gbp_vstate_stop_name(res->stop),
                   res->restore_ok ? "ok" : "error", res->restore_reason, res->teardown_variant ? res->teardown_variant : "-",
                   res->power_cycle_required, (unsigned long)res->errors, res->transport_ok);
    gbp_initirqa_log_summary_records(log, &res->a);

    ringlog_printf(log, "CLOCKS tb_hz=%lu epoch=%llx capture_start=%llx stop=%llx capture_elapsed=%llx baseline_elapsed=%llx valid=%llx valid_at_target=%llx safety=%llx",
                   (unsigned long)tb, (unsigned long long)res->t_control_transform, (unsigned long long)res->t_capture_start,
                   (unsigned long long)res->t_stop, (unsigned long long)res->capture_elapsed,
                   (unsigned long long)res->baseline_elapsed, (unsigned long long)res->valid_observation_elapsed,
                   (unsigned long long)res->valid_observation_at_target, (unsigned long long)res->safety_elapsed);
    ringlog_printf(log, "CLOCKSEC capture_s=%lu.%03lu baseline_s=%lu.%03lu valid_s=%lu.%03lu safety_s=%lu.%03lu target_s=%lu limit_s=%lu",
                   (unsigned long)gbp_time64_seconds(tb, res->capture_elapsed), (unsigned long)gbp_time64_millis_part(tb, res->capture_elapsed),
                   (unsigned long)gbp_time64_seconds(tb, res->baseline_elapsed), (unsigned long)gbp_time64_millis_part(tb, res->baseline_elapsed),
                   (unsigned long)gbp_time64_seconds(tb, res->valid_observation_elapsed), (unsigned long)gbp_time64_millis_part(tb, res->valid_observation_elapsed),
                   (unsigned long)gbp_time64_seconds(tb, res->safety_elapsed), (unsigned long)gbp_time64_millis_part(tb, res->safety_elapsed),
                   (unsigned long)cfg->min_valid_observation_s, (unsigned long)cfg->hard_wallclock_s);

    if (st) {
        ringlog_printf(log, "FRAMECAP frames=%lu complete=%lu incomplete=%lu resync=%lu anomaly_frame=%lu anomaly_region=%lu counted=%lu blocks=%llu pre_boundary=%lu store_full=%d",
                       (unsigned long)st->frames_n, (unsigned long)st->frames_complete, (unsigned long)st->frames_incomplete,
                       (unsigned long)st->resync_frames, (unsigned long)st->anomalies_frame, (unsigned long)st->anomalies_region,
                       (unsigned long)st->frames_counted, (unsigned long long)st->blocks_total,
                       (unsigned long)st->blocks_before_first_boundary, st->frame_store_full);
        ringlog_printf(log, "PREDICATES boundaries_disc=%lu boundaries_gbi=%lu disagreements=%lu first_frame=%lu first_block=%lu first4=%02x%02x%02x%02x segmentation=disc",
                       (unsigned long)st->boundaries_disc, (unsigned long)st->boundaries_gbi, (unsigned long)st->disagreements_total,
                       (unsigned long)st->disagreement_first_frame, (unsigned long)st->disagreement_first_block,
                       st->disagreement_first4[0], st->disagreement_first4[1], st->disagreement_first4[2], st->disagreement_first4[3]);
        {
            char buf[224];
            size_t p = 0;
            int wr;
            for (i = 0; i <= GBP_VSTATE_FRAME_MAX_BLOCKS + 1u && p + 12u < sizeof buf; i++) {
                if (!st->interval_hist[i]) continue;
                wr = snprintf(buf + p, sizeof buf - p, "%s%u:%lu", p ? "," : "", i, (unsigned long)st->interval_hist[i]);
                if (wr <= 0) break;
                p += (size_t)wr;
            }
            if (!p) { buf[0] = '-'; buf[1] = 0; }
            ringlog_printf(log, "INTERVALS %s  (index 49 = 48 blocks with no boundary; 40 is never assumed)", buf);
        }
        ringlog_printf(log, "BASELINE valid=%d frames_seen=%lu frame_index=%lu t_valid=%llx sig0=%08lx sig39=%08lx reference_updates=%lu early_candidates=%lu",
                       st->baseline_valid, (unsigned long)st->baseline_frames_seen, (unsigned long)st->baseline_frame_index,
                       (unsigned long long)st->t_baseline_valid, (unsigned long)st->original_baseline_sig[0],
                       (unsigned long)st->original_baseline_sig[GBP_VSTATE_FRAME_SIGS - 1u],
                       (unsigned long)st->reference_updates, (unsigned long)st->early_candidates);
        ringlog_printf(log, "STRUCTURED status=%s episodes=%lu stable=%lu unstable=%lu not_preserved=%lu store_full=%d descriptors=%lu raw_slots=%lu tail_frames=%lu tail_ticks=%llx tail_truncated=%d",
                       st->episode_count ? "observed" : "not_observed", (unsigned long)st->episode_count,
                       (unsigned long)st->stable_episodes, (unsigned long)st->unstable_episodes,
                       (unsigned long)st->episodes_not_preserved, st->episode_store_full, (unsigned long)st->episodes_n,
                       (unsigned long)st->episode_raw_used, (unsigned long)st->tail_frames,
                       (unsigned long long)st->tail_ticks, st->tail_truncated_by_cap);
        for (i = 0; i < st->episodes_n; i++) {
            const struct gbp_vstate_episode *ep = &st->episodes[i];
            ringlog_printf(log, "EPISODE i=%lu idx=%08lx state=%s flags=%04lx frames=%lu stable_count=%lu open_frame=%lu close_frame=%lu t_open=%llx t_close=%llx raw=%lu/%lu sig0=%08lx",
                           (unsigned long)i, (unsigned long)ep->index, gbp_vstate_episode_state_name(ep->state),
                           (unsigned long)ep->flags, (unsigned long)ep->frames, (unsigned long)ep->stable_count,
                           (unsigned long)ep->open_frame, (unsigned long)ep->close_frame,
                           (unsigned long long)ep->t_open, (unsigned long long)ep->t_close,
                           (unsigned long)ep->raw_frames, (unsigned long)GBP_VSTATE_EPISODE_RAW_SLOTS,
                           (unsigned long)ep->final_sig[0]);
        }
        ringlog_printf(log, "AUDIOAGG selected=%lu attempted=%lu completed=%lu failures=%lu bytes=%llu raw_kept=%u first_valid=%d last_valid=%d",
                       (unsigned long)st->audio.selected, (unsigned long)st->audio.attempted, (unsigned long)st->audio.completed,
                       (unsigned long)st->audio.failures, (unsigned long long)st->audio.bytes,
                       gbp_vstate_audio_raw_count(st), st->audio.first_valid, st->audio.last_valid);
        {
            int ex_med = 0, ex_p95 = 0;
            uint32_t w_med = 0, w_p95 = 0;
            uint32_t med = gbp_vsig_cost_quantile(&st->cost, 500u, &ex_med, &w_med);
            uint32_t p95 = gbp_vsig_cost_quantile(&st->cost, 950u, &ex_p95, &w_p95);
            ringlog_printf(log, "SIGCOST samples=%llu min=%lu median=%lu(exact=%d,w=%lu) p95=%lu(exact=%d,w=%lu) max=%lu mean=%lu overflow=%lu threshold=none",
                           (unsigned long long)st->cost.count, (unsigned long)(st->cost.count ? st->cost.min : 0u),
                           (unsigned long)med, ex_med, (unsigned long)w_med, (unsigned long)p95, ex_p95, (unsigned long)w_p95,
                           (unsigned long)st->cost.max, (unsigned long)gbp_vsig_cost_mean(&st->cost),
                           (unsigned long)st->cost.overflow);
        }
        /* the events: sequence numbers define the order, and a run that filled the store says so */
        {
            uint32_t shown = 0, head = st->events_n, tail_from = 0;
            if (head > 128u) head = 128u;
            if (st->events_n > 192u) tail_from = st->events_n - 64u;
            for (i = 0; i < head; i++) {
                const struct gbp_vstate_event *e = &st->events[i];
                ringlog_printf(log, "EV seq=%lu t=%llx type=%s f=%lu ep=%08lx a=%lu b=%lu c=%08lx d=%lu",
                               (unsigned long)e->seq, (unsigned long long)e->t, gbp_vstate_event_name(e->type),
                               (unsigned long)e->frame, (unsigned long)e->episode, (unsigned long)e->a,
                               (unsigned long)e->b, (unsigned long)e->c, (unsigned long)e->d);
                shown++;
            }
            if (tail_from) {
                ringlog_printf(log, "EVGAP omitted=%lu (all of them are in the sidecar)", (unsigned long)(tail_from - head));
                for (i = tail_from; i < st->events_n; i++) {
                    const struct gbp_vstate_event *e = &st->events[i];
                    ringlog_printf(log, "EV seq=%lu t=%llx type=%s f=%lu ep=%08lx a=%lu b=%lu c=%08lx d=%lu",
                                   (unsigned long)e->seq, (unsigned long long)e->t, gbp_vstate_event_name(e->type),
                                   (unsigned long)e->frame, (unsigned long)e->episode, (unsigned long)e->a,
                                   (unsigned long)e->b, (unsigned long)e->c, (unsigned long)e->d);
                    shown++;
                }
            }
            ringlog_printf(log, "EVENTS n=%lu shown=%lu dropped=%lu store_full=%d seq_last=%lu",
                           (unsigned long)st->events_n, (unsigned long)shown, (unsigned long)st->events_dropped,
                           st->event_store_full, (unsigned long)st->event_seq);
        }
    }
    if (st && st->diag.valid) {
        /* AFTER the teardown, never before: the bytes come from the preserved record, never from
         * a reconstruction, and the offline tool (tools/vstate.py diag) explains them. */
        char hex[GBP_BLOCK_SIZE * 2 + 1];
        ringlog_hex(hex, sizeof hex, st->diag.raw, GBP_BLOCK_SIZE);
        ringlog_printf(log, "READDISAGREE cycle=%lu read=%s t=%llx disc=%04x gbi=%04x attempts=%u frame=%lu blk=%lu lat=%lu xfer=%lu/%u dspcr=%04x/%04x raw=%s",
                       (unsigned long)st->diag.cycle, gbp_vstate_diag_read_name(st->diag.read_kind),
                       (unsigned long long)st->diag.t, (unsigned)st->diag.disc_value, (unsigned)st->diag.gbi_value,
                       (unsigned)st->diag.attempts, (unsigned long)st->diag.frame_index,
                       (unsigned long)st->diag.block_in_frame, (unsigned long)st->diag.latency_ticks,
                       (unsigned long)st->diag.xfer_ticks, (unsigned)st->diag.xfer_polls,
                       (unsigned)st->diag.dma_status_before, (unsigned)st->diag.dma_status, hex);
        ringlog_printf(log, "READDISAGREEPI intsr_entry=%08lx intsr_after_w1c=%08lx intmr_entry=%08lx control_exp=%02x",
                       (unsigned long)st->diag.intsr_entry, (unsigned long)st->diag.intsr_after_w1c,
                       (unsigned long)st->diag.intmr_entry, (unsigned)st->diag.control_exp);
    }
    log_cycles(log, "CYCF", cfg->cyc_first, res->cyc_first_n);
    log_cycles(log, "CYCL", cfg->cyc_last, res->cyc_last_n);
    log_cycles(log, "CYCA", cfg->cyc_anomaly, res->cyc_anomaly_n);
    log_cycles(log, "CYCE", cfg->cyc_episode, res->cyc_episode_n);

    ringlog_printf(log, "COUNTERS unmasks=%lu deliveries=%lu acks=%lu rearms=%lu lean=%lu verify=%lu audio=%lu video=%lu/%lu isr_w1c=%lu main_w1c=%lu teardown_w1c=%lu overflow=%lu uncertain=%lu control_ok=%d",
                   (unsigned long)res->unmasks, (unsigned long)res->deliveries, (unsigned long)res->acks,
                   (unsigned long)res->rearms, (unsigned long)res->lean_cycles, (unsigned long)res->verify_cycles_done,
                   (unsigned long)res->audio_drains, (unsigned long)res->video_completed, (unsigned long)res->video_drains,
                   (unsigned long)res->isr_w1c, (unsigned long)res->main_w1c, (unsigned long)res->teardown_w1c,
                   (unsigned long)res->counter_overflow, (unsigned long)res->uncertain_writes, res->control_ok);
    ringlog_printf(log, "BYTES video=%llu audio=%llu", (unsigned long long)res->bytes_video, (unsigned long long)res->bytes_audio);
    ringlog_printf(log, "MATRIX service=%s service_reason=%s stop=%s frame_capture=%s baseline=%s structured=%s reference_match=offline restore=%s save=deferred",
                   res->service_ok ? "ok" : "failed", res->service_reason,
                   gbp_vstate_stop_name(res->stop),
                   (st && st->frame_store_full) ? "frame_store_cap" : (st && st->event_store_full) ? "event_store_cap" : "ok",
                   (st && st->baseline_valid) ? "valid" : "never_established",
                   (st && st->episode_count) ? "observed" : "not_observed",
                   res->restore_ok ? "ok" : "failed");
    ringlog_printf(log, "RESTOREVSTATE handler_installed=%d handler_restored=%d old_handler=%s mask_ok=%d intmr_final=%08lx pi_sticky_final=%d unmasks=%lu teardown_begin=%llx teardown_end=%llx",
                   res->h.handler_was_installed, res->h.handler_restored, old_handler_name(&res->h), res->h.mask_ok,
                   (unsigned long)res->h.intmr_final, res->pi_sticky_final, (unsigned long)res->unmasks,
                   (unsigned long long)res->t_teardown_begin, (unsigned long long)res->t_teardown_end);
}

/* Stop, tear the hardware down, and only then report. */
static void finish(struct run_ctx *x, gbp_vstate_status st, const char *reason, const char *variant, int stop)
{
    struct gbp_vstate_result *res = x->res;
    set_status(res, st, reason);
    if (stop != GBP_VSTATE_STOP_NONE) { res->stop = stop; res->stop_name = gbp_vstate_stop_name(stop); }
    if (stop == GBP_VSTATE_STOP_FAILURE) service_failed(res, reason);
    /* minimal RAM snapshot: the clocks. Nothing is summarised, hashed or formatted here. */
    res->t_stop = now64(x->t);
    if (x->st) {
        gbp_vstate_event(x->st, res->t_stop, GBP_VSTATE_EV_STOP, (uint32_t)res->stop, res->deliveries,
                         x->st->frames_n, x->st->episode_count);
        res->valid_observation_elapsed = x->st->valid_observation_elapsed;
    }
    teardown_hardware(x, variant);
    if (res->service_ok) {
        gbp_vstate_status main_st = gbp_vstate_main_status(res);
        set_status(res, main_st, reason);
    }
    gbp_vstate_report(x->log, x->cfg, res);
}


/*
 * The U-GBP-032 diagnostic. Called at the instant a disagreement is detected,
 * from the buffer the transport already filled: no extra read, no re-read, no
 * retry, no change to the number or order of hardware operations. Field stores
 * and one 32-byte memcpy; nothing is formatted here. The extra context comes
 * only from values already resident in RAM.
 */
static void capture_disagreement(struct run_ctx *x, uint32_t n, const uint8_t *raw,
                                 uint16_t disc, uint16_t gbi, uint16_t kind,
                                 const struct gbp_xfer_info *info)
{
    struct gbp_vstate_result *res = x->res;
    struct gbp_vstate *st = x->st;
    if (!st) return;
    if (gbp_vstate_diag_capture(st, n, now64(x->t), raw, disc, gbi, kind)) {
        st->diag.intsr_entry = res->d.rec.intsr_before_ack;
        st->diag.intsr_after_w1c = res->d.rec.intsr_after_ack;
        st->diag.intmr_entry = res->d.rec.intmr_at_entry;
        st->diag.latency_ticks = res->d.latency_ticks;
        st->diag.control_exp = res->a.control_exp;
        if (info) {
            st->diag.xfer_ticks = info->ticks;
            st->diag.xfer_polls = info->polls;
            st->diag.dma_status = info->dma_status;
            st->diag.dma_status_before = info->dma_status_before;
        }
    }
}

/* ---- snapshot checks of the verify cycles (as GBP-VIDEO-001) --------- */
static int common_checks(struct run_ctx *x, const struct gbp_initirqa_snapshot *s, const char *site, uint32_t n,
                         gbp_vstate_status *st, const char **reason)
{
    struct gbp_vstate_result *res = x->res;
    const struct gbp_vstate_config *cfg = x->cfg;
    uint16_t unexpected;
    note_control(res, s);
    if (!s->pi_ok || s->control_rc != GBP_OK || s->irq_rc != GBP_OK) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "%s_read_failed_cycle_%lu", site, (unsigned long)n);
        *st = GBP_VSTATE_ABORT_TRANSPORT; *reason = res->reason_buf; return 0;
    }
    if (s->irq_disc != s->irq_gbi) {
        /* U-GBP-032: secure the bytes FIRST, from the snapshot the read already filled */
        capture_disagreement(x, n, s->irq, s->irq_disc, s->irq_gbi,
                             (uint16_t)(strcmp(site, "PRESVC") == 0 ? GBP_VSTATE_DIAG_READ_PRESVC :
                                        strcmp(site, "POSTDRAIN") == 0 ? GBP_VSTATE_DIAG_READ_POSTDRAIN :
                                        strcmp(site, "POSTACK") == 0 ? GBP_VSTATE_DIAG_READ_POSTACK :
                                        GBP_VSTATE_DIAG_READ_OTHER),
                             &s->irq_info);
        snprintf(res->reason_buf, sizeof res->reason_buf, "%s_semantic_disagree_cycle_%lu", site, (unsigned long)n);
        *st = GBP_VSTATE_ABORT_READ_INCONSISTENT; *reason = res->reason_buf; return 0;
    }
    if (s->control_vote != res->a.control_exp || s->control_vote != s->control_b1f) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "control_changed_%s_cycle_%lu", site, (unsigned long)n);
        *st = GBP_VSTATE_ANOMALY_CONTROL_CHANGED; *reason = res->reason_buf; return 0;
    }
    if (bit13(s->intmr) || (s->pi2_ok && bit13(s->intmr2))) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "intmr13_set_%s_cycle_%lu", site, (unsigned long)n);
        *st = GBP_VSTATE_ANOMALY_MASK_FAILURE; *reason = res->reason_buf; return 0;
    }
    unexpected = (uint16_t)(s->irq_gbi & cfg->src_mask & (uint16_t)~cfg->av_mask);
    if (unexpected) {
        res->unexpected = unexpected;
        res->unexpected_site = site;
        res->unexpected_cycle = n;
        snprintf(res->reason_buf, sizeof res->reason_buf, "unexpected_source_%s_cycle_%lu", site, (unsigned long)n);
        *st = GBP_VSTATE_ANOMALY_UNEXPECTED_SOURCE; *reason = res->reason_buf; return 0;
    }
    return 1;
}

static gbp_vstate_status dma_status(int is_audio, gbp_status rc)
{
    if (rc == GBP_ERR_BUSY) return is_audio ? GBP_VSTATE_AUDIO_DMA_BUSY : GBP_VSTATE_VIDEO_DMA_BUSY;
    if (rc == GBP_ERR_TIMEOUT) return is_audio ? GBP_VSTATE_AUDIO_DMA_TIMEOUT : GBP_VSTATE_VIDEO_DMA_TIMEOUT;
    return is_audio ? GBP_VSTATE_AUDIO_DMA_ERROR : GBP_VSTATE_VIDEO_DMA_ERROR;
}

static void cycle_names(struct gbp_vstate_result *res, uint32_t n)
{
    snprintf(res->id_presvc, sizeof res->id_presvc, "PRESVC-%lu", (unsigned long)n);
    snprintf(res->id_postdrain, sizeof res->id_postdrain, "POSTDRAIN-%lu", (unsigned long)n);
    snprintf(res->id_postack, sizeof res->id_postack, "POSTACK-%lu", (unsigned long)n);
    snprintf(res->id_rearmpost, sizeof res->id_rearmpost, "REARMPOST-%lu", (unsigned long)n);
    snprintf(res->tag_ack, sizeof res->tag_ack, "tag=ACK-%lu", (unsigned long)n);
    snprintf(res->tag_rearm, sizeof res->tag_rearm, "tag=REARM-%lu", (unsigned long)n);
    snprintf(res->nfield, sizeof res->nfield, " n=%lu", (unsigned long)n);
    snprintf(res->sfx, sizeof res->sfx, "-%lu", (unsigned long)n);
}

/* WAIT_NEXT: masked, read-only, bounded by T_NEXT_CAUSE. Nothing is written to the PI here. */
static int wait_next(struct run_ctx *x, struct gbp_vstate_cycle *c, uint32_t t_ref32)
{
    const struct gbp_transport *t = x->t;
    uint32_t bound = x->cfg->t_next_cause_ticks;
    uint32_t intsr = 0;
    for (;;) {
        uint32_t tnow = now32(t);
        if (t->poll_intsr(t->ctx, &intsr) == GBP_OK) {
            if (intsr & GBP_PI_HSP_BIT) {
                c->next_observed = 1; c->intsr_next = intsr; c->t_next = now64(t);
                return 1;
            }
        } else {
            x->res->a.poll_errors++;
        }
        if ((uint32_t)(tnow - t_ref32) >= bound) { c->intsr_next = intsr; c->t_next = now64(t); return 0; }
    }
}

int gbp_vstate_probe_run(const struct gbp_transport *t, struct ringlog *log,
                         const struct gbp_vstate_config *cfg, struct gbp_vstate_result *res)
{
    struct run_ctx xs, *x = &xs;
    struct gbp_vstate *st = cfg->st;
    gbp_initirqa_cause_rc crc;
    const struct gbp_initirqa_snapshot *ev;
    struct gbp_irq_record rec0;
    gbp_vstate_status status;
    const char *why = "-";
    int old_null = -1;
    uint64_t t64_pre = 0, t64_post = 0, t_cause_next = 0;
    uint32_t t32_pre = 0;
    uint32_t n;

    memset(&xs, 0, sizeof xs);
    xs.t = t; xs.log = log; xs.cfg = cfg; xs.res = res; xs.st = st;
    memset(res, 0, sizeof *res);
    res->st = st;
    res->restore_ok = 1;
    res->restore_reason = "-";
    res->reason = "-";
    res->status_name = "-";
    res->status_class = "-";
    res->stop_name = "none";
    res->preunmask_reason = "-";
    res->unexpected_site = "-";
    res->service_reason = "-";
    res->service_ok = 1;
    res->control_ok = 1;
    res->save_reason = "not_attempted";
    gbp_irq_service_handler_init(&res->h);
    gbp_irq_service_delivery_init(&res->d);
    gbp_irq_service_ack_init(&res->k);

    ringlog_printf(log, "VSTATE start test=GBP-VIDEO-002 target_s=%lu limit_s=%lu limit_ticks=%llx max_deliveries=%lu verify=%lu t_delivery_ms=%lu t_next_cause_ms=%lu",
                   (unsigned long)cfg->min_valid_observation_s, (unsigned long)cfg->hard_wallclock_s,
                   (unsigned long long)cfg->hard_wallclock_ticks, (unsigned long)cfg->max_deliveries,
                   (unsigned long)cfg->verify_cycles, (unsigned long)cfg->t_delivery_ms, (unsigned long)cfg->t_next_cause_ms);
    ringlog_printf(log, "VSTATE stores frames=%lu x %lu event=%lu x %lu episodes=%lu x %lu raw_ring=%lu x %lu audio_raw=%lu n_stable=%lu ep_max_frames=%lu static_bytes=%llu",
                   (unsigned long)GBP_VSTATE_MAX_FRAMES, (unsigned long)GBP_VSTATE_FRAME_REC,
                   (unsigned long)GBP_VSTATE_MAX_EVENTS, (unsigned long)GBP_VSTATE_EVENT_REC,
                   (unsigned long)GBP_VSTATE_MAX_EPISODES, (unsigned long)GBP_VSTATE_EPISODE_RAW_SLOTS,
                   (unsigned long)GBP_VSTATE_RAW_RING_SLOTS, (unsigned long)GBP_VSTATE_RAW_FRAME_BYTES,
                   (unsigned long)GBP_VSTATE_AUDIO_RAW_SLOTS, (unsigned long)GBP_VSTATE_N_STABLE,
                   (unsigned long)GBP_VSTATE_EPISODE_MAX_FRAMES, (unsigned long long)gbp_vstate_static_bytes());
    ringlog_printf(log, "VSTATE policy handler=003b_ext_installed_once record=reset_under_mask order=read_audio_video_ack_piclean_sign_rearm_waitnext checksum=between_ack_and_rearm oracle=offline_only early_positive_stop=none");
    ringlog_printf(log, "VSTATE caps frame_store=stops event_store=stops episode_raw_store=does_not_stop safety_epoch=t_control_transform precedence=fatal,safety,stores,target,no_next_cause,delivery");

    if (!st || !gbp_vstate_storage_ok(st)) {
        set_status(res, GBP_VSTATE_ABORT_STORE_UNAVAILABLE, "store_or_bounds_invalid");
        res->stop = GBP_VSTATE_STOP_FAILURE; res->stop_name = gbp_vstate_stop_name(res->stop);
        service_failed(res, "store_or_bounds_invalid");
        res->teardown_variant = "none";
        res->t_stop = now64(t);            /* a real reading: an unset field must never be reported as a time */
        ringlog_printf(log, "VSTATE abort reason=store_or_bounds_invalid");
        gbp_vstate_report(log, cfg, res);
        return 0;
    }
    if (!gbp_transport_has_time64(t)) {
        set_status(res, GBP_VSTATE_ABORT_TIME64_UNAVAILABLE, "time64_unavailable");
        res->stop = GBP_VSTATE_STOP_FAILURE; res->stop_name = gbp_vstate_stop_name(res->stop);
        service_failed(res, "time64_unavailable");
        res->teardown_variant = "none";
        res->t_stop = now64(t);            /* 0 here is honest: this is the path where there is no 64-bit base */
        ringlog_printf(log, "VSTATE abort reason=time64_unavailable");
        gbp_vstate_report(log, cfg, res);
        return 0;
    }
    /* known state of every raw slot before the run, outside the timed region */
    memset(st->raw_ring, 0, GBP_VSTATE_RAW_RING_BYTES);
    memset(st->episode_raw, 0, GBP_VSTATE_EPISODE_RAW_BYTES);
    memset(st->audio_raw, 0, GBP_VSTATE_AUDIO_RAW_BYTES);

    /* ---- 1. the 003A sequence verbatim, PI masked, no handler ----
     * The safety epoch is the CONTROL transform 0x90 -> 0x8C, the first
     * experimental write. The stage records it on the 32-bit time base, so it
     * is lifted to 64 bits from a pair of reads taken immediately before the
     * stage: exact while the stage lasts under 2^32 ticks (106 s), and it is
     * bounded by a few seconds. */
    t64_pre = now64(t);
    t32_pre = now32(t);
    crc = gbp_initirqa_run_cause(t, log, &cfg->a, &res->a);
    t64_post = now64(t);
    /* The reconstruction, and its check. The stage performs a BOUNDED number of transfers before
     * the CONTROL write (measured: 12, each bounded by the transport's own operational timeout,
     * with no polling loop in that window), so the 32-bit difference cannot be ambiguous by 2^32.
     * That bound is not merely asserted: the true epoch necessarily lies between the two u64 reads
     * taken around the stage, and the reconstruction is required to land inside that bracket. */
    if (res->a.control_written && res->a.w_ctl_exp.completed) {
        uint64_t recon = t64_pre + (uint64_t)(uint32_t)(res->a.t_control - t32_pre);
        if (recon >= t64_pre && recon <= t64_post) {
            res->t_control_transform = recon;
            res->epoch_ok = 1;
        } else {
            /* outside the bracket: take the earlier end, which precedes the real write, so the
             * safety budget is over-counted rather than under-counted */
            res->t_control_transform = t64_pre;
            res->epoch_ok = 0;
        }
    } else {
        /* No experimental write was made. There is no epoch, and a fabricated one would be worse
         * than none: the field carries the probe's own start instead, and says so. */
        res->t_control_transform = t64_pre;
        res->epoch_ok = -1;
    }
    ringlog_printf(log, "EPOCH t64_pre=%llx t64_post=%llx t32_pre=%lu t_control32=%lu control_written=%d epoch_ok=%d t_control_transform=%llx deadline=%llx",
                   (unsigned long long)t64_pre, (unsigned long long)t64_post, (unsigned long)t32_pre,
                   (unsigned long)res->a.t_control, res->a.control_written, res->epoch_ok,
                   (unsigned long long)res->t_control_transform,
                   (unsigned long long)(res->t_control_transform + cfg->hard_wallclock_ticks));
    if (crc == GBP_INITIRQA_CAUSE_ABORTED) {
        res->stage_a_aborted = 1;
        res->status = GBP_VSTATE_ABORT_STAGE_A;
        res->status_name = gbp_initirqa_status_name(res->a.status);
        res->status_class = gbp_vstate_status_class(GBP_VSTATE_ABORT_STAGE_A);
        res->reason = res->a.reason ? res->a.reason : "-";
        res->teardown_variant = "stage_a";
        res->stop = GBP_VSTATE_STOP_FAILURE; res->stop_name = gbp_vstate_stop_name(res->stop);
        service_failed(res, res->reason);
        if (!res->a.restore_ok) restore_fail(res, res->a.restore_reason);
        res->t_stop = t64_post;            /* the stage's own end, already read: never a zero timestamp */
        gbp_vstate_report(log, cfg, res);
        return 0;
    }
    xs.irq_addr = gbp_block_addr(res->a.base, GBP_IDX_IRQ, 0);
    xs.audio_addr = gbp_block_addr(res->a.base, cfg->audio_index, 0);
    xs.video_addr = gbp_block_addr(res->a.base, cfg->video_index, 0);
    if (crc == GBP_INITIRQA_CAUSE_NOT_OBSERVED) {
        finish(x, GBP_VSTATE_NO_INITIAL_CAUSE, "no_intsr13_within_t_max", "S2_before_unmask", GBP_VSTATE_STOP_FAILURE);
        return 0;
    }

    ev = &res->a.snap[GBP_INITIRQA_SNAP_EVENT];
    res->t_cause32 = ev->taken ? ev->ticks : res->a.t_first_intsr13;
    res->cause_irq = ev->irq_gbi;

    /* ---- 2. the 003B extended one-shot handler, installed ONCE ---- */
    res->h.irq_path_available = gbp_transport_has_irq_path(t);
    if (!res->h.irq_path_available) { finish(x, GBP_VSTATE_ABORT_HANDLER_INSTALL, "irq_ops_unavailable", "S2_before_unmask", GBP_VSTATE_STOP_FAILURE); return 0; }
    if (!gbp_transport_has_bulk_read(t)) { finish(x, GBP_VSTATE_ABORT_BULK_UNAVAILABLE, "bulk_read_unavailable", "S2_before_unmask", GBP_VSTATE_STOP_FAILURE); return 0; }
    if (!gbp_transport_has_irq_reset(t)) { finish(x, GBP_VSTATE_ABORT_RESET_UNAVAILABLE, "record_reset_unavailable", "S2_before_unmask", GBP_VSTATE_STOP_FAILURE); return 0; }
    res->h.install_rc = t->irq_install(t->ctx, &old_null);
    if (res->h.install_rc != GBP_OK) {
        res->a.errors++;
        ringlog_printf(log, "IRQ install rc=%s", gbp_status_name(res->h.install_rc));
        finish(x, GBP_VSTATE_ABORT_HANDLER_INSTALL, "install_failed", "S2_before_unmask", GBP_VSTATE_STOP_FAILURE);
        return 0;
    }
    res->h.handler_installed = 1;
    res->h.handler_was_installed = 1;
    res->h.old_handler_null = old_null ? 1 : 0;
    memset(&rec0, 0, sizeof rec0);
    t->irq_record(t->ctx, &rec0);
    res->h.install_count = rec0.count;
    res->h.install_fired = rec0.fired;
    ringlog_printf(log, "IRQ install rc=ok old_handler=%s record_count=%lu record_fired=%lu", old_null ? "null" : "nonnull",
                   (unsigned long)rec0.count, (unsigned long)rec0.fired);

    /* ---- 3. PREUNMASK ---- */
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
    if (!res->preunmask_ok) {
        if (res->unexpected) finish(x, GBP_VSTATE_ANOMALY_UNEXPECTED_SOURCE, "unexpected_source_PREUNMASK", "S2_before_unmask", GBP_VSTATE_STOP_FAILURE);
        else if (strcmp(why, "control_changed") == 0) finish(x, GBP_VSTATE_ANOMALY_CONTROL_CHANGED, "control_changed_PREUNMASK", "S2_before_unmask", GBP_VSTATE_STOP_FAILURE);
        else finish(x, GBP_VSTATE_ABORT_PRE_UNMASK_STATE, why, "S2_before_unmask", GBP_VSTATE_STOP_FAILURE);
        return 0;
    }

    /* ---- 4. the long service loop ---- */
    t_cause_next = now64(t);
    for (n = 0; ; n++) {
        struct gbp_vstate_cycle cyc;
        struct gbp_vstate_step step;
        int verify = (n < cfg->verify_cycles) ? 1 : 0;
        uint16_t pending;
        uint32_t t_ref32;
        uint64_t tnow;

        memset(&cyc, 0, sizeof cyc);
        memset(&step, 0, sizeof step);
        cyc.index = n;
        cyc.t_cause = t_cause_next;
        cyc.frame_index = st->frames_n;
        cyc.block_in_frame = st->cur_blocks;

        /* ---- CHECK_ADMISSION: the ONLY place a stop condition is evaluated.
         * An accepted transaction is never re-checked, so a cap can never
         * produce a partial ACK or an unwritten re-arm. ---- */
        if (n > 0u) {
            tnow = now64(t);
            /* 2. the hard wall-clock safety budget, counted from the CONTROL transform */
            if (gbp_time64_reached(res->t_control_transform, cfg->hard_wallclock_ticks, tnow)) {
                res->next_cause_at_end = 1;
                gbp_vstate_safety_stop(st, tnow);
                finish(x, GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE, "-", "S5_safety_budget", GBP_VSTATE_STOP_SAFETY_BUDGET);
                return 0;
            }
            /* 3. the two stores that really do end the run (the episode RAW store never does) */
            if (st->frame_store_full) {
                res->next_cause_at_end = 1;
                if (st->tail_active) gbp_vstate_tail_truncate(st, tnow);
                finish(x, GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE, "-", "S5_frame_store_cap", GBP_VSTATE_STOP_FRAME_STORE_CAP);
                return 0;
            }
            if (st->event_store_full) {
                res->next_cause_at_end = 1;
                if (st->tail_active) gbp_vstate_tail_truncate(st, tnow);
                finish(x, GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE, "-", "S5_event_store_cap", GBP_VSTATE_STOP_EVENT_STORE_CAP);
                return 0;
            }
            /* 4. the scientific target, measured on valid observation only */
            if (st->baseline_valid && st->valid_observation_elapsed >= cfg->min_valid_observation_ticks) {
                if (!res->valid_observation_at_target) {
                    res->valid_observation_at_target = st->valid_observation_elapsed;
                    if (!gbp_vstate_target_reached(st, tnow)) {
                        res->next_cause_at_end = 1;
                        finish(x, GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL, "-", "S5_target", GBP_VSTATE_STOP_NOMINAL_NEGATIVE);
                        return 0;
                    }
                } else if (!st->tail_active) {
                    /* the tail ended (the episode closed or was truncated): stop now */
                    res->next_cause_at_end = 1;
                    finish(x, GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL, "-", "S5_target", GBP_VSTATE_STOP_NOMINAL_NEGATIVE);
                    return 0;
                } else if (st->tail_frames >= GBP_VSTATE_EPISODE_MAX_FRAMES) {
                    gbp_vstate_tail_truncate(st, tnow);
                    res->next_cause_at_end = 1;
                    finish(x, GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL, "-", "S5_target", GBP_VSTATE_STOP_NOMINAL_NEGATIVE);
                    return 0;
                }
            }
            /* 6. the delivery guard (5. is evaluated where WAIT_NEXT ends) */
            if (res->deliveries >= cfg->max_deliveries) {
                res->next_cause_at_end = 1;
                finish(x, GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE, "-", "S5_delivery_cap", GBP_VSTATE_STOP_DELIVERY_CAP);
                return 0;
            }
            if (res->counter_overflow) {
                finish(x, GBP_VSTATE_ABORT_CAPACITY, "counter_overflow", "S5_counter_overflow", GBP_VSTATE_STOP_FAILURE);
                return 0;
            }
            /* only a verify cycle ever formats anything, and there are four of them: naming every
             * one of ~639 000 cycles would be eight snprintf calls per cycle for nothing */
            if (verify) cycle_names(res, n);
            /* ---- PREPARE: the record back to zero (memory only); no PI write ---- */
            {
                gbp_status rc = t->irq_record_reset(t->ctx);
                uint32_t intsr = 0, intmr = 0;
                struct gbp_irq_record rr;
                if (rc != GBP_OK) { res->a.errors++; finish(x, GBP_VSTATE_ANOMALY_RECORD_NOT_CLEAR, "record_reset_refused", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
                if (t->read_pi(t->ctx, &intsr, &intmr) != GBP_OK) { res->a.errors++; finish(x, GBP_VSTATE_ABORT_TRANSPORT, "prepare_pi_read_failed", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
                memset(&rr, 0, sizeof rr);
                t->irq_record(t->ctx, &rr);
                if (bit13(intmr)) { finish(x, GBP_VSTATE_ANOMALY_MASK_FAILURE, "intmr13_set_before_unmask", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
                if (rr.count || rr.fired) { finish(x, GBP_VSTATE_ANOMALY_RECORD_NOT_CLEAR, "record_not_clear_before_unmask", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
                if (!bit13(intsr)) { finish(x, GBP_VSTATE_ANOMALY_REARM_STATE, "no_cause_latched_at_admission", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
            }
        } else {
            cycle_names(res, n);
        }
        if (!verify) { res->nfield[0] = 0; res->sfx[0] = 0; }

        /* ---- UNMASK + CONFIRM ---- */
        gbp_irq_service_delivery_init(&res->d);
        gbp_irq_service_deliver_quiet(t, cfg->a.tb_hz, cfg->t_delivery_ticks, -1, &res->d, &res->a.errors);
        if (verify) gbp_irq_service_deliver_log(log, cfg->a.tb_hz, cfg->t_delivery_ms, cfg->t_delivery_ticks, res->nfield, res->sfx, &res->d);
        bump(res, &res->unmasks);
        cyc.t_unmask = now64(t);
        if (n == 0u) {
            res->t_capture_start = cyc.t_unmask;
            st->t_capture_start = cyc.t_unmask;
            gbp_vstate_event(st, cyc.t_unmask, GBP_VSTATE_EV_CAPTURE_START, 0u, 0u, 0u, 0u);
        }
        cyc.isr_count = (uint8_t)(res->d.rec.count > 255u ? 255u : res->d.rec.count);
        cyc.isr_reentry = (uint8_t)(res->d.reentry ? 1u : 0u);
        cyc.latency_ticks = res->d.latency_ticks;
        cyc.intsr_entry = res->d.rec.intsr_before_ack;
        cyc.intsr_after_w1c = res->d.rec.intsr_after_ack;
        if (res->d.mask_rc != GBP_OK) restore_fail(res, "mask_failed");
        if (!res->d.fired) {
            int never_opened = (res->d.unmask_rc != GBP_OK) ||
                               (res->d.pi_post_unmask_ok && !bit13(res->d.intmr_post_unmask) && res->d.rec.count == 0u);
            if (res->d.unmask_rc != GBP_OK) res->a.errors++;
            cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
            if (n == 0u) finish(x, never_opened ? GBP_VSTATE_ABORT_UNMASK : GBP_VSTATE_FIRST_DELIVERY_TIMEOUT,
                                never_opened ? "unmask_not_effective" : "no_delivery_within_t_delivery", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE);
            else finish(x, GBP_VSTATE_ANOMALY_MISSED_ENTRY, "no_handler_entry_after_unmask", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE);
            return 0;
        }
        bump(res, &res->deliveries);
        bump(res, &res->isr_w1c);
        cyc.t_entry = cyc.t_unmask;            /* the entry happened inside the unmask call, masked throughout */
        if (res->d.reentry) { cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY); finish(x, GBP_VSTATE_ANOMALY_REENTRY, "handler_entered_more_than_once", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
        if (res->d.rec.count != 1u || !bit13(res->d.rec.intsr_before_ack) || !bit13(res->d.rec.intmr_at_entry) ||
            bit13(res->d.rec.intmr_after_mask) || bit13(res->d.rec.intsr_after_ack)) {
            cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
            finish(x, GBP_VSTATE_ANOMALY_ISR_STATE, "handler_record_state_unexpected", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0;
        }
        if (res->d.main_mask_ok != 1) { cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY); finish(x, GBP_VSTATE_ANOMALY_MASK_FAILURE, "intmr13_still_set_after_remask", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }

        /* ---- READ: the authoritative snapshot of this cycle ---- */
        if (verify) {
            gbp_initirqa_snapshot_take(t, &res->a, &res->presvc, res->id_presvc, 0, 1);
            gbp_initirqa_snapshot_log(log, &res->a, &res->presvc);
            if (!common_checks(x, &res->presvc, "PRESVC", n, &status, &why)) { cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY); finish(x, status, why, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
            pending = res->presvc.irq_gbi;
            cyc.t_read = now64(t);
        } else {
            uint8_t irq_raw[GBP_BLOCK_SIZE];
            struct gbp_xfer_info info;
            gbp_status rc;
            uint16_t disc, gbi;
            memset(&info, 0, sizeof info);
            rc = t->read_block(t->ctx, xs.irq_addr, irq_raw, &info);
            cyc.t_read = now64(t);
            if (rc != GBP_OK) { res->a.errors++; cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY); snprintf(res->reason_buf, sizeof res->reason_buf, "READ_failed_cycle_%lu", (unsigned long)n); finish(x, GBP_VSTATE_ABORT_TRANSPORT, res->reason_buf, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
            disc = gbp_irq_value_disc(irq_raw);
            gbi = gbp_irq_value_gbi(irq_raw);
            if (disc != gbi) {
                /* U-GBP-032: the 32 bytes are still exactly as the transport delivered them into
                 * irq_raw. Copy them out BEFORE anything else touches the cycle record or the
                 * reason string; nothing here reads the device again. */
                capture_disagreement(x, n, irq_raw, disc, gbi, GBP_VSTATE_DIAG_READ_LEAN, &info);
                cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
                snprintf(res->reason_buf, sizeof res->reason_buf, "READ_semantic_disagree_cycle_%lu", (unsigned long)n);
                finish(x, GBP_VSTATE_ABORT_READ_INCONSISTENT, res->reason_buf, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE);
                return 0;
            }
            pending = gbi;
            if ((uint16_t)(pending & cfg->src_mask & (uint16_t)~cfg->av_mask) != 0u) {
                res->unexpected = (uint16_t)(pending & cfg->src_mask & (uint16_t)~cfg->av_mask);
                res->unexpected_site = "READ"; res->unexpected_cycle = n;
                cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
                snprintf(res->reason_buf, sizeof res->reason_buf, "unexpected_source_READ_cycle_%lu", (unsigned long)n);
                finish(x, GBP_VSTATE_ANOMALY_UNEXPECTED_SOURCE, res->reason_buf, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0;
            }
        }
        cyc.pending = pending;
        if ((pending & cfg->av_mask) == 0u) { cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY); snprintf(res->reason_buf, sizeof res->reason_buf, "cause_without_av_source_cycle_%lu", (unsigned long)n); finish(x, GBP_VSTATE_ANOMALY_CAUSE_WITHOUT_SOURCE, res->reason_buf, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
        if ((pending & cfg->odd_mask) != 0u || (pending & cfg->bit15_mask) != 0u || (pending & cfg->high_mask) != 0u) {
            cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
            snprintf(res->reason_buf, sizeof res->reason_buf, "irq_shape_READ_cycle_%lu", (unsigned long)n);
            finish(x, GBP_VSTATE_ABORT_PRESVC_STATE, res->reason_buf, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0;
        }
        cyc.audio_selected = (uint8_t)((pending & cfg->audio_src) ? 1u : 0u);
        cyc.video_selected = (uint8_t)((pending & cfg->video_src) ? 1u : 0u);
        cyc.ack_value = (uint16_t)(pending | cfg->ack_or);

        /* ---- AUDIO: drained whenever selected, aggregate counters only ---- */
        if (cyc.audio_selected) {
            unsigned slot = 0;
            uint8_t *buf = gbp_vstate_audio_target(st, &slot);
            if (!buf) { finish(x, GBP_VSTATE_ABORT_CAPACITY, "audio_slot_unavailable", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
            bump(res, &st->audio.selected);
            gbp_avblock_init(&res->audio, "audio", cfg->audio_index, cfg->audio_src, buf, GBP_VSTATE_AUDIO_BLOCK_SIZE, cfg->audio_len);
            res->audio.selected = 1;
            bump(res, &res->audio_drains);
            gbp_avblock_read(t, res->a.base, &res->audio, &res->a.errors);
            gbp_vstate_audio_commit(st, slot, res->audio.completed, res->audio.completed ? cfg->audio_len : 0u, n);
            cyc.audio_completed = (uint8_t)(res->audio.completed ? 1u : 0u);
            cyc.audio_wait = res->audio.info.ticks;
            cyc.rc |= (uint32_t)res->audio.rc;
            if (res->audio.completed) res->bytes_audio += cfg->audio_len;
            if (verify) gbp_avblock_log_read(log, "AUDIOREAD", &res->audio);
            if (!res->audio.completed) {
                cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
                snprintf(res->reason_buf, sizeof res->reason_buf, "audio_read_failed_cycle_%lu", (unsigned long)n);
                finish(x, dma_status(1, res->audio.rc), res->reason_buf, "S3_dma_failed", GBP_VSTATE_STOP_FAILURE);
                return 0;
            }
        }

        /* ---- VIDEO: one whole-block DMA into the working ring ---- */
        if (cyc.video_selected) {
            uint8_t *buf = gbp_vstate_video_target(st);
            if (!buf) { finish(x, GBP_VSTATE_ABORT_CAPACITY, "video_slot_unavailable", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
            gbp_avblock_init(&res->video, "video", cfg->video_index, cfg->video_src, buf, GBP_VSTATE_VIDEO_BLOCK_SIZE, cfg->video_len);
            res->video.selected = 1;
            bump(res, &res->video_drains);
            gbp_avblock_read(t, res->a.base, &res->video, &res->a.errors);
            cyc.video_completed = (uint8_t)(res->video.completed ? 1u : 0u);
            cyc.video_wait = res->video.info.ticks;
            cyc.rc |= (uint32_t)res->video.rc << 8;
            if (verify) gbp_avblock_log_read(log, "VIDEOREAD", &res->video);
            if (!res->video.completed) {
                cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
                snprintf(res->reason_buf, sizeof res->reason_buf, "video_read_failed_cycle_%lu", (unsigned long)n);
                finish(x, dma_status(0, res->video.rc), res->reason_buf, "S3_dma_failed", GBP_VSTATE_STOP_FAILURE);
                return 0;
            }
            bump(res, &res->video_completed);
            res->bytes_video += cfg->video_len;
        }

        /* ---- POSTDRAIN (verify cycles only) ---- */
        if (verify) {
            gbp_initirqa_snapshot_take(t, &res->a, &res->postdrain, res->id_postdrain, 0, 1);
            gbp_initirqa_snapshot_log(log, &res->a, &res->postdrain);
            if (!common_checks(x, &res->postdrain, "POSTDRAIN", n, &status, &why)) { finish(x, status, why, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
        }

        /* ---- ACK := pending | 0x8000 (the whole value, never partial) ---- */
        if (verify) {
            gbp_irq_service_ack_init(&res->k);
            gbp_irq_service_ack_write_postack(t, log, &res->a, pending, cfg->ack_or, cfg->src_mask, res->nfield, res->id_postack, res->tag_ack, res->sfx,
                                              &res->k, &res->a.errors);
            res->w_ack = res->k.w_ack;
        } else {
            res->a.irq_writes_attempted++;
            res->a.power_cycle_required = 1;
            gbp_regwrite_irq_u16(t, "tag=ACK", res->a.base, pending, cyc.ack_value, &res->w_ack, &res->a.errors);
            if (res->w_ack.completed) res->a.irq_writes_completed++;
        }
        cyc.t_ack = now64(t);
        cyc.rc |= (uint32_t)(res->w_ack.completed ? 0u : 1u) << 16;
        if (!res->w_ack.completed) {
            res->uncertain_writes++;
            cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
            finish(x, GBP_VSTATE_ACK_WRITE_FAILED, "ack_write_failed", "S4_ack_failed", GBP_VSTATE_STOP_FAILURE);
            return 0;
        }
        bump(res, &res->acks);

        /* ---- PICLEAN: at most one main-loop W1C ---- */
        if (verify) {
            const struct gbp_initirqa_snapshot *ps = &res->k.postack;
            if (!common_checks(x, ps, "POSTACK", n, &status, &why)) { finish(x, status, why, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
            if ((ps->irq_gbi & cfg->odd_mask) != 0u || (ps->irq_gbi & cfg->bit15_mask) == 0u || (ps->irq_gbi & cfg->high_mask) != 0u) {
                snprintf(res->reason_buf, sizeof res->reason_buf, "postack_shape_cycle_%lu", (unsigned long)n);
                finish(x, GBP_VSTATE_ANOMALY_POSTACK_SHAPE, res->reason_buf, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0;
            }
            cyc.intsr_postack = ps->intsr;
            if (res->k.main_pi_w1c) {
                cyc.main_w1c = 1; bump(res, &res->main_w1c);
                if (res->k.main_w1c_rc != GBP_OK) restore_fail(res, "main_pi_w1c_failed");
                if (bit13(res->k.main_w1c_intmr_after)) { finish(x, GBP_VSTATE_ANOMALY_MASK_FAILURE, "intmr13_set_PICLEAN", "S3_pi_sticky", GBP_VSTATE_STOP_FAILURE); return 0; }
                if (bit13(res->k.main_w1c_intsr_after)) { finish(x, GBP_VSTATE_ANOMALY_PI_STICKY, "pi_sticky_after_ack", "S3_pi_sticky", GBP_VSTATE_STOP_FAILURE); return 0; }
            }
        } else {
            uint32_t intsr = 0, intmr = 0;
            if (t->read_pi(t->ctx, &intsr, &intmr) != GBP_OK) { res->a.errors++; finish(x, GBP_VSTATE_ABORT_TRANSPORT, "piclean_read_failed", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
            cyc.intsr_postack = intsr;
            if (bit13(intmr)) { finish(x, GBP_VSTATE_ANOMALY_MASK_FAILURE, "intmr13_set_PICLEAN", "S3_pi_sticky", GBP_VSTATE_STOP_FAILURE); return 0; }
            if (bit13(intsr)) {
                if (!t->write_intsr) { finish(x, GBP_VSTATE_ANOMALY_PI_STICKY, "pi_set_after_ack_no_w1c_op", "S3_pi_sticky", GBP_VSTATE_STOP_FAILURE); return 0; }
                cyc.main_w1c = 1;
                bump(res, &res->main_w1c);
                if (t->write_intsr(t->ctx, GBP_PI_HSP_BIT) != GBP_OK) { res->a.errors++; restore_fail(res, "main_pi_w1c_failed"); }
                if (t->read_pi(t->ctx, &intsr, &intmr) != GBP_OK) { res->a.errors++; finish(x, GBP_VSTATE_ABORT_TRANSPORT, "piclean_reread_failed", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
                if (bit13(intsr)) { finish(x, GBP_VSTATE_ANOMALY_PI_STICKY, "pi_sticky_after_ack", "S3_pi_sticky", GBP_VSTATE_STOP_FAILURE); return 0; }
                if (bit13(intmr)) { finish(x, GBP_VSTATE_ANOMALY_MASK_FAILURE, "intmr13_set_PICLEAN", "S3_pi_sticky", GBP_VSTATE_STOP_FAILURE); return 0; }
            }
        }

        /* ---- SIGNATURE + STATE, between the ACK and the RE-ARM ----
         * That is where GBI does the equivalent work (FUN_8000BF30: read ->
         * drains -> ACK -> convert and checksum -> RE-ARM, the last device
         * access of the pass). It does not lengthen DMA->ACK and it does not
         * leave a latched cause waiting, because the re-arm is what invites
         * the next cause. The checksum NEVER runs inside the ISR. */
        if (cyc.video_selected && !cfg->bench_skip_signature) {
            const uint8_t *blk = gbp_vstate_video_target(st);
            uint8_t first4[4];
            uint32_t sig, c0, c1;
            if (!blk) { finish(x, GBP_VSTATE_ABORT_CAPACITY, "video_slot_lost", "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
            first4[0] = blk[0]; first4[1] = blk[1]; first4[2] = blk[2]; first4[3] = blk[3];
            c0 = now32(t);
            sig = gbp_vsig_block(blk, GBP_VSTATE_VIDEO_BLOCK_SIZE);
            c1 = now32(t);
            cyc.sig_ticks = (uint32_t)(c1 - c0);
            gbp_vstate_block(st, blk, GBP_VSTATE_VIDEO_BLOCK_SIZE, first4, now64(t), sig, cyc.sig_ticks, &step);
        }

        /* ---- REARM: IRQ := 0x0000, the last device access of the pass ---- */
        cyc.t_rearm = now64(t);
        res->a.irq_writes_attempted++;
        res->a.power_cycle_required = 1;
        gbp_regwrite_irq_u16(t, verify ? res->tag_rearm : "tag=REARM", res->a.base,
                             verify ? res->k.postack.irq_gbi : cyc.ack_value, 0x0000, &res->w_rearm, &res->a.errors);
        cyc.rc |= (uint32_t)(res->w_rearm.completed ? 0u : 1u) << 24;
        if (res->w_rearm.completed) { res->a.irq_writes_completed++; bump(res, &res->rearms); }
        if (verify) gbp_regwrite_log(log, &res->w_rearm);
        if (!res->w_rearm.completed) {
            res->uncertain_writes++;
            cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
            finish(x, GBP_VSTATE_REARM_WRITE_FAILED, "rearm_write_failed", "S4_rearm_failed", GBP_VSTATE_STOP_FAILURE);
            return 0;
        }
        t_ref32 = res->w_rearm.t_after;

        /* ---- WAIT_NEXT: masked, read-only ---- */
        {
            int got = wait_next(x, &cyc, t_ref32);
            t_cause_next = cyc.t_next;
            if (verify) res->verify_cycles_done++; else bump(res, &res->lean_cycles);
            /* the bounded records: the first cycles, a rolling window of the last ones, and every
             * cycle observed while an episode is open */
            if (n < GBP_VSTATE_CYC_FIRST) cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_FIRST);
            cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_LAST);
            if (st->episode_open || step.episode_opened || step.episode_closed) cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_EPISODE);
            if (!got) {
                res->next_cause_at_end = 0;
                finish(x, GBP_VSTATE_OBSERVATION_NO_NEXT_CAUSE, "no_next_cause_within_bound", "S5_no_next_cause", GBP_VSTATE_STOP_NO_NEXT_CAUSE);
                return 0;
            }
        }
    }
}

int gbp_vstate_summary(const struct gbp_vstate_result *res, char *dst, size_t cap)
{
    const struct gbp_initirqa_result *a = &res->a;
    const struct gbp_vstate *st = res->st;
    uint32_t tb = res->tb_hz ? res->tb_hz : 1u;
    return snprintf(dst, cap,
                    "DONE status=%s class=%s reason=%s stop=%s restore=%s restore_reason=%s teardown=%s verdict=%s det=%u/%u "
                    "service=%s service_reason=%s deliveries=%lu video=%lu/%lu audio=%lu frames=%lu complete=%lu incomplete=%lu resync=%lu "
                    "baseline=%s baseline_s=%lu.%03lu valid_s=%lu.%03lu capture_s=%lu.%03lu safety_s=%lu.%03lu target_s=%lu limit_s=%lu "
                    "structured=%s episodes=%lu stable=%lu unstable=%lu not_preserved=%lu episode_store_full=%d tail_frames=%lu tail_truncated=%d "
                    "frame_store_full=%d event_store_full=%d events=%lu boundaries_disc=%lu boundaries_gbi=%lu disagreements=%lu "
                    "reference_match=offline next_cause_at_end=%d handler=%d restored=%d mask_ok=%d isr_w1c=%lu main_w1c=%lu teardown_w1c=%lu "
                    "control_ok=%d pi_sticky_final=%d uncertain=%lu overflow=%lu arinfo_restore_ok=%d power_cycle_required=%d errors=%lu transport_ok=%d",
                    res->status_name, res->status_class, res->reason ? res->reason : "-", gbp_vstate_stop_name(res->stop),
                    res->restore_ok ? "ok" : "error", res->restore_reason ? res->restore_reason : "-",
                    res->teardown_variant ? res->teardown_variant : "-", gbp_verdict_name(a->det.verdict), a->det.vote_ok, a->det.run,
                    res->service_ok ? "ok" : "failed", res->service_reason ? res->service_reason : "-",
                    (unsigned long)res->deliveries, (unsigned long)res->video_completed, (unsigned long)res->video_drains,
                    (unsigned long)res->audio_drains,
                    (unsigned long)(st ? st->frames_n : 0u), (unsigned long)(st ? st->frames_complete : 0u),
                    (unsigned long)(st ? st->frames_incomplete : 0u), (unsigned long)(st ? st->resync_frames : 0u),
                    (st && st->baseline_valid) ? "valid" : "never_established",
                    (unsigned long)gbp_time64_seconds(tb, res->baseline_elapsed), (unsigned long)gbp_time64_millis_part(tb, res->baseline_elapsed),
                    (unsigned long)gbp_time64_seconds(tb, res->valid_observation_elapsed), (unsigned long)gbp_time64_millis_part(tb, res->valid_observation_elapsed),
                    (unsigned long)gbp_time64_seconds(tb, res->capture_elapsed), (unsigned long)gbp_time64_millis_part(tb, res->capture_elapsed),
                    (unsigned long)gbp_time64_seconds(tb, res->safety_elapsed), (unsigned long)gbp_time64_millis_part(tb, res->safety_elapsed),
                    (unsigned long)GBP_VSTATE_MIN_VALID_OBSERVATION_SECONDS, (unsigned long)GBP_VSTATE_HARD_WALLCLOCK_LIMIT_SECONDS,
                    (st && st->episode_count) ? "observed" : "not_observed",
                    (unsigned long)(st ? st->episode_count : 0u), (unsigned long)(st ? st->stable_episodes : 0u),
                    (unsigned long)(st ? st->unstable_episodes : 0u), (unsigned long)(st ? st->episodes_not_preserved : 0u),
                    st ? st->episode_store_full : 0, (unsigned long)(st ? st->tail_frames : 0u), st ? st->tail_truncated_by_cap : 0,
                    st ? st->frame_store_full : 0, st ? st->event_store_full : 0, (unsigned long)(st ? st->events_n : 0u),
                    (unsigned long)(st ? st->boundaries_disc : 0u), (unsigned long)(st ? st->boundaries_gbi : 0u),
                    (unsigned long)(st ? st->disagreements_total : 0u),
                    res->next_cause_at_end, res->h.handler_was_installed, res->h.handler_restored, res->h.mask_ok,
                    (unsigned long)res->isr_w1c, (unsigned long)res->main_w1c, (unsigned long)res->teardown_w1c,
                    res->control_ok, res->pi_sticky_final, (unsigned long)res->uncertain_writes, (unsigned long)res->counter_overflow,
                    a->arinfo_restore_ok, res->power_cycle_required, (unsigned long)res->errors, res->transport_ok);
}
