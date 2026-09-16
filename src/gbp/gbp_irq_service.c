#include "gbp_irq_service.h"

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

static void read_record(const struct gbp_transport *t, int slot, struct gbp_irq_record *out)
{
    memset(out, 0, sizeof *out);
    if (slot >= 0 && t->irq_record_slot) t->irq_record_slot(t->ctx, (uint32_t)slot, out);
    else t->irq_record(t->ctx, out);
}

void gbp_irq_service_delivery_init(struct gbp_irq_delivery *d)
{
    memset(d, 0, sizeof *d);
    d->main_mask_ok = -1;
}

void gbp_irq_service_ack_init(struct gbp_irq_ack *k)
{
    memset(k, 0, sizeof *k);
    k->ack_skip_reason = "-";
    k->main_pi_w1c_site = "-";
}

void gbp_irq_service_handler_init(struct gbp_irq_handler_state *h)
{
    memset(h, 0, sizeof *h);
    h->old_handler_null = -1;
    h->handler_restored = -1;
    h->mask_ok = -1;
}

int gbp_irq_service_preunmask_check(const struct gbp_initirqa_snapshot *s, uint8_t control_exp,
                                    uint16_t src_mask, uint16_t odd_mask, uint16_t bit15_mask, uint16_t high_mask,
                                    uint32_t install_count, uint32_t install_fired, const char **why)
{
    if (!s->pi_ok || s->control_rc != GBP_OK || s->irq_rc != GBP_OK) { *why = "read_failed"; return 0; }
    if (install_count || install_fired) { *why = "record_not_clear"; return 0; }
    if (!bit13(s->intsr) || (s->pi2_ok && !bit13(s->intsr2))) { *why = "cause_lost"; return 0; }
    if (bit13(s->intmr) || (s->pi2_ok && bit13(s->intmr2))) { *why = "intmr13_unmasked"; return 0; }
    if (s->control_vote != control_exp || s->control_vote != s->control_b1f) { *why = "control_changed"; return 0; }
    if (s->irq_disc != s->irq_gbi) { *why = "semantic_disagree"; return 0; }
    if ((s->irq_gbi & src_mask) == 0 || (s->irq_gbi & odd_mask) != 0 ||
        (s->irq_gbi & bit15_mask) != 0 || (s->irq_gbi & high_mask) != 0) { *why = "irq_state_unexpected"; return 0; }
    *why = "-";
    return 1;
}

void gbp_irq_service_log_preunmask(struct ringlog *log, const char *nfield, const struct gbp_initirqa_snapshot *s,
                                   int ok, const char *why, uint16_t src_mask, uint16_t odd_mask, uint16_t bit15_mask)
{
    ringlog_printf(log, "PREUNMASK%s ok=%d reason=%s intsr13=%u,%u intmr13=%u,%u control=%02x irq=%04x/%04x src=%04x odd=%04x bit15=%u",
                   nfield, ok, why, bit13(s->intsr), bit13(s->intsr2), bit13(s->intmr), bit13(s->intmr2),
                   (unsigned)s->control_vote, (unsigned)s->irq_gbi, (unsigned)s->irq_disc,
                   (unsigned)(s->irq_gbi & src_mask), (unsigned)(s->irq_gbi & odd_mask),
                   (unsigned)((s->irq_gbi & bit15_mask) ? 1u : 0u));
}

void gbp_irq_service_deliver_quiet(const struct gbp_transport *t, uint32_t tb_hz, uint32_t t_delivery_ticks, int slot,
                                   struct gbp_irq_delivery *d, unsigned *errors)
{
    struct gbp_irq_record rec0;
    const struct gbp_irq_record *r;

    /* ---- 5. one unmask; values only ---- */
    d->pi_pre_unmask_ok = (t->read_pi(t->ctx, &d->intsr_pre_unmask, &d->intmr_pre_unmask) == GBP_OK) ? 1 : 0;
    d->t_unmask = now(t);
    d->unmask_rc = t->irq_unmask(t->ctx);
    d->irq_unmasked = 1;                         /* even on failure: the teardown re-masks anyway */
    d->t_post_unmask = now(t);                   /* the handler may already have run inside __UnmaskIrq */
    d->pi_post_unmask_ok = (t->read_pi(t->ctx, &d->intsr_post_unmask, &d->intmr_post_unmask) == GBP_OK) ? 1 : 0;
    read_record(t, slot, &rec0);
    d->rec0_fired = rec0.fired;
    if (!d->pi_pre_unmask_ok || !d->pi_post_unmask_ok) (*errors)++;

    /* ---- 6. wait for the handler or the operational bound; no DMA, no formatting in here ---- */
    {
        uint32_t tnow;
        for (;;) {
            struct gbp_irq_record rr;
            read_record(t, slot, &rr);
            d->polls++;
            if (rr.fired) break;
            tnow = now(t);
            if ((uint32_t)(tnow - d->t_unmask) >= t_delivery_ticks) { d->timed_out = 1; break; }
        }
    }
    d->t_wait_end = now(t);
    d->wait_ticks = (uint32_t)(d->t_wait_end - d->t_unmask);

    /* ---- 7. IRQ 26 masked again by the main loop (idempotent with the handler's own mask), then verified ---- */
    d->mask_rc = t->irq_mask(t->ctx);
    if (d->mask_rc == GBP_OK) d->irq_masked_again = 1; else (*errors)++;
    if (!t->read_pi) {
        d->remask_unavailable = 1;
        d->remask_rc = GBP_ERR_BACKEND;
        (*errors)++;
    } else {
        d->remask_rc = t->read_pi(t->ctx, &d->intsr_remask_first, &d->intmr_remask_first);
        if (d->remask_rc != GBP_OK) {
            (*errors)++;
        } else {
            d->intsr_remask = d->intsr_remask_first; d->intmr_remask = d->intmr_remask_first;
            d->main_mask_ok = bit13(d->intmr_remask) ? 0 : 1;
            if (!d->main_mask_ok) {
                uint32_t intsr = 0, intmr = 0;
                d->retry_rc = t->irq_mask(t->ctx);
                d->remask_retry = 1;
                d->remask2_read = 1;
                d->remask2_rc = t->read_pi(t->ctx, &intsr, &intmr);
                if (d->remask2_rc == GBP_OK) { d->intsr_remask = intsr; d->intmr_remask = intmr; d->main_mask_ok = bit13(intmr) ? 0 : 1; }
            }
        }
    }

    /* ---- 8. the record, copied only now (masked) ---- */
    read_record(t, slot, &d->rec);
    r = &d->rec;
    d->fired = r->fired ? 1 : 0;
    d->reentry = (r->count > 1u) ? 1 : 0;
    if (d->fired) {
        d->latency_ticks = (uint32_t)(r->t_entry - d->t_unmask);   /* wrap-safe; never from t_post_unmask */
        d->latency_us = ticks_to_us(tb_hz, d->latency_ticks);
    }
}

void gbp_irq_service_deliver_log(struct ringlog *log, uint32_t tb_hz, uint32_t t_delivery_ms, uint32_t t_delivery_ticks,
                                 const char *nfield, const char *sfx, const struct gbp_irq_delivery *d)
{
    const struct gbp_irq_record *r = &d->rec;
    char tag[32];
    ringlog_printf(log, "PI tag=UNMASKPRE%s rc=%s intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u", sfx,
                   d->pi_pre_unmask_ok ? "ok" : "fail", (unsigned long)d->intsr_pre_unmask, (unsigned long)d->intmr_pre_unmask,
                   bit13(d->intsr_pre_unmask), bit13(d->intmr_pre_unmask));
    ringlog_printf(log, "UNMASK%s t_unmask=%lu rc=%s t_post=%lu dt_post=%lu", nfield, (unsigned long)d->t_unmask,
                   gbp_status_name(d->unmask_rc), (unsigned long)d->t_post_unmask,
                   (unsigned long)(uint32_t)(d->t_post_unmask - d->t_unmask));
    ringlog_printf(log, "PI tag=UNMASKPOST%s rc=%s intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u fired=%lu", sfx,
                   d->pi_post_unmask_ok ? "ok" : "fail", (unsigned long)d->intsr_post_unmask, (unsigned long)d->intmr_post_unmask,
                   bit13(d->intsr_post_unmask), bit13(d->intmr_post_unmask), (unsigned long)d->rec0_fired);
    ringlog_printf(log, "IRQ mask tag=MAIN%s rc=%s", nfield, gbp_status_name(d->mask_rc));
    ringlog_printf(log, "WAIT%s fired=%d timed_out=%d polls=%u wait_ticks=%lu wait_us=%lu t_delivery_ms=%lu t_delivery_ticks=%lu",
                   nfield, d->timed_out ? 0 : 1, d->timed_out, d->polls, (unsigned long)d->wait_ticks,
                   (unsigned long)ticks_to_us(tb_hz, d->wait_ticks), (unsigned long)t_delivery_ms, (unsigned long)t_delivery_ticks);
    snprintf(tag, sizeof tag, "tag=REMASKCHK%s", sfx);
    if (d->remask_unavailable) gbp_rawlog_log_pi(log, tag, "unavailable", 0, 0);
    else if (d->remask_rc != GBP_OK) gbp_rawlog_log_pi(log, tag, gbp_status_name(d->remask_rc), 0, 0);
    else gbp_rawlog_log_pi(log, tag, "ok", d->intsr_remask_first, d->intmr_remask_first);
    if (d->remask_retry) {
        ringlog_printf(log, "IRQ mask tag=RETRY%s rc=%s", nfield, gbp_status_name(d->retry_rc));
        snprintf(tag, sizeof tag, "tag=REMASKCHK2%s", sfx);
        if (d->remask2_rc != GBP_OK) gbp_rawlog_log_pi(log, tag, gbp_status_name(d->remask2_rc), 0, 0);
        else gbp_rawlog_log_pi(log, tag, "ok", d->intsr_remask, d->intmr_remask);
    }
    ringlog_printf(log, "HANDLER%s fired=%lu count=%lu t_entry=%lu t_unmask=%lu latency_ticks=%lu latency_us=%lu reentry=%d",
                   nfield, (unsigned long)r->fired, (unsigned long)r->count, (unsigned long)r->t_entry,
                   (unsigned long)d->t_unmask, (unsigned long)d->latency_ticks, (unsigned long)d->latency_us, d->reentry);
    ringlog_printf(log, "HANDLERPI%s intsr_at_entry=%08lx intmr_at_entry=%08lx intmr_after_mask=%08lx intsr_before_w1c=%08lx intsr_after_w1c=%08lx reentry_intsr=%08lx reentry_intmr=%08lx",
                   nfield, (unsigned long)r->intsr_before_ack, (unsigned long)r->intmr_at_entry, (unsigned long)r->intmr_after_mask,
                   (unsigned long)r->intsr_before_w1c, (unsigned long)r->intsr_after_ack,
                   (unsigned long)r->reentry_intsr, (unsigned long)r->reentry_intmr);
    ringlog_printf(log, "HANDLERPI2%s t_second=%lu dt_second=%lu intsr_second=%08lx intmr_second=%08lx reentry_t=%lu",
                   nfield, (unsigned long)r->t_second, (unsigned long)(uint32_t)(r->t_second - r->t_entry),
                   (unsigned long)r->intsr_second, (unsigned long)r->intmr_second, (unsigned long)r->reentry_t);
    ringlog_printf(log, "DELIVERY%s fired=%d count=%lu latency_ticks=%lu latency_us=%lu intsr13_entry=%u intmr13_entry=%u intmr13_after_mask=%u intsr13_before_w1c=%u intsr13_after_w1c=%u intsr13_second=%u intmr13_second=%u main_mask_ok=%d reentry=%d",
                   nfield, d->fired, (unsigned long)r->count, (unsigned long)d->latency_ticks, (unsigned long)d->latency_us,
                   bit13(r->intsr_before_ack), bit13(r->intmr_at_entry), bit13(r->intmr_after_mask), bit13(r->intsr_before_w1c),
                   bit13(r->intsr_after_ack), bit13(r->intsr_second), bit13(r->intmr_second), d->main_mask_ok, d->reentry);
}

void gbp_irq_service_deliver(const struct gbp_transport *t, struct ringlog *log, uint32_t tb_hz,
                             uint32_t t_delivery_ms, uint32_t t_delivery_ticks, int slot,
                             const char *nfield, const char *sfx, struct gbp_irq_delivery *d, unsigned *errors)
{
    gbp_irq_service_deliver_quiet(t, tb_hz, t_delivery_ticks, slot, d, errors);
    gbp_irq_service_deliver_log(log, tb_hz, t_delivery_ms, t_delivery_ticks, nfield, sfx, d);
}

static void postack_and_w1c(const struct gbp_transport *t, struct ringlog *log, struct gbp_initirqa_result *a,
                            uint16_t src_mask, const char *nfield, const char *tag_postack, const char *sfx,
                            struct gbp_irq_ack *k, unsigned *errors);

void gbp_irq_service_ack(const struct gbp_transport *t, struct ringlog *log, struct gbp_initirqa_result *a,
                         uint16_t ack_or, uint16_t src_mask, uint16_t allowed_src, int require_source,
                         int require_control, uint8_t control_exp,
                         const char *nfield, const char *tag_preack, const char *tag_postack, const char *tag_ack,
                         const char *sfx, struct gbp_irq_ack *k, unsigned *errors)
{
    /* ---- 9. PREACK: the device has not been acknowledged; PI, CONTROL, IRQ as they are now ---- */
    gbp_initirqa_snapshot_take(t, a, &k->preack, tag_preack, 0, 1);
    gbp_initirqa_snapshot_log(log, a, &k->preack);
    ringlog_printf(log, "PREACK%s intsr13=%u,%u intmr13=%u control=%02x irq=%04x/%04x src_pending=%04x", nfield,
                   bit13(k->preack.intsr), bit13(k->preack.intsr2), bit13(k->preack.intmr),
                   (unsigned)k->preack.control_vote, (unsigned)k->preack.irq_gbi, (unsigned)k->preack.irq_disc,
                   (unsigned)(k->preack.irq_gbi & src_mask));

    /* ---- 10. device ACK: IRQ := read | ack_or (GBI's form; A1's physically validated write), derived from the read ---- */
    if (k->preack.irq_rc != GBP_OK) {
        k->ack_skipped = 1; k->ack_skip_reason = "irq_read_failed";
    } else if (k->preack.irq_disc != k->preack.irq_gbi) {
        k->ack_skipped = 1; k->ack_skip_reason = "semantic_disagree";
    } else if (require_control && (k->preack.control_rc != GBP_OK || k->preack.control_vote != control_exp ||
                                   k->preack.control_vote != k->preack.control_b1f)) {
        k->ack_skipped = 1; k->ack_skip_reason = "control_changed";
    } else if (require_control && (!k->preack.pi_ok || bit13(k->preack.intmr) || (k->preack.pi2_ok && bit13(k->preack.intmr2)))) {
        k->ack_skipped = 1; k->ack_skip_reason = "intmr13_set";
    } else {
        k->unexpected = (uint16_t)(k->preack.irq_gbi & src_mask & (uint16_t)~allowed_src);
        k->source_zero = ((k->preack.irq_gbi & src_mask) == 0) ? 1 : 0;
        if (k->unexpected) {
            k->ack_skipped = 1; k->ack_skip_reason = "unexpected_source";
        } else if (require_source && k->source_zero) {
            k->ack_skipped = 1; k->ack_skip_reason = "source_lost";
        } else {
            gbp_irq_service_ack_write_postack(t, log, a, k->preack.irq_gbi, ack_or, src_mask, nfield, tag_postack, tag_ack, sfx, k, errors);
            return;
        }
    }
    ringlog_printf(log, "ACK%s skipped=1 reason=%s", nfield, k->ack_skip_reason);
    postack_and_w1c(t, log, a, src_mask, nfield, tag_postack, sfx, k, errors);
}

void gbp_irq_service_ack_write_postack(const struct gbp_transport *t, struct ringlog *log, struct gbp_initirqa_result *a,
                                       uint16_t pending, uint16_t ack_or, uint16_t src_mask,
                                       const char *nfield, const char *tag_postack, const char *tag_ack, const char *sfx,
                                       struct gbp_irq_ack *k, unsigned *errors)
{
    /* ---- 10. device ACK: IRQ := pending | ack_or (GBI's form; A1's physically validated write), derived from a read ---- */
    k->irq_pending = pending;
    k->ack_value = (uint16_t)(k->irq_pending | ack_or);
    ringlog_printf(log, "ACK%s before=%04x ack_or=%04x ack_value=%04x formula=read|ack_or", nfield, (unsigned)k->irq_pending,
                   (unsigned)ack_or, (unsigned)k->ack_value);
    a->irq_writes_attempted++;              /* before the transport call, as in 003A */
    a->power_cycle_required = 1;
    gbp_regwrite_irq_u16(t, tag_ack, a->base, k->irq_pending, k->ack_value, &k->w_ack, errors);
    if (k->w_ack.completed) a->irq_writes_completed++;
    gbp_regwrite_log(log, &k->w_ack);
    postack_and_w1c(t, log, a, src_mask, nfield, tag_postack, sfx, k, errors);
}

/* ---- 11.–12. POSTACK snapshot and the cycle's single main-loop W1C ---- */
static void postack_and_w1c(const struct gbp_transport *t, struct ringlog *log, struct gbp_initirqa_result *a,
                            uint16_t src_mask, const char *nfield, const char *tag_postack, const char *sfx,
                            struct gbp_irq_ack *k, unsigned *errors)
{
    uint32_t intsr = 0, intmr = 0;
    char tag[32];

    /* ---- 11. POSTACK ---- */
    gbp_initirqa_snapshot_take(t, a, &k->postack, tag_postack, 0, 1);
    gbp_initirqa_snapshot_log(log, a, &k->postack);
    ringlog_printf(log, "POSTACK%s intsr13=%u,%u intmr13=%u control=%02x irq=%04x/%04x src_pending=%04x bit15=%u ack=%d/%d", nfield,
                   bit13(k->postack.intsr), bit13(k->postack.intsr2), bit13(k->postack.intmr),
                   (unsigned)k->postack.control_vote, (unsigned)k->postack.irq_gbi, (unsigned)k->postack.irq_disc,
                   (unsigned)(k->postack.irq_gbi & src_mask), (unsigned)((k->postack.irq_gbi & 0x8000u) ? 1u : 0u),
                   k->w_ack.attempted, k->w_ack.completed);

    /* ---- 12. main-loop PI W1C: at most one per cycle, here only if bit 13 reads 1 while masked ---- */
    if (k->postack.pi_ok && bit13(k->postack.intsr) && !bit13(k->postack.intmr) && t->write_intsr && !k->main_pi_w1c) {
        k->main_pi_w1c = 1;
        k->main_pi_w1c_site = "POSTACK";
        k->main_w1c_intsr_before = k->postack.intsr;
        ringlog_printf(log, "MAINPICLEANUP%s site=POSTACK performed=1 value=%08lx", nfield, (unsigned long)GBP_PI_HSP_BIT);
        k->main_w1c_rc = t->write_intsr(t->ctx, GBP_PI_HSP_BIT);
        if (k->main_w1c_rc != GBP_OK) (*errors)++;
        snprintf(tag, sizeof tag, "tag=MAINCLEANUP%s", sfx);
        if (!gbp_rawlog_read_pi(t, log, tag, &intsr, &intmr)) (*errors)++;
        k->main_w1c_intsr_after = intsr;
        k->main_w1c_intmr_after = intmr;
        k->main_w1c_sticky = bit13(intsr) ? 1 : 0;
        ringlog_printf(log, "MAINPICLEANUP%s result rc=%s intsr_before=%08lx intsr_after=%08lx intsr13_after=%u sticky=%d", nfield,
                       gbp_status_name(k->main_w1c_rc), (unsigned long)k->main_w1c_intsr_before,
                       (unsigned long)k->main_w1c_intsr_after, bit13(intsr), k->main_w1c_sticky);
    } else {
        ringlog_printf(log, "MAINPICLEANUP%s site=POSTACK performed=0 intsr13=%u intmr13=%u", nfield, bit13(k->postack.intsr), bit13(k->postack.intmr));
    }
}

const char *gbp_irq_service_teardown_hook(const struct gbp_transport *t, struct ringlog *log,
                                          struct gbp_irq_handler_state *h, int engaged, unsigned *errors)
{
    const char *fail = 0;
    uint32_t intsr = 0, intmr = 0;
    gbp_status rc;

    /* 1. previous handler back, verbatim (NULL or not) */
    if (h->handler_installed) {
        h->handler_restore_rc = t->irq_restore ? t->irq_restore(t->ctx) : GBP_ERR_BACKEND;
        h->handler_restored = (h->handler_restore_rc == GBP_OK) ? 1 : 0;
        ringlog_printf(log, "IRQ restore rc=%s ok=%d old_handler=%s", gbp_status_name(h->handler_restore_rc),
                       h->handler_restored, h->old_handler_null == 1 ? "null" : h->old_handler_null == 0 ? "nonnull" : "?");
        if (h->handler_restored) h->handler_installed = 0;
        else { (*errors)++; if (!fail) fail = "handler_restore_failed"; }
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
            h->intmr_final = intmr;
        } else {
            (*errors)++;
        }
        h->mask_ok = ok;
        ringlog_printf(log, "MASK final intmr=%08lx intmr13=%u orig_intmr13=0 ok=%d", (unsigned long)intmr, bit13(intmr), ok);
        if (!ok && !fail) fail = "mask_not_restored";
    }
    return fail;
}
