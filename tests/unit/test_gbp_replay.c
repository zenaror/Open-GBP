#include <stdio.h>
#include <stdlib.h>
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

static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb");
    long n; char *buf;
    if (!f) return 0;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    buf = (char *)malloc((size_t)n + 1u);
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(buf); return 0; }
    buf[n] = '\0';
    fclose(f);
    return buf;
}

/* Regression against recorded fixtures. argv[1] = physical run with the
 * GBP attached (2026-09-14), argv[2] = physical baseline without the GBP,
 * argv[3]/argv[4] = Dolphin 2606a model runs (present / absent). The replay
 * backend must reproduce exactly what was logged, and the presence policy
 * must classify each correctly. */
static void run_fixture(const char *path, struct gbp_probe_result *res, struct ringlog *rl, char *store,
                        struct gbp_replay *r)
{
    char *text = read_file(path);
    struct gbp_transport t; struct gbp_probe_config cfg;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; memset(res, 0, sizeof *res); return; }
    gbp_replay_init(r, text);
    gbp_replay_transport(r, &t);
    gbp_probe_config_default(&cfg);          /* same config as probe-0001/0002 */
    ringlog_init(rl, store, 256, 160);
    CHECK(gbp_probe_run(&t, rl, &cfg, res) == 0);
    CHECK(r->exhausted == 0 && r->mismatches == 0);
    free(text);
}

static void test_hardware_fixture_gbp(const char *path)
{
    struct gbp_probe_result res; struct ringlog rl; struct gbp_replay r;
    static char big[160 * 256];
    unsigned k;
    run_fixture(path, &res, &rl, big, &r);
    CHECK(res.arinfo_orig == 0x0043 && res.mode[1].arinfo_before == 0x005b && res.arinfo_final == 0x0043);
    CHECK(res.arinfo_changed == 1 && res.arinfo_restored == 1 && res.errors == 0 && res.transport_ok == 1);
    CHECK(res.mode[0].tests_match_all == 2 && res.mode[0].tests_match_1f == 4);
    CHECK(res.mode[1].tests_match_all == 3 && res.mode[1].tests_match_1f == 4);
    /* official criteria pass 8/8 → PRESENT in both modes (probe-0002 policy) */
    CHECK(res.mode[0].tests_match_b1 == 4 && res.mode[0].tests_match_vote == 4);
    CHECK(res.mode[1].tests_match_b1 == 4 && res.mode[1].tests_match_vote == 4);
    CHECK(res.mode[0].verdict == GBP_VERDICT_PRESENT && res.mode[1].verdict == GBP_VERDICT_PRESENT);
    CHECK(res.present[0] == 1 && res.present[1] == 1);
    for (k = 0; k < GBP_BLOCK_SIZE; k++) { CHECK(res.mode[0].raw[1][k] == 0x00); CHECK(res.mode[0].raw[2][k] == 0x90); }
    for (k = 0; k < GBP_BLOCK_SIZE; k++) CHECK(res.mode[1].raw[1][k] == 0x90);
    CHECK(res.mode[1].raw[2][0] == 0xae && res.mode[1].raw[2][1] == 0x8a && res.mode[1].raw[2][2] == 0xae && res.mode[1].raw[2][3] == 0xae);
    for (k = 4; k < GBP_BLOCK_SIZE; k += 4) {
        CHECK(res.mode[1].raw[2][k] == 0x8a && res.mode[1].raw[2][k + 1] == 0x8a &&
              res.mode[1].raw[2][k + 2] == 0xae && res.mode[1].raw[2][k + 3] == 0xae);
    }
    CHECK(rl.dropped == 0);
    {
        size_t i; int seen7c = 0, seenc7c7 = 0;
        for (i = 0; i < rl.count; i++) {
            const char *l = ringlog_line(&rl, i);
            if (strstr(l, "mode=A") && strstr(l, "data=7c3c3c3c")) seen7c++;
            if (strstr(l, "mode=A") && strstr(l, "data=c7c3c3c3c3c3c7c3")) seenc7c7++;
        }
        CHECK(seen7c == 1 && seenc7c7 == 1);
    }
}

static void test_hardware_fixture_nogbp(const char *path)
{
    struct gbp_probe_result res; struct ringlog rl; struct gbp_replay r;
    static char big[160 * 256];
    unsigned m, i, k;
    run_fixture(path, &res, &rl, big, &r);
    CHECK(res.arinfo_orig == 0x0043 && res.mode[1].arinfo_before == 0x005b && res.arinfo_final == 0x0043);
    CHECK(res.arinfo_restored == 1 && res.errors == 0 && res.transport_ok == 1);
    CHECK(r.step == 36);                                       /* 28 transfers + 6 AR_INFO reads + 2 writes */
    for (m = 0; m < 2; m++) {
        CHECK(res.mode[m].reads_ok == 6 && res.mode[m].tests_run == 4 && res.mode[m].tests_transport_ok == 4);
        CHECK(res.mode[m].tests_match_all == 0 && res.mode[m].tests_match_1f == 0);
        CHECK(res.mode[m].tests_match_b1 == 0 && res.mode[m].tests_match_vote == 0);
        CHECK(res.mode[m].verdict == GBP_VERDICT_ABSENT && res.present[m] == 0);
        for (i = 0; i < 3; i++) for (k = 0; k < GBP_BLOCK_SIZE; k++) CHECK(res.mode[m].raw[i][k] == 0xc0);
    }
    /* every logged block is c0×32: the parser/replay must not have normalized anything */
    {
        size_t li; int n = 0;
        for (li = 0; li < rl.count; li++) if (strstr(ringlog_line(&rl, li), "data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0")) n++;
        CHECK(n == 20);
    }
}

static void test_model_fixtures(const char *present, const char *absent)
{
    struct gbp_probe_result res; struct ringlog rl; struct gbp_replay r;
    static char big[160 * 256];
    run_fixture(present, &res, &rl, big, &r);
    CHECK(res.present[0] == 1 && res.present[1] == 1);         /* Dolphin GBPlayer model: uniform inverse */
    run_fixture(absent, &res, &rl, big, &r);
    /* Dolphin without HSP device returns zeros: only the FF pattern "passes" → inconsistent, not present */
    CHECK(res.mode[0].tests_match_vote == 1 && res.mode[0].tests_match_b1 == 1);
    CHECK(res.mode[0].verdict == GBP_VERDICT_INCONSISTENT && res.present[0] == 0 && res.present[1] == 0);
}

int main(int argc, char **argv)
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

    /* A FULL constructor must leave every operation it does not provide reading back as NULL, not
     * as whatever the caller's stack held: callers declare `struct gbp_transport t;` without
     * initialising it, and gbp_transport_has_*() answers from those fields. Poison the struct and
     * prove the constructor zeroes it — this is what keeps a newly added transport operation from
     * silently becoming a garbage pointer on a replay. */
    {
        struct gbp_transport poisoned;
        struct gbp_replay rr;
        memset(&poisoned, 0xAB, sizeof poisoned);
        gbp_replay_init(&rr, "R 01000000 ok 00\n");
        gbp_replay_transport(&rr, &poisoned);
        CHECK(poisoned.ctx == &rr);
        CHECK(poisoned.ticks == t.ticks);
        CHECK(poisoned.ticks64 == 0);                    /* a replay has no 64-bit time base */
        CHECK(gbp_transport_has_time64(&poisoned) == 0);
        CHECK(poisoned.irq_install == 0);                /* and no interrupt path */
        CHECK(gbp_transport_has_irq_path(&poisoned) == 0);
        CHECK(poisoned.read_bulk == 0);                  /* this script has no bulk lines */
        CHECK(gbp_transport_has_bulk_read(&poisoned) == 0);
        /* and not one poison byte survives anywhere in the struct, so a field added tomorrow
         * cannot come back indeterminate either */
        {
            const unsigned char *p = (const unsigned char *)&poisoned;
            size_t k, run = 0, worst = 0;
            for (k = 0; k < sizeof poisoned; k++) {
                run = (p[k] == 0xABu) ? run + 1u : 0u;
                if (run > worst) worst = run;
            }
            CHECK(worst < sizeof(void *));     /* no whole pointer-sized field left as poison */
        }
    }

    if (argc > 1) test_hardware_fixture_gbp(argv[1]);
    if (argc > 2) test_hardware_fixture_nogbp(argv[2]);
    if (argc > 4) test_model_fixtures(argv[3], argv[4]);

    printf("test_gbp_replay: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
