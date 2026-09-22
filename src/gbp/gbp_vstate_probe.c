#include "gbp_vstate_probe.h"
#include "gbp_vwitness_drive.h"
#include "gbp_awin.h"       /* Issue #59: the AUDIO window, NULL in every earlier build */

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
    cfg->prehandler_wait_ms = 0u;        /* the diagnostic is OFF unless a build asks for it */
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
    case GBP_VSTATE_OK_SESSION_ENDED: return "ok_session_ended";
    default: return "?";
    }
}

const char *gbp_vstate_status_class(gbp_vstate_status s)
{
    switch (s) {
    case GBP_VSTATE_OK_STRUCTURED_CHANGE_OBSERVED:
    case GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL:
    case GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE:
    case GBP_VSTATE_OK_SESSION_ENDED: return "ok";
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
    case GBP_VSTATE_STOP_COLOR_CERTIFIED: return "color_certified";
    case GBP_VSTATE_STOP_COLOR_SEARCH_WINDOW: return "color_search_window";
    case GBP_VSTATE_STOP_COLOR_FRAME_CAP: return "color_frame_cap";
    case GBP_VSTATE_STOP_WITNESS_TARGET: return "witness_target_reached";
    case GBP_VSTATE_STOP_WITNESS_STORE_FULL: return "witness_store_full";
    case GBP_VSTATE_STOP_SESSION_END: return "session_end";
    default: return "none";
    }
}

/*
 * The main status, exactly as §20 defines it, from the matrix and nothing
 * else. The classification keys on valid_observation_elapsed, NEVER on which
 * cap fired: a safety stop before the target is `ok_no_change_inconclusive`,
 * never `nominal_negative`.
 *
 * Issue #39: the ONE stop that is not a cap and not the scientific target --
 * the operator's session end -- is its own status, whatever the change
 * detector saw. An ended session is the run's normal end, and a game session
 * that opened episodes is not thereby "structured change observed".
 */
gbp_vstate_status gbp_vstate_main_status(const struct gbp_vstate_result *res)
{
    const struct gbp_vstate *st = res->st;
    if (!res->service_ok) return res->status;
    if (res->stop == GBP_VSTATE_STOP_SESSION_END) return GBP_VSTATE_OK_SESSION_ENDED;
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
    if (st && st->diags && st->diags_n) {
        /* AFTER the teardown, never before: the bytes come from preserved records,
         * never from a reconstruction, and tools/vstate.py explains them offline.
         * The first records are printed in full and the rest are summarised; the
         * sidecar carries all of them. */
        uint32_t di, shown = st->diags_n < GBP_VSTATE_DIAG_LOG_MAX ? st->diags_n : GBP_VSTATE_DIAG_LOG_MAX;
        char hex[GBP_BLOCK_SIZE * 2 + 1];
        for (di = 0; di < shown; di++) {
            const struct gbp_vstate_diag *d = &st->diags[di];
            ringlog_hex(hex, sizeof hex, d->raw, GBP_BLOCK_SIZE);
            ringlog_printf(log, "READDISAGREE i=%lu cycle=%lu read=%s class=%s t=%llx disc=%04x gbi=%04x "
                                "delta=%04x dx=%04x mx=%04x auth=%04x ack=%04x svc=%04x flags=%04x",
                           (unsigned long)di, (unsigned long)d->cycle, gbp_vstate_diag_read_name(d->read_kind),
                           gbp_vstate_class_name(d->classification), (unsigned long long)d->t,
                           (unsigned)d->disc_value, (unsigned)d->gbi_value, (unsigned)d->delta,
                           (unsigned)d->disc_extra_sources, (unsigned)d->majority_extra_sources,
                           (unsigned)d->authoritative_value, (unsigned)d->ack_value,
                           (unsigned)d->service_selected, (unsigned)d->record_flags);
            ringlog_printf(log, "READDISAGREERAW i=%lu raw=%s", (unsigned long)di, hex);
            ringlog_printf(log, "READDISAGREEPI i=%lu intsr=%08lx/%08lx intmr=%08lx ctl=%02x frame=%lu blk=%lu "
                                "lat=%lu xfer=%lu/%u dspcr=%04x/%04x",
                           (unsigned long)di, (unsigned long)d->intsr_entry, (unsigned long)d->intsr_after_w1c,
                           (unsigned long)d->intmr_entry, (unsigned)d->control_exp,
                           (unsigned long)d->frame_index, (unsigned long)d->block_in_frame,
                           (unsigned long)d->latency_ticks, (unsigned long)d->xfer_ticks,
                           (unsigned)d->xfer_polls, (unsigned)d->dma_status_before, (unsigned)d->dma_status);
            ringlog_printf(log, "READDISAGREEFU i=%lu fu=%s reason=%s t_ack=%llx t_rearm=%llx t_next=%llx "
                                "next=%04x/%04x gapmin=%lu gapn=%u pay=%04x/%08lx/%08lx",
                           (unsigned long)di, gbp_vstate_fu_name(d->followup_state),
                           gbp_vstate_fur_name(d->followup_reason),
                           (unsigned long long)d->t_ack, (unsigned long long)d->t_rearm,
                           (unsigned long long)d->t_next_cause, (unsigned)d->next_pending_gbi,
                           (unsigned)d->next_pending_disc, (unsigned long)d->gap_min_before_ticks,
                           (unsigned)d->gap_count_before, (unsigned)d->payload_source,
                           (unsigned long)d->payload_crc32, (unsigned long)d->payload_first_word);
        }
        if (st->diags_n > shown)
            ringlog_printf(log, "READDISAGREEMORE preserved=%lu shown=%lu (the sidecar carries every record)",
                           (unsigned long)st->diags_n, (unsigned long)shown);
    }
    if (st) {
        const struct gbp_vstate_semantic *m = &st->sem;
        unsigned k;
        ringlog_printf(log, "SEMANTIC total=%lu serviced=%lu other=%lu non_source=%lu disc_extra=%lu "
                            "maj_extra=%lu both=%lu mx_video=%lu mx_audio=%lu quarantined=%lu deferred=%lu",
                       (unsigned long)m->disagreements_total, (unsigned long)m->source_serviced,
                       (unsigned long)m->source_other, (unsigned long)m->non_source,
                       (unsigned long)m->disc_extra_events, (unsigned long)m->majority_extra_events,
                       (unsigned long)m->both_direction_events, (unsigned long)m->majority_extra_video_services,
                       (unsigned long)m->majority_extra_audio_services, (unsigned long)m->frames_quarantined,
                       (unsigned long)m->frames_source_deferred);
        ringlog_printf(log, "SEMANTIC2 preserved=%lu not_preserved=%lu capped=%lu fu_present=%lu fu_absent=%lu "
                            "fu_no_next=%lu fu_unknown=%lu observational=%lu service_sel=%lu payloads=%lu incomplete=%lu",
                       (unsigned long)m->diagnostics_preserved, (unsigned long)m->diagnostics_not_preserved,
                       (unsigned long)m->store_capped, (unsigned long)m->followup_present,
                       (unsigned long)m->followup_absent, (unsigned long)m->followup_no_next,
                       (unsigned long)m->followup_unknown, (unsigned long)m->observational_disagreements,
                       (unsigned long)m->service_selecting_disagreements,
                       (unsigned long)m->payload_diagnostics_captured, (unsigned long)m->service_incomplete_events);
        for (k = 0; k < GBP_VSTATE_GAP_SLOTS; k++) {
            const struct gbp_vstate_gap *g = &m->gap[k];
            if (!g->count && g->last_cause_t == 0u) continue;
            ringlog_printf(log, "SEMGAP src=%04x n=%lu min=%lu max=%lu last=%lu",
                           (unsigned)gbp_vstate_gap_slot_bit(k), (unsigned long)g->count,
                           (unsigned long)g->min_ticks, (unsigned long)g->max_ticks,
                           (unsigned long)g->last_ticks);
        }
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
    /* No record may reach the file as FU_PENDING (§R3.14): a record still waiting
     * is closed here, before the teardown, as NO_NEXT_CAUSE on a normal stop or
     * UNKNOWN/run_aborted when the run ended on a failure. RAM only. */
    if (x->st) gbp_vstate_diag_close(x->st, (unsigned)(stop == GBP_VSTATE_STOP_FAILURE));
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
static gbp_vstate_diag_handle capture_disagreement(struct run_ctx *x, uint32_t n, const uint8_t *raw,
                                                  uint16_t disc, uint16_t gbi, uint16_t kind,
                                                  unsigned classification,
                                                  const struct gbp_xfer_info *info)
{
    struct gbp_vstate_result *res = x->res;
    struct gbp_vstate *st = x->st;
    gbp_vstate_diag_handle idx;
    if (!st) return GBP_VSTATE_DIAG_INVALID;
    idx = gbp_vstate_diag_open(st, n, now64(x->t), raw, disc, gbi, kind, classification);
    res->semantic_disagreements = st->sem.disagreements_total;
    /* The context of THIS read, into the record this call just opened and named.
     * It goes through the same handle-taking setter as everything else: this
     * file never indexes the diagnostic store. */
    gbp_vstate_diag_context(st, idx, res->d.rec.intsr_before_ack, res->d.rec.intsr_after_ack,
                            res->d.rec.intmr_at_entry, res->d.latency_ticks, res->a.control_exp,
                            info);
    return idx;
}

/*
 * The normative order of §R3.6, in one place so it cannot drift: classify, then
 * refuse the classes that have no contract, then compose, then apply the pending
 * guard INDEPENDENTLY of the delta, and only then decide whether a disagreement
 * is survivable. Returns 1 to continue, 0 when the caller must abort with the
 * status and reason it fills in. `*authoritative` is always composed.
 */
static int semantic_gate(struct run_ctx *x, uint32_t n, const char *site, uint16_t kind,
                         const uint8_t *raw, uint16_t disc, uint16_t gbi,
                         const struct gbp_xfer_info *info, uint16_t *authoritative,
                         gbp_vstate_status *status, const char **reason,
                         gbp_vstate_diag_handle *opened)
{
    struct gbp_vstate_result *res = x->res;
    const struct gbp_vstate_config *cfg = x->cfg;
    unsigned cls = gbp_vstate_classify(disc, gbi);
    uint16_t unexpected;

    /* The handle of the record THIS read opens, if any. The caller decides what
     * it means: a service-selecting site keeps it for the whole transaction, an
     * observational site drops it, because an observational record receives no
     * current-cycle field at all (§R4.4, §R4.5). */
    if (opened) *opened = GBP_VSTATE_DIAG_INVALID;
    *authoritative = gbp_vstate_authoritative(disc, gbi);
    res->last_disc_extra = (uint16_t)((disc & GBP_VSTATE_SRC_MASK) & ~(gbi & GBP_VSTATE_SRC_MASK));
    res->last_majority_extra = (uint16_t)((gbi & GBP_VSTATE_SRC_MASK) & ~(disc & GBP_VSTATE_SRC_MASK));

    if (cls == GBP_VSTATE_DIS_NON_SOURCE || cls == GBP_VSTATE_DIS_SOURCE_OTHER) {
        /* Fatal: the record preserves the read and the transaction ends here, so
         * it never receives a service decision, an ACK or a re-arm (§R4.9). Its
         * handle is not published - there is no transaction left to own it. */
        (void)capture_disagreement(x, n, raw, disc, gbi, kind, cls, info);
        snprintf(res->reason_buf, sizeof res->reason_buf, "READ_%s_semantic_disagree_%s_cycle_%lu",
                 cls == GBP_VSTATE_DIS_NON_SOURCE ? "non_source" : "source_other",
                 site, (unsigned long)n);
        res->semantic_failed = 1;
        *status = GBP_VSTATE_ABORT_READ_INCONSISTENT;
        *reason = res->reason_buf;
        return 0;
    }

    /* The pending guard is NOT a consequence of the disagreement machinery: it
     * fires on the authoritative value whatever the delta is, including 0. A
     * source with no drain ends the run exactly as it always has. */
    unexpected = (uint16_t)(*authoritative & cfg->src_mask & (uint16_t)~cfg->av_mask);
    if (unexpected != 0u) {
        res->unexpected = unexpected;
        res->unexpected_site = site;
        res->unexpected_cycle = n;
        snprintf(res->reason_buf, sizeof res->reason_buf, "unexpected_source_%s_cycle_%lu",
                 site, (unsigned long)n);
        *status = GBP_VSTATE_ANOMALY_UNEXPECTED_SOURCE;
        *reason = res->reason_buf;
        return 0;
    }

    if (cls == GBP_VSTATE_DIS_SOURCE_SERVICED) {
        /* Survivable, counted, preserved. The run does not stop for it. */
        gbp_vstate_diag_handle h = capture_disagreement(x, n, raw, disc, gbi, kind, cls, info);
        if (opened) *opened = h;
    }
    return 1;
}

/* ---- snapshot checks of the verify cycles (as GBP-VIDEO-001) --------- */
static int common_checks(struct run_ctx *x, const struct gbp_initirqa_snapshot *s, const char *site, uint32_t n,
                         gbp_vstate_status *st, const char **reason, uint16_t *authoritative,
                         gbp_vstate_diag_handle *service_handle)
{
    struct gbp_vstate_result *res = x->res;
    uint16_t kind = (uint16_t)(strcmp(site, "PRESVC") == 0 ? GBP_VSTATE_DIAG_READ_PRESVC :
                               strcmp(site, "POSTDRAIN") == 0 ? GBP_VSTATE_DIAG_READ_POSTDRAIN :
                               strcmp(site, "POSTACK") == 0 ? GBP_VSTATE_DIAG_READ_POSTACK :
                               GBP_VSTATE_DIAG_READ_OTHER);
    uint16_t auth = 0u;
    gbp_vstate_diag_handle opened = GBP_VSTATE_DIAG_INVALID;
    note_control(res, s);
    if (!s->pi_ok || s->control_rc != GBP_OK || s->irq_rc != GBP_OK) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "%s_read_failed_cycle_%lu", site, (unsigned long)n);
        *st = GBP_VSTATE_ABORT_TRANSPORT; *reason = res->reason_buf; return 0;
    }
    /* The whole semantic policy, in the normative order, from the bytes this read
     * already delivered. No second read exists here or anywhere. */
    if (!semantic_gate(x, n, site, kind, s->irq, s->irq_disc, s->irq_gbi, &s->irq_info,
                       &auth, st, reason, &opened)) return 0;
    if (authoritative) *authoritative = auth;
    /* ONLY the PRESVC caller passes a service handle, because only PRESVC
     * selects the service of this transaction. A POSTDRAIN or POSTACK record is
     * complete when it is opened: it keeps its own read and claims nothing about
     * service, so its handle is deliberately dropped here (§R4.4). */
    if (service_handle) *service_handle = opened;
    if (s->control_vote != res->a.control_exp || s->control_vote != s->control_b1f) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "control_changed_%s_cycle_%lu", site, (unsigned long)n);
        *st = GBP_VSTATE_ANOMALY_CONTROL_CHANGED; *reason = res->reason_buf; return 0;
    }
    if (bit13(s->intmr) || (s->pi2_ok && bit13(s->intmr2))) {
        snprintf(res->reason_buf, sizeof res->reason_buf, "intmr13_set_%s_cycle_%lu", site, (unsigned long)n);
        *st = GBP_VSTATE_ANOMALY_MASK_FAILURE; *reason = res->reason_buf; return 0;
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

    res->target_s = cfg->min_valid_observation_s;
    res->limit_s = cfg->hard_wallclock_s;
    ringlog_printf(log, "VSTATE start test=GBP-VIDEO-002 target_s=%lu limit_s=%lu limit_ticks=%llx max_deliveries=%lu verify=%lu t_delivery_ms=%lu t_next_cause_ms=%lu",
                   (unsigned long)cfg->min_valid_observation_s, (unsigned long)cfg->hard_wallclock_s,
                   (unsigned long long)cfg->hard_wallclock_ticks, (unsigned long)cfg->max_deliveries,
                   (unsigned long)cfg->verify_cycles, (unsigned long)cfg->t_delivery_ms, (unsigned long)cfg->t_next_cause_ms);
    ringlog_printf(log, "VSTATE stores frames=%lu x %lu event=%lu x %lu episodes=%lu x %lu raw_ring=%lu x %lu audio_raw=%lu n_stable=%lu ep_max_frames=%lu required_bytes=%llu",
                   (unsigned long)GBP_VSTATE_MAX_FRAMES, (unsigned long)GBP_VSTATE_FRAME_REC,
                   (unsigned long)GBP_VSTATE_MAX_EVENTS, (unsigned long)GBP_VSTATE_EVENT_REC,
                   (unsigned long)GBP_VSTATE_MAX_EPISODES, (unsigned long)GBP_VSTATE_EPISODE_RAW_SLOTS,
                   (unsigned long)gbp_vstate_ring_slots(st), (unsigned long)GBP_VSTATE_RAW_FRAME_BYTES,
                   (unsigned long)GBP_VSTATE_AUDIO_RAW_SLOTS, (unsigned long)GBP_VSTATE_N_STABLE,
                   (unsigned long)GBP_VSTATE_EPISODE_MAX_FRAMES, (unsigned long long)gbp_vstate_required_capacity_bytes());
    /* THE ACTUAL CONFIGURATION, beside the requirement it must meet.
     *
     * The line above prints the model's CAPACITY CONSTANTS. `stream-0002` had
     * allocated a quarter of the frame table and no episode store at all, and
     * that line still read `frames=16384`: the log that should have exposed the
     * defect concealed it, and the run was lost to `store_or_bounds_invalid`
     * with no field named (HARDWARE_TESTS §V5.29.6). This line exists so that
     * can never happen twice — every capacity as CONFIGURED, the requirement
     * beside it, the configured total, and the first unmet field by name. */
    {
        const char *fault = gbp_vstate_storage_fault(st);
        ringlog_printf(log, "VSTATE storecfg frames=%lu/%lu events=%lu/%lu raw_ring=%lu/%lu slots=%lu/%lu episode_raw=%lu/%lu audio_raw=%lu/%lu configured_bytes=%llu required_bytes=%llu fault=%s",
                       (unsigned long)(st ? st->frames_cap : 0u), (unsigned long)GBP_VSTATE_MAX_FRAMES,
                       (unsigned long)(st ? st->events_cap : 0u), (unsigned long)GBP_VSTATE_MAX_EVENTS,
                       (unsigned long)(st ? st->raw_ring_cap : 0u), (unsigned long)GBP_VSTATE_RAW_RING_BYTES,
                       (unsigned long)(st ? st->raw_ring_slots : 0u), (unsigned long)GBP_VSTATE_RAW_RING_SLOTS_MIN,
                       (unsigned long)(st ? st->episode_raw_cap : 0u), (unsigned long)GBP_VSTATE_EPISODE_RAW_BYTES,
                       (unsigned long)(st ? st->audio_raw_cap : 0u), (unsigned long)GBP_VSTATE_AUDIO_RAW_BYTES,
                       (unsigned long long)gbp_vstate_configured_bytes(st),
                       (unsigned long long)gbp_vstate_required_capacity_bytes(),
                       fault ? fault : "-");
    }
    ringlog_printf(log, "VSTATE policy handler=003b_ext_installed_once record=reset_under_mask order=read_audio_video_ack_piclean_sign_rearm_waitnext checksum=between_ack_and_rearm oracle=offline_only early_positive_stop=none");
    ringlog_printf(log, "VSTATE caps frame_store=stops event_store=stops episode_raw_store=does_not_stop safety_epoch=t_control_transform precedence=fatal,safety,stores,target,no_next_cause,delivery");

    if (!st || !gbp_vstate_storage_ok(st)) {
        set_status(res, GBP_VSTATE_ABORT_STORE_UNAVAILABLE, "store_or_bounds_invalid");
        res->stop = GBP_VSTATE_STOP_FAILURE; res->stop_name = gbp_vstate_stop_name(res->stop);
        service_failed(res, "store_or_bounds_invalid");
        res->teardown_variant = "none";
        res->t_stop = now64(t);            /* a real reading: an unset field must never be reported as a time */
        /* The status stays `store_or_bounds_invalid` — it is the stable name of
         * this gate and nothing downstream may be re-keyed — but the FIELD is
         * now on the same line, because naming only the gate cost a physical
         * run (§V5.29.1). */
        ringlog_printf(log, "VSTATE abort reason=store_or_bounds_invalid field=%s",
                       gbp_vstate_storage_fault(st));
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
    memset(st->raw_ring, 0, (size_t)gbp_vstate_ring_slots(st) * GBP_VSTATE_RAW_FRAME_BYTES);
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
        /* The stage aborts before the service loop, so no record can exist here -
         * the stage's reads never reach semantic_gate(). The call is a no-op and
         * is made anyway, so "no record reaches the report as FU_PENDING" is a
         * structural property of every exit rather than an argument about one. */
        gbp_vstate_diag_close(st, 1u);
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

    /* ---- 1b. PRE-HANDLER MASKED WAIT - a DIAGNOSTIC, default OFF ----
     * Stage A has put CONTROL in the running shape, so the AGB is executing;
     * PI is still masked and NO handler exists, so nothing is being serviced and
     * nothing is in flight. This is the only point in the run with that
     * property, which is why it is both the question worth asking and the only
     * place a future operator ARM could sit.
     *
     * What happens here when the wait is zero: NOTHING. Not a read, not a log
     * line, not a branch beyond this test - the operation stream stays the one
     * vstate-0004 executed. What happens when it is non-zero: one read-only
     * snapshot either side, and a spin on the CPU time base in between. The spin
     * touches no device (now64() is the 64-bit time base, an mftb pair through
     * the transport, not a GBP access), allocates nothing, logs nothing and
     * cannot run forever - it exits on the time bound or on the iteration cap,
     * whichever comes first. A transport without a 64-bit clock never gets here
     * at all: the run already aborted with time64_unavailable. */
    res->prehandler_wait_ms = cfg->prehandler_wait_ms;
    if (cfg->prehandler_wait_ms) {
        /* The iteration cap is not decoration: it is what makes this loop finite
         * whatever the clock does. */
    uint64_t want = ((uint64_t)cfg->a.tb_hz * cfg->prehandler_wait_ms) / 1000u;
        uint64_t t0;
        uint32_t iters = 0;
        /* the state the wait STARTS from, read-only */
        gbp_initirqa_snapshot_take(t, &res->a, &res->waitpre, "WAITPRE", 0, 1);
        gbp_initirqa_snapshot_log(log, &res->a, &res->waitpre);
        note_control(res, &res->waitpre);
        t0 = now64(t);
        res->t_prehandler_wait_begin = t0;
        while (!gbp_time64_reached(t0, want, now64(t))) {
            if (++iters >= GBP_VSTATE_PREHANDLER_WAIT_MAX_ITERS) break;
        }
        res->t_prehandler_wait_end = now64(t);
        res->prehandler_wait_iters = iters;
        res->prehandler_wait_done = (iters >= GBP_VSTATE_PREHANDLER_WAIT_MAX_ITERS) ? -1 : 1;
        /* and the state it ENDS in: the whole point is whether these differ */
        gbp_initirqa_snapshot_take(t, &res->a, &res->waitpost, "WAITPOST", 0, 1);
        gbp_initirqa_snapshot_log(log, &res->a, &res->waitpost);
        note_control(res, &res->waitpost);
        /* TWO records, not one. The single combined line reached 266 characters on
         * the physical runs - the timestamps alone are 14 hex digits at 40.5 MHz -
         * and the logger cut it at its 255-character line, setting truncated=1 in
         * two physical logs (the vstate-prewait-5000 and color-0001 runs). Split
         * by subject, each half fits with room to spare at every field's maximum
         * width, and neither costs anything in the critical path: both are written
         * after the wait has ended and before the handler is installed. */
        ringlog_printf(log,
                       "PREHANDLERWAIT ms=%lu want_ticks=%llu begin=%llx end=%llx elapsed=%llu iters=%lu done=%d",
                       (unsigned long)cfg->prehandler_wait_ms, (unsigned long long)want,
                       (unsigned long long)res->t_prehandler_wait_begin,
                       (unsigned long long)res->t_prehandler_wait_end,
                       (unsigned long long)gbp_time64_delta(res->t_prehandler_wait_begin, res->t_prehandler_wait_end),
                       (unsigned long)iters, res->prehandler_wait_done);
        ringlog_printf(log,
                       "PREHANDLERWAITSTATE control_pre=%02x control_post=%02x irq_pre=%04x irq_post=%04x "
                       "intsr_pre=%08lx intsr_post=%08lx intmr_pre=%08lx intmr_post=%08lx",
                       (unsigned)res->waitpre.control_vote, (unsigned)res->waitpost.control_vote,
                       (unsigned)res->waitpre.irq_gbi, (unsigned)res->waitpost.irq_gbi,
                       (unsigned long)res->waitpre.intsr, (unsigned long)res->waitpost.intsr,
                       (unsigned long)res->waitpre.intmr, (unsigned long)res->waitpost.intmr);
    }

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
        uint16_t majority_extra = 0u;      /* sources selected ONLY by the majority */
        int video_majority_extra = 0;      /* this cycle's VIDEO block is quarantined */
        /* The ONE record this transaction owns (§R4.3). It is born INVALID,
         * receives a value only from the read that selects the service, is the
         * only handle any current-cycle setter below is given, and dies with the
         * iteration: nothing carries it into the next cycle, and no store member
         * mirrors it. */
        gbp_vstate_diag_handle service_handle = GBP_VSTATE_DIAG_INVALID;
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
            /* 3s. Issue #39: THE OPERATOR'S SESSION END. A SUCCESS, evaluated
             *     AFTER the safety budget (safety always wins: a run past its
             *     budget has gone wrong whatever the operator pressed) and
             *     AFTER the two store caps (a run that lost its bookkeeping at
             *     the same admission is reported as the cap it hit, never as a
             *     clean end), and BEFORE every other success. One flag read,
             *     no device access. With cfg->session_end NULL this block does
             *     not exist for any earlier build. */
            if (cfg->session_end && *cfg->session_end) {
                res->next_cause_at_end = 1;
                if (st->tail_active) gbp_vstate_tail_truncate(st, tnow);
                finish(x, GBP_VSTATE_OK_SESSION_ENDED, "-", "S5_session_end", GBP_VSTATE_STOP_SESSION_END);
                return 0;
            }
            /* 3a. GBP-VIDEO-004's indexed retention (§V5.39.3). It sits with the
             *     store caps for the same reason they do: a run that has lost
             *     its bookkeeping cannot support a conclusion. The two reasons
             *     are kept apart on purpose — reaching the target is the NORMAL
             *     end of the experiment, and overflowing the store is a design
             *     failure that must never be read as one. Overflow is checked
             *     FIRST so a run that somehow did both is reported as the
             *     failure it is. */
            if (cfg->witness) {
                if (gbp_vwitness_store_full(cfg->witness)) {
                    res->next_cause_at_end = 1;
                    if (st->tail_active) gbp_vstate_tail_truncate(st, tnow);
                    finish(x, GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE, "-", "S5_witness_store_full",
                           GBP_VSTATE_STOP_WITNESS_STORE_FULL);
                    return 0;
                }
                if (gbp_vwitness_target_reached(cfg->witness)) {
                    res->next_cause_at_end = 1;
                    if (st->tail_active) gbp_vstate_tail_truncate(st, tnow);
                    finish(x, GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE, "-", "S5_witness_target",
                           GBP_VSTATE_STOP_WITNESS_TARGET);
                    return 0;
                }
            }
            /* 3b. GBP-VIDEO-003's own stop conditions. They sit AFTER the safety
             *     budget and the store caps deliberately: safety always wins over
             *     success (§V3.12), and a run that fills a store has already lost
             *     the bookkeeping the evidence depends on. With cfg->color NULL
             *     this block does not exist for GBP-VIDEO-002. */
            if (cfg->color) {
                if (gbp_vcolor_done(cfg->color)) {
                    res->next_cause_at_end = 1;
                    finish(x, GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE, "-", "S5_color_certified",
                           GBP_VSTATE_STOP_COLOR_CERTIFIED);
                    return 0;
                }
                if (cfg->color->frames_total >= GBP_VCOLOR_MAX_FRAMES) {
                    /* FRAME_CAP: the capture's own bound, independent of the state
                     * model's much larger stores (§V3.12). It has its OWN stop
                     * reason: "the table filled" and "the clock ran out" are
                     * different observations and a reader must not have to guess
                     * which one a file records. */
                    res->next_cause_at_end = 1;
                    finish(x, GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE, "-", "S5_color_frame_cap",
                           GBP_VSTATE_STOP_COLOR_FRAME_CAP);
                    return 0;
                }
                if (!cfg->color->certified && cfg->color_search_ticks &&
                    gbp_time64_reached(res->t_capture_start, cfg->color_search_ticks, tnow)) {
                    res->next_cause_at_end = 1;
                    finish(x, GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE, "-", "S5_color_search_window",
                           GBP_VSTATE_STOP_COLOR_SEARCH_WINDOW);
                    return 0;
                }
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
        res->last_majority_extra = 0u; res->last_disc_extra = 0u;
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
            /* the follow-up of a record still waiting is filled from THIS read,
             * before anything else may open a new one (§R3.8) */
            (void)gbp_vstate_diag_followup(st, cyc.t_cause, res->presvc.irq_gbi, res->presvc.irq_disc);
            if (!common_checks(x, &res->presvc, "PRESVC", n, &status, &why, &pending, &service_handle)) { cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY); finish(x, status, why, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
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
            /* Close a record that was waiting on THIS read before any new record
             * can be opened from it: one read serves two roles and never fills
             * the wrong one (§R3.8). */
            (void)gbp_vstate_diag_followup(st, cyc.t_cause, gbi, disc);
            /* The 32 bytes are still exactly as the transport delivered them into
             * irq_raw; the gate copies them out before anything else touches the
             * cycle record or the reason string, and never reads the device. */
            if (!semantic_gate(x, n, "READ", GBP_VSTATE_DIAG_READ_LEAN, irq_raw, disc, gbi, &info,
                               &pending, &status, &why, &service_handle)) {
                cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
                finish(x, status, why, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE);
                return 0;
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
        /* The service decision of THIS transaction, written to the record this
         * transaction owns and to no other (§R4.6). `pending` is the composed
         * authoritative value of the read above, so the v5 invariant
         * service_selected == authoritative & AV_MASK holds by construction and
         * is checked offline against the raw bytes, never against this call. */
        gbp_vstate_diag_service(st, service_handle, pending, (uint16_t)(pending & cfg->av_mask), 0u);
        /* cause -> cause statistics, for every delivery, disagreements included.
         * Data only: no runtime decision reads them (§R3.28). */
        gbp_vstate_gap_observe(st, (uint16_t)(pending & cfg->src_mask), cyc.t_cause);
        /* Which of the selected sources exist ONLY because the majority carried a
         * bit the Disc reading did not. Empty in every ordinary cycle. */
        majority_extra = (uint16_t)(res->last_majority_extra & cfg->av_mask);
        if (res->last_disc_extra & cfg->video_src) {
            /* The Disc reading had VIDEO and the majority did not, so no VIDEO is
             * drained this cycle. Nothing is fabricated: the marker is descriptive
             * and the assembler's own rules decide what the short interval means. */
            if (gbp_vstate_mark_source_deferred(st)) gbp_vstate_diag_deferred(st, service_handle);
        }

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
            /* Issue #59 (GBP-AUDIO-001, §V8): the ONE extra thing the audio
             * window does, and it happens after the drain and its commit. With
             * cfg->awin NULL this block does nothing and costs one predictable
             * branch. Cost when armed: one 4096-byte copy in RAM, no device
             * access, no allocation, no filesystem, no clock of its own -- and
             * MEASURED here, the way the witness step has been since §V5.39. */
            if (cfg->awin) {
                uint32_t q0 = now32(t), q1;
                gbp_awin_block(cfg->awin, buf, cfg->audio_len, n, res->audio.completed);
                q1 = now32(t);
                gbp_awin_note_ticks(cfg->awin, (uint32_t)(q1 - q0));
            }
            cyc.audio_completed = (uint8_t)(res->audio.completed ? 1u : 0u);
            cyc.audio_wait = res->audio.info.ticks;
            cyc.rc |= (uint32_t)res->audio.rc;
            if (res->audio.completed) res->bytes_audio += cfg->audio_len;
            if ((majority_extra & cfg->audio_src) && res->audio.completed) {
                /* §R3.22: a completed drain gives a real CRC; a failed one is
                 * fatal by the existing transport rule and records no CRC. */
                gbp_vstate_diag_payload(st, service_handle, GBP_VSTATE_SRC_AUDIO, res->audio.crc32,
                                        res->audio.first_word);
            }
            if (verify) gbp_avblock_log_read(log, "AUDIOREAD", &res->audio);
            if (!res->audio.completed) {
                /* A source this cycle selected was not drained. The transaction
                 * ends here, so the flag is the record's last word about its own
                 * service; no ACK and no re-arm will follow it. */
                gbp_vstate_diag_service_incomplete(st, service_handle);
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
                gbp_vstate_diag_service_incomplete(st, service_handle);
                cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
                snprintf(res->reason_buf, sizeof res->reason_buf, "video_read_failed_cycle_%lu", (unsigned long)n);
                finish(x, dma_status(0, res->video.rc), res->reason_buf, "S3_dma_failed", GBP_VSTATE_STOP_FAILURE);
                return 0;
            }
            bump(res, &res->video_completed);
            res->bytes_video += cfg->video_len;
            if (majority_extra & cfg->video_src) {
                /* §R3.11/§R3.12: this block exists only because of the majority.
                 * Its provenance travels with it into the assembler so the frame
                 * that consumes it can be quarantined. */
                video_majority_extra = 1;
                gbp_vstate_diag_payload(st, service_handle, GBP_VSTATE_SRC_VIDEO, res->video.crc32,
                                        res->video.first_word);
            }
        }

        /* ---- POSTDRAIN (verify cycles only) ---- */
        if (verify) {
            gbp_initirqa_snapshot_take(t, &res->a, &res->postdrain, res->id_postdrain, 0, 1);
            gbp_initirqa_snapshot_log(log, &res->a, &res->postdrain);
            if (!common_checks(x, &res->postdrain, "POSTDRAIN", n, &status, &why, 0, 0)) { finish(x, status, why, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
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
            /* No ACK happened. The record keeps ACK_WRITTEN clear and its t_ack
             * and ack_value at the documented invalid encoding (zero), so the
             * file can never be read as though this cycle had acknowledged. */
            res->uncertain_writes++;
            cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
            finish(x, GBP_VSTATE_ACK_WRITE_FAILED, "ack_write_failed", "S4_ack_failed", GBP_VSTATE_STOP_FAILURE);
            return 0;
        }
        /* The ACK of the transaction that owns `service_handle`, recorded only
         * after the write completed: a flag that tracked the intention rather
         * than the write would be the same class of claim this revision removes. */
        gbp_vstate_diag_ack(st, service_handle, cyc.ack_value, cyc.t_ack);
        bump(res, &res->acks);

        /* ---- PICLEAN: at most one main-loop W1C ---- */
        if (verify) {
            const struct gbp_initirqa_snapshot *ps = &res->k.postack;
            if (!common_checks(x, ps, "POSTACK", n, &status, &why, 0, 0)) { finish(x, status, why, "S3_service_aborted", GBP_VSTATE_STOP_FAILURE); return 0; }
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
            if (video_majority_extra) { gbp_vstate_block_majority_extra(st); gbp_vstate_diag_quarantined(st, service_handle); }
            gbp_vstate_block(st, blk, GBP_VSTATE_VIDEO_BLOCK_SIZE, first4, now64(t), sig, cyc.sig_ticks, &step);
            /* ---- GBP-VIDEO-004 OGBPIDX1 WITNESS RETENTION (§V5.39.4) ----
             *
             * SOURCE LAYER, and deliberately ABOVE the two publication hooks
             * below: what is retained must not depend on what the consumer was
             * willing to accept. Quarantined, anomalous, incomplete and resync
             * frames are all preserved here, because a source-continuity claim
             * built from a consumer-filtered population would be worthless.
             *
             * The ORDER is dictated by the assembler, never guessed: it reports
             * whether the block it just accumulated belongs to the frame that
             * closed in this same call (the 48-block give-up) or to the one that
             * is now opening (a boundary). Recomputing that decision here is
             * exactly the kind of duplicated state machine that drifts silently.
             *
             * Cost: 54 word extractions and one 108-byte placement, in RAM, with
             * no device access, no allocation, no filesystem and no branch on
             * anything the device did. It is MEASURED, not asserted. */
            if (cfg->witness) {
                uint32_t w0 = now32(t), w1;
                gbp_vwitness_step(cfg->witness, st, &step);
                w1 = now32(t);
                gbp_vwitness_note_ticks(cfg->witness, (uint32_t)(w1 - w0));
            }
            /* GBP-VIDEO-003 (§V3.23): the ONE extra thing the colour capture
             * does per cycle, and it happens only when a frame closed.
             *
             * BOUNDED BY CONSTRUCTION. What crosses into this window is a frame
             * RECORD and a SLOT INDEX - an integer. `gbp_vstate_closed_frame_slot`
             * forms no pointer into the ring and reads no frame byte, and the
             * capture's whole cost is an eligibility test plus at most 40 word
             * comparisons. The 153 600-byte memcmp/memcpy the first
             * implementation did here is gone; the certified bytes are read
             * once, after the teardown, straight out of the ring.
             *
             * No device access, no second read, no clock read of its own. */
            if (cfg->color && step.frame_closed && st->frames_n > 0u) {
                uint32_t fr_blocks = 0u;
                int fr_slot = gbp_vstate_closed_frame_slot(st, &fr_blocks);
                const struct gbp_vstate_frame *fr = &st->frames[st->frames_n - 1u];
                if (fr_blocks != GBP_VCOLOR_BLOCKS) fr_slot = -1;
                (void)gbp_vcolor_frame(cfg->color, fr, fr_slot, now64(t));
            }
            /* GBP-VIDEO-004 (§V5.7): the streaming publish, the same shape and
             * the same cost class as the colour hook above. It classifies
             * integers the assembler already computed and writes one small
             * descriptor. It reads NO frame byte, forms no pointer into the
             * ring, reads no clock of its own (the frame's own timestamps are
             * used) and cannot block. A consumer that is behind loses a frame
             * here; the device never waits for it. */
            if (cfg->stream && step.frame_closed && st->frames_n > 0u) {
                uint32_t fr_blocks = 0u;
                int fr_slot = gbp_vstate_closed_frame_slot(st, &fr_blocks);
                const struct gbp_vstate_frame *fr = &st->frames[st->frames_n - 1u];
                (void)gbp_vqueue_publish(cfg->stream, fr->index, fr_blocks, fr->flags,
                                         fr_slot, fr->t_first_block, fr->t_last_block);
            }
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
            /* No re-arm happened, so no next cause was ever invited: the record
             * keeps REARM_WRITTEN clear, t_rearm stays at the invalid encoding,
             * and it does NOT become a follow-up waiter. The teardown closes it
             * as FU_UNKNOWN / run_aborted. */
            res->uncertain_writes++;
            cycle_record(x, &cyc, GBP_VSTATE_CYC_KIND_ANOMALY);
            finish(x, GBP_VSTATE_REARM_WRITE_FAILED, "rearm_write_failed", "S4_rearm_failed", GBP_VSTATE_STOP_FAILURE);
            return 0;
        }
        /* The re-arm of the transaction that owns `service_handle`, then the ONE
         * place a follow-up waiter is armed (§R4.6). From here the record's
         * current-cycle fields are final; only the follow-up block, written
         * through the separate waiter, may still change - once. */
        gbp_vstate_diag_rearm(st, service_handle, cyc.t_rearm);
        (void)gbp_vstate_diag_arm_followup(st, service_handle);
        service_handle = GBP_VSTATE_DIAG_INVALID;   /* the transaction's handle dies here */
        t_ref32 = res->w_rearm.t_after;

        /* GBP-VIDEO-004 (§V5.7, §V5.26): the consumer's slice, and the only place
         * it may run in a single-threaded probe. The RE-ARM above was the pass's
         * last device access, so nothing on the device is waiting for US here —
         * but the pre-hardware audit measured the RE-ARM→next-cause window at
         * 1.9 us on 34 % of physical cycles, which means the next cause is
         * usually ALREADY LATCHED at this point.
         *
         * So the cause is read first and the slice runs only when nothing is
         * waiting. One extra `poll_intsr` per cycle buys that priority; the
         * value is also recorded either side of the slice so the first physical
         * run can measure what the consumer cost, instead of assuming it.
         *
         * With no stream configured none of this exists and the operation
         * stream vstate-0004 executed is unchanged. */
        if (cfg->stream) {
            uint32_t intsr_pre = 0, intsr_post = 0;
            int pending_pre = 0, pending_post = 0;
            if (t->poll_intsr(t->ctx, &intsr_pre) == GBP_OK)
                pending_pre = (intsr_pre & GBP_PI_HSP_BIT) ? 1 : 0;
            gbp_vqueue_pump(cfg->stream, pending_pre);
            if (!pending_pre) {
                if (t->poll_intsr(t->ctx, &intsr_post) == GBP_OK)
                    pending_post = (intsr_post & GBP_PI_HSP_BIT) ? 1 : 0;
                if (pending_post) {
                    cfg->stream->cause_pending_after_pump++;
                    /* Defined mechanically and claiming nothing more: it was not
                     * pending before the slice and it is pending after. */
                    cfg->stream->cause_arrived_during_pump++;
                }
            }
        }

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
                    (unsigned long)res->target_s, (unsigned long)res->limit_s,
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
