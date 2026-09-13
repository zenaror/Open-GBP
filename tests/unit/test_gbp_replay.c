#include <stdio.h>
#include <string.h>
#include "gbp_probe.h"
#include "gbp_replay.h"
#include "gbp_mock.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static char storage[64 * 200];

/* A hand-written script for a mode-A-only run with one index and one pattern. */
static const char script[] =
    "# replay fixture\n"
    "A r 0043\n"
    "A r 0043\n"
    "R 01000000 ok 3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c\n"
    "W 01000000 ok\n"
    "R 01000000 ok 3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c\n"
    "R 01000000 ok 3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c\n"
    "A r 0043\n"
    "A r 0043\n";

int main(void)
{
    struct gbp_replay r; struct gbp_transport t; struct gbp_probe_config cfg;
    struct gbp_probe_result res; struct ringlog rl;
    uint8_t out[GBP_BLOCK_SIZE];
    uint8_t buf[4];

    CHECK(gbp_hex_decode("0aFFzz", buf, 4) == 2 && buf[0] == 0x0a && buf[1] == 0xff);

    gbp_replay_init(&r, script);
    gbp_replay_transport(&r, &t);
    gbp_probe_config_default(&cfg);
    cfg.npatterns = 1; cfg.patterns[0] = 0xC3;
    cfg.nindices = 1; cfg.indices[0] = 0;
    cfg.run_mode_b = 0;
    ringlog_init(&rl, storage, 200, 64);
    CHECK(gbp_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.present[0] == 1);
    CHECK(res.errors == 0);
    CHECK(r.exhausted == 0 && r.mismatches == 0 && r.step == 8);

    /* exhausted script → backend errors, no crash */
    CHECK(t.read_block(t.ctx, 0x01000000, out, 0) == GBP_ERR_BACKEND);
    CHECK(r.exhausted == 1);

    /* address mismatch is flagged */
    gbp_replay_init(&r, "R 01400000 ok 00\n");
    CHECK(t.read_block(t.ctx, 0x01000000, out, 0) == GBP_ERR_BACKEND);
    CHECK(r.mismatches == 1);

    /* rc names round-trip */
    gbp_replay_init(&r, "R 01000000 timeout\nW 01000000 busy\nA w 005b\n");
    CHECK(t.read_block(t.ctx, 0x01000000, out, 0) == GBP_ERR_TIMEOUT);
    CHECK(t.write_block(t.ctx, 0x01000000, out, 0) == GBP_ERR_BUSY);
    CHECK(t.write_arinfo(t.ctx, 0x005b) == GBP_OK);
    CHECK(t.write_arinfo(t.ctx, 0x0000) == GBP_ERR_BACKEND);

    printf("test_gbp_replay: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
