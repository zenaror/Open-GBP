/*
 * Probe logic against the mock backend: present / absent / expansion
 * required / timeout / DMA error / stuck busy / mirrored layout /
 * unexpected block / ring buffer full / AR_INFO restore / write policy.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_probe.h"
#include "gbp_mock.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

#define LINES 128
#define LINE_LEN 256
static char storage[LINES * LINE_LEN];

static int count_lines_with(const struct ringlog *rl, const char *needle)
{
    size_t i; int n = 0;
    for (i = 0; i < rl->count; i++) if (strstr(ringlog_line(rl, i), needle)) n++;
    return n;
}

static void run(struct gbp_mock *m, struct ringlog *rl, struct gbp_probe_result *res, int mode_b)
{
    struct gbp_transport t;
    struct gbp_probe_config cfg;
    gbp_mock_transport(m, &t);
    gbp_probe_config_default(&cfg);
    cfg.run_mode_b = mode_b;
    ringlog_init(rl, storage, LINE_LEN, LINES);
    CHECK(gbp_probe_run(&t, rl, &cfg, res) == 0);
}

static void test_present(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_probe_result res;
    gbp_mock_init(&m);
    run(&m, &rl, &res, 1);
    CHECK(res.modes_run == 2);
    CHECK(res.present[0] == 1 && res.present[1] == 1);
    CHECK(res.mode[0].tests_run == 4 && res.mode[0].tests_match_all == 4 && res.mode[0].tests_match_1f == 4);
    CHECK(res.errors == 0);
    CHECK(res.arinfo_orig == 0x0043);
    CHECK(res.mode[1].arinfo_before == 0x005B);         /* bits 3-5 = 3 */
    CHECK(res.arinfo_changed == 1 && res.arinfo_restored == 1 && res.arinfo_final == 0x0043);
    CHECK(m.arinfo == 0x0043);                           /* restored on the device */
    /* writes only to TEST (index 0), never to CONTROL/IRQ */
    CHECK(gbp_mock_writes_outside(&m, 0x01000000, 0) == 0);
    /* raw dumps happen twice per mode for 3 indices */
    CHECK(res.mode[0].reads_ok == 6 && res.mode[1].reads_ok == 6);
    CHECK(count_lines_with(&rl, "RAW mode=A") == 6);
    CHECK(count_lines_with(&rl, "TESTR mode=B") == 4);
    CHECK(count_lines_with(&rl, "ARINFO restore") == 1);
    CHECK(rl.dropped == 0);
    /* the CONTROL raw block keeps the mock's byte-doubled layout verbatim */
    CHECK(res.mode[0].raw[1][31] == 0x02 && res.mode[0].raw[1][30] == 0x02 && res.mode[0].raw[1][29] == 0x00);
}

static void test_absent(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_probe_result res;
    gbp_mock_init(&m);
    m.present = 0;
    m.absent_fill = 0x00;
    run(&m, &rl, &res, 1);
    CHECK(res.present[0] == 0 && res.present[1] == 0);
    CHECK(res.errors == 0 && res.transport_ok == 1);      /* transfers complete, data just wrong */
    CHECK(res.mode[0].tests_match_all == 1);              /* zero fill == ~0xFF for the FF pattern only */
    CHECK(res.mode[0].verdict == GBP_VERDICT_INCONSISTENT);
    CHECK(res.arinfo_restored == 1);
    /* a 0xC0 fill (what the real GameCube returned without the GBP) → ABSENT */
    gbp_mock_init(&m);
    m.present = 0;
    m.absent_fill = 0xC0;
    run(&m, &rl, &res, 1);
    CHECK(res.mode[0].verdict == GBP_VERDICT_ABSENT && res.mode[1].verdict == GBP_VERDICT_ABSENT);
    CHECK(res.transport_ok == 1 && res.present[0] == 0);
}

static void test_expansion_required(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_probe_result res;
    gbp_mock_init(&m);
    m.require_expansion = 1;
    m.absent_fill = 0x55;
    run(&m, &rl, &res, 1);
    CHECK(res.present[0] == 0 && res.mode[0].verdict == GBP_VERDICT_ABSENT);
    CHECK(res.present[1] == 1 && res.mode[1].verdict == GBP_VERDICT_PRESENT);
    CHECK(res.arinfo_restored == 1);
    /* mode A only: no B, AR_INFO never written */
    gbp_mock_init(&m);
    m.require_expansion = 1;
    run(&m, &rl, &res, 0);
    CHECK(res.modes_run == 1 && res.arinfo_changed == 0 && res.arinfo_restored == 1);
    CHECK(count_lines_with(&rl, "ARINFO write") == 0);
}

static void test_timeout_and_stuck(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_probe_result res;
    gbp_mock_init(&m);
    m.fail_at_op = 1;                     /* first raw read times out */
    m.fail_rc = GBP_ERR_TIMEOUT;
    run(&m, &rl, &res, 1);
    CHECK(res.errors == 1);
    CHECK(res.mode[0].reads_failed == 1 && res.mode[0].reads_ok == 5);
    CHECK(res.present[0] == 1);           /* handshake itself still fine */
    CHECK(count_lines_with(&rl, "rc=timeout") == 1);
    CHECK(res.arinfo_restored == 1);

    gbp_mock_init(&m);
    m.fail_at_op = 4;                     /* first handshake write times out ... */
    m.fail_rc = GBP_ERR_TIMEOUT;
    m.stuck_after_timeout = 1;            /* ... and the engine stays busy */
    run(&m, &rl, &res, 1);
    CHECK(res.mode[0].tests_failed == 4);
    CHECK(res.present[0] == 0 && res.present[1] == 0);
    CHECK(res.mode[0].verdict == GBP_VERDICT_INCONSISTENT && res.transport_ok == 0);
    CHECK(count_lines_with(&rl, "rc=busy") > 0);
    CHECK(res.arinfo_changed == 1 && res.arinfo_restored == 1);   /* restore still happens */
    CHECK(res.errors > 4);
}

static void test_dma_error_and_unexpected_block(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_probe_result res;
    struct gbp_transport t; struct gbp_probe_config cfg;
    gbp_mock_init(&m);
    m.fail_at_op = 2;
    m.fail_rc = GBP_ERR_BACKEND;
    run(&m, &rl, &res, 0);
    CHECK(res.errors == 1 && count_lines_with(&rl, "rc=backend") == 1);

    /* an index the mock does not model returns the 0xEE marker: recorded raw, not interpreted */
    gbp_mock_init(&m);
    gbp_mock_transport(&m, &t);
    gbp_probe_config_default(&cfg);
    cfg.indices[0] = 0x2; cfg.nindices = 1; cfg.run_mode_b = 0;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.mode[0].raw[0][0] == 0xEE && res.mode[0].raw[0][31] == 0xEE);
    CHECK(count_lines_with(&rl, "idx=2") == 2);
}

static void test_plain_layout(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_probe_result res;
    gbp_mock_init(&m);
    m.byte_doubled = 0;
    m.irq_value = 0x8115;
    run(&m, &rl, &res, 0);
    CHECK(res.mode[0].raw[2][30] == 0x81 && res.mode[0].raw[2][31] == 0x15 && res.mode[0].raw[2][29] == 0x00);
    gbp_mock_init(&m);
    m.irq_value = 0x8115;
    run(&m, &rl, &res, 0);
    CHECK(res.mode[0].raw[2][28] == 0x81 && res.mode[0].raw[2][29] == 0x81 &&
          res.mode[0].raw[2][30] == 0x15 && res.mode[0].raw[2][31] == 0x15);
}

static void test_ring_full(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_probe_result res;
    struct gbp_transport t; struct gbp_probe_config cfg;
    gbp_mock_init(&m);
    gbp_mock_transport(&m, &t);
    gbp_probe_config_default(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, 5);     /* far too small */
    CHECK(gbp_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(rl.count == 5 && rl.dropped > 0);
    CHECK(res.arinfo_restored == 1);              /* logging failure never affects the sequence */
    CHECK(res.present[0] == 1 && res.present[1] == 1);
}

static void test_summary(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_probe_result res;
    char s[256];
    gbp_mock_init(&m);
    run(&m, &rl, &res, 1);
    CHECK(gbp_probe_summary(&res, s, sizeof s) > 0);
    CHECK(strstr(s, "a_present=1 b_present=1 a_verdict=present b_verdict=present") != 0);
    CHECK(strstr(s, "transport_ok=1") != 0);
    CHECK(strstr(s, "changed=1 restored=1") != 0);
}

/* Sentinel behavior: what the logic reports when the backend completes a
 * read but the buffer content is not what a real device would return.
 * Documents a known limitation of probe-0001: the probe zero-fills its
 * buffers, so a silent DMA is indistinguishable from a device returning
 * 0x00 (both are logged as rc=ok data=00..00). */
static void test_sentinel_and_raw_preservation(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_probe_result res;
    static const uint8_t partial[GBP_BLOCK_SIZE] = { 0x7c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c,
        0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c,
        0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c, 0x3c };
    static const uint8_t ninety[GBP_BLOCK_SIZE] = { 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90,
        0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90,
        0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
    unsigned k;

    /* silent DMA → logic sees zeros (its own fill), rc ok, "present" false */
    gbp_mock_init(&m);
    m.silent_reads = 1;
    run(&m, &rl, &res, 0);
    CHECK(res.errors == 0);
    for (k = 0; k < GBP_BLOCK_SIZE; k++) CHECK(res.mode[0].raw[0][k] == 0x00);
    CHECK(res.present[0] == 0);
    CHECK(res.mode[0].tests_match_all == 1);        /* only the 0xFF pattern "matches" zeros */
    CHECK(count_lines_with(&rl, "data=0000000000000000000000000000000000000000000000000000000000000000") > 0);

    /* device returns 0x90 everywhere: kept verbatim, never mistaken for a match */
    gbp_mock_init(&m);
    m.canned = ninety;
    run(&m, &rl, &res, 0);
    for (k = 0; k < GBP_BLOCK_SIZE; k++) CHECK(res.mode[0].raw[2][k] == 0x90);
    CHECK(res.mode[0].tests_match_all == 0 && res.mode[0].tests_match_1f == 0);

    /* partial pattern (byte 0 anomalous, as seen on hardware): match_all=0, match_1f=1, bytes intact */
    gbp_mock_init(&m);
    m.canned = partial;
    run(&m, &rl, &res, 0);
    CHECK(res.mode[0].tests_match_all == 0);
    CHECK(res.mode[0].tests_match_1f == 1);          /* only pattern C3 expects 3C at 0x1F */
    /* every read of the mode (6 raw dumps + 4 handshake reads) logged the block verbatim */
    CHECK(count_lines_with(&rl, "data=7c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c") == 10);
    CHECK(res.present[0] == 0);
}

/* The POC stores records in 256-byte lines; the longest record (TESTR with
 * a full 64-hex data field) must never be truncated. */
static void test_record_length_fits(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_probe_result res;
    size_t i, longest = 0;
    gbp_mock_init(&m);
    run(&m, &rl, &res, 1);
    CHECK(rl.truncated == 0);
    for (i = 0; i < rl.count; i++) { size_t n = strlen(ringlog_line(&rl, i)); if (n > longest) longest = n; }
    CHECK(longest < 256);
    CHECK(longest > 200);   /* proves the old 200-byte lines would have cut TESTR records */
}

int main(void)
{
    test_record_length_fits();
    test_sentinel_and_raw_preservation();
    test_present();
    test_absent();
    test_expansion_required();
    test_timeout_and_stuck();
    test_dma_error_and_unexpected_block();
    test_plain_layout();
    test_ring_full();
    test_summary();
    printf("test_gbp_probe: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
