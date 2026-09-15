#include "gbp_probe.h"

#include <stdio.h>
#include <string.h>

void gbp_probe_config_default(struct gbp_probe_config *cfg)
{
    memset(cfg, 0, sizeof *cfg);
    /* Values used by the Start-up Disc (C3 3C FF 00); GBI uses C3 and FF. */
    cfg->patterns[0] = 0xC3;
    cfg->patterns[1] = 0x3C;
    cfg->patterns[2] = 0xFF;
    cfg->patterns[3] = 0x00;
    cfg->npatterns = 4;
    cfg->indices[0] = 0x0;   /* TEST */
    cfg->indices[1] = 0x4;   /* CONTROL */
    cfg->indices[2] = 0xD;   /* IRQ */
    cfg->nindices = 3;
    cfg->expansion_code = 3;
    cfg->run_mode_b = 1;
    cfg->handshake_index = 0;
}

static const char *mode_name(unsigned m)
{
    return m == 0 ? "A" : "B";
}

static gbp_status read_arinfo_logged(const struct gbp_transport *t, struct ringlog *log,
                                     const char *tag, uint16_t *v, struct gbp_probe_result *res)
{
    gbp_status rc = t->read_arinfo(t->ctx, v);
    if (rc != GBP_OK) {
        if (res->arinfo_rc == 0) res->arinfo_rc = (int)rc;
        res->errors++;
        ringlog_printf(log, "ARINFO %s rc=%s", tag, gbp_status_name(rc));
    } else {
        ringlog_printf(log, "ARINFO %s value=%04x size_code=%u exp_code=%u base=%08lx", tag,
                       (unsigned)*v, (unsigned)(*v & 7u), (unsigned)((*v >> 3) & 7u),
                       (unsigned long)gbp_internal_size_from_arinfo(*v));
    }
    return rc;
}

static void dump_blocks(const struct gbp_transport *t, struct ringlog *log,
                        const struct gbp_probe_config *cfg, unsigned m,
                        struct gbp_probe_mode_result *mr, struct gbp_probe_result *res)
{
    unsigned i;
    char hex[GBP_BLOCK_SIZE * 2 + 1];

    for (i = 0; i < cfg->nindices && i < GBP_PROBE_MAX_INDICES; i++) {
        struct gbp_xfer_info info;
        uint32_t addr = gbp_block_addr(mr->base, cfg->indices[i], 0);
        gbp_status rc;

        memset(&info, 0, sizeof info);
        memset(mr->raw[i], 0, GBP_BLOCK_SIZE);
        rc = t->read_block(t->ctx, addr, mr->raw[i], &info);
        mr->raw_rc[i] = rc;
        if (rc == GBP_OK) {
            mr->reads_ok++;
        } else {
            mr->reads_failed++;
            res->errors++;
        }
        ringlog_hex(hex, sizeof hex, mr->raw[i], GBP_BLOCK_SIZE);
        ringlog_printf(log, "RAW mode=%s idx=%x addr=%08lx rc=%s ticks=%lu polls=%u dspcr=%04x data=%s",
                       mode_name(m), cfg->indices[i], (unsigned long)addr, gbp_status_name(rc),
                       (unsigned long)info.ticks, (unsigned)info.polls, (unsigned)info.dma_status,
                       rc == GBP_OK ? hex : "-");
    }
}

static void handshake(const struct gbp_transport *t, struct ringlog *log,
                      const struct gbp_probe_config *cfg, unsigned m,
                      struct gbp_probe_mode_result *mr, struct gbp_probe_result *res)
{
    unsigned p;
    uint8_t out[GBP_BLOCK_SIZE];
    uint8_t in[GBP_BLOCK_SIZE];
    char hex[GBP_BLOCK_SIZE * 2 + 1];
    uint32_t addr = gbp_block_addr(mr->base, (unsigned)cfg->handshake_index, 0);

    for (p = 0; p < cfg->npatterns && p < GBP_PROBE_MAX_PATTERNS; p++) {
        struct gbp_xfer_info wi, ri;
        uint8_t pat = cfg->patterns[p];
        uint8_t expect = (uint8_t)~pat;
        gbp_status wrc, rrc;
        unsigned match_all = 0, match_1f = 0, match_b1 = 0, match_vote = 0, vote = 0;

        memset(&wi, 0, sizeof wi);
        memset(&ri, 0, sizeof ri);
        memset(out, pat, sizeof out);
        memset(in, 0, sizeof in);
        mr->tests_run++;

        wrc = t->write_block(t->ctx, addr, out, &wi);
        ringlog_printf(log, "TESTW mode=%s idx=%x pattern=%02x rc=%s ticks=%lu polls=%u dspcr=%04x",
                       mode_name(m), (unsigned)cfg->handshake_index, (unsigned)pat,
                       gbp_status_name(wrc), (unsigned long)wi.ticks, (unsigned)wi.polls,
                       (unsigned)wi.dma_status);
        if (wrc != GBP_OK) {
            mr->tests_failed++;
            res->errors++;
            continue;
        }
        rrc = t->read_block(t->ctx, addr, in, &ri);
        if (rrc == GBP_OK) {
            mr->tests_transport_ok++;
            match_all = (unsigned)gbp_test_whole_block(in, pat);
            match_1f = (in[GBP_BLOCK_SIZE - 1u] == expect) ? 1u : 0u;
            match_b1 = (unsigned)gbp_test_startup_disc_style(in, pat);
            match_vote = (unsigned)gbp_test_majority_vote(in, pat);
            vote = gbp_majority_vote_byte(in);
            mr->tests_match_all += match_all;
            mr->tests_match_1f += match_1f;
            mr->tests_match_b1 += match_b1;
            mr->tests_match_vote += match_vote;
        } else {
            mr->tests_failed++;
            res->errors++;
        }
        ringlog_hex(hex, sizeof hex, in, GBP_BLOCK_SIZE);
        ringlog_printf(log, "TESTR mode=%s idx=%x pattern=%02x expect=%02x rc=%s ticks=%lu polls=%u dspcr=%04x match_all=%u match_1f=%u match_b1=%u match_vote=%u vote=%02x data=%s",
                       mode_name(m), (unsigned)cfg->handshake_index, (unsigned)pat, (unsigned)expect,
                       gbp_status_name(rrc), (unsigned long)ri.ticks, (unsigned)ri.polls,
                       (unsigned)ri.dma_status, match_all, match_1f, match_b1, match_vote, vote,
                       rrc == GBP_OK ? hex : "-");
    }
}

int gbp_probe_run(const struct gbp_transport *t, struct ringlog *log,
                  const struct gbp_probe_config *cfg, struct gbp_probe_result *res)
{
    unsigned m, nmodes;
    uint16_t v;

    memset(res, 0, sizeof *res);
    ringlog_printf(log, "PROBE start npatterns=%u nindices=%u exp_code=%u mode_b=%d",
                   cfg->npatterns, cfg->nindices, cfg->expansion_code, cfg->run_mode_b);

    if (read_arinfo_logged(t, log, "orig", &res->arinfo_orig, res) != GBP_OK) {
        ringlog_printf(log, "PROBE abort reason=arinfo_unreadable");
        return -1;
    }

    nmodes = cfg->run_mode_b ? 2u : 1u;
    for (m = 0; m < nmodes; m++) {
        struct gbp_probe_mode_result *mr = &res->mode[m];

        if (m == 1) {
            uint16_t want = gbp_arinfo_with_expansion(res->arinfo_orig, cfg->expansion_code);
            gbp_status rc = t->write_arinfo(t->ctx, want);
            res->arinfo_changed = 1;
            ringlog_printf(log, "ARINFO write mode=B value=%04x rc=%s", (unsigned)want, gbp_status_name(rc));
            if (rc != GBP_OK) {
                res->errors++;
                if (res->arinfo_rc == 0) res->arinfo_rc = (int)rc;
            }
        }
        if (read_arinfo_logged(t, log, m == 0 ? "modeA" : "modeB", &v, res) != GBP_OK) {
            v = res->arinfo_orig;
        }
        mr->arinfo_before = v;
        mr->base = gbp_internal_size_from_arinfo(v);
        ringlog_printf(log, "MODE %s begin base=%08lx", mode_name(m), (unsigned long)mr->base);

        dump_blocks(t, log, cfg, m, mr, res);
        handshake(t, log, cfg, m, mr, res);
        /* Second raw dump after the handshake: shows what the writes left behind. */
        dump_blocks(t, log, cfg, m, mr, res);

        if (read_arinfo_logged(t, log, m == 0 ? "endA" : "endB", &v, res) == GBP_OK) {
            mr->arinfo_after = v;
        }
        mr->verdict = gbp_presence_verdict(mr->tests_run, mr->tests_transport_ok,
                                           mr->tests_match_vote, mr->tests_match_b1);
        res->present[m] = (mr->verdict == GBP_VERDICT_PRESENT) ? 1 : 0;
        ringlog_printf(log, "MODE %s end reads_ok=%u reads_failed=%u tests=%u transport_ok=%u match_all=%u match_1f=%u match_b1=%u match_vote=%u tests_failed=%u verdict=%s present=%d",
                       mode_name(m), mr->reads_ok, mr->reads_failed, mr->tests_run, mr->tests_transport_ok,
                       mr->tests_match_all, mr->tests_match_1f, mr->tests_match_b1, mr->tests_match_vote,
                       mr->tests_failed, gbp_verdict_name(mr->verdict), res->present[m]);
        res->modes_run++;
    }

    if (res->arinfo_changed) {
        gbp_status rc = t->write_arinfo(t->ctx, res->arinfo_orig);
        ringlog_printf(log, "ARINFO restore value=%04x rc=%s", (unsigned)res->arinfo_orig, gbp_status_name(rc));
        if (rc != GBP_OK) {
            res->errors++;
            if (res->arinfo_rc == 0) res->arinfo_rc = (int)rc;
        }
    }
    if (read_arinfo_logged(t, log, "final", &res->arinfo_final, res) != GBP_OK) {
        res->arinfo_final = 0xFFFF;
    }
    res->arinfo_restored = (res->arinfo_final == res->arinfo_orig) ? 1 : 0;
    res->transport_ok = (res->errors == 0) ? 1 : 0;
    ringlog_printf(log, "PROBE end modes=%u errors=%u transport_ok=%d changed=%d restored=%d",
                   res->modes_run, res->errors, res->transport_ok, res->arinfo_changed, res->arinfo_restored);
    return 0;
}

int gbp_probe_summary(const struct gbp_probe_result *res, char *dst, size_t cap)
{
    return snprintf(dst, cap,
                    "DONE modes=%u a_present=%d b_present=%d a_verdict=%s b_verdict=%s "
                    "a_vote=%u/%u b_vote=%u/%u a_b1=%u/%u b_b1=%u/%u a_all32=%u/%u b_all32=%u/%u "
                    "a_reads=%u/%u b_reads=%u/%u errors=%u transport_ok=%d arinfo=%04x changed=%d restored=%d final=%04x",
                    res->modes_run, res->present[0], res->present[1],
                    gbp_verdict_name(res->mode[0].verdict), gbp_verdict_name(res->mode[1].verdict),
                    res->mode[0].tests_match_vote, res->mode[0].tests_run,
                    res->mode[1].tests_match_vote, res->mode[1].tests_run,
                    res->mode[0].tests_match_b1, res->mode[0].tests_run,
                    res->mode[1].tests_match_b1, res->mode[1].tests_run,
                    res->mode[0].tests_match_all, res->mode[0].tests_run,
                    res->mode[1].tests_match_all, res->mode[1].tests_run,
                    res->mode[0].reads_ok, res->mode[0].reads_ok + res->mode[0].reads_failed,
                    res->mode[1].reads_ok, res->mode[1].reads_ok + res->mode[1].reads_failed,
                    res->errors, res->transport_ok, (unsigned)res->arinfo_orig, res->arinfo_changed,
                    res->arinfo_restored, (unsigned)res->arinfo_final);
}
