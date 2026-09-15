#include "gbp_detect.h"

#include <string.h>

uint8_t gbp_majority_vote_byte_n(const uint8_t *bytes, unsigned n)
{
    unsigned bit, i, out = 0;
    for (bit = 0; bit < 8; bit++) {
        unsigned count = 0;
        for (i = 0; i < n; i++) {
            count += (bytes[i] >> bit) & 1u;
        }
        /* GBI: starts at n/2, subtracts one per set bit, takes the sign:
         * the bit is 1 only when strictly more than half are set. */
        if (count > n / 2u) {
            out |= 1u << bit;
        }
    }
    return (uint8_t)out;
}

uint8_t gbp_majority_vote_byte(const uint8_t block[GBP_BLOCK_SIZE])
{
    return gbp_majority_vote_byte_n(block, GBP_BLOCK_SIZE);
}

int gbp_test_startup_disc_style(const uint8_t resp[GBP_BLOCK_SIZE], uint8_t pattern)
{
    return resp[1] == (uint8_t)~pattern;
}

int gbp_test_majority_vote(const uint8_t resp[GBP_BLOCK_SIZE], uint8_t pattern)
{
    return gbp_majority_vote_byte(resp) == (uint8_t)~pattern;
}

int gbp_test_whole_block(const uint8_t resp[GBP_BLOCK_SIZE], uint8_t pattern)
{
    unsigned i;
    uint8_t expect = (uint8_t)~pattern;
    for (i = 0; i < GBP_BLOCK_SIZE; i++) {
        if (resp[i] != expect) return 0;
    }
    return 1;
}

gbp_verdict gbp_presence_verdict(unsigned n_handshakes, unsigned n_transport_ok,
                                 unsigned n_vote_ok, unsigned n_disc_ok)
{
    if (n_handshakes == 0) return GBP_VERDICT_NO_DATA;
    if (n_transport_ok != n_handshakes) return GBP_VERDICT_INCONSISTENT;
    if (n_vote_ok == n_handshakes && n_disc_ok == n_handshakes) return GBP_VERDICT_PRESENT;
    if (n_vote_ok == 0 && n_disc_ok == 0) return GBP_VERDICT_ABSENT;
    return GBP_VERDICT_INCONSISTENT;
}

const char *gbp_verdict_name(gbp_verdict v)
{
    switch (v) {
    case GBP_VERDICT_ABSENT: return "absent";
    case GBP_VERDICT_PRESENT: return "present";
    case GBP_VERDICT_INCONSISTENT: return "inconsistent";
    case GBP_VERDICT_NO_DATA: return "no_data";
    default: return "?";
    }
}

void gbp_detect_handshake(const struct gbp_transport *t, struct ringlog *log, const char *tag,
                          uint32_t base, unsigned index, const uint8_t *patterns, unsigned npatterns,
                          struct gbp_handshake_result *out)
{
    unsigned p;
    uint8_t wr[GBP_BLOCK_SIZE];
    uint8_t in[GBP_BLOCK_SIZE];
    char hex[GBP_BLOCK_SIZE * 2 + 1];
    uint32_t addr = gbp_block_addr(base, index, 0);

    memset(out, 0, sizeof *out);
    for (p = 0; p < npatterns; p++) {
        struct gbp_xfer_info wi, ri;
        uint8_t pat = patterns[p];
        uint8_t expect = (uint8_t)~pat;
        gbp_status wrc, rrc;
        unsigned all32 = 0, b1f = 0, b1 = 0, vote_ok = 0, vote = 0;

        memset(&wi, 0, sizeof wi);
        memset(&ri, 0, sizeof ri);
        memset(wr, pat, sizeof wr);
        memset(in, 0, sizeof in);
        out->run++;

        wrc = t->write_block(t->ctx, addr, wr, &wi);
        ringlog_printf(log, "TESTW %s idx=%x addr=%08lx pattern=%02x rc=%s ticks=%lu polls=%u dspcr=%04x",
                       tag, index, (unsigned long)addr, (unsigned)pat, gbp_status_name(wrc),
                       (unsigned long)wi.ticks, (unsigned)wi.polls, (unsigned)wi.dma_status);
        if (wrc != GBP_OK) {
            out->failed++;
            continue;
        }
        rrc = t->read_block(t->ctx, addr, in, &ri);
        if (rrc == GBP_OK) {
            out->transport_ok++;
            all32 = (unsigned)gbp_test_whole_block(in, pat);
            b1f = (in[GBP_BLOCK_SIZE - 1u] == expect) ? 1u : 0u;
            b1 = (unsigned)gbp_test_startup_disc_style(in, pat);
            vote_ok = (unsigned)gbp_test_majority_vote(in, pat);
            vote = gbp_majority_vote_byte(in);
            out->all32_ok += all32;
            out->b1f_ok += b1f;
            out->b1_ok += b1;
            out->vote_ok += vote_ok;
            memcpy(out->last_resp, in, GBP_BLOCK_SIZE);
        } else {
            out->failed++;
        }
        ringlog_hex(hex, sizeof hex, in, GBP_BLOCK_SIZE);
        ringlog_printf(log, "TESTR %s idx=%x addr=%08lx pattern=%02x expect=%02x rc=%s ticks=%lu polls=%u dspcr=%04x match_all=%u match_1f=%u match_b1=%u match_vote=%u vote=%02x data=%s",
                       tag, index, (unsigned long)addr, (unsigned)pat, (unsigned)expect,
                       gbp_status_name(rrc), (unsigned long)ri.ticks, (unsigned)ri.polls,
                       (unsigned)ri.dma_status, all32, b1f, b1, vote_ok, vote, rrc == GBP_OK ? hex : "-");
    }
    out->verdict = gbp_presence_verdict(out->run, out->transport_ok, out->vote_ok, out->b1_ok);
}
