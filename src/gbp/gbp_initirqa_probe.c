#include "gbp_initirqa_probe.h"

#include <stdio.h>
#include <string.h>
#include "gbp_rawlog.h"

/* Defaults for the GameCube: 40.5 MHz time base. */
#define DEFAULT_TB_HZ 40500000u

static const uint32_t DEFAULT_A1_US[GBP_INITIRQA_MAX_A1_OBS] = { 50u, 500u };
static const uint32_t DEFAULT_A2_US[GBP_INITIRQA_MAX_A2_OBS] = { 50u, 500u, 5000u, 50000u, 500000u, 2000000u };

static uint32_t us_to_ticks(uint32_t tb_hz, uint32_t us)
{
    return (uint32_t)(((uint64_t)tb_hz * us) / 1000000u);
}

static void obs_id(char *dst, size_t cap, const char *phase, uint32_t us)
{
    if (us >= 1000u && (us % 1000u) == 0u) snprintf(dst, cap, "%s-%luMS", phase, (unsigned long)(us / 1000u));
    else snprintf(dst, cap, "%s-%luUS", phase, (unsigned long)us);
}

void gbp_initirqa_config_timebase(struct gbp_initirqa_config *cfg, uint32_t tb_hz)
{
    unsigned k;
    cfg->tb_hz = tb_hz;
    for (k = 0; k < GBP_INITIRQA_MAX_A1_OBS; k++) {
        cfg->a1_obs_ticks[k] = us_to_ticks(tb_hz, cfg->a1_obs_us[k]);
        obs_id(cfg->a1_obs_id[k], GBP_INITIRQA_ID_LEN, "A1", cfg->a1_obs_us[k]);
    }
    for (k = 0; k < GBP_INITIRQA_MAX_A2_OBS; k++) {
        cfg->a2_obs_ticks[k] = us_to_ticks(tb_hz, cfg->a2_obs_us[k]);
        obs_id(cfg->a2_obs_id[k], GBP_INITIRQA_ID_LEN, "A2", cfg->a2_obs_us[k]);
    }
    cfg->t_max_ms = cfg->n_a2_obs ? cfg->a2_obs_us[cfg->n_a2_obs - 1u] / 1000u : 0u;
}

void gbp_initirqa_config_default(struct gbp_initirqa_config *cfg)
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
    cfg->irq_req_masks = 0x0AAA;
    cfg->irq_req_set = 0x8000;
    cfg->irq_req_clear = 0x7000;
    cfg->ack_or = 0x8000;
    cfg->stop_or = 0x8AAA;
    memcpy(cfg->a1_obs_us, DEFAULT_A1_US, sizeof cfg->a1_obs_us);
    cfg->n_a1_obs = GBP_INITIRQA_MAX_A1_OBS;
    memcpy(cfg->a2_obs_us, DEFAULT_A2_US, sizeof cfg->a2_obs_us);
    cfg->n_a2_obs = GBP_INITIRQA_MAX_A2_OBS;
    cfg->poll_between = 1;
    cfg->end_window_on_event = 1;
    gbp_initirqa_config_timebase(cfg, DEFAULT_TB_HZ);
}

const char *gbp_initirqa_status_name(gbp_initirqa_status s)
{
    switch (s) {
    case GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED: return "ok_no_pi_cause_observed";
    case GBP_INITIRQA_OK_PI_CAUSE_OBSERVED: return "ok_pi_cause_observed";
    case GBP_INITIRQA_ABORT_ARINFO: return "abort_arinfo";
    case GBP_INITIRQA_ABORT_NOT_PRESENT: return "abort_not_present";
    case GBP_INITIRQA_ABORT_INCONSISTENT: return "abort_inconsistent";
    case GBP_INITIRQA_ABORT_PI_PRECONDITION: return "abort_pi_precondition";
    case GBP_INITIRQA_ABORT_CONTROL_READ: return "abort_control_read";
    case GBP_INITIRQA_ABORT_CONTROL_SHAPE: return "abort_control_shape";
    case GBP_INITIRQA_ABORT_IRQ_SHAPE: return "abort_irq_shape";
    case GBP_INITIRQA_ABORT_TRANSPORT: return "abort_transport";
    default: return "?";
    }
}

int gbp_initirqa_irq_shape(const struct gbp_initirqa_config *cfg, uint16_t disc, uint16_t gbi, const char **reason)
{
    /* Both readings must agree (byte 0 is part of neither); the vote is the value used. */
    if (disc != gbi) { *reason = "irq_ambiguous"; return 0; }
    if ((gbi & cfg->irq_req_masks) != cfg->irq_req_masks) { *reason = "irq_masks_not_set"; return 0; }
    if ((gbi & cfg->irq_req_set) != cfg->irq_req_set) { *reason = "irq_bit15_clear"; return 0; }
    if ((gbi & cfg->irq_req_clear) != 0) { *reason = "irq_high_bits_set"; return 0; }
    *reason = "-";
    return 1;
}

static uint32_t now(const struct gbp_transport *t)
{
    return t->ticks ? t->ticks(t->ctx) : 0u;
}

static uint32_t ticks_to_us(const struct gbp_initirqa_config *cfg, uint32_t ticks)
{
    if (!cfg->tb_hz) return 0u;
    return (uint32_t)(((uint64_t)ticks * 1000000u) / cfg->tb_hz);
}

static void restore_fail(struct gbp_initirqa_result *res, const char *why)
{
    if (res->restore_ok) res->restore_reason = why;
    res->restore_ok = 0;
}

static void note_intsr13(struct gbp_initirqa_result *res, uint32_t tnow, uint32_t intsr, const char *phase, unsigned polls)
{
    if (res->intsr13_seen) return;
    res->intsr13_seen = 1;
    res->t_first_intsr13 = tnow;
    res->first_intsr13_value = intsr;
    res->first_intsr13_phase = phase;
    res->polls_at_first_intsr13 = polls;
}

/* ---- quiet capture (no formatting) ----------------------------------- */

static void read_irq_quiet(const struct gbp_transport *t, struct gbp_initirqa_result *res, struct gbp_initirqa_irqread *r)
{
    memset(r, 0, sizeof *r);
    r->taken = 1;
    r->rc = t->read_block(t->ctx, gbp_block_addr(res->base, GBP_IDX_IRQ, 0), r->raw, &r->info);
    if (r->rc != GBP_OK) res->errors++;
    r->disc = gbp_irq_value_disc(r->raw);
    r->gbi = gbp_irq_value_gbi(r->raw);
}

/* One snapshot: PI, CONTROL raw, IRQ raw (+ TEST raw). `have_tnow`: the
 * caller already read the time base (deadline loops); else read it here. */
static struct gbp_initirqa_snapshot *take_snapshot(const struct gbp_transport *t, struct gbp_initirqa_result *res,
                                                   unsigned slot, const char *id, int have_tnow, uint32_t tnow,
                                                   int with_test, unsigned polls_before)
{
    struct gbp_initirqa_snapshot *s = &res->snap[slot];
    memset(s, 0, sizeof *s);
    s->id = id;
    s->taken = 1;
    s->ticks = have_tnow ? tnow : now(t);
    s->since_control = res->control_written ? (uint32_t)(s->ticks - res->t_control) : 0u;
    s->since_a1 = res->w_a1.attempted ? (uint32_t)(s->ticks - res->t_a1) : 0u;
    s->since_a2 = res->w_a2.attempted ? (uint32_t)(s->ticks - res->t_a2) : 0u;
    s->polls_before = polls_before;
    if (t->read_pi) {
        s->pi_rc = t->read_pi(t->ctx, &s->intsr, &s->intmr);
        s->pi_ok = (s->pi_rc == GBP_OK) ? 1 : 0;
    } else {
        s->pi_rc = GBP_ERR_BACKEND;
        s->pi_ok = 0;
    }
    if (!s->pi_ok) res->errors++;
    s->control_rc = t->read_block(t->ctx, gbp_block_addr(res->base, GBP_IDX_CONTROL, 0), s->control, &s->control_info);
    if (s->control_rc != GBP_OK) res->errors++;
    s->control_vote = gbp_majority_vote_byte(s->control);
    s->control_b1f = s->control[GBP_BLOCK_SIZE - 1u];
    s->irq_rc = t->read_block(t->ctx, gbp_block_addr(res->base, GBP_IDX_IRQ, 0), s->irq, &s->irq_info);
    if (s->irq_rc != GBP_OK) res->errors++;
    s->irq_disc = gbp_irq_value_disc(s->irq);
    s->irq_gbi = gbp_irq_value_gbi(s->irq);
    if (with_test) {
        s->has_test = 1;
        s->test_rc = t->read_block(t->ctx, gbp_block_addr(res->base, GBP_IDX_TEST, 0), s->test, &s->test_info);
        if (s->test_rc != GBP_OK) res->errors++;
    }
    if (res->control_written && s->pi_ok && (s->intsr & GBP_PI_HSP_BIT)) note_intsr13(res, s->ticks, s->intsr, id, polls_before);
    return s;
}

/* ---- formatting (after the fact) -------------------------------------- */

static void log_snapshot(struct ringlog *log, const struct gbp_initirqa_result *res, const struct gbp_initirqa_snapshot *s)
{
    char tag[24];
    if (!s->taken) return;
    if (s->is_event)
        ringlog_printf(log, "SNAP tag=%s ticks=%lu since_control=%lu since_a1=%lu since_a2=%lu polls_before=%u poll_intsr=%08lx",
                       s->id, (unsigned long)s->ticks, (unsigned long)s->since_control, (unsigned long)s->since_a1,
                       (unsigned long)s->since_a2, s->polls_before, (unsigned long)s->poll_intsr);
    else
        ringlog_printf(log, "SNAP tag=%s ticks=%lu since_control=%lu since_a1=%lu since_a2=%lu polls_before=%u",
                       s->id, (unsigned long)s->ticks, (unsigned long)s->since_control, (unsigned long)s->since_a1,
                       (unsigned long)s->since_a2, s->polls_before);
    snprintf(tag, sizeof tag, "tag=%s", s->id);
    gbp_rawlog_log_pi(log, tag, s->pi_ok ? "ok" : (s->pi_rc == GBP_ERR_BACKEND && !s->intsr && !s->intmr ? gbp_status_name(s->pi_rc) : gbp_status_name(s->pi_rc)),
                      s->intsr, s->intmr);
    gbp_rawlog_log_block(log, s->id, gbp_block_addr(res->base, GBP_IDX_CONTROL, 0), GBP_IDX_CONTROL, s->control_rc, &s->control_info, s->control);
    gbp_rawlog_log_block(log, s->id, gbp_block_addr(res->base, GBP_IDX_IRQ, 0), GBP_IDX_IRQ, s->irq_rc, &s->irq_info, s->irq);
    if (s->has_test)
        gbp_rawlog_log_block(log, s->id, gbp_block_addr(res->base, GBP_IDX_TEST, 0), GBP_IDX_TEST, s->test_rc, &s->test_info, s->test);
}

static void log_irqread(struct ringlog *log, const struct gbp_initirqa_result *res, const char *tag, const struct gbp_initirqa_irqread *r)
{
    if (!r->taken) return;
    gbp_rawlog_log_block(log, tag, gbp_block_addr(res->base, GBP_IDX_IRQ, 0), GBP_IDX_IRQ, r->rc, &r->info, r->raw);
}

static void log_irq_shape(struct ringlog *log, const struct gbp_initirqa_config *cfg, const char *tag,
                          uint16_t disc, uint16_t gbi, int ok, const char *reason)
{
    ringlog_printf(log, "IRQSHAPE tag=%s disc=%04x gbi=%04x agree=%d masks_ok=%d bit15_ok=%d high_ok=%d req_masks=%04x req_set=%04x req_clear=%04x ok=%d reason=%s",
                   tag, (unsigned)disc, (unsigned)gbi, disc == gbi ? 1 : 0,
                   ((gbi & cfg->irq_req_masks) == cfg->irq_req_masks) ? 1 : 0,
                   ((gbi & cfg->irq_req_set) == cfg->irq_req_set) ? 1 : 0,
                   ((gbi & cfg->irq_req_clear) == 0) ? 1 : 0,
                   (unsigned)cfg->irq_req_masks, (unsigned)cfg->irq_req_set, (unsigned)cfg->irq_req_clear, ok, reason);
}

/* Everything captured inside the experimental region, in the order it happened. */
static void flush_window(struct ringlog *log, const struct gbp_initirqa_config *cfg, struct gbp_initirqa_result *res)
{
    unsigned k;
    if (!res->window_entered) return;
    res->log_count_window_end = log->count;
    log_irqread(log, res, "A1PRE", &res->irq_a1pre);
    if (res->irq_shape_a1pre_ok != -1)
        log_irq_shape(log, cfg, "A1PRE", res->irq_a1pre.disc, res->irq_a1pre.gbi, res->irq_shape_a1pre_ok,
                      res->irq_shape_a1pre_ok ? "-" : res->irq_shape_reason);
    if (res->w_a1.attempted) {
        ringlog_printf(log, "A1 before=%04x ack_or=%04x ack_value=%04x formula=read|ack_or", (unsigned)res->w_a1.before,
                       (unsigned)cfg->ack_or, (unsigned)res->ack_value);
        gbp_regwrite_log(log, &res->w_a1);
    }
    log_snapshot(log, res, &res->snap[GBP_INITIRQA_SNAP_A1_0]);
    for (k = 0; k < res->a1_obs_taken; k++) log_snapshot(log, res, &res->snap[GBP_INITIRQA_SNAP_A1_OBS + k]);
    if (res->w_a1.completed)
        ringlog_printf(log, "WINDOW tag=A1 deadlines=%u/%u polls=%u poll_errors=%u intsr13_seen=%d no_timebase=%d",
                       res->a1_obs_taken, cfg->n_a1_obs, res->a1_polls, res->poll_errors, res->intsr13_seen, res->no_timebase);
    if (res->irq_a2pre.taken) {
        log_irqread(log, res, "A2PRE", &res->irq_a2pre);
        gbp_rawlog_log_pi(log, "tag=A2PRE", res->a2pre_pi_ok ? "ok" : "fail", res->a2pre_intsr, res->a2pre_intmr);
        ringlog_printf(log, "A2CHK irq_rc=%s pi_ok=%d intsr13=%u intmr13=%u ok=%d", gbp_status_name(res->irq_a2pre.rc), res->a2pre_pi_ok,
                       (res->a2pre_intsr & GBP_PI_HSP_BIT) ? 1u : 0u, (res->a2pre_intmr & GBP_PI_HSP_BIT) ? 1u : 0u,
                       (res->irq_a2pre.rc == GBP_OK && res->a2pre_pi_ok && !(res->a2pre_intmr & GBP_PI_HSP_BIT)) ? 1 : 0);
    }
    if (res->w_a2.attempted) {
        ringlog_printf(log, "A2 before=%04x value=0000 formula=zero", (unsigned)res->w_a2.before);
        gbp_regwrite_log(log, &res->w_a2);
    }
    log_snapshot(log, res, &res->snap[GBP_INITIRQA_SNAP_A2_0]);
    for (k = 0; k < res->n_a2_order; k++) log_snapshot(log, res, &res->snap[res->a2_order[k]]);
    if (res->w_a2.completed) {
        uint32_t elapsed = (uint32_t)(res->t_window_end - res->t_a2);
        ringlog_printf(log, "WINDOW tag=A2 deadlines=%u/%u polls=%u poll_errors=%u ended_early=%d event=%d t_event=%lu intsr13_seen=%d t_end=%lu elapsed_ticks=%lu elapsed_us=%lu no_timebase=%d",
                       res->a2_obs_taken, cfg->n_a2_obs, res->a2_polls, res->poll_errors, res->window_ended_early,
                       res->event_taken, (unsigned long)res->t_event, res->intsr13_seen, (unsigned long)res->t_window_end,
                       (unsigned long)elapsed, (unsigned long)ticks_to_us(cfg, elapsed), res->no_timebase);
    }
    ringlog_printf(log, "REGION log_count_start=%lu log_count_end=%lu formatted_inside=%lu", (unsigned long)res->log_count_window_start,
                   (unsigned long)res->log_count_window_end, (unsigned long)(res->log_count_window_end - res->log_count_window_start));
}

/* ---- deadline loops (no formatting, no DMA between the samples) ------- */

static void wait_phase(const struct gbp_transport *t, const struct gbp_initirqa_config *cfg,
                       struct gbp_initirqa_result *res, int phase)
{
    uint32_t t0 = (phase == 1) ? res->t_a1 : res->t_a2;
    unsigned n = (phase == 1) ? cfg->n_a1_obs : cfg->n_a2_obs;
    const uint32_t *dl = (phase == 1) ? cfg->a1_obs_ticks : cfg->a2_obs_ticks;
    unsigned *polls = (phase == 1) ? &res->a1_polls : &res->a2_polls;
    unsigned slot0 = (phase == 1) ? GBP_INITIRQA_SNAP_A1_OBS : GBP_INITIRQA_SNAP_A2_OBS;
    unsigned k;
    uint32_t tnow, intsr;
    int can_poll = (cfg->poll_between && t->poll_intsr) ? 1 : 0;

    if (!t->ticks) { res->no_timebase = 1; return; }
    if (n > ((phase == 1) ? (unsigned)GBP_INITIRQA_MAX_A1_OBS : (unsigned)GBP_INITIRQA_MAX_A2_OBS)) return;
    for (k = 0; k < n; k++) {
        for (;;) {
            tnow = now(t);
            if (can_poll) {
                if (t->poll_intsr(t->ctx, &intsr) == GBP_OK) {
                    (*polls)++;
                    if (intsr & GBP_PI_HSP_BIT) {
                        note_intsr13(res, tnow, intsr, (phase == 1) ? "A1" : "A2", *polls);
                        if (phase == 2 && !res->event_taken) {
                            struct gbp_initirqa_snapshot *s;
                            res->event_taken = 1;
                            res->t_event = tnow;
                            s = take_snapshot(t, res, GBP_INITIRQA_SNAP_EVENT, "EVENT", 1, tnow, 0, *polls);
                            s->is_event = 1;
                            s->poll_intsr = intsr;
                            res->a2_order[res->n_a2_order++] = GBP_INITIRQA_SNAP_EVENT;
                            if (cfg->end_window_on_event) { res->window_ended_early = 1; return; }
                        }
                    }
                } else {
                    res->poll_errors++;
                }
            }
            if ((uint32_t)(tnow - t0) >= dl[k]) break;
        }
        take_snapshot(t, res, slot0 + k, (phase == 1) ? cfg->a1_obs_id[k] : cfg->a2_obs_id[k], 1, tnow, 0, *polls);
        if (phase == 1) res->a1_obs_taken++;
        else { res->a2_obs_taken++; res->a2_order[res->n_a2_order++] = slot0 + k; }
    }
}

/* Writes that were issued but whose completion the transport did not
 * report: the device may or may not have taken them (state uncertain). */
static unsigned count_uncertain(const struct gbp_initirqa_result *res)
{
    const struct gbp_regwrite_result *w[5];
    unsigned i, n = 0;
    w[0] = &res->w_ctl_exp; w[1] = &res->w_a1; w[2] = &res->w_a2; w[3] = &res->w_stop; w[4] = &res->w_ctl_restore;
    for (i = 0; i < 5; i++) if (w[i]->attempted && !w[i]->completed) n++;
    return n;
}

/* ---- teardown, PI still masked --------------------------------------- */

static void teardown(const struct gbp_transport *t, struct ringlog *log, const struct gbp_initirqa_config *cfg,
                     struct gbp_initirqa_result *res)
{
    int any_exp = (res->control_written || res->irq_writes_attempted) ? 1 : 0;
    uint32_t intsr = 0, intmr = 0;
    gbp_status rc;

    ringlog_printf(log, "TEARDOWN start control_written=%d irq_attempted=%u irq_completed=%u uncertain_writes=%u intsr13_seen=%d pi_policy=never_unmasked",
                   res->control_written, res->irq_writes_attempted, res->irq_writes_completed, count_uncertain(res), res->intsr13_seen);

    /* 1. CONTROL back to the ORIGINAL semantic value (GBI layout), then readback */
    if (res->control_written) {
        gbp_regwrite_control_byte(t, "tag=RESTORE", res->base, res->control_orig, &res->w_ctl_restore, &res->errors);
        gbp_regwrite_log(log, &res->w_ctl_restore);
        res->control_restore_read_rc = gbp_rawlog_read_block(t, log, "TDCTL", res->base, GBP_IDX_CONTROL, res->control_restore_raw, &res->errors);
        res->control_restore_vote = gbp_majority_vote_byte(res->control_restore_raw);
        res->control_restore_b1f = res->control_restore_raw[GBP_BLOCK_SIZE - 1u];
        res->control_restore_ok = (res->w_ctl_restore.completed && res->control_restore_read_rc == GBP_OK &&
                                   res->control_restore_vote == res->control_orig) ? 1 : 0;
        ringlog_printf(log, "CONTROL restore semantic=%02x rc=%s readback_rc=%s readback_vote=%02x readback_b1f=%02x ok=%d",
                       (unsigned)res->control_orig, gbp_status_name(res->w_ctl_restore.rc), gbp_status_name(res->control_restore_read_rc),
                       (unsigned)res->control_restore_vote, (unsigned)res->control_restore_b1f, res->control_restore_ok);
        if (!res->control_restore_ok) restore_fail(res, "control_restore_failed");
    }

    /* 2.–5. IRQ register: read, Start-up Disc stop word, re-read — only if an experimental IRQ write was attempted */
    if (res->irq_writes_attempted) {
        uint16_t before;
        read_irq_quiet(t, res, &res->irq_stop_pre);
        log_irqread(log, res, "IRQSTOPPRE", &res->irq_stop_pre);
        before = (res->irq_stop_pre.rc == GBP_OK) ? res->irq_stop_pre.gbi : 0u;
        /* Startup Disc stop shadow: bit15 + odd mask bits for all six serviced slots (GBP-IRQ-002/006);
         * pending sources read as 1 are written as 1 (acknowledged under the W1C model). If the read
         * failed the shadow alone is written (nothing unknown is acknowledged). */
        res->stop_value = (uint16_t)(before | cfg->stop_or);
        ringlog_printf(log, "IRQSTOP pre rc=%s disc=%04x gbi=%04x stop_or=%04x stop_value=%04x formula=%s comment=startup-disc-stop-shadow",
                       gbp_status_name(res->irq_stop_pre.rc), (unsigned)res->irq_stop_pre.disc, (unsigned)res->irq_stop_pre.gbi,
                       (unsigned)cfg->stop_or, (unsigned)res->stop_value,
                       (res->irq_stop_pre.rc == GBP_OK) ? "read|stop_or" : "stop_or(read_failed)");
        res->irq_writes_attempted++;             /* before the transport call (see step 5) */
        res->power_cycle_required = 1;
        gbp_regwrite_irq_u16(t, "tag=STOP", res->base, before, res->stop_value, &res->w_stop, &res->errors);
        if (res->w_stop.completed) res->irq_writes_completed++;
        gbp_regwrite_log(log, &res->w_stop);
        res->irq_stop_write_ok = res->w_stop.completed;
        if (!res->irq_stop_write_ok) restore_fail(res, "irq_stop_write_failed");
        read_irq_quiet(t, res, &res->irq_stop_post);
        log_irqread(log, res, "IRQSTOPPOST", &res->irq_stop_post);
        res->irq_stop_readback_ok = (res->irq_stop_post.rc == GBP_OK) ? 1 : 0;
        if (res->irq_stop_readback_ok) {
            uint16_t masks = (uint16_t)(cfg->stop_or & 0x0AAAu);
            res->stop_masks_readback = ((res->irq_stop_post.gbi & masks) == masks) ? 1 : 0;
            res->stop_bit15_readback = (res->irq_stop_post.gbi & 0x8000u) ? 1 : 0;
        } else {
            restore_fail(res, "irq_stop_readback_failed");
        }
        ringlog_printf(log, "IRQSTOP post rc=%s disc=%04x gbi=%04x write_ok=%d readback_ok=%d masks_readback=%d bit15_readback=%d",
                       gbp_status_name(res->irq_stop_post.rc), (unsigned)res->irq_stop_post.disc, (unsigned)res->irq_stop_post.gbi,
                       res->irq_stop_write_ok, res->irq_stop_readback_ok, res->stop_masks_readback, res->stop_bit15_readback);
    }

    /* 6.–7. PI: observe; a single W1C only if bit 13 is set while masked */
    if (any_exp) {
        if (gbp_rawlog_read_pi(t, log, "tag=CLEANUPCHK", &intsr, &intmr)) {
            res->cleanup_intsr_before = intsr;
            res->cleanup_intmr_before = intmr;
            if (intsr & GBP_PI_HSP_BIT) note_intsr13(res, 0, intsr, "CLEANUPCHK", 0);
            if ((intsr & GBP_PI_HSP_BIT) && !(intmr & GBP_PI_HSP_BIT) && t->write_intsr) {
                res->cleanup_rc = t->write_intsr(t->ctx, GBP_PI_HSP_BIT);
                res->pi_cleanup_performed = 1;
                if (res->cleanup_rc != GBP_OK) res->errors++;
                if (!gbp_rawlog_read_pi(t, log, "tag=CLEANUP", &intsr, &intmr)) res->errors++;
                res->cleanup_intsr_after = intsr;
                res->pi_cleanup_sticky = (intsr & GBP_PI_HSP_BIT) ? 1 : 0;
                res->pi_cleanup_ok = (res->cleanup_rc == GBP_OK && !res->pi_cleanup_sticky) ? 1 : 0;
                ringlog_printf(log, "CLEANUP performed=1 value=%08lx rc=%s intsr_before=%08lx intsr_after=%08lx intsr13_after=%u sticky=%d ok=%d",
                               (unsigned long)GBP_PI_HSP_BIT, gbp_status_name(res->cleanup_rc),
                               (unsigned long)res->cleanup_intsr_before, (unsigned long)res->cleanup_intsr_after,
                               (intsr & GBP_PI_HSP_BIT) ? 1u : 0u, res->pi_cleanup_sticky, res->pi_cleanup_ok);
                if (res->cleanup_rc != GBP_OK) restore_fail(res, "pi_cleanup_write_failed");
            } else {
                res->cleanup_intsr_after = intsr;
                res->pi_cleanup_skip_reason = !(intsr & GBP_PI_HSP_BIT) ? "intsr13_clear"
                                              : (intmr & GBP_PI_HSP_BIT) ? "intmr13_set" : "write_intsr_unavailable";
                ringlog_printf(log, "CLEANUP performed=0 intsr=%08lx intsr13=%u intmr13=%u reason=%s",
                               (unsigned long)intsr, (intsr & GBP_PI_HSP_BIT) ? 1u : 0u,
                               (intmr & GBP_PI_HSP_BIT) ? 1u : 0u, res->pi_cleanup_skip_reason);
            }
        } else {
            res->errors++;
            res->pi_cleanup_skip_reason = "pi_unreadable";
        }
    }

    /* 8. AR_INFO back */
    if (res->arinfo_changed) {
        rc = t->write_arinfo(t->ctx, res->arinfo_orig);
        if (rc != GBP_OK || t->read_arinfo(t->ctx, &res->arinfo_final) != GBP_OK) {
            res->arinfo_final = 0xFFFF;
            res->errors++;
        }
        res->arinfo_restore_ok = (res->arinfo_final == res->arinfo_orig) ? 1 : 0;
        ringlog_printf(log, "ARINFO restore value=%04x rc=%s readback=%04x ok=%d", (unsigned)res->arinfo_orig,
                       gbp_status_name(rc), (unsigned)res->arinfo_final, res->arinfo_restore_ok);
        if (!res->arinfo_restore_ok) restore_fail(res, "arinfo_restore_failed");
    } else {
        res->arinfo_final = res->arinfo_orig;
        res->arinfo_restore_ok = 1;
    }

    /* 9. final snapshot, under the restored AR_INFO */
    if (any_exp) {
        struct gbp_initirqa_snapshot *s = take_snapshot(t, res, GBP_INITIRQA_SNAP_FINAL, "FINAL", 0, 0, 0, 0);
        log_snapshot(log, res, s);
        ringlog_printf(log, "FINAL arinfo=%04x intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u control=%02x irq=%04x power_cycle_required=%d",
                       (unsigned)res->arinfo_final, (unsigned long)s->intsr, (unsigned long)s->intmr,
                       (s->intsr & GBP_PI_HSP_BIT) ? 1u : 0u, (s->intmr & GBP_PI_HSP_BIT) ? 1u : 0u,
                       (unsigned)s->control_vote, (unsigned)s->irq_gbi, res->power_cycle_required);
    }
}

static void finish(const struct gbp_transport *t, struct ringlog *log, const struct gbp_initirqa_config *cfg,
                   struct gbp_initirqa_result *res, gbp_initirqa_status st, const char *reason)
{
    res->status = st;
    res->reason = reason;
    flush_window(log, cfg, res);
    teardown(t, log, cfg, res);
    res->transport_ok = (res->errors == 0) ? 1 : 0;
    res->uncertain_writes = count_uncertain(res);
    /* Four short records instead of one: the worst-case field widths of a
     * single record exceeded the 255-byte line and would have cut off the
     * safety fields at its end. */
    ringlog_printf(log, "INITIRQA end status=%s reason=%s restore=%s restore_reason=%s power_cycle_required=%d errors=%u transport_ok=%d",
                   gbp_initirqa_status_name(st), reason, res->restore_ok ? "ok" : "error", res->restore_reason,
                   res->power_cycle_required, res->errors, res->transport_ok);
    ringlog_printf(log, "WRITES control_written=%d irq_attempted=%u irq_completed=%u ctl_exp=%d/%d a1=%d/%d a2=%d/%d stop=%d/%d ctl_restore=%d/%d uncertain=%u power_cycle_required=%d format=attempted/completed",
                   res->control_written, res->irq_writes_attempted, res->irq_writes_completed,
                   res->w_ctl_exp.attempted, res->w_ctl_exp.completed, res->w_a1.attempted, res->w_a1.completed,
                   res->w_a2.attempted, res->w_a2.completed, res->w_stop.attempted, res->w_stop.completed,
                   res->w_ctl_restore.attempted, res->w_ctl_restore.completed, res->uncertain_writes, res->power_cycle_required);
    ringlog_printf(log, "OBSERVED intsr13_seen=%d t_first_intsr13=%lu first_phase=%s first_value=%08lx polls_at_first=%u event=%d ended_early=%d",
                   res->intsr13_seen, (unsigned long)res->t_first_intsr13, res->first_intsr13_phase,
                   (unsigned long)res->first_intsr13_value, res->polls_at_first_intsr13, res->event_taken, res->window_ended_early);
    ringlog_printf(log, "RESTORE control_restore_ok=%d irq_stop_write_ok=%d irq_stop_readback_ok=%d stop_masks_readback=%d stop_bit15_readback=%d "
                        "pi_cleanup_performed=%d pi_cleanup_ok=%d pi_cleanup_sticky=%d arinfo_restore_ok=%d",
                   res->control_restore_ok, res->irq_stop_write_ok, res->irq_stop_readback_ok, res->stop_masks_readback,
                   res->stop_bit15_readback, res->pi_cleanup_performed, res->pi_cleanup_ok, res->pi_cleanup_sticky,
                   res->arinfo_restore_ok);
}

int gbp_initirqa_probe_run(const struct gbp_transport *t, struct ringlog *log,
                           const struct gbp_initirqa_config *cfg, struct gbp_initirqa_result *res)
{
    uint16_t want;
    gbp_status rc;
    struct gbp_initirqa_snapshot *s;
    const char *why = "-";

    memset(res, 0, sizeof *res);
    res->restore_ok = 1;
    res->restore_reason = "-";
    res->first_intsr13_phase = "-";
    res->irq_shape_reason = "-";
    res->pi_cleanup_skip_reason = "-";
    res->control_restore_ok = -1;
    res->arinfo_restore_ok = -1;
    res->irq_shape_base_ok = -1;
    res->irq_shape_a1pre_ok = -1;
    res->irq_stop_write_ok = -1;
    res->irq_stop_readback_ok = -1;
    res->stop_masks_readback = -1;
    res->stop_bit15_readback = -1;
    res->pi_cleanup_ok = -1;
    ringlog_printf(log, "INITIRQA start exp_code=%u clear=%02x set=%02x idle_shape=%d req_masks=%04x req_set=%04x req_clear=%04x ack_or=%04x stop_or=%04x tb_hz=%lu",
                   cfg->expansion_code, (unsigned)cfg->clear_mask, (unsigned)cfg->set_mask, cfg->require_idle_shape,
                   (unsigned)cfg->irq_req_masks, (unsigned)cfg->irq_req_set, (unsigned)cfg->irq_req_clear,
                   (unsigned)cfg->ack_or, (unsigned)cfg->stop_or, (unsigned long)cfg->tb_hz);
    ringlog_printf(log, "INITIRQA window a1_obs_ticks=%lu,%lu a2_obs_ticks=%lu,%lu,%lu,%lu,%lu,%lu n_a1=%u n_a2=%u t_max_ms=%lu poll=%d end_on_event=%d",
                   (unsigned long)cfg->a1_obs_ticks[0], (unsigned long)cfg->a1_obs_ticks[1],
                   (unsigned long)cfg->a2_obs_ticks[0], (unsigned long)cfg->a2_obs_ticks[1], (unsigned long)cfg->a2_obs_ticks[2],
                   (unsigned long)cfg->a2_obs_ticks[3], (unsigned long)cfg->a2_obs_ticks[4], (unsigned long)cfg->a2_obs_ticks[5],
                   cfg->n_a1_obs, cfg->n_a2_obs, (unsigned long)cfg->t_max_ms, cfg->poll_between, cfg->end_window_on_event);

    /* ---- 1. AR_INFO: bits 3-5 := expansion code (both references do this before the TEST handshake) ---- */
    if (t->read_arinfo(t->ctx, &res->arinfo_orig) != GBP_OK) {
        ringlog_printf(log, "ARINFO orig rc=fail");
        res->status = GBP_INITIRQA_ABORT_ARINFO;
        res->reason = "arinfo_unreadable";
        ringlog_printf(log, "INITIRQA end status=%s reason=%s", gbp_initirqa_status_name(res->status), res->reason);
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
            finish(t, log, cfg, res, GBP_INITIRQA_ABORT_ARINFO, "arinfo_not_settable");
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
    if (res->det.verdict == GBP_VERDICT_ABSENT) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_NOT_PRESENT, gbp_verdict_name(res->det.verdict));
        return 0;
    }
    if (res->det.verdict != GBP_VERDICT_PRESENT) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_INCONSISTENT, gbp_verdict_name(res->det.verdict));
        return 0;
    }

    /* ---- 3. PI preconditions: read only; never adjust ---- */
    res->pi_pre_ok = gbp_rawlog_read_pi(t, log, "tag=PRE", &res->intsr_pre, &res->intmr_pre);
    if (!res->pi_pre_ok) {
        ringlog_printf(log, "PRECOND ok=0 reason=pi_unavailable");
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_PI_PRECONDITION, "pi_unavailable");
        return 0;
    }
    if (res->intmr_pre & GBP_PI_HSP_BIT) {
        ringlog_printf(log, "PRECOND intsr13=%u intmr13=1 ok=0 reason=intmr13_unmasked",
                       (res->intsr_pre & GBP_PI_HSP_BIT) ? 1u : 0u);
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_PI_PRECONDITION, "intmr13_unmasked");
        return 0;
    }
    if (res->intsr_pre & GBP_PI_HSP_BIT) {
        ringlog_printf(log, "PRECOND intsr13=1 intmr13=0 ok=0 reason=intsr13_set");
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_PI_PRECONDITION, "intsr13_set");
        return 0;
    }
    ringlog_printf(log, "PRECOND intsr13=0 intmr13=0 irq_path_required=0 poll_intsr=%d write_intsr=%d ticks=%d ok=1 reason=-",
                   t->poll_intsr ? 1 : 0, t->write_intsr ? 1 : 0, t->ticks ? 1 : 0);

    /* ---- 4. BASE + CONTROL baseline + IRQ shape ---- */
    s = take_snapshot(t, res, GBP_INITIRQA_SNAP_BASE, "BASE", 0, 0, 1, 0);
    log_snapshot(log, res, s);
    if (s->control_rc != GBP_OK || !s->pi_ok || s->irq_rc != GBP_OK) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_CONTROL_READ, "base_read_failed");
        return 0;
    }
    if (s->control_vote != s->control_b1f) {
        ringlog_printf(log, "CONTROL ambiguous vote=%02x b1f=%02x", (unsigned)s->control_vote, (unsigned)s->control_b1f);
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_CONTROL_READ, "control_ambiguous");
        return 0;
    }
    res->control_orig = s->control_vote;
    res->control_exp = (uint8_t)((res->control_orig & (uint8_t)~cfg->clear_mask) | cfg->set_mask);
    ringlog_printf(log, "CONTROL semantic orig=%02x exp=%02x method=gbi-majority-vote transform=(v&~%02x)|%02x",
                   (unsigned)res->control_orig, (unsigned)res->control_exp, (unsigned)cfg->clear_mask, (unsigned)cfg->set_mask);
    if (cfg->require_idle_shape &&
        (((res->control_orig & cfg->clear_mask) == 0) || ((res->control_orig & cfg->set_mask) != 0))) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_CONTROL_SHAPE, "control_not_idle_shape");
        return 0;
    }
    if (res->control_exp == res->control_orig) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_CONTROL_SHAPE, "transform_is_noop");
        return 0;
    }
    res->irq_shape_base_ok = gbp_initirqa_irq_shape(cfg, s->irq_disc, s->irq_gbi, &why);
    log_irq_shape(log, cfg, "BASE", s->irq_disc, s->irq_gbi, res->irq_shape_base_ok, why);
    if (!res->irq_shape_base_ok) {
        res->irq_shape_reason = why;
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_IRQ_SHAPE, why);
        return 0;
    }

    /* ---- 5. experimental CONTROL write (validated transform, GBI layout) ----
     * Safety state FIRST, before the transport is invoked: from this point the
     * device may have taken the write whatever the transport reports (a timeout
     * or a busy refusal does not prove the DMA never reached the GBP). Never
     * set after, never conditioned on rc. */
    res->control_written = 1;
    res->power_cycle_required = 1;
    gbp_regwrite_control_byte(t, "tag=EXP", res->base, res->control_exp, &res->w_ctl_exp, &res->errors);
    res->t_control = res->w_ctl_exp.t_after;
    gbp_regwrite_log(log, &res->w_ctl_exp);
    if (!res->w_ctl_exp.completed) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_TRANSPORT, "control_write_failed");
        return 0;
    }

    /* ---- 6. P0 + INTMR re-check ---- */
    s = take_snapshot(t, res, GBP_INITIRQA_SNAP_P0, "P0", 0, 0, 1, 0);
    log_snapshot(log, res, s);
    if (!s->pi_ok || s->control_rc != GBP_OK || s->irq_rc != GBP_OK) {
        ringlog_printf(log, "P0CHK pi_ok=%d control_rc=%s irq_rc=%s ok=0 reason=p0_read_failed", s->pi_ok,
                       gbp_status_name(s->control_rc), gbp_status_name(s->irq_rc));
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_TRANSPORT, "p0_read_failed");
        return 0;
    }
    ringlog_printf(log, "P0CHK intsr13=%u intmr13=%u control=%02x irq=%04x ok=%d reason=%s",
                   (s->intsr & GBP_PI_HSP_BIT) ? 1u : 0u, (s->intmr & GBP_PI_HSP_BIT) ? 1u : 0u,
                   (unsigned)s->control_vote, (unsigned)s->irq_gbi, (s->intmr & GBP_PI_HSP_BIT) ? 0 : 1,
                   (s->intmr & GBP_PI_HSP_BIT) ? "intmr13_unmasked_p0" : "-");
    if (s->intmr & GBP_PI_HSP_BIT) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_PI_PRECONDITION, "intmr13_unmasked_p0");
        return 0;
    }

    /* ================= experimental region: no formatting until flush_window ================= */
    res->window_entered = 1;
    res->log_count_window_start = log->count;

    /* ---- 7. A1PRE: the read that feeds A1; shape re-checked ---- */
    read_irq_quiet(t, res, &res->irq_a1pre);
    if (res->irq_a1pre.rc != GBP_OK) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_TRANSPORT, "a1pre_read_failed");
        return 0;
    }
    res->irq_shape_a1pre_ok = gbp_initirqa_irq_shape(cfg, res->irq_a1pre.disc, res->irq_a1pre.gbi, &why);
    if (!res->irq_shape_a1pre_ok) {
        res->irq_shape_reason = why;
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_IRQ_SHAPE, why);
        return 0;
    }

    /* ---- 8. A1: IRQ := read | 0x8000 (GBI's acknowledge; u16 replicated 16×) ---- */
    res->ack_value = (uint16_t)(res->irq_a1pre.gbi | cfg->ack_or);
    res->irq_writes_attempted++;                 /* before the transport call (see step 5) */
    res->power_cycle_required = 1;
    gbp_regwrite_irq_u16(t, "tag=A1", res->base, res->irq_a1pre.gbi, res->ack_value, &res->w_a1, &res->errors);
    res->t_a1 = res->w_a1.t_after;
    if (!res->w_a1.completed) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_TRANSPORT, "a1_write_failed");
        return 0;
    }
    res->irq_writes_completed++;

    /* ---- 9. A1-0 immediately, then the read-only samples ---- */
    take_snapshot(t, res, GBP_INITIRQA_SNAP_A1_0, "A1-0", 0, 0, 0, 0);
    wait_phase(t, cfg, res, 1);

    /* ---- 10. A2PRE: irq_before_zero + PI; INTMR must still be masked ---- */
    read_irq_quiet(t, res, &res->irq_a2pre);
    if (t->read_pi && t->read_pi(t->ctx, &res->a2pre_intsr, &res->a2pre_intmr) == GBP_OK) res->a2pre_pi_ok = 1;
    else { res->a2pre_pi_ok = 0; res->errors++; }
    if (res->a2pre_pi_ok && (res->a2pre_intsr & GBP_PI_HSP_BIT)) note_intsr13(res, 0, res->a2pre_intsr, "A2PRE", res->a1_polls);
    if (res->irq_a2pre.rc != GBP_OK || !res->a2pre_pi_ok) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_TRANSPORT, "a2pre_read_failed");
        return 0;
    }
    if (res->a2pre_intmr & GBP_PI_HSP_BIT) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_PI_PRECONDITION, "intmr13_unmasked_a2pre");
        return 0;
    }

    /* ---- 11. A2: IRQ := 0 (GBI's end-of-pass write; 32 × 00) ---- */
    res->irq_writes_attempted++;                 /* before the transport call (see step 5) */
    res->power_cycle_required = 1;
    gbp_regwrite_irq_u16(t, "tag=A2", res->base, res->irq_a2pre.gbi, 0x0000u, &res->w_a2, &res->errors);
    res->t_a2 = res->w_a2.t_after;
    if (!res->w_a2.completed) {
        finish(t, log, cfg, res, GBP_INITIRQA_ABORT_TRANSPORT, "a2_write_failed");
        return 0;
    }
    res->irq_writes_completed++;

    /* ---- 12. A2-0 immediately, then the temporal window with INTSR polling ---- */
    take_snapshot(t, res, GBP_INITIRQA_SNAP_A2_0, "A2-0", 0, 0, 0, 0);
    wait_phase(t, cfg, res, 2);
    res->t_window_end = now(t);
    /* ================= end of the experimental region ================= */

    finish(t, log, cfg, res, res->intsr13_seen ? GBP_INITIRQA_OK_PI_CAUSE_OBSERVED : GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED, "-");
    return 0;
}

int gbp_initirqa_summary(const struct gbp_initirqa_result *res, char *dst, size_t cap)
{
    const struct gbp_initirqa_snapshot *base = &res->snap[GBP_INITIRQA_SNAP_BASE];
    const struct gbp_initirqa_snapshot *a10 = &res->snap[GBP_INITIRQA_SNAP_A1_0];
    const struct gbp_initirqa_snapshot *a20 = &res->snap[GBP_INITIRQA_SNAP_A2_0];
    const struct gbp_initirqa_snapshot *last = a20;
    const struct gbp_initirqa_snapshot *fin = &res->snap[GBP_INITIRQA_SNAP_FINAL];
    if (res->n_a2_order) last = &res->snap[res->a2_order[res->n_a2_order - 1u]];
    return snprintf(dst, cap,
                    "DONE status=%s reason=%s restore=%s restore_reason=%s verdict=%s det=%u/%u written=%d "
                    "irq_attempted=%u irq_completed=%u ctl_exp=%d/%d a1=%d/%d a2=%d/%d stop=%d/%d ctl_restore=%d/%d uncertain_writes=%u "
                    "intsr13_seen=%d t_first_intsr13=%lu first_phase=%s event=%d ended_early=%d "
                    "a1_polls=%u a2_polls=%u a1_obs=%u a2_obs=%u "
                    "base_irq=%04x a1pre_irq=%04x a1_write=%04x a1_0_irq=%04x a2pre_irq=%04x a2_0_irq=%04x last_irq=%04x "
                    "stop_pre=%04x stop_write=%04x stop_post=%04x final_irq=%04x "
                    "control_orig=%02x control_exp=%02x control_restore_ok=%d irq_stop_write_ok=%d irq_stop_readback_ok=%d "
                    "stop_masks_readback=%d pi_cleanup_performed=%d pi_cleanup_ok=%d pi_cleanup_sticky=%d arinfo_restore_ok=%d "
                    "power_cycle_required=%d errors=%u transport_ok=%d",
                    gbp_initirqa_status_name(res->status), res->reason ? res->reason : "-",
                    res->restore_ok ? "ok" : "error", res->restore_reason ? res->restore_reason : "-",
                    gbp_verdict_name(res->det.verdict), res->det.vote_ok, res->det.run, res->control_written,
                    res->irq_writes_attempted, res->irq_writes_completed,
                    res->w_ctl_exp.attempted, res->w_ctl_exp.completed, res->w_a1.attempted, res->w_a1.completed,
                    res->w_a2.attempted, res->w_a2.completed, res->w_stop.attempted, res->w_stop.completed,
                    res->w_ctl_restore.attempted, res->w_ctl_restore.completed, res->uncertain_writes,
                    res->intsr13_seen, (unsigned long)res->t_first_intsr13,
                    res->first_intsr13_phase ? res->first_intsr13_phase : "-", res->event_taken, res->window_ended_early,
                    res->a1_polls, res->a2_polls, res->a1_obs_taken, res->a2_obs_taken,
                    (unsigned)base->irq_gbi, (unsigned)res->irq_a1pre.gbi, (unsigned)res->ack_value, (unsigned)a10->irq_gbi,
                    (unsigned)res->irq_a2pre.gbi, (unsigned)a20->irq_gbi, (unsigned)last->irq_gbi,
                    (unsigned)res->irq_stop_pre.gbi, (unsigned)res->stop_value, (unsigned)res->irq_stop_post.gbi, (unsigned)fin->irq_gbi,
                    (unsigned)res->control_orig, (unsigned)res->control_exp, res->control_restore_ok, res->irq_stop_write_ok,
                    res->irq_stop_readback_ok, res->stop_masks_readback, res->pi_cleanup_performed, res->pi_cleanup_ok,
                    res->pi_cleanup_sticky, res->arinfo_restore_ok, res->power_cycle_required, res->errors, res->transport_ok);
}
