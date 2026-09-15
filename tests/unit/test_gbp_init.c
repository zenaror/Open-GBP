/*
 * GBP-INIT-001 logic against the mock and against replay scripts built
 * from the physical captures of 2026-09-14. Every scenario required by the
 * Phase 3 plan is here; the physical no-GBP data must never reach the
 * CONTROL write.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_init_probe.h"
#include "gbp_replay.h"
#include "gbp_mock.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

#define LINES 160
#define LINE_LEN 256
static char storage[LINES * LINE_LEN];

/* physical blocks, GBP attached, expansion code 3 (captures/fixtures/hw-gamecube-gbp-…) */
static const uint8_t HW_CONTROL_94[32] = { 0x94, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90,
                                           0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
static const uint8_t HW_IRQ_8AAE[32] = { 0xae, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae,
                                         0x8a, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae };

static int count_lines_with(const struct ringlog *rl, const char *needle)
{
    size_t i; int n = 0;
    for (i = 0; i < rl->count; i++) if (strstr(ringlog_line(rl, i), needle)) n++;
    return n;
}

static void run(struct gbp_mock *m, struct ringlog *rl, struct gbp_init_result *res)
{
    struct gbp_transport t; struct gbp_init_config cfg;
    gbp_mock_transport(m, &t);
    gbp_init_config_default(&cfg);
    ringlog_init(rl, storage, LINE_LEN, LINES);
    gbp_init_probe_run(&t, rl, &cfg, res);
}

static void test_present_normal(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_init_result res;
    gbp_mock_init(&m);                       /* control 0x90, intmr 0xf0 (masked), intsr 0 */
    m.intsr_bit13_follows_control = 1;       /* one possible hardware behavior; not a claim */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INIT_OK);
    CHECK(res.det.verdict == GBP_VERDICT_PRESENT && res.det.vote_ok == 4 && res.det.b1_ok == 4);
    CHECK(res.arinfo_orig == 0x0043 && res.arinfo_exp == 0x005b && res.arinfo_final == 0x0043 && res.arinfo_restored == 1);
    CHECK(res.intmr_changed == 0 && res.intmr_restored == -1);
    CHECK(res.control_orig == 0x90 && res.control_exp == 0x8c);
    CHECK(res.control_written == 1 && res.write_rc == GBP_OK);
    CHECK(res.write_raw[0] == 0x8c && res.write_raw[31] == 0x8c);            /* GBI layout */
    CHECK(res.restore_raw[0] == 0x90 && res.restore_raw[31] == 0x90);        /* original value, not an inverse */
    CHECK(res.snap[1].control_vote == 0x8c && res.snap[4].control_vote == 0x90);
    CHECK((res.snap[0].intsr & GBP_PI_HSP_BIT) == 0 && (res.snap[1].intsr & GBP_PI_HSP_BIT) != 0 && (res.snap[4].intsr & GBP_PI_HSP_BIT) == 0);
    CHECK(res.control_restored == 1 && res.transport_ok == 1 && res.errors == 0);
    CHECK(res.snap[5].taken && res.snap[0].has_test && !res.snap[1].has_test);
    CHECK(m.control_writes == 2);                                            /* experimental + restore, nothing else */
    CHECK(gbp_mock_writes_outside(&m, 0x01000000, 0) == 2);                  /* the two CONTROL writes are the only non-TEST writes */
    CHECK(count_lines_with(&rl, "CTLW tag=EXP") == 1 && count_lines_with(&rl, "CTLW tag=RESTORE") == 1);
    CHECK(count_lines_with(&rl, "SNAP tag=S") == 6);
    CHECK(count_lines_with(&rl, "idx=d") == 6);                              /* IRQ read in every snapshot, never written */
    CHECK(rl.dropped == 0 && rl.truncated == 0);
    /* summary line carries the essentials */
    {
        char s[400];
        gbp_init_summary(&res, s, sizeof s);
        CHECK(strstr(s, "status=ok") && strstr(s, "written=1") && strstr(s, "control_restored=1 arinfo_restored=1 intmr_restored=-1"));
    }
}

static void test_absent_and_inconsistent_never_write(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_init_result res;
    gbp_mock_init(&m); m.present = 0; m.absent_fill = 0xC0;                 /* physical no-GBP baseline */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INIT_ABORT_NOT_PRESENT && res.det.verdict == GBP_VERDICT_ABSENT);
    CHECK(res.control_written == 0 && m.control_writes == 0);
    CHECK(res.arinfo_restored == 1 && m.arinfo == 0x0043);
    CHECK(count_lines_with(&rl, "CTLW") == 0 && count_lines_with(&rl, "SNAP") == 0);

    gbp_mock_init(&m); m.present = 0; m.absent_fill = 0x00;                 /* zeros: FF pattern passes → inconsistent */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INIT_ABORT_NOT_PRESENT && res.det.verdict == GBP_VERDICT_INCONSISTENT);
    CHECK(m.control_writes == 0 && res.arinfo_restored == 1);
}

static void test_control_shapes(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_init_result res;
    /* bit 0x10 initially clear → not the required shape → no write */
    gbp_mock_init(&m); m.control_byte = 0x80;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INIT_ABORT_CONTROL_SHAPE && m.control_writes == 0 && res.arinfo_restored == 1);
    /* bits 0x0C already set → no write */
    gbp_mock_init(&m); m.control_byte = 0x9C;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INIT_ABORT_CONTROL_SHAPE && m.control_writes == 0);
    /* byte-0 anomaly as seen on hardware (94 90 90 …): vote and byte 0x1F agree → proceeds with orig 0x90 */
    gbp_mock_init(&m); m.control_block = HW_CONTROL_94; m.irq_block = HW_IRQ_8AAE;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INIT_OK && res.control_orig == 0x90 && res.control_exp == 0x8c);
    CHECK(res.snap[0].control[0] == 0x94 && res.snap[0].control_b1f == 0x90 && res.snap[0].control_vote == 0x90);
    CHECK(res.snap[0].irq_disc == 0x8aae && count_lines_with(&rl, "sem_disc=8aae sem_gbi=8aae") >= 1);
    /* ambiguous read: vote != byte 0x1F → abort */
    {
        static uint8_t half[32];
        memset(half, 0x90, 15); memset(half + 15, 0x80, 17);   /* vote: bit4 set in 15/32 → 0x80 */
        half[31] = 0x90;                                        /* b1f 0x90 ≠ vote 0x80 (bit4 now 16/32, still 0) */
        gbp_mock_init(&m); m.control_block = half;
        run(&m, &rl, &res);
        CHECK(res.status == GBP_INIT_ABORT_CONTROL_READ && m.control_writes == 0);
    }
}

static void test_intmr_paths(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_init_result res;
    /* initially unmasked (bit 13 set): probe clears only that bit, restores it at the end */
    gbp_mock_init(&m); m.intmr = 0x000020f0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INIT_OK && res.intmr_changed == 1 && res.intmr_exp == 0x000000f0);
    CHECK(res.intmr_restored == 1 && m.intmr == 0x000020f0 && m.intmr_writes == 2);
    /* INTMR write ignored → cannot mask → abort before the CONTROL write, restore AR_INFO */
    gbp_mock_init(&m); m.intmr = 0x000020f0; m.intmr_write_ignored = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INIT_ABORT_PI && m.control_writes == 0 && res.arinfo_restored == 1);
    /* PI unreadable → abort */
    gbp_mock_init(&m); m.pi_unavailable = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INIT_ABORT_PI && m.control_writes == 0);
    /* INTSR bit 13 initially set: recorded, experiment still runs, no ack ever issued */
    gbp_mock_init(&m); m.intsr = GBP_PI_HSP_BIT;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INIT_OK && (res.snap[0].intsr & GBP_PI_HSP_BIT) && (res.snap[5].intsr & GBP_PI_HSP_BIT));
    CHECK(count_lines_with(&rl, "intsr13=1") >= 6);
}

static void test_timeouts_and_restore_failures(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_init_result res;
    /* timeout before the write (during detection) → inconsistent → no write */
    gbp_mock_init(&m); m.fail_at_op = 2; m.fail_rc = GBP_ERR_TIMEOUT;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INIT_ABORT_NOT_PRESENT && m.control_writes == 0 && res.arinfo_restored == 1);
    /* timeout on the experimental write itself: restore still attempted, status error_after_write */
    gbp_mock_init(&m); m.fail_at_op = 12; m.fail_rc = GBP_ERR_TIMEOUT;     /* 8 handshake + 3 S0 reads + 1 = write */
    run(&m, &rl, &res);
    CHECK(res.control_written == 1 && res.write_rc == GBP_ERR_TIMEOUT);
    CHECK(res.status == GBP_INIT_ERROR_AFTER_WRITE && res.restore_rc == GBP_OK && res.control_restored == 1);
    CHECK(res.arinfo_restored == 1 && res.transport_ok == 0);
    /* timeout during restore: flagged, AR_INFO still restored */
    gbp_mock_init(&m); m.fail_at_op = 19; m.fail_rc = GBP_ERR_TIMEOUT;     /* write + 3 snapshots × 2 reads = 12+6 → 19 = restore */
    run(&m, &rl, &res);
    CHECK(res.restore_rc == GBP_ERR_TIMEOUT && res.status == GBP_INIT_ERROR_AFTER_WRITE);
    CHECK(res.arinfo_restored == 1);
    /* restore write ignored by the device: readback ≠ orig → control_restored=0, everything else restored */
    gbp_mock_init(&m); m.control_write_fail_at = 2;
    run(&m, &rl, &res);
    CHECK(res.control_restored == 0 && res.snap[4].control_vote == 0x8c && res.arinfo_restored == 1);
    /* AR_INFO restore failure is reported (mock cannot fail AR writes; verify the flag logic via final mismatch) */
    CHECK(count_lines_with(&rl, "ARINFO restore") == 1);
    /* ring overflow: sequence completes and restores regardless */
    {
        struct gbp_transport t; struct gbp_init_config cfg;
        gbp_mock_init(&m);
        gbp_mock_transport(&m, &t);
        gbp_init_config_default(&cfg);
        ringlog_init(&rl, storage, LINE_LEN, 6);
        gbp_init_probe_run(&t, &rl, &cfg, &res);
        CHECK(rl.dropped > 0 && res.status == GBP_INIT_OK && res.control_restored == 1 && res.arinfo_restored == 1);
    }
    /* truncation: the longest record must fit 256 bytes */
    gbp_mock_init(&m); m.control_block = HW_CONTROL_94; m.irq_block = HW_IRQ_8AAE;
    run(&m, &rl, &res);
    CHECK(rl.truncated == 0);
}

/* Replay: the physical no-GBP handshake bytes must stop the probe before
 * any CONTROL write; the script deliberately contains no W to 0x01400000. */
static void test_replay_nogbp_never_writes_control(void)
{
    static const char script[] =
        "# derived from hw-gamecube-nogbp-2026-09-14-probe-0001 (MODE B handshakes)\n"
        "A r 0043\nA w 005b\nA r 005b\n"
        "W 01000000 ok\nR 01000000 ok c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0\n"
        "W 01000000 ok\nR 01000000 ok c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0\n"
        "W 01000000 ok\nR 01000000 ok c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0\n"
        "W 01000000 ok\nR 01000000 ok c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0\n"
        "A w 0043\nA r 0043\n";
    struct gbp_replay r; struct gbp_transport t; struct gbp_init_config cfg;
    struct gbp_init_result res; struct ringlog rl;
    gbp_replay_init(&r, script);
    gbp_replay_transport(&r, &t);
    gbp_init_config_default(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_init_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.status == GBP_INIT_ABORT_NOT_PRESENT && res.det.verdict == GBP_VERDICT_ABSENT);
    CHECK(res.control_written == 0 && r.exhausted == 0 && r.mismatches == 0);
    CHECK(res.arinfo_restored == 1);
}

/* Replay: physical with-GBP handshake bytes (MODE B, with the byte-0
 * anomaly) reach the write; PI values and post-write blocks are synthetic
 * (no hardware data exists yet) and are marked as such. */
static void test_replay_gbp_reaches_write(void)
{
    static const char script[] =
        "# detection part = physical MODE B TESTR blocks of 2026-09-14; the rest is SYNTHETIC\n"
        "A r 0043\nA w 005b\nA r 005b\n"
        "W 01000000 ok\nR 01000000 ok 3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c\n"
        "W 01000000 ok\nR 01000000 ok c7c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3\n"
        "W 01000000 ok\nR 01000000 ok 0000000000000000000000000000000000000000000000000000000000000000\n"
        "W 01000000 ok\nR 01000000 ok ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff\n"
        "P r 00000000 000000f0\n"
        /* S0 */
        "P r 00000000 000000f0\n"
        "R 01400000 ok 9490909090909090909090909090909090909090909090909090909090909090\n"
        "R 01d00000 ok ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae\n"
        "R 01000000 ok 0000000000000000000000000000000000000000000000000000000000000000\n"
        /* experimental write, then S1..S3 (synthetic: unchanged) */
        "W 01400000 ok\n"
        "P r 00000000 000000f0\nR 01400000 ok 8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c\nR 01d00000 ok ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae\n"
        "P r 00000000 000000f0\nR 01400000 ok 8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c\nR 01d00000 ok ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae\n"
        "P r 00000000 000000f0\nR 01400000 ok 8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c\nR 01d00000 ok ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae\n"
        /* restore, S4 */
        "W 01400000 ok\n"
        "P r 00000000 000000f0\nR 01400000 ok 9090909090909090909090909090909090909090909090909090909090909090\nR 01d00000 ok ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae\n"
        "A w 0043\nA r 0043\n"
        /* S5 */
        "P r 00000000 000000f0\nR 01400000 ok 0000000000000000000000000000000000000000000000000000000000000000\nR 01d00000 ok 9090909090909090909090909090909090909090909090909090909090909090\n";
    struct gbp_replay r; struct gbp_transport t; struct gbp_init_config cfg;
    struct gbp_init_result res; struct ringlog rl;
    gbp_replay_init(&r, script);
    gbp_replay_transport(&r, &t);
    gbp_init_config_default(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_init_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.status == GBP_INIT_OK && r.exhausted == 0 && r.mismatches == 0);
    CHECK(res.control_orig == 0x90 && res.control_exp == 0x8c && res.control_restored == 1);
    CHECK(res.snap[0].control[0] == 0x94 && res.snap[0].irq_disc == 0x8aae);
    CHECK(res.snap[5].control_vote == 0x00 && res.snap[5].irq_disc == 0x9090);   /* S5 under exp code 0, as MODE A showed */
    CHECK(res.transition_s1_s2 == 0 && res.arinfo_restored == 1);
}

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

static void run_fixture(const char *path, struct gbp_init_result *res, struct ringlog *rl, struct gbp_replay *r)
{
    char *text = read_file(path);
    struct gbp_transport t; struct gbp_init_config cfg;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; memset(res, 0, sizeof *res); return; }
    gbp_replay_init(r, text);
    gbp_replay_transport(r, &t);
    gbp_init_config_default(&cfg);
    ringlog_init(rl, storage, LINE_LEN, LINES);
    CHECK(gbp_init_probe_run(&t, rl, &cfg, res) == 0);
    CHECK(r->exhausted == 0 && r->mismatches == 0);
    free(text);
}

/* Physical run GBP-INIT-001 with the GBP attached (2026-09-15, commit a3d9668). */
static void test_hw_init_gbp(const char *path)
{
    struct gbp_init_result res; struct ringlog rl; struct gbp_replay r;
    unsigned k, n;
    run_fixture(path, &res, &rl, &r);
    CHECK(res.status == GBP_INIT_OK && res.det.verdict == GBP_VERDICT_PRESENT && res.det.vote_ok == 4 && res.det.b1_ok == 4 && res.det.all32_ok == 3);
    CHECK(res.arinfo_orig == 0x0043 && res.arinfo_exp == 0x005b && res.arinfo_final == 0x0043 && res.arinfo_restored == 1);
    CHECK(res.intmr_orig == 0x000001fa && res.intmr_changed == 0 && res.intmr_restored == -1);
    CHECK(res.control_orig == 0x90 && res.control_exp == 0x8c && res.control_written == 1 && res.control_restored == 1);
    /* semantic values per snapshot: 90, 8c, 8c, 8c, 90, 00 */
    CHECK(res.snap[0].control_vote == 0x90 && res.snap[1].control_vote == 0x8c && res.snap[2].control_vote == 0x8c &&
          res.snap[3].control_vote == 0x8c && res.snap[4].control_vote == 0x90 && res.snap[5].control_vote == 0x00);
    /* bytes 1..31 uniform in every CONTROL block; byte 0 as logged */
    {
        static const uint8_t b0[6] = { 0x98, 0xec, 0xac, 0xac, 0x98, 0x00 };
        for (n = 0; n < 6; n++) {
            CHECK(res.snap[n].control[0] == b0[n]);
            for (k = 1; k < GBP_BLOCK_SIZE; k++) CHECK(res.snap[n].control[k] == res.snap[n].control_vote);
        }
    }
    /* IRQ: 8aae in S0..S4 (bytes 1..31 pattern 8a 8a ae ae), 9090 in S5; byte 0 as logged */
    {
        static const uint8_t b0[6] = { 0xaa, 0xea, 0xaa, 0xaa, 0xea, 0x98 };
        for (n = 0; n < 5; n++) CHECK(res.snap[n].irq_disc == 0x8aae);
        CHECK(res.snap[5].irq_disc == 0x9090);
        for (n = 0; n < 6; n++) CHECK(res.snap[n].irq[0] == b0[n]);
    }
    /* INTSR 0x00010000 (bit 16 RSWST), bit 13 never set; INTMR untouched */
    for (n = 0; n < 6; n++) CHECK(res.snap[n].intsr == 0x00010000 && res.snap[n].intmr == 0x000001fa);
    CHECK(res.transition_s1_s2 == 1);          /* byte 0 only */
    CHECK(res.errors == 0 && res.transport_ok == 1 && rl.dropped == 0 && rl.truncated == 0);
}

/* Physical baseline without the GBP (2026-09-15): C1×32, abort before any CONTROL write. */
static void test_hw_init_nogbp(const char *path)
{
    struct gbp_init_result res; struct ringlog rl; struct gbp_replay r;
    unsigned k;
    run_fixture(path, &res, &rl, &r);
    CHECK(res.status == GBP_INIT_ABORT_NOT_PRESENT && res.det.verdict == GBP_VERDICT_ABSENT);
    CHECK(res.det.run == 4 && res.det.transport_ok == 4 && res.det.vote_ok == 0 && res.det.b1_ok == 0);
    for (k = 0; k < GBP_BLOCK_SIZE; k++) CHECK(res.det.last_resp[k] == 0xc1);
    CHECK(res.control_written == 0 && res.arinfo_restored == 1 && res.arinfo_final == 0x0043);
    CHECK(count_lines_with(&rl, "CTLW") == 0 && count_lines_with(&rl, "SNAP") == 0);
    CHECK(r.step == 13);                        /* 3 AR_INFO ops + 8 handshake transfers + restore write + readback */
}

int main(int argc, char **argv)
{
    test_present_normal();
    test_absent_and_inconsistent_never_write();
    test_control_shapes();
    test_intmr_paths();
    test_timeouts_and_restore_failures();
    test_replay_nogbp_never_writes_control();
    test_replay_gbp_reaches_write();
    if (argc > 1) test_hw_init_gbp(argv[1]);
    if (argc > 2) test_hw_init_nogbp(argv[2]);
    printf("test_gbp_init: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
