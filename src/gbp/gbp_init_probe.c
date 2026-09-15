#include "gbp_init_probe.h"

#include <stdio.h>
#include <string.h>

#define IDX_TEST 0u
#define IDX_CONTROL 4u
#define IDX_IRQ 0xDu

void gbp_init_config_default(struct gbp_init_config *cfg)
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
}

const char *gbp_init_status_name(gbp_init_status s)
{
    switch (s) {
    case GBP_INIT_OK: return "ok";
    case GBP_INIT_ABORT_ARINFO: return "abort_arinfo";
    case GBP_INIT_ABORT_NOT_PRESENT: return "abort_not_present";
    case GBP_INIT_ABORT_PI: return "abort_pi";
    case GBP_INIT_ABORT_CONTROL_READ: return "abort_control_read";
    case GBP_INIT_ABORT_CONTROL_SHAPE: return "abort_control_shape";
    case GBP_INIT_ERROR_AFTER_WRITE: return "error_after_write";
    default: return "?";
    }
}

static uint32_t now(const struct gbp_transport *t)
{
    return t->ticks ? t->ticks(t->ctx) : 0u;
}

static gbp_status read_block_logged(const struct gbp_transport *t, struct ringlog *log, const char *tag,
                                    uint32_t base, unsigned idx, uint8_t out[GBP_BLOCK_SIZE],
                                    struct gbp_init_result *res)
{
    struct gbp_xfer_info info;
    char hex[GBP_BLOCK_SIZE * 2 + 1];
    uint32_t addr = gbp_block_addr(base, idx, 0);
    gbp_status rc;

    memset(&info, 0, sizeof info);
    memset(out, 0, GBP_BLOCK_SIZE);
    rc = t->read_block(t->ctx, addr, out, &info);
    if (rc != GBP_OK) res->errors++;
    ringlog_hex(hex, sizeof hex, out, GBP_BLOCK_SIZE);
    if (idx == IDX_CONTROL) {
        ringlog_printf(log, "RAW %s idx=%x addr=%08lx rc=%s ticks=%lu polls=%u dspcr=%04x sem_vote=%02x sem_b1f=%02x data=%s",
                       tag, idx, (unsigned long)addr, gbp_status_name(rc), (unsigned long)info.ticks,
                       (unsigned)info.polls, (unsigned)info.dma_status,
                       (unsigned)gbp_majority_vote_byte(out), (unsigned)out[GBP_BLOCK_SIZE - 1u],
                       rc == GBP_OK ? hex : "-");
    } else if (idx == IDX_IRQ) {
        uint8_t hi[8], lo[8];
        unsigned k;
        for (k = 0; k < 8; k++) { hi[k] = out[4 * k + 1]; lo[k] = out[4 * k + 3]; }
        ringlog_printf(log, "RAW %s idx=%x addr=%08lx rc=%s ticks=%lu polls=%u dspcr=%04x sem_disc=%04x sem_gbi=%04x data=%s",
                       tag, idx, (unsigned long)addr, gbp_status_name(rc), (unsigned long)info.ticks,
                       (unsigned)info.polls, (unsigned)info.dma_status,
                       (unsigned)((out[0x1D] << 8) | out[0x1F]),
                       (unsigned)((gbp_majority_vote_byte_n(hi, 8) << 8) | gbp_majority_vote_byte_n(lo, 8)),
                       rc == GBP_OK ? hex : "-");
    } else {
        ringlog_printf(log, "RAW %s idx=%x addr=%08lx rc=%s ticks=%lu polls=%u dspcr=%04x data=%s",
                       tag, idx, (unsigned long)addr, gbp_status_name(rc), (unsigned long)info.ticks,
                       (unsigned)info.polls, (unsigned)info.dma_status, rc == GBP_OK ? hex : "-");
    }
    return rc;
}

static int read_pi_logged(const struct gbp_transport *t, struct ringlog *log, const char *tag,
                          uint32_t *intsr, uint32_t *intmr)
{
    gbp_status rc;
    if (!t->read_pi) {
        ringlog_printf(log, "PI %s rc=unavailable", tag);
        return 0;
    }
    rc = t->read_pi(t->ctx, intsr, intmr);
    if (rc != GBP_OK) {
        ringlog_printf(log, "PI %s rc=%s", tag, gbp_status_name(rc));
        return 0;
    }
    ringlog_printf(log, "PI %s intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u", tag,
                   (unsigned long)*intsr, (unsigned long)*intmr,
                   (*intsr & GBP_PI_HSP_BIT) ? 1u : 0u, (*intmr & GBP_PI_HSP_BIT) ? 1u : 0u);
    return 1;
}

static void snapshot(const struct gbp_transport *t, struct ringlog *log, struct gbp_init_result *res,
                     unsigned n, int with_test, uint32_t write_ticks)
{
    struct gbp_init_snapshot *s = &res->snap[n];

    snprintf(s->id, sizeof s->id, "S%u", n);
    s->taken = 1;
    s->ticks = now(t);
    s->ticks_since_write = (n >= 1 && write_ticks) ? (uint32_t)(s->ticks - write_ticks) : 0u;
    ringlog_printf(log, "SNAP tag=%s ticks=%lu since_write=%lu", s->id, (unsigned long)s->ticks,
                   (unsigned long)s->ticks_since_write);
    s->pi_ok = read_pi_logged(t, log, s->id, &s->intsr, &s->intmr);
    s->control_rc = read_block_logged(t, log, s->id, res->base, IDX_CONTROL, s->control, res);
    s->control_vote = gbp_majority_vote_byte(s->control);
    s->control_b1f = s->control[GBP_BLOCK_SIZE - 1u];
    s->irq_rc = read_block_logged(t, log, s->id, res->base, IDX_IRQ, s->irq, res);
    s->irq_disc = (uint16_t)((s->irq[0x1D] << 8) | s->irq[0x1F]);
    if (with_test) {
        s->has_test = 1;
        s->test_rc = read_block_logged(t, log, s->id, res->base, IDX_TEST, s->test, res);
    }
}

static gbp_status write_control_logged(const struct gbp_transport *t, struct ringlog *log, const char *tag,
                                       uint32_t base, uint8_t value, uint8_t raw_out[GBP_BLOCK_SIZE],
                                       struct gbp_init_result *res)
{
    struct gbp_xfer_info info;
    char hex[GBP_BLOCK_SIZE * 2 + 1];
    uint32_t addr = gbp_block_addr(base, IDX_CONTROL, 0);
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

static void restore_intmr(const struct gbp_transport *t, struct ringlog *log, struct gbp_init_result *res)
{
    uint32_t s, m;
    gbp_status rc;
    if (!res->intmr_changed) { res->intmr_restored = -1; return; }
    rc = t->write_intmr(t->ctx, res->intmr_orig);
    if (rc == GBP_OK && t->read_pi(t->ctx, &s, &m) == GBP_OK) {
        res->intmr_final = m;
        res->intmr_restored = (m == res->intmr_orig) ? 1 : 0;
    } else {
        res->intmr_restored = 0;
        res->errors++;
    }
    ringlog_printf(log, "INTMR restore value=%08lx rc=%s readback=%08lx ok=%d", (unsigned long)res->intmr_orig,
                   gbp_status_name(rc), (unsigned long)res->intmr_final, res->intmr_restored);
}

static void restore_arinfo(const struct gbp_transport *t, struct ringlog *log, struct gbp_init_result *res)
{
    gbp_status rc;
    if (!res->arinfo_changed) { res->arinfo_restored = 1; res->arinfo_final = res->arinfo_orig; return; }
    rc = t->write_arinfo(t->ctx, res->arinfo_orig);
    if (rc != GBP_OK || t->read_arinfo(t->ctx, &res->arinfo_final) != GBP_OK) {
        res->arinfo_final = 0xFFFF;
        res->errors++;
    }
    res->arinfo_restored = (res->arinfo_final == res->arinfo_orig) ? 1 : 0;
    ringlog_printf(log, "ARINFO restore value=%04x rc=%s readback=%04x ok=%d", (unsigned)res->arinfo_orig,
                   gbp_status_name(rc), (unsigned)res->arinfo_final, res->arinfo_restored);
}

static void finish(const struct gbp_transport *t, struct ringlog *log, struct gbp_init_result *res,
                   gbp_init_status st, const char *reason)
{
    res->status = st;
    res->abort_reason = reason;
    restore_intmr(t, log, res);
    restore_arinfo(t, log, res);
    res->transport_ok = (res->errors == 0) ? 1 : 0;
    ringlog_printf(log, "INIT end status=%s reason=%s written=%d control_restored=%d arinfo_restored=%d intmr_restored=%d errors=%u transport_ok=%d",
                   gbp_init_status_name(st), reason, res->control_written, res->control_restored,
                   res->arinfo_restored, res->intmr_restored, res->errors, res->transport_ok);
}

int gbp_init_probe_run(const struct gbp_transport *t, struct ringlog *log,
                       const struct gbp_init_config *cfg, struct gbp_init_result *res)
{
    uint16_t want;
    uint32_t intsr, intmr, write_ticks = 0;
    gbp_status rc;
    struct gbp_init_snapshot *s0;

    memset(res, 0, sizeof *res);
    res->control_restored = -1;
    res->intmr_restored = -1;
    ringlog_printf(log, "INIT start exp_code=%u clear=%02x set=%02x idle_shape=%d npatterns=%u",
                   cfg->expansion_code, (unsigned)cfg->clear_mask, (unsigned)cfg->set_mask,
                   cfg->require_idle_shape, cfg->npatterns);

    /* ---- AR_INFO ---------------------------------------------------- */
    if (t->read_arinfo(t->ctx, &res->arinfo_orig) != GBP_OK) {
        ringlog_printf(log, "ARINFO orig rc=fail");
        res->status = GBP_INIT_ABORT_ARINFO;
        res->abort_reason = "arinfo_unreadable";
        ringlog_printf(log, "INIT end status=%s reason=%s", gbp_init_status_name(res->status), res->abort_reason);
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
            finish(t, log, res, GBP_INIT_ABORT_ARINFO, "arinfo_not_settable");
            return 0;
        }
    } else {
        res->arinfo_exp = res->arinfo_orig;
    }
    ringlog_printf(log, "ARINFO exp value=%04x exp_code=%u", (unsigned)res->arinfo_exp, (unsigned)((res->arinfo_exp >> 3) & 7u));
    res->base = gbp_internal_size_from_arinfo(res->arinfo_exp);

    /* ---- presence (policy of gbp_detect.h) --------------------------- */
    gbp_detect_handshake(t, log, "tag=DET", res->base, IDX_TEST, cfg->patterns, cfg->npatterns, &res->det);
    ringlog_printf(log, "DET verdict=%s run=%u transport_ok=%u vote_ok=%u b1_ok=%u all32_ok=%u",
                   gbp_verdict_name(res->det.verdict), res->det.run, res->det.transport_ok,
                   res->det.vote_ok, res->det.b1_ok, res->det.all32_ok);
    res->errors += res->det.failed;
    if (res->det.verdict != GBP_VERDICT_PRESENT) {
        finish(t, log, res, GBP_INIT_ABORT_NOT_PRESENT, gbp_verdict_name(res->det.verdict));
        return 0;
    }

    /* ---- PI: read, make sure the HSP interrupt is masked ------------- */
    if (!read_pi_logged(t, log, "tag=PRE", &intsr, &intmr)) {
        finish(t, log, res, GBP_INIT_ABORT_PI, "pi_unavailable");
        return 0;
    }
    res->intmr_orig = intmr;
    res->intmr_final = intmr;
    if (intmr & GBP_PI_HSP_BIT) {
        uint32_t wanted = intmr & ~GBP_PI_HSP_BIT;   /* only bit 13, libogc2 polarity: 1 = enabled */
        uint32_t s, m;
        rc = t->write_intmr ? t->write_intmr(t->ctx, wanted) : GBP_ERR_BACKEND;
        res->intmr_changed = 1;
        if (rc != GBP_OK || t->read_pi(t->ctx, &s, &m) != GBP_OK || (m & GBP_PI_HSP_BIT)) {
            res->errors++;
            ringlog_printf(log, "INTMR mask wanted=%08lx rc=%s readback=%08lx ok=0", (unsigned long)wanted,
                           gbp_status_name(rc), (unsigned long)m);
            finish(t, log, res, GBP_INIT_ABORT_PI, "intmr_not_maskable");
            return 0;
        }
        res->intmr_exp = m;
        ringlog_printf(log, "INTMR mask wanted=%08lx rc=ok readback=%08lx ok=1", (unsigned long)wanted, (unsigned long)m);
    } else {
        res->intmr_exp = intmr;
        ringlog_printf(log, "INTMR unchanged value=%08lx bit13=0", (unsigned long)intmr);
    }

    /* ---- S0 ----------------------------------------------------------- */
    snapshot(t, log, res, 0, 1, 0);
    s0 = &res->snap[0];
    if (s0->control_rc != GBP_OK || !s0->pi_ok) {
        finish(t, log, res, GBP_INIT_ABORT_CONTROL_READ, "s0_read_failed");
        return 0;
    }
    if (s0->control_vote != s0->control_b1f) {
        ringlog_printf(log, "CONTROL ambiguous vote=%02x b1f=%02x", (unsigned)s0->control_vote, (unsigned)s0->control_b1f);
        finish(t, log, res, GBP_INIT_ABORT_CONTROL_READ, "control_ambiguous");
        return 0;
    }
    res->control_orig = s0->control_vote;
    res->control_exp = (uint8_t)((res->control_orig & (uint8_t)~cfg->clear_mask) | cfg->set_mask);
    ringlog_printf(log, "CONTROL semantic orig=%02x exp=%02x method=gbi-majority-vote transform=(v&~%02x)|%02x",
                   (unsigned)res->control_orig, (unsigned)res->control_exp, (unsigned)cfg->clear_mask, (unsigned)cfg->set_mask);
    if (cfg->require_idle_shape &&
        (((res->control_orig & cfg->clear_mask) == 0) || ((res->control_orig & cfg->set_mask) != 0))) {
        finish(t, log, res, GBP_INIT_ABORT_CONTROL_SHAPE, "control_not_idle_shape");
        return 0;
    }
    if (res->control_exp == res->control_orig) {
        finish(t, log, res, GBP_INIT_ABORT_CONTROL_SHAPE, "transform_is_noop");
        return 0;
    }

    /* ---- experimental write ------------------------------------------ */
    res->write_rc = write_control_logged(t, log, "tag=EXP", res->base, res->control_exp, res->write_raw, res);
    write_ticks = now(t);
    res->control_written = 1;

    /* ---- S1, S2, S3 (no delays) --------------------------------------- */
    snapshot(t, log, res, 1, 0, write_ticks);
    snapshot(t, log, res, 2, 0, write_ticks);
    res->transition_s1_s2 = (memcmp(res->snap[1].control, res->snap[2].control, GBP_BLOCK_SIZE) != 0 ||
                             memcmp(res->snap[1].irq, res->snap[2].irq, GBP_BLOCK_SIZE) != 0 ||
                             res->snap[1].intsr != res->snap[2].intsr) ? 1 : 0;
    ringlog_printf(log, "TRANSITION s1_s2=%d", res->transition_s1_s2);
    snapshot(t, log, res, 3, 0, write_ticks);

    /* ---- restore CONTROL with the ORIGINAL semantic value ------------- */
    res->restore_rc = write_control_logged(t, log, "tag=RESTORE", res->base, res->control_orig, res->restore_raw, res);
    snapshot(t, log, res, 4, 0, write_ticks);
    res->control_restored = (res->snap[4].control_rc == GBP_OK && res->snap[4].control_vote == res->control_orig) ? 1 : 0;
    ringlog_printf(log, "CONTROL restore semantic=%02x readback_vote=%02x readback_b1f=%02x ok=%d",
                   (unsigned)res->control_orig, (unsigned)res->snap[4].control_vote,
                   (unsigned)res->snap[4].control_b1f, res->control_restored);

    /* ---- INTMR / AR_INFO restore, then S5 ------------------------------ */
    finish(t, log, res, (res->write_rc == GBP_OK && res->restore_rc == GBP_OK && res->errors == 0)
                            ? GBP_INIT_OK : GBP_INIT_ERROR_AFTER_WRITE,
           (res->write_rc == GBP_OK && res->restore_rc == GBP_OK && res->errors == 0) ? "-" : "transfer_error");
    /* S5 is taken after the restores; its CONTROL read happens under the
     * original AR_INFO (base unchanged, expansion code as found). */
    snapshot(t, log, res, 5, 0, write_ticks);
    return 0;
}

int gbp_init_summary(const struct gbp_init_result *res, char *dst, size_t cap)
{
    const struct gbp_init_snapshot *s0 = &res->snap[0], *s1 = &res->snap[1], *s4 = &res->snap[4];
    return snprintf(dst, cap,
                    "DONE status=%s reason=%s verdict=%s det=%u/%u written=%d control_orig=%02x control_exp=%02x "
                    "s0_ctl=%02x s1_ctl=%02x s4_ctl=%02x s0_irq=%04x s1_irq=%04x s0_intsr13=%u s1_intsr13=%u "
                    "transition=%d control_restored=%d arinfo_restored=%d intmr_restored=%d intmr=%08lx errors=%u transport_ok=%d",
                    gbp_init_status_name(res->status), res->abort_reason ? res->abort_reason : "-",
                    gbp_verdict_name(res->det.verdict), res->det.vote_ok, res->det.run, res->control_written,
                    (unsigned)res->control_orig, (unsigned)res->control_exp,
                    (unsigned)s0->control_vote, (unsigned)s1->control_vote, (unsigned)s4->control_vote,
                    (unsigned)s0->irq_disc, (unsigned)s1->irq_disc,
                    (s0->intsr & GBP_PI_HSP_BIT) ? 1u : 0u, (s1->intsr & GBP_PI_HSP_BIT) ? 1u : 0u,
                    res->transition_s1_s2, res->control_restored, res->arinfo_restored, res->intmr_restored,
                    (unsigned long)res->intmr_orig, res->errors, res->transport_ok);
}
