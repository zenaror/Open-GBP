#include "gbp_detect.h"

uint8_t gbp_majority_vote_byte(const uint8_t block[GBP_BLOCK_SIZE])
{
    unsigned bit, i, out = 0;
    for (bit = 0; bit < 8; bit++) {
        unsigned count = 0;
        for (i = 0; i < GBP_BLOCK_SIZE; i++) {
            count += (block[i] >> bit) & 1u;
        }
        /* GBI: starts at 16, subtracts one per set bit, takes the sign:
         * the bit is 1 only when strictly more than half are set. */
        if (count > GBP_BLOCK_SIZE / 2u) {
            out |= 1u << bit;
        }
    }
    return (uint8_t)out;
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
