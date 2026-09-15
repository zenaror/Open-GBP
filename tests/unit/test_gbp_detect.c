/* gbp_detect: official TEST criteria and the presence policy, checked on the
 * exact blocks the hardware returned on 2026-09-14 (with and without GBP). */
#include <stdio.h>
#include <string.h>
#include "gbp_detect.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static void fill(uint8_t *b, uint8_t v) { memset(b, v, GBP_BLOCK_SIZE); }

int main(void)
{
    uint8_t b[GBP_BLOCK_SIZE];

    /* --- hardware, GBP attached: anomalous byte 0 (and once byte 6) --- */
    fill(b, 0x3c); b[0] = 0x7c;                       /* C3 response, MODE A */
    CHECK(gbp_test_startup_disc_style(b, 0xc3) == 1);
    CHECK(gbp_test_majority_vote(b, 0xc3) == 1);
    CHECK(gbp_majority_vote_byte(b) == 0x3c);
    CHECK(gbp_test_whole_block(b, 0xc3) == 0);
    fill(b, 0xc3); b[0] = 0xc7; b[6] = 0xc7;          /* 3C response, MODE A */
    CHECK(gbp_test_startup_disc_style(b, 0x3c) == 1);
    CHECK(gbp_test_majority_vote(b, 0x3c) == 1);
    CHECK(gbp_test_whole_block(b, 0x3c) == 0);
    fill(b, 0x00);                                    /* FF response */
    CHECK(gbp_test_startup_disc_style(b, 0xff) && gbp_test_majority_vote(b, 0xff) && gbp_test_whole_block(b, 0xff));
    fill(b, 0xff);                                    /* 00 response */
    CHECK(gbp_test_startup_disc_style(b, 0x00) && gbp_test_majority_vote(b, 0x00) && gbp_test_whole_block(b, 0x00));

    /* --- hardware, GBP removed: 0xC0 everywhere, every pattern must fail --- */
    fill(b, 0xc0);
    CHECK(!gbp_test_startup_disc_style(b, 0xc3) && !gbp_test_majority_vote(b, 0xc3));
    CHECK(!gbp_test_startup_disc_style(b, 0x3c) && !gbp_test_majority_vote(b, 0x3c));
    CHECK(!gbp_test_startup_disc_style(b, 0xff) && !gbp_test_majority_vote(b, 0xff));
    CHECK(!gbp_test_startup_disc_style(b, 0x00) && !gbp_test_majority_vote(b, 0x00));

    /* --- vote threshold is "strictly more than 16" like GBI --- */
    fill(b, 0x00); memset(b, 0x01, 16);               /* 16 of 32 set → bit stays 0 */
    CHECK(gbp_majority_vote_byte(b) == 0x00);
    memset(b, 0x01, 17);                              /* 17 of 32 → 1 */
    CHECK(gbp_majority_vote_byte(b) == 0x01);
    /* vote survives up to 15 corrupted bytes; byte 1 does not survive its own corruption */
    fill(b, 0x3c); memset(b, 0xff, 15);
    CHECK(gbp_test_majority_vote(b, 0xc3) == 1);
    CHECK(gbp_test_startup_disc_style(b, 0xc3) == 0);

    /* --- policy --- */
    CHECK(gbp_presence_verdict(0, 0, 0, 0) == GBP_VERDICT_NO_DATA);
    CHECK(gbp_presence_verdict(4, 4, 4, 4) == GBP_VERDICT_PRESENT);
    CHECK(gbp_presence_verdict(4, 4, 0, 0) == GBP_VERDICT_ABSENT);
    CHECK(gbp_presence_verdict(4, 4, 1, 1) == GBP_VERDICT_INCONSISTENT);   /* e.g. zeros: only FF passes */
    CHECK(gbp_presence_verdict(4, 4, 4, 3) == GBP_VERDICT_INCONSISTENT);   /* criteria disagree */
    CHECK(gbp_presence_verdict(4, 3, 3, 3) == GBP_VERDICT_INCONSISTENT);   /* a transfer failed */
    CHECK(strcmp(gbp_verdict_name(GBP_VERDICT_PRESENT), "present") == 0);

    printf("test_gbp_detect: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
