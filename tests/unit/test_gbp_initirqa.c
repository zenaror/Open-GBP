/*
 * GBP-INIT-003A logic against the mock's SYNTHETIC source/mask model of
 * the GBP IRQ register and against the physical fixtures of GBP-INIT-001
 * and GBP-INIT-002 (detection gate, PI preconditions, BASE snapshot and
 * the CONTROL/IRQ shape checks: everything before the first experimental
 * write — no physical GBP-INIT-003A data exists, and none is invented).
 *
 * Every scenario of the implementation brief is covered, plus the
 * event-order assertions (AR_INFO exp < handshake < CONTROL exp < P0 reads
 * < A1 < A1 samples < A2PRE < A2 < A2 samples/EVENT < CONTROL restore < IRQ
 * stop < optional PI cleanup < AR_INFO restore < FINAL) and the "never"
 * properties (zero handler installs, zero unmasks, zero INTMR writes, zero
 * KEYPAD/VIDEO/AUDIO/SIO writes, IRQ writes only to index D with the GBI
 * u16-replicated layout, the BASE raw block never written back).
 *
 * Modes:  test_gbp_initirqa [init-gbp init-nogbp initirq-gbp]
 *         test_gbp_initirqa --dump-log <file>   (writes the synthetic event scenario's
 *                                                log in the SD-log format, for the
 *                                                fixture round trip of tests/host)
 *         test_gbp_initirqa --replay <fixture>  (runs the probe on a replay script
 *                                                and prints its DONE summary)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_initirqa_probe.h"
#include "gbp_rawlog.h"
#include "gbp_replay.h"
#include "gbp_mock.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

#define LINES 192
#define LINE_LEN 256
static char storage[LINES * LINE_LEN];
#define BASE 0x01000000u

/* mock-tick deadlines (the mock's ticks() advances by 10 per call) */
static const uint32_t A1_DL[GBP_INITIRQA_MAX_A1_OBS] = { 50u, 100u };
static const uint32_t A2_DL[GBP_INITIRQA_MAX_A2_OBS] = { 50u, 100u, 200u, 400u, 800u, 1600u };

/* physical blocks, GBP attached, expansion code 3 (captures/fixtures/hw-gamecube-gbp-2026-09-15-init-0001) */
static const uint8_t HW_CONTROL_98[32] = { 0x98, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90,
                                           0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
static const uint8_t HW_IRQ_8AAE[32] = { 0xaa, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae,
                                         0x8a, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae, 0x8a, 0x8a, 0xae, 0xae };

static int count_lines_with(const struct ringlog *rl, const char *needle)
{
    size_t i; int n = 0;
    for (i = 0; i < rl->count; i++) if (strstr(ringlog_line(rl, i), needle)) n++;
    return n;
}

static int line_index_with(const struct ringlog *rl, const char *needle)
{
    size_t i;
    for (i = 0; i < rl->count; i++) if (strstr(ringlog_line(rl, i), needle)) return (int)i;
    return -1;
}

static size_t max_line_len(const struct ringlog *rl)
{
    size_t i, m = 0, l;
    for (i = 0; i < rl->count; i++) { l = strlen(ringlog_line(rl, i)); if (l > m) m = l; }
    return m;
}

static void test_config(struct gbp_initirqa_config *cfg)
{
    gbp_initirqa_config_default(cfg);
    memcpy(cfg->a1_obs_ticks, A1_DL, sizeof A1_DL);
    memcpy(cfg->a2_obs_ticks, A2_DL, sizeof A2_DL);
}

/* a mock in the SOURCE_MASK model with the physical idle value 0x8AAE */
static void mock_003a(struct gbp_mock *m)
{
    gbp_mock_init(m);
    m->irq_model = MOCK_IRQ_MODEL_SOURCE_MASK;
}

static void run_cfg(struct gbp_mock *m, struct ringlog *rl, struct gbp_initirqa_result *res, struct gbp_initirqa_config *cfg)
{
    struct gbp_transport t;
    gbp_mock_transport(m, &t);
    ringlog_init(rl, storage, LINE_LEN, LINES);
    gbp_initirqa_probe_run(&t, rl, cfg, res);
}

static void run(struct gbp_mock *m, struct ringlog *rl, struct gbp_initirqa_result *res)
{
    struct gbp_initirqa_config cfg;
    test_config(&cfg);
    run_cfg(m, rl, res, &cfg);
}

/* ---- the "never" properties, applied to every run ---------------------- */
static void check_never(const struct gbp_mock *m)
{
    unsigned idx;
    CHECK(gbp_mock_first_op(m, MOCK_IRQ_INSTALL, BASE, 16) < 0);            /* zero handler installs */
    CHECK(gbp_mock_first_op(m, MOCK_IRQ_UNMASK, BASE, 16) < 0);             /* zero unmasks */
    CHECK(gbp_mock_first_op(m, MOCK_IRQ_MASK, BASE, 16) < 0);               /* zero masks (nothing to undo) */
    CHECK(gbp_mock_first_op(m, MOCK_IRQ_RESTORE, BASE, 16) < 0);
    CHECK(gbp_mock_first_op(m, MOCK_ISR_ENTRY, BASE, 16) < 0 && m->deliveries == 0 && m->handler_installed == 0);
    CHECK(m->intmr_writes == 0);                                             /* INTMR never written */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xC) == 0);             /* KEYPAD never written */
    for (idx = 0; idx < 16; idx++) {
        if (idx == 0 || idx == 4 || idx == 0xD) continue;
        CHECK(gbp_mock_count_block_ops(m, MOCK_RD, BASE, idx) == 0);         /* VIDEO/AUDIO/SIO/... never read */
        CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, idx) == 0);         /* ... never written */
    }
    CHECK(m->intsr_writes <= 1);                                             /* at most one W1C, teardown only */
}

/* ---- the mandatory order, applied to every run that wrote CONTROL ------- */
static void check_order(const struct gbp_mock *m, const struct gbp_initirqa_result *res)
{
    int ar_exp = gbp_mock_first_op(m, MOCK_AR_W, BASE, 16);
    int hs_w = gbp_mock_first_op(m, MOCK_WR, BASE, 0);
    int ctl_exp = gbp_mock_nth_op(m, MOCK_WR, BASE, 4, 1);
    int ctl_rest = gbp_mock_nth_op(m, MOCK_WR, BASE, 4, 2);
    int a1 = gbp_mock_nth_op(m, MOCK_WR, BASE, 0xD, 1);
    int a2 = res->w_a2.attempted ? gbp_mock_nth_op(m, MOCK_WR, BASE, 0xD, 2) : -1;
    int stop = gbp_mock_last_op(m, MOCK_WR, BASE, 0xD);
    int w1c = gbp_mock_first_op(m, MOCK_INTSR_W, BASE, 16);
    int ar_rest = gbp_mock_last_op(m, MOCK_AR_W, BASE, 16);
    int last_rd = gbp_mock_last_op(m, MOCK_RD, BASE, 16);
    CHECK(ar_exp >= 0 && hs_w > ar_exp);                                     /* ARINFO_EXP < handshake */
    CHECK(ctl_exp > hs_w);                                                   /* PRESENCE/PRECOND < CONTROL_EXP */
    if (a1 >= 0) {
        CHECK(a1 > ctl_exp);                                                 /* CONTROL_EXP < P0 < A1 */
        CHECK(gbp_mock_nth_op(m, MOCK_RD, BASE, 0xD, 3) > ctl_exp && gbp_mock_nth_op(m, MOCK_RD, BASE, 0xD, 3) < a1); /* P0 + A1PRE reads between */
        if (a2 >= 0) CHECK(a2 > a1 && a2 < ctl_rest);                        /* A1 < A2 < CONTROL_RESTORE */
        CHECK(ctl_rest > a1 && stop > ctl_rest);                             /* CONTROL_RESTORE < IRQ_STOP */
        if (w1c >= 0) CHECK(w1c > stop);                                     /* PI cleanup after the stop */
    }
    if (ctl_rest >= 0) CHECK(ar_rest > ctl_rest);                            /* AR_INFO restore after the restores */
    if (w1c >= 0) CHECK(ar_rest > w1c);
    CHECK(last_rd > ar_rest);                                                /* FINAL after the AR_INFO restore */
    CHECK(m->violations == 0);
}

/* IRQ writes: index D only, exactly the three computed values in GBI's layout, never the BASE raw block */
static void check_irq_writes(const struct gbp_mock *m, const struct gbp_initirqa_result *res, unsigned expected)
{
    unsigned n = gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xD), i;
    uint8_t layout[32];
    CHECK(n == expected && res->irq_writes_attempted == expected);
    for (i = 1; i <= n; i++) {
        int op = gbp_mock_nth_op(m, MOCK_WR, BASE, 0xD, i);
        const struct gbp_regwrite_result *w = (i == 1) ? &res->w_a1 : (i == 2 && res->w_a2.attempted) ? &res->w_a2 : &res->w_stop;
        CHECK(op >= 0 && m->ops[(unsigned)op].addr == BASE + (0xDu << 20));
        gbp_regwrite_u16_layout(w->value, layout);
        CHECK(memcmp(m->ops[(unsigned)op].data, layout, 32) == 0);
        CHECK(memcmp(m->ops[(unsigned)op].data, w->raw, 32) == 0);
        CHECK(memcmp(m->ops[(unsigned)op].data, res->snap[GBP_INITIRQA_SNAP_BASE].irq, 32) != 0);   /* raw S0 write-back prohibited */
    }
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 4) == (res->control_written ? 2u : 0u));
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0) == 4);                /* handshake only */
}

/* 1: nominal — PRESENT, PI masked, A1 clears the pending source, A2 zeroes, no cause, Disc stop word */
static void test_nominal_no_cause(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED && strcmp(res.reason, "-") == 0);
    CHECK(res.restore_ok == 1 && res.transport_ok == 1 && res.errors == 0 && res.power_cycle_required == 1);
    CHECK(res.det.verdict == GBP_VERDICT_PRESENT && res.det.vote_ok == 4 && res.det.b1_ok == 4);
    CHECK(res.arinfo_orig == 0x0043 && res.arinfo_exp == 0x005b && res.arinfo_final == 0x0043 && res.arinfo_restore_ok == 1);
    CHECK(res.control_orig == 0x90 && res.control_exp == 0x8c && res.control_written == 1 && res.control_restore_ok == 1);
    CHECK(res.w_ctl_exp.raw[0] == 0x8c && res.w_ctl_exp.raw[31] == 0x8c && res.w_ctl_restore.raw[0] == 0x90 && res.w_ctl_restore.raw[31] == 0x90);
    CHECK(res.irq_shape_base_ok == 1 && res.irq_shape_a1pre_ok == 1);
    CHECK(res.snap[GBP_INITIRQA_SNAP_BASE].irq_gbi == 0x8aae && res.snap[GBP_INITIRQA_SNAP_BASE].irq_disc == 0x8aae);
    CHECK(res.snap[GBP_INITIRQA_SNAP_BASE].has_test && res.snap[GBP_INITIRQA_SNAP_P0].has_test && !res.snap[GBP_INITIRQA_SNAP_A1_0].has_test);
    CHECK(res.snap[GBP_INITIRQA_SNAP_P0].control_vote == 0x8c && res.snap[GBP_INITIRQA_SNAP_P0].irq_gbi == 0x8aae);
    CHECK(res.irq_a1pre.taken && res.irq_a1pre.gbi == 0x8aae && res.ack_value == 0x8aae);
    CHECK(res.w_a1.attempted && res.w_a1.completed && res.w_a1.value == 0x8aae && res.w_a1.before == 0x8aae);
    CHECK(res.snap[GBP_INITIRQA_SNAP_A1_0].taken && res.snap[GBP_INITIRQA_SNAP_A1_0].irq_gbi == 0x8aaa);   /* synthetic: source 2 W1C-cleared */
    CHECK(res.a1_obs_taken == 2 && res.snap[GBP_INITIRQA_SNAP_A1_OBS].taken && res.snap[GBP_INITIRQA_SNAP_A1_OBS + 1].taken);
    CHECK(res.snap[GBP_INITIRQA_SNAP_A1_OBS].since_a1 >= 50u && res.snap[GBP_INITIRQA_SNAP_A1_OBS + 1].since_a1 >= 100u);
    CHECK(strcmp(res.snap[GBP_INITIRQA_SNAP_A1_OBS].id, "A1-50US") == 0 && strcmp(res.snap[GBP_INITIRQA_SNAP_A1_OBS + 1].id, "A1-500US") == 0);
    CHECK(res.irq_a2pre.taken && res.irq_a2pre.gbi == 0x8aaa && res.a2pre_pi_ok && (res.a2pre_intmr & GBP_PI_HSP_BIT) == 0);
    CHECK(res.w_a2.attempted && res.w_a2.completed && res.w_a2.value == 0 && res.w_a2.before == 0x8aaa);
    CHECK(res.snap[GBP_INITIRQA_SNAP_A2_0].taken && res.snap[GBP_INITIRQA_SNAP_A2_0].irq_gbi == 0x0000);
    CHECK(res.a2_obs_taken == 6 && res.n_a2_order == 6 && res.event_taken == 0 && res.window_ended_early == 0);
    CHECK(strcmp(res.snap[GBP_INITIRQA_SNAP_A2_OBS + 5].id, "A2-2000MS") == 0 && res.snap[GBP_INITIRQA_SNAP_A2_OBS + 5].since_a2 >= 1600u);
    CHECK(res.a1_polls > 0 && res.a2_polls > 0 && res.poll_errors == 0);
    CHECK(res.intsr13_seen == 0 && res.t_first_intsr13 == 0 && strcmp(res.first_intsr13_phase, "-") == 0);
    CHECK(res.irq_writes_attempted == 3 && res.irq_writes_completed == 3);
    CHECK(res.irq_stop_pre.gbi == 0x0000 && res.stop_value == 0x8aaa && res.w_stop.value == 0x8aaa);
    CHECK(res.irq_stop_write_ok == 1 && res.irq_stop_readback_ok == 1 && res.irq_stop_post.gbi == 0x8aaa);
    CHECK(res.stop_masks_readback == 1 && res.stop_bit15_readback == 1);
    CHECK(res.pi_cleanup_performed == 0 && res.pi_cleanup_ok == -1 && m.intsr_writes == 0);
    CHECK(res.snap[GBP_INITIRQA_SNAP_FINAL].taken && res.snap[GBP_INITIRQA_SNAP_FINAL].control_vote == 0x90);
    CHECK((m.intmr & GBP_PI_HSP_BIT) == 0 && (m.intsr & GBP_PI_HSP_BIT) == 0 && m.arinfo == 0x0043 && m.irq_reg == 0x8aaa);
    CHECK(res.window_entered && res.log_count_window_start == res.log_count_window_end);   /* nothing formatted inside */
    check_never(&m);
    check_order(&m, &res);
    check_irq_writes(&m, &res, 3);
    /* log records */
    CHECK(count_lines_with(&rl, "INITIRQA start ") == 1 && count_lines_with(&rl, "INITIRQA window ") == 1);
    CHECK(count_lines_with(&rl, "IRQSHAPE tag=BASE") == 1 && count_lines_with(&rl, "IRQSHAPE tag=A1PRE") == 1);
    CHECK(count_lines_with(&rl, "CTLW tag=EXP") == 1 && count_lines_with(&rl, "CTLW tag=RESTORE") == 1);
    CHECK(count_lines_with(&rl, "IRQW tag=A1 ") == 1 && count_lines_with(&rl, "IRQW tag=A2 ") == 1 && count_lines_with(&rl, "IRQW tag=STOP ") == 1);
    CHECK(count_lines_with(&rl, "layout=gbi-u16-replicated") == 3);
    CHECK(count_lines_with(&rl, "SNAP tag=") == 2 + 1 + 2 + 1 + 6 + 1);
    CHECK(count_lines_with(&rl, "RAW A1PRE idx=d") == 1 && count_lines_with(&rl, "RAW A2PRE idx=d") == 1);
    CHECK(count_lines_with(&rl, "WINDOW tag=A1 deadlines=2/2") == 1 && count_lines_with(&rl, "WINDOW tag=A2 deadlines=6/6") == 1);
    CHECK(count_lines_with(&rl, "REGION log_count_start=") == 1 && count_lines_with(&rl, "formatted_inside=0") == 1);
    CHECK(count_lines_with(&rl, "TEARDOWN start") == 1 && count_lines_with(&rl, "IRQSTOP pre ") == 1 && count_lines_with(&rl, "IRQSTOP post ") == 1);
    CHECK(count_lines_with(&rl, "CLEANUP performed=0") == 1 && count_lines_with(&rl, "ARINFO restore") == 1);
    CHECK(count_lines_with(&rl, "INITIRQA end status=ok_no_pi_cause_observed") == 1 && count_lines_with(&rl, "RESTORE control_restore_ok=1") == 1);
    CHECK(count_lines_with(&rl, "IRQ install") == 0 && count_lines_with(&rl, "UNMASK") == 0 && count_lines_with(&rl, "HANDLER") == 0);
    /* record order mirrors the sequence */
    CHECK(line_index_with(&rl, "ARINFO exp") < line_index_with(&rl, "TESTW tag=DET"));
    CHECK(line_index_with(&rl, "DET verdict") < line_index_with(&rl, "PRECOND"));
    CHECK(line_index_with(&rl, "PRECOND") < line_index_with(&rl, "SNAP tag=BASE"));
    CHECK(line_index_with(&rl, "IRQSHAPE tag=BASE") < line_index_with(&rl, "CTLW tag=EXP"));
    CHECK(line_index_with(&rl, "CTLW tag=EXP") < line_index_with(&rl, "SNAP tag=P0"));
    CHECK(line_index_with(&rl, "P0CHK") < line_index_with(&rl, "RAW A1PRE"));
    CHECK(line_index_with(&rl, "RAW A1PRE") < line_index_with(&rl, "IRQW tag=A1"));
    CHECK(line_index_with(&rl, "IRQW tag=A1") < line_index_with(&rl, "SNAP tag=A1-0"));
    CHECK(line_index_with(&rl, "SNAP tag=A1-0") < line_index_with(&rl, "SNAP tag=A1-50US"));
    CHECK(line_index_with(&rl, "SNAP tag=A1-500US") < line_index_with(&rl, "RAW A2PRE"));
    CHECK(line_index_with(&rl, "A2CHK") < line_index_with(&rl, "IRQW tag=A2"));
    CHECK(line_index_with(&rl, "IRQW tag=A2") < line_index_with(&rl, "SNAP tag=A2-0"));
    CHECK(line_index_with(&rl, "SNAP tag=A2-0") < line_index_with(&rl, "SNAP tag=A2-50US"));
    CHECK(line_index_with(&rl, "SNAP tag=A2-500MS") < line_index_with(&rl, "SNAP tag=A2-2000MS"));
    CHECK(line_index_with(&rl, "SNAP tag=A2-2000MS") < line_index_with(&rl, "WINDOW tag=A2"));
    CHECK(line_index_with(&rl, "WINDOW tag=A2") < line_index_with(&rl, "TEARDOWN start"));
    CHECK(line_index_with(&rl, "TEARDOWN start") < line_index_with(&rl, "CTLW tag=RESTORE"));
    CHECK(line_index_with(&rl, "CTLW tag=RESTORE") < line_index_with(&rl, "RAW IRQSTOPPRE"));
    CHECK(line_index_with(&rl, "RAW IRQSTOPPRE") < line_index_with(&rl, "IRQW tag=STOP"));
    CHECK(line_index_with(&rl, "IRQW tag=STOP") < line_index_with(&rl, "RAW IRQSTOPPOST"));
    CHECK(line_index_with(&rl, "RAW IRQSTOPPOST") < line_index_with(&rl, "PI tag=CLEANUPCHK"));
    CHECK(line_index_with(&rl, "PI tag=CLEANUPCHK") < line_index_with(&rl, "ARINFO restore"));
    CHECK(line_index_with(&rl, "ARINFO restore") < line_index_with(&rl, "SNAP tag=FINAL"));
    CHECK(line_index_with(&rl, "SNAP tag=FINAL") < line_index_with(&rl, "INITIRQA end"));
    CHECK(line_index_with(&rl, "comment=startup-disc-stop-shadow") > 0);
    CHECK(rl.dropped == 0 && rl.truncated == 0);
    {
        char s[900];
        int n = gbp_initirqa_summary(&res, s, sizeof s);
        CHECK(n > 0 && (size_t)n < sizeof s);
        CHECK(strstr(s, "status=ok_no_pi_cause_observed reason=- restore=ok") && strstr(s, "written=1 irq_attempted=3 irq_completed=3"));
        CHECK(strstr(s, "a1_write=8aae a1_0_irq=8aaa a2pre_irq=8aaa a2_0_irq=0000") && strstr(s, "stop_write=8aaa stop_post=8aaa"));
        CHECK(strstr(s, "power_cycle_required=1 errors=0 transport_ok=1"));
    }
}

/* 2, 3: a source re-asserts after A2 (masks open) → INTSR bit 13 while masked → EVENT, early end,
 * Disc stop word acknowledges it, one PI cleanup (latched model) / none (level model) */
static void test_cause_after_a2(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m); m.source_assert_after_write = 2; m.source_assert_delay = 300; m.source_assert_bits = 0x0100;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_PI_CAUSE_OBSERVED && res.restore_ok == 1 && res.errors == 0);
    CHECK(res.intsr13_seen == 1 && strcmp(res.first_intsr13_phase, "A2") == 0 && res.polls_at_first_intsr13 > 0);
    CHECK(res.event_taken == 1 && res.window_ended_early == 1 && res.t_event == res.t_first_intsr13);
    CHECK(res.t_first_intsr13 - res.t_a2 >= 280u && res.t_first_intsr13 - res.t_a2 <= 300u);   /* asserted 300 mock ticks after the write itself */
    CHECK(res.a2_obs_taken == 3 && res.n_a2_order == 4 && res.a2_order[3] == GBP_INITIRQA_SNAP_EVENT);
    CHECK(res.snap[GBP_INITIRQA_SNAP_EVENT].taken && res.snap[GBP_INITIRQA_SNAP_EVENT].is_event);
    CHECK((res.snap[GBP_INITIRQA_SNAP_EVENT].poll_intsr & GBP_PI_HSP_BIT) != 0 && (res.snap[GBP_INITIRQA_SNAP_EVENT].intsr & GBP_PI_HSP_BIT) != 0);
    CHECK(res.snap[GBP_INITIRQA_SNAP_EVENT].irq_gbi == 0x0100 && res.snap[GBP_INITIRQA_SNAP_EVENT].control_vote == 0x8c);   /* same-moment IRQ + CONTROL */
    CHECK(!res.snap[GBP_INITIRQA_SNAP_A2_OBS + 3].taken);                          /* window ended before the 4th deadline */
    CHECK(res.irq_stop_pre.gbi == 0x0100 && res.stop_value == 0x8baa && res.irq_stop_post.gbi == 0x8aaa);   /* pending source acknowledged */
    CHECK(res.stop_masks_readback == 1 && res.stop_bit15_readback == 1);
    CHECK(res.pi_cleanup_performed == 1 && res.pi_cleanup_ok == 1 && res.pi_cleanup_sticky == 0 && m.intsr_writes == 1 && m.last_intsr_write == GBP_PI_HSP_BIT);
    CHECK((res.cleanup_intsr_before & GBP_PI_HSP_BIT) != 0 && (res.cleanup_intsr_after & GBP_PI_HSP_BIT) == 0);
    CHECK((res.snap[GBP_INITIRQA_SNAP_FINAL].intsr & GBP_PI_HSP_BIT) == 0 && (m.intmr & GBP_PI_HSP_BIT) == 0);
    CHECK(m.deliveries == 0);                                                    /* never delivered: PI masked */
    check_never(&m);
    check_order(&m, &res);
    check_irq_writes(&m, &res, 3);
    CHECK(count_lines_with(&rl, "SNAP tag=EVENT") == 1 && count_lines_with(&rl, "poll_intsr=00002000") == 1);
    CHECK(line_index_with(&rl, "SNAP tag=A2-5MS") < line_index_with(&rl, "SNAP tag=EVENT"));
    CHECK(line_index_with(&rl, "SNAP tag=EVENT") < line_index_with(&rl, "WINDOW tag=A2"));
    CHECK(count_lines_with(&rl, "WINDOW tag=A2 deadlines=3/6") == 1 && count_lines_with(&rl, "ended_early=1 event=1") == 1);
    CHECK(count_lines_with(&rl, "CLEANUP performed=1") == 1 && count_lines_with(&rl, "sticky=0 ok=1") == 1);
    CHECK(count_lines_with(&rl, "INITIRQA end status=ok_pi_cause_observed") == 1);
    CHECK(count_lines_with(&rl, "SNAP tag=A2-50MS") == 0);
    CHECK(rl.dropped == 0 && rl.truncated == 0);
    /* level model: the stop word drops the line, INTSR clears by itself, no cleanup */
    mock_003a(&m); m.source_assert_after_write = 2; m.source_assert_delay = 300; m.source_assert_bits = 0x0100; m.pi_cause_level = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_PI_CAUSE_OBSERVED && res.event_taken == 1);
    CHECK(res.pi_cleanup_performed == 0 && m.intsr_writes == 0 && (res.cleanup_intsr_before & GBP_PI_HSP_BIT) == 0);
    CHECK(count_lines_with(&rl, "CLEANUP performed=0 intsr=") == 1 && count_lines_with(&rl, "reason=intsr13_clear") == 1);
    check_never(&m);
    check_order(&m, &res);
}

/* 4: the single cleanup W1C does not clear bit 13 → sticky recorded, no loop, not a restore failure */
static void test_cleanup_sticky(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m); m.source_assert_after_write = 2; m.source_assert_delay = 100; m.source_assert_bits = 0x0400; m.intsr_w1c_ignored = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_PI_CAUSE_OBSERVED);
    CHECK(res.pi_cleanup_performed == 1 && res.pi_cleanup_ok == 0 && res.pi_cleanup_sticky == 1 && m.intsr_writes == 1);
    CHECK(res.restore_ok == 1);                                                  /* observation, not a restore failure */
    CHECK((res.snap[GBP_INITIRQA_SNAP_FINAL].intsr & GBP_PI_HSP_BIT) != 0);      /* still visible at FINAL, still masked */
    CHECK((res.snap[GBP_INITIRQA_SNAP_FINAL].intmr & GBP_PI_HSP_BIT) == 0);
    CHECK(count_lines_with(&rl, "sticky=1 ok=0") == 1 && count_lines_with(&rl, "pi_cleanup_sticky=1") >= 1);
    check_never(&m);
    check_order(&m, &res);
}

/* 5: a source asserts right after A1 (behind the masks) and becomes visible at A2 — seen by the A2-0 snapshot itself */
static void test_cause_visible_at_a2_0(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m); m.source_assert_after_write = 1; m.source_assert_delay = 0; m.source_assert_bits = 0x0100;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_PI_CAUSE_OBSERVED);
    CHECK(res.snap[GBP_INITIRQA_SNAP_A1_0].irq_gbi == 0x8baa);                  /* pending under its mask, no cause */
    CHECK((res.snap[GBP_INITIRQA_SNAP_A1_0].intsr & GBP_PI_HSP_BIT) == 0 && (res.a2pre_intsr & GBP_PI_HSP_BIT) == 0);
    CHECK(res.snap[GBP_INITIRQA_SNAP_A2_0].irq_gbi == 0x0100 && (res.snap[GBP_INITIRQA_SNAP_A2_0].intsr & GBP_PI_HSP_BIT) != 0);
    CHECK(strcmp(res.first_intsr13_phase, "A2-0") == 0 && res.t_first_intsr13 == res.snap[GBP_INITIRQA_SNAP_A2_0].ticks);
    CHECK(res.event_taken == 1 && res.a2_obs_taken == 0 && res.n_a2_order == 1 && res.window_ended_early == 1);
    CHECK(res.stop_value == 0x8baa && res.irq_stop_post.gbi == 0x8aaa);
    check_never(&m);
    check_order(&m, &res);
    check_irq_writes(&m, &res, 3);
    CHECK(count_lines_with(&rl, "WINDOW tag=A2 deadlines=0/6") == 1);
}

/* 6: bit 15 as a W1C pending summary (the other reading) — A1 clears it, the stop word cannot set it */
static void test_bit15_summary(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m); m.bit15_mode = MOCK_BIT15_SUMMARY;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED && res.restore_ok == 1);
    CHECK(res.snap[GBP_INITIRQA_SNAP_A1_0].irq_gbi == 0x0aaa && res.snap[GBP_INITIRQA_SNAP_A2_0].irq_gbi == 0x0000);
    CHECK(res.irq_stop_post.gbi == 0x0aaa && res.stop_masks_readback == 1 && res.stop_bit15_readback == 0);
    CHECK(res.irq_stop_readback_ok == 1);                                        /* a clear bit 15 is an observation */
    check_never(&m);
    check_order(&m, &res);
    /* window continues after the event when configured; the device write is ignored by a static model */
    {
        struct gbp_initirqa_config cfg;
        mock_003a(&m); m.source_assert_after_write = 2; m.source_assert_delay = 300; m.source_assert_bits = 0x0100;
        test_config(&cfg); cfg.end_window_on_event = 0;
        run_cfg(&m, &rl, &res, &cfg);
        CHECK(res.status == GBP_INITIRQA_OK_PI_CAUSE_OBSERVED && res.event_taken == 1 && res.window_ended_early == 0);
        CHECK(res.a2_obs_taken == 6 && res.n_a2_order == 7 && res.a2_order[3] == GBP_INITIRQA_SNAP_EVENT);
        CHECK(count_lines_with(&rl, "SNAP tag=") == 2 + 1 + 2 + 1 + 6 + 1 + 1);
        check_never(&m);
        check_order(&m, &res);
    }
    {
        /* STATIC model: the device ignores every IRQ write (read-back unchanged) — a valid outcome */
        gbp_mock_init(&m); m.irq_block = HW_IRQ_8AAE; m.control_block = HW_CONTROL_98;
        run(&m, &rl, &res);
        CHECK(res.status == GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED && res.control_orig == 0x90);
        CHECK(res.snap[GBP_INITIRQA_SNAP_A1_0].irq_gbi == 0x8aae && res.snap[GBP_INITIRQA_SNAP_A2_0].irq_gbi == 0x8aae);
        CHECK(res.irq_stop_pre.gbi == 0x8aae && res.stop_value == 0x8aae && res.irq_stop_post.gbi == 0x8aae);
        CHECK(res.stop_masks_readback == 1 && res.stop_bit15_readback == 1 && res.restore_ok == 1);
        CHECK(res.snap[GBP_INITIRQA_SNAP_BASE].control[0] == 0x98 && res.snap[GBP_INITIRQA_SNAP_BASE].irq[0] == 0xaa);
        check_never(&m);
        check_order(&m, &res);
        check_irq_writes(&m, &res, 3);
    }
}

/* 7, 8, 9: IRQ write failures — A1 (no A2), A2 (no window), stop (restore=error) */
static void test_irq_write_failures(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m); m.irq_write_fail_at = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && strcmp(res.reason, "a1_write_failed") == 0);
    CHECK(res.w_a1.attempted == 1 && res.w_a1.completed == 0 && res.w_a2.attempted == 0);
    CHECK(res.irq_writes_attempted == 2 && res.irq_writes_completed == 1);       /* A1 (failed) + stop */
    CHECK(!res.snap[GBP_INITIRQA_SNAP_A1_0].taken && res.a1_obs_taken == 0 && !res.irq_a2pre.taken);
    CHECK(res.control_restore_ok == 1 && res.irq_stop_write_ok == 1 && res.irq_stop_readback_ok == 1 && res.arinfo_restore_ok == 1);
    CHECK(res.restore_ok == 1 && res.transport_ok == 0 && res.errors == 1 && res.power_cycle_required == 1);
    CHECK(res.irq_stop_pre.gbi == 0x8aae && res.stop_value == 0x8aae);         /* the failed write did not apply */
    CHECK(count_lines_with(&rl, "IRQW tag=A1 ") == 1 && count_lines_with(&rl, "rc=timeout") == 1 && count_lines_with(&rl, "IRQW tag=A2 ") == 0);
    CHECK(count_lines_with(&rl, "WINDOW tag=A1") == 0 && count_lines_with(&rl, "IRQW tag=STOP ") == 1);
    /* teardown attempted after the failed A1: CONTROL restore and the stop word both issued; device state uncertain */
    CHECK(res.w_ctl_restore.attempted == 1 && res.w_ctl_restore.completed == 1 && res.w_stop.attempted == 1 && res.w_stop.completed == 1);
    CHECK(res.uncertain_writes == 1 && res.power_cycle_required == 1);
    CHECK(count_lines_with(&rl, "WRITES control_written=1 irq_attempted=2 irq_completed=1 ctl_exp=1/1 a1=1/0 a2=0/0 stop=1/1 ctl_restore=1/1 uncertain=1 power_cycle_required=1") == 1);
    CHECK(count_lines_with(&rl, "TEARDOWN start control_written=1 irq_attempted=1 irq_completed=0 uncertain_writes=1") == 1);
    {
        char s[900];
        gbp_initirqa_summary(&res, s, sizeof s);
        CHECK(strstr(s, "irq_attempted=2 irq_completed=1 ctl_exp=1/1 a1=1/0 a2=0/0 stop=1/1 ctl_restore=1/1 uncertain_writes=1"));
        CHECK(strstr(s, "power_cycle_required=1"));
    }
    check_never(&m);
    check_order(&m, &res);
    check_irq_writes(&m, &res, 2);
    /* a busy refusal (returned before the DMA is programmed) is handled exactly like a timeout: attempted, not completed */
    mock_003a(&m); m.fail_at_op = 17; m.fail_rc = GBP_ERR_BUSY;                  /* 17th transfer = the A1 write */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && strcmp(res.reason, "a1_write_failed") == 0);
    CHECK(res.w_a1.attempted == 1 && res.w_a1.completed == 0 && res.w_a1.rc == GBP_ERR_BUSY && res.w_a2.attempted == 0);
    CHECK(res.power_cycle_required == 1 && res.uncertain_writes == 1 && res.w_stop.attempted == 1);
    check_never(&m);
    /* the failed A1 may still have reached the device (DMA started): stop word computed from the new read */
    mock_003a(&m); m.irq_write_fail_at = 1; m.irq_write_fail_applies = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && res.irq_stop_pre.gbi == 0x8aaa && res.stop_value == 0x8aaa);
    check_never(&m);
    /* A2 fails: no window, stop still written */
    mock_003a(&m); m.irq_write_fail_at = 2;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && strcmp(res.reason, "a2_write_failed") == 0);
    CHECK(res.w_a2.attempted == 1 && res.w_a2.completed == 0 && res.irq_writes_attempted == 3 && res.irq_writes_completed == 2);
    CHECK(res.a1_obs_taken == 2 && res.a2_obs_taken == 0 && !res.snap[GBP_INITIRQA_SNAP_A2_0].taken && res.n_a2_order == 0);
    CHECK(res.restore_ok == 1 && res.irq_stop_write_ok == 1 && res.irq_stop_pre.gbi == 0x8aaa && res.stop_value == 0x8aaa);
    CHECK(count_lines_with(&rl, "IRQW tag=A2 ") == 1 && count_lines_with(&rl, "WINDOW tag=A2") == 0 && count_lines_with(&rl, "WINDOW tag=A1") == 1);
    CHECK(res.w_a2.attempted == 1 && res.w_a2.completed == 0 && res.power_cycle_required == 1 && res.uncertain_writes == 1);
    CHECK(res.w_ctl_restore.attempted == 1 && res.w_stop.attempted == 1);      /* teardown attempted */
    CHECK(count_lines_with(&rl, "WRITES control_written=1 irq_attempted=3 irq_completed=2 ctl_exp=1/1 a1=1/1 a2=1/0 stop=1/1 ctl_restore=1/1 uncertain=1 power_cycle_required=1") == 1);
    check_never(&m);
    check_order(&m, &res);
    check_irq_writes(&m, &res, 3);
    /* the stop write fails: restore=error, readback still taken, AR_INFO still restored; the power-cycle flag is not cleared */
    mock_003a(&m); m.irq_write_fail_at = 3;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED);
    CHECK(res.irq_stop_write_ok == 0 && res.irq_stop_readback_ok == 1 && res.irq_stop_post.gbi == 0x0000);
    CHECK(res.restore_ok == 0 && strcmp(res.restore_reason, "irq_stop_write_failed") == 0);
    CHECK(res.control_restore_ok == 1 && res.arinfo_restore_ok == 1 && res.stop_masks_readback == 0);
    CHECK(res.w_stop.attempted == 1 && res.w_stop.completed == 0 && res.power_cycle_required == 1 && res.uncertain_writes == 1);
    CHECK(count_lines_with(&rl, "RESTORE control_restore_ok=1 irq_stop_write_ok=0 irq_stop_readback_ok=1") == 1);
    CHECK(count_lines_with(&rl, "WRITES control_written=1 irq_attempted=3 irq_completed=2 ctl_exp=1/1 a1=1/1 a2=1/1 stop=1/0 ctl_restore=1/1 uncertain=1 power_cycle_required=1") == 1);
    CHECK(count_lines_with(&rl, "INITIRQA end status=ok_no_pi_cause_observed reason=- restore=error restore_reason=irq_stop_write_failed power_cycle_required=1") == 1);
    check_never(&m);
    /* restore=ok never removes the power-cycle requirement once a write was attempted */
    mock_003a(&m);
    run(&m, &rl, &res);
    CHECK(res.restore_ok == 1 && res.power_cycle_required == 1 && res.uncertain_writes == 0);
    CHECK(count_lines_with(&rl, "restore=ok restore_reason=- power_cycle_required=1") == 1);
}

/* 10, 11, 12: CONTROL write failure (no IRQ writes at all), CONTROL restore ignored, AR_INFO restore failure */
static void test_control_and_arinfo_failures(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m); m.fail_at_op = 12; m.fail_rc = GBP_ERR_TIMEOUT;               /* 8 handshake + 3 BASE reads, 12th = CONTROL EXP */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && strcmp(res.reason, "control_write_failed") == 0);
    CHECK(res.control_written == 1 && res.power_cycle_required == 1 && res.irq_writes_attempted == 0);
    CHECK(res.w_ctl_exp.attempted == 1 && res.w_ctl_exp.completed == 0 && res.w_a1.attempted == 0 && res.w_a2.attempted == 0);
    CHECK(res.w_ctl_restore.attempted == 1 && res.w_stop.attempted == 0 && res.uncertain_writes == 1);   /* best-effort teardown, no stop word */
    CHECK(count_lines_with(&rl, "WRITES control_written=1 irq_attempted=0 irq_completed=0 ctl_exp=1/0 a1=0/0 a2=0/0 stop=0/0 ctl_restore=1/1 uncertain=1 power_cycle_required=1") == 1);
    CHECK(!res.window_entered && !res.snap[GBP_INITIRQA_SNAP_P0].taken && res.irq_stop_write_ok == -1);
    CHECK(res.control_restore_ok == 1 && res.arinfo_restore_ok == 1 && res.restore_ok == 1);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_WR, BASE, 0xD) == 0);
    CHECK(count_lines_with(&rl, "CTLW tag=RESTORE") == 1 && count_lines_with(&rl, "IRQW") == 0 && count_lines_with(&rl, "REGION") == 0);
    CHECK(count_lines_with(&rl, "SNAP tag=FINAL") == 1);
    check_never(&m);
    check_order(&m, &res);
    /* P0 read failure: abort before the region, CONTROL restored, no IRQ write */
    mock_003a(&m); m.fail_at_op = 13; m.fail_rc = GBP_ERR_BUSY;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && strcmp(res.reason, "p0_read_failed") == 0);
    CHECK(res.irq_writes_attempted == 0 && res.control_restore_ok == 1 && !res.window_entered);
    check_never(&m);
    /* A1PRE read failure: region entered, nothing written to the IRQ register */
    mock_003a(&m); m.fail_at_op = 16; m.fail_rc = GBP_ERR_TIMEOUT;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && strcmp(res.reason, "a1pre_read_failed") == 0);
    CHECK(res.window_entered && res.irq_writes_attempted == 0 && res.w_a1.attempted == 0 && res.irq_stop_write_ok == -1);
    CHECK(count_lines_with(&rl, "RAW A1PRE idx=d") == 1 && count_lines_with(&rl, "rc=timeout") == 1 && count_lines_with(&rl, "IRQW") == 0);
    CHECK(res.log_count_window_start == res.log_count_window_end);
    check_never(&m);
    /* A2PRE read failure: A1 done, no A2, stop word written */
    mock_003a(&m); m.fail_at_op = 24; m.fail_rc = GBP_ERR_TIMEOUT;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && strcmp(res.reason, "a2pre_read_failed") == 0);
    CHECK(res.w_a1.completed == 1 && res.w_a2.attempted == 0 && res.irq_writes_attempted == 2 && res.irq_writes_completed == 2);
    CHECK(res.a1_obs_taken == 2 && res.irq_a2pre.taken && res.irq_a2pre.rc == GBP_ERR_TIMEOUT);
    CHECK(count_lines_with(&rl, "A2CHK irq_rc=timeout") == 1 && count_lines_with(&rl, "IRQW tag=A2 ") == 0);
    check_never(&m);
    check_order(&m, &res);
    /* a read fails inside the A2 window: recorded, the window goes on, transport_ok=0 */
    mock_003a(&m); m.fail_at_op = 30; m.fail_rc = GBP_ERR_BUSY;                  /* A2-500US CONTROL read */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED && res.errors == 1 && res.transport_ok == 0 && res.restore_ok == 1);
    CHECK(res.a2_obs_taken == 6 && res.snap[GBP_INITIRQA_SNAP_A2_OBS + 1].control_rc == GBP_ERR_BUSY);
    CHECK(count_lines_with(&rl, "RAW A2-500US idx=4 addr=01400000 rc=busy") == 1);
    check_never(&m);
    check_order(&m, &res);
    /* CONTROL restore ignored by the device */
    mock_003a(&m); m.control_write_fail_at = 2;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED && res.control_restore_ok == 0);
    CHECK(res.restore_ok == 0 && strcmp(res.restore_reason, "control_restore_failed") == 0);
    CHECK(res.irq_stop_write_ok == 1 && res.arinfo_restore_ok == 1 && res.control_restore_vote == 0x8c);
    CHECK(count_lines_with(&rl, "CONTROL restore semantic=90 rc=ok readback_rc=ok readback_vote=8c readback_b1f=8c ok=0") == 1);
    check_never(&m);
    /* AR_INFO restore fails: reported, everything else restored */
    mock_003a(&m); m.arinfo_write_fail_at = 2;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED && res.arinfo_restore_ok == 0 && res.arinfo_final == 0xFFFF);
    CHECK(res.restore_ok == 0 && strcmp(res.restore_reason, "arinfo_restore_failed") == 0);
    CHECK(res.control_restore_ok == 1 && res.irq_stop_write_ok == 1 && m.arinfo == 0x005b);
    CHECK(count_lines_with(&rl, "ARINFO restore value=0043 rc=backend") == 1);
    check_never(&m);
}

/* 13, 14: IRQ shape preconditions — at BASE (no write at all) and at A1PRE (CONTROL restored, no IRQ write) */
static void test_irq_shape(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    struct gbp_initirqa_config cfg; const char *why = 0;
    test_config(&cfg);
    CHECK(gbp_initirqa_irq_shape(&cfg, 0x8aae, 0x8aae, &why) == 1 && strcmp(why, "-") == 0);
    CHECK(gbp_initirqa_irq_shape(&cfg, 0x8fae, 0x8fae, &why) == 1);              /* physical S2 value */
    CHECK(gbp_initirqa_irq_shape(&cfg, 0x8aaa, 0x8aaa, &why) == 1);              /* sources may vary */
    CHECK(gbp_initirqa_irq_shape(&cfg, 0x8fff, 0x8fff, &why) == 1);
    CHECK(gbp_initirqa_irq_shape(&cfg, 0x0aae, 0x0aae, &why) == 0 && strcmp(why, "irq_bit15_clear") == 0);
    CHECK(gbp_initirqa_irq_shape(&cfg, 0x8aa8, 0x8aa8, &why) == 0 && strcmp(why, "irq_masks_not_set") == 0);
    CHECK(gbp_initirqa_irq_shape(&cfg, 0x9aae, 0x9aae, &why) == 0 && strcmp(why, "irq_high_bits_set") == 0);
    CHECK(gbp_initirqa_irq_shape(&cfg, 0x9090, 0x9090, &why) == 0 && strcmp(why, "irq_masks_not_set") == 0);
    CHECK(gbp_initirqa_irq_shape(&cfg, 0x8aaf, 0x8aae, &why) == 0 && strcmp(why, "irq_ambiguous") == 0);
    CHECK(gbp_initirqa_irq_shape(&cfg, 0x0000, 0x0000, &why) == 0);             /* Dolphin-like zero */
    mock_003a(&m); m.irq_reg = 0x0aae;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_IRQ_SHAPE && strcmp(res.reason, "irq_bit15_clear") == 0);
    CHECK(res.control_written == 0 && res.irq_writes_attempted == 0 && res.power_cycle_required == 0 && m.control_writes == 0);
    CHECK(res.arinfo_restore_ok == 1 && res.restore_ok == 1 && !res.snap[GBP_INITIRQA_SNAP_FINAL].taken);
    CHECK(count_lines_with(&rl, "IRQSHAPE tag=BASE disc=0aae gbi=0aae agree=1 masks_ok=1 bit15_ok=0 high_ok=1") == 1);
    CHECK(count_lines_with(&rl, "CTLW") == 0 && count_lines_with(&rl, "IRQW") == 0);
    check_never(&m);
    mock_003a(&m); m.irq_reg = 0x8aa8;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_IRQ_SHAPE && strcmp(res.reason, "irq_masks_not_set") == 0 && m.control_writes == 0);
    mock_003a(&m); m.irq_reg = 0x9aae;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_IRQ_SHAPE && strcmp(res.reason, "irq_high_bits_set") == 0 && m.control_writes == 0);
    /* Disc reading and GBI reading disagree → ambiguous, no write */
    {
        static uint8_t amb[32];
        memcpy(amb, HW_IRQ_8AAE, 32); amb[0x1F] = 0xaf;
        gbp_mock_init(&m); m.irq_block = amb;
        run(&m, &rl, &res);
        CHECK(res.status == GBP_INITIRQA_ABORT_IRQ_SHAPE && strcmp(res.reason, "irq_ambiguous") == 0 && m.control_writes == 0);
        CHECK(res.snap[GBP_INITIRQA_SNAP_BASE].irq_disc == 0x8aaf && res.snap[GBP_INITIRQA_SNAP_BASE].irq_gbi == 0x8aae);
    }
    /* the shape changes between BASE and A1PRE → abort_irq_shape after the CONTROL write: CONTROL restored, IRQ never written */
    gbp_mock_init(&m); m.irq_block = HW_IRQ_8AAE; m.irq_after_write = 0x90;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_IRQ_SHAPE && strcmp(res.reason, "irq_masks_not_set") == 0);
    CHECK(res.irq_shape_base_ok == 1 && res.irq_shape_a1pre_ok == 0 && res.irq_a1pre.gbi == 0x9090);
    CHECK(res.control_written == 1 && res.irq_writes_attempted == 0 && res.control_restore_ok == 1 && res.power_cycle_required == 1);
    CHECK(res.window_entered && res.log_count_window_start == res.log_count_window_end);
    CHECK(count_lines_with(&rl, "IRQSHAPE tag=A1PRE disc=9090 gbi=9090 agree=1 masks_ok=0") == 1 && count_lines_with(&rl, "IRQW") == 0);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_WR, BASE, 0xD) == 0);
    check_never(&m);
    check_order(&m, &res);
    /* byte 0 anomalies never feed a decision */
    mock_003a(&m); m.irq_byte0_anomaly = 1; m.control_block = HW_CONTROL_98; m.test_byte0_anomaly = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED && res.snap[GBP_INITIRQA_SNAP_BASE].irq[0] != 0x8a);
    CHECK(res.snap[GBP_INITIRQA_SNAP_BASE].irq_gbi == 0x8aae && res.snap[GBP_INITIRQA_SNAP_BASE].irq_disc == 0x8aae);
    check_never(&m);
}

/* 15: PI preconditions — start, P0 re-check, A2PRE re-check; never adjusted */
static void test_pi_preconditions(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m); m.intsr = GBP_PI_HSP_BIT;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_PI_PRECONDITION && strcmp(res.reason, "intsr13_set") == 0);
    CHECK(m.control_writes == 0 && m.irq_writes == 0 && m.intsr_writes == 0 && m.intmr_writes == 0 && (m.intsr & GBP_PI_HSP_BIT) != 0);
    CHECK(res.arinfo_restore_ok == 1 && res.power_cycle_required == 0 && count_lines_with(&rl, "PRECOND intsr13=1 intmr13=0 ok=0 reason=intsr13_set") == 1);
    check_never(&m);
    mock_003a(&m); m.intmr = 0x000020f0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_PI_PRECONDITION && strcmp(res.reason, "intmr13_unmasked") == 0);
    CHECK(m.control_writes == 0 && m.irq_writes == 0 && m.intmr == 0x000020f0);  /* not silently masked */
    check_never(&m);
    mock_003a(&m); m.pi_unavailable = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_PI_PRECONDITION && strcmp(res.reason, "pi_unavailable") == 0 && m.control_writes == 0);
    /* INTMR bit 13 becomes 1 right after the CONTROL write (external unmask model): abort at P0, CONTROL restored, no IRQ write.
     * The mock flags its own "DMA while unmasked" invariant for the reads that follow — expected in this synthetic scenario. */
    mock_003a(&m); m.intmr13_set_after_control_write = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_PI_PRECONDITION && strcmp(res.reason, "intmr13_unmasked_p0") == 0);
    CHECK(res.control_written == 1 && res.irq_writes_attempted == 0 && res.control_restore_ok == 1 && !res.window_entered);
    CHECK(count_lines_with(&rl, "P0CHK intsr13=0 intmr13=1 control=8c irq=8aae ok=0 reason=intmr13_unmasked_p0") == 1);
    CHECK(m.intmr_writes == 0 && m.irq_writes == 0);
    /* INTMR bit 13 becomes 1 after A1: A2 skipped, stop word still written */
    mock_003a(&m); m.intmr13_set_after_irq_write = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_PI_PRECONDITION && strcmp(res.reason, "intmr13_unmasked_a2pre") == 0);
    CHECK(res.w_a1.completed == 1 && res.w_a2.attempted == 0 && res.irq_writes_attempted == 2 && res.irq_stop_write_ok == 1);
    CHECK((res.a2pre_intmr & GBP_PI_HSP_BIT) != 0 && count_lines_with(&rl, "A2CHK irq_rc=ok pi_ok=1 intsr13=0 intmr13=1 ok=0") == 1);
    CHECK(m.intmr_writes == 0 && count_lines_with(&rl, "IRQW tag=A2 ") == 0);
    CHECK(count_lines_with(&rl, "CLEANUP performed=0") == 1 && count_lines_with(&rl, "reason=intsr13_clear") == 1);
}

/* 16: absent / inconsistent → nothing written, AR_INFO restored */
static void test_absent_and_inconsistent(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m); m.present = 0; m.absent_fill = 0xC1;                          /* physical no-GBP value of init-0001 */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_NOT_PRESENT && res.det.verdict == GBP_VERDICT_ABSENT && strcmp(res.reason, "absent") == 0);
    CHECK(res.control_written == 0 && res.irq_writes_attempted == 0 && res.power_cycle_required == 0);
    CHECK(m.control_writes == 0 && m.irq_writes == 0 && res.arinfo_restore_ok == 1 && m.arinfo == 0x0043);
    CHECK(count_lines_with(&rl, "CTLW") == 0 && count_lines_with(&rl, "SNAP") == 0 && count_lines_with(&rl, "IRQW") == 0);
    CHECK(res.restore_ok == 1 && count_lines_with(&rl, "INITIRQA end status=abort_not_present reason=absent") == 1);
    check_never(&m);
    mock_003a(&m); m.present = 0; m.absent_fill = 0x00;                          /* FF pattern passes → inconsistent */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_INCONSISTENT && res.det.verdict == GBP_VERDICT_INCONSISTENT);
    CHECK(m.control_writes == 0 && res.arinfo_restore_ok == 1);
    mock_003a(&m); m.fail_at_op = 3; m.fail_rc = GBP_ERR_TIMEOUT;               /* transport failure inside the handshake */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_INCONSISTENT && res.det.verdict == GBP_VERDICT_INCONSISTENT && m.control_writes == 0);
    check_never(&m);
}

/* 17: CONTROL shape / ambiguity / read failure → abort before any write */
static void test_control_shapes(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m); m.control_byte = 0x80;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_CONTROL_SHAPE && m.control_writes == 0 && m.irq_writes == 0 && res.arinfo_restore_ok == 1);
    mock_003a(&m); m.control_byte = 0x9C;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_CONTROL_SHAPE && m.control_writes == 0);
    mock_003a(&m); m.control_byte = 0x03;                                        /* Dolphin GBPlayer model idle value */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_CONTROL_SHAPE && strcmp(res.reason, "control_not_idle_shape") == 0);
    CHECK(res.irq_shape_base_ok == -1 && count_lines_with(&rl, "IRQSHAPE") == 0);   /* CONTROL shape is checked first */
    {
        static uint8_t half[32];
        memset(half, 0x90, 15); memset(half + 15, 0x80, 17); half[31] = 0x90;
        mock_003a(&m); m.control_block = half;
        run(&m, &rl, &res);
        CHECK(res.status == GBP_INITIRQA_ABORT_CONTROL_READ && strcmp(res.reason, "control_ambiguous") == 0 && m.control_writes == 0);
    }
    mock_003a(&m); m.fail_at_op = 9; m.fail_rc = GBP_ERR_BUSY;                   /* BASE CONTROL read */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_CONTROL_READ && strcmp(res.reason, "base_read_failed") == 0 && m.control_writes == 0);
    check_never(&m);
}

/* 18: transports without a time base or without INTSR polling; polling disabled; ring overflow */
static void test_transport_variants(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    struct gbp_transport t; struct gbp_initirqa_config cfg;
    /* no ticks(): the deadline loops are skipped, the writes still happen, everything restored */
    mock_003a(&m); gbp_mock_transport(&m, &t); t.ticks = 0;
    test_config(&cfg); ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_initirqa_probe_run(&t, &rl, &cfg, &res);
    CHECK(res.status == GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED && res.no_timebase == 1);
    CHECK(res.a1_obs_taken == 0 && res.a2_obs_taken == 0 && res.snap[GBP_INITIRQA_SNAP_A1_0].taken && res.snap[GBP_INITIRQA_SNAP_A2_0].taken);
    CHECK(res.irq_writes_attempted == 3 && res.restore_ok == 1 && res.w_a1.t_after == 0);
    CHECK(count_lines_with(&rl, "no_timebase=1") == 2);
    check_never(&m);
    /* no poll_intsr(): the loops run on the time base alone */
    mock_003a(&m); gbp_mock_transport(&m, &t); t.poll_intsr = 0;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_initirqa_probe_run(&t, &rl, &cfg, &res);
    CHECK(res.status == GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED && res.a1_polls == 0 && res.a2_polls == 0 && res.a2_obs_taken == 6);
    CHECK(count_lines_with(&rl, "PRECOND intsr13=0 intmr13=0 irq_path_required=0 poll_intsr=0") == 1);
    check_never(&m);
    /* polling disabled: a cause is still caught by the next deadline snapshot (no EVENT) */
    mock_003a(&m); m.source_assert_after_write = 2; m.source_assert_delay = 300; m.source_assert_bits = 0x0100;
    test_config(&cfg); cfg.poll_between = 0;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.status == GBP_INITIRQA_OK_PI_CAUSE_OBSERVED && res.event_taken == 0 && res.a2_polls == 0);
    CHECK(strcmp(res.first_intsr13_phase, "A2-50MS") == 0 && res.a2_obs_taken == 6);
    CHECK((res.snap[GBP_INITIRQA_SNAP_A2_OBS + 3].intsr & GBP_PI_HSP_BIT) != 0 && res.snap[GBP_INITIRQA_SNAP_A2_OBS + 3].irq_gbi == 0x0100);
    check_never(&m);
    check_order(&m, &res);
    /* poll failures are counted, not fatal */
    mock_003a(&m); gbp_mock_transport(&m, &t);
    test_config(&cfg); ringlog_init(&rl, storage, LINE_LEN, LINES);
    m.pi_unavailable = 0;
    gbp_initirqa_probe_run(&t, &rl, &cfg, &res);
    CHECK(res.poll_errors == 0);
    /* ring overflow: the probe completes, restores, and the log reports the drops */
    {
        static char tiny[8 * LINE_LEN];
        mock_003a(&m); m.source_assert_after_write = 2; m.source_assert_delay = 300; m.source_assert_bits = 0x0100;
        gbp_mock_transport(&m, &t);
        test_config(&cfg);
        ringlog_init(&rl, tiny, LINE_LEN, 8);
        gbp_initirqa_probe_run(&t, &rl, &cfg, &res);
        CHECK(res.status == GBP_INITIRQA_OK_PI_CAUSE_OBSERVED && res.restore_ok == 1 && res.arinfo_restore_ok == 1);
        CHECK(rl.dropped > 0 && rl.count == 8);
        check_never(&m);
        check_order(&m, &res);
    }
}

/* line-length regression: worst-case field widths must fit LINE_LEN without truncation; time base wraps inside the run */
static void test_line_lengths_and_wrap(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m); m.source_assert_after_write = 2; m.source_assert_delay = 300; m.source_assert_bits = 0x0500;
    m.intsr_w1c_ignored = 1; m.irq_byte0_anomaly = 1;
    m.tick = 0xFFFFFF00u;                                  /* wrap the time base inside the run */
    m.intsr = 0x00010000u; m.intmr = 0x000001fau;          /* physical PI values */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_OK_PI_CAUSE_OBSERVED);
    CHECK(rl.truncated == 0 && rl.dropped == 0);
    CHECK(max_line_len(&rl) < LINE_LEN - 1);
    CHECK(res.snap[GBP_INITIRQA_SNAP_P0].since_control < 1000u && res.snap[GBP_INITIRQA_SNAP_A1_0].since_a1 < 1000u);   /* wrap-safe */
    CHECK((uint32_t)(res.t_first_intsr13 - res.t_a2) >= 280u && (uint32_t)(res.t_first_intsr13 - res.t_a2) <= 300u);
    CHECK(res.snap[GBP_INITIRQA_SNAP_EVENT].since_a2 == (uint32_t)(res.t_event - res.t_a2));
    {
        char s[900];
        int n = gbp_initirqa_summary(&res, s, sizeof s);
        CHECK(n > 0 && (size_t)n < sizeof s);
    }
    /* config: the µs → ticks conversion at the console's time base and the ids */
    {
        struct gbp_initirqa_config cfg;
        gbp_initirqa_config_default(&cfg);
        CHECK(cfg.tb_hz == 40500000u && cfg.a1_obs_ticks[0] == 2025u && cfg.a1_obs_ticks[1] == 20250u);
        CHECK(cfg.a2_obs_ticks[0] == 2025u && cfg.a2_obs_ticks[2] == 202500u && cfg.a2_obs_ticks[5] == 81000000u);
        CHECK(cfg.t_max_ms == 2000u && cfg.n_a1_obs == 2 && cfg.n_a2_obs == 6);
        CHECK(strcmp(cfg.a2_obs_id[0], "A2-50US") == 0 && strcmp(cfg.a2_obs_id[2], "A2-5MS") == 0 && strcmp(cfg.a2_obs_id[5], "A2-2000MS") == 0);
        CHECK(cfg.irq_req_masks == 0x0AAA && cfg.irq_req_set == 0x8000 && cfg.irq_req_clear == 0x7000 && cfg.ack_or == 0x8000 && cfg.stop_or == 0x8AAA);
        gbp_initirqa_config_timebase(&cfg, 81000000u);
        CHECK(cfg.a1_obs_ticks[0] == 4050u && cfg.a2_obs_ticks[5] == 162000000u);
    }
}

/* the write primitive: GBI layouts byte by byte */
static void test_layouts(void)
{
    uint8_t buf[32]; unsigned i;
    struct gbp_mock m; struct gbp_transport t; struct gbp_regwrite_result w; unsigned errors = 0;
    gbp_regwrite_u16_layout(0x8AAE, buf);
    for (i = 0; i < 32; i += 2) CHECK(buf[i] == 0x8A && buf[i + 1] == 0xAE);
    CHECK(buf[0x1E] == 0x8A && buf[0x1F] == 0xAE);                              /* the positions the Start-up Disc writes */
    for (i = 0; i < 32; i += 4) CHECK(((uint32_t)buf[i] << 24 | (uint32_t)buf[i + 1] << 16 | (uint32_t)buf[i + 2] << 8 | buf[i + 3]) == 0x8AAE8AAEu);  /* 8 words of value<<16|value */
    gbp_regwrite_u16_layout(0x0000, buf);
    for (i = 0; i < 32; i++) CHECK(buf[i] == 0x00);
    gbp_regwrite_u16_layout(0x8AAA, buf);
    for (i = 0; i < 32; i += 2) CHECK(buf[i] == 0x8A && buf[i + 1] == 0xAA);
    gbp_regwrite_u16_layout(0x1234, buf);
    for (i = 0; i < 32; i += 2) CHECK(buf[i] == 0x12 && buf[i + 1] == 0x34);
    gbp_regwrite_byte_layout(0x8C, buf);
    for (i = 0; i < 32; i++) CHECK(buf[i] == 0x8C);
    /* not the CONTROL byte replication, not the Disc's single-position style */
    gbp_regwrite_u16_layout(0x8AAE, buf);
    CHECK(buf[0] != buf[1] && buf[0] == buf[2]);
    /* the primitive: address index D offset 0, result fields, no log call needed */
    mock_003a(&m); gbp_mock_transport(&m, &t);
    gbp_regwrite_irq_u16(&t, "tag=T", BASE, 0x8AAE, 0x8AAE, &w, &errors);
    CHECK(w.kind == GBP_REGWRITE_IRQ_U16 && w.attempted && w.completed && w.rc == GBP_OK && w.addr == BASE + (0xDu << 20));
    CHECK(w.before == 0x8AAE && w.value == 0x8AAE && w.t_after == m.tick && errors == 0 && m.irq_writes == 1);
    for (i = 0; i < 32; i += 2) CHECK(w.raw[i] == 0x8A && w.raw[i + 1] == 0xAE);
    CHECK(m.last_irq_write_value == 0x8AAE && m.irq_reg == 0x8AAA);
    gbp_regwrite_control_byte(&t, "tag=C", BASE, 0x8C, &w, &errors);
    CHECK(w.kind == GBP_REGWRITE_CONTROL_BYTE && w.addr == BASE + (4u << 20) && w.value == 0x8C && m.control_byte == 0x8C);
    for (i = 0; i < 32; i++) CHECK(w.raw[i] == 0x8C);
    {
        struct ringlog rl; ringlog_init(&rl, storage, LINE_LEN, LINES);
        gbp_regwrite_log(&rl, &w);
        CHECK(count_lines_with(&rl, "CTLW tag=C addr=01400000 semantic=8c rc=ok") == 1 && count_lines_with(&rl, "layout=gbi-replicated data=8c8c") == 1);
        gbp_regwrite_irq_u16(&t, "tag=X", BASE, 0x8AAA, 0x0000, &w, &errors);
        gbp_regwrite_log(&rl, &w);
        CHECK(count_lines_with(&rl, "IRQW tag=X addr=01d00000 before=8aaa write=0000 layout=gbi-u16-replicated rc=ok") == 1);
        CHECK(count_lines_with(&rl, "data=0000000000000000000000000000000000000000000000000000000000000000") == 1);
        memset(&w, 0, sizeof w);
        gbp_regwrite_log(&rl, &w);                                              /* nothing attempted: nothing logged */
        CHECK(rl.count == 2);
    }
    /* the mock's own model, driven by hand: W1C sources, level masks, bit 15 per mode */
    mock_003a(&m); gbp_mock_transport(&m, &t);
    gbp_regwrite_irq_u16(&t, "tag=T", BASE, 0, 0x0004, &w, &errors);           /* ack source 2; masks and bit 15 written 0 */
    CHECK(m.irq_reg == 0x0000 && (m.intsr & GBP_PI_HSP_BIT) == 0);              /* nothing pending: no line */
    mock_003a(&m); gbp_mock_transport(&m, &t);
    gbp_regwrite_irq_u16(&t, "tag=T", BASE, 0, 0x8000, &w, &errors);           /* masks written 0 → open; bit 15 level 1 */
    CHECK(m.irq_reg == 0x8004);
    gbp_regwrite_irq_u16(&t, "tag=T", BASE, 0, 0x0000, &w, &errors);           /* bit 15 → 0: source 2 propagates */
    CHECK(m.irq_reg == 0x0004 && (m.intsr & GBP_PI_HSP_BIT) != 0 && m.deliveries == 0);   /* masked: visible, not delivered */
}

/* ---- attempted/completed observed at the moment the transport is invoked ----
 * The mock calls write_hook at the entry of write_block; the hook samples the
 * probe's safety state right then — before the write "happens", before rc is
 * known. A flag set after the call, or only on rc == ok, fails here. */
struct call_sample {
    unsigned idx;                                    /* block index written (4 = CONTROL, 0xD = IRQ) */
    int ctl_exp_att, ctl_exp_comp, control_written, pcr;
    int a1_att, a1_comp, a2_att, a2_comp, stop_att, stop_comp, ctl_rest_att, ctl_rest_comp;
    unsigned irq_att, irq_comp;
};
static struct gbp_initirqa_result *hook_res;
static struct call_sample samples[8];
static unsigned nsamples;

static void sample_hook(struct gbp_mock *m, uint32_t addr, const uint8_t *data, void *user)
{
    unsigned idx = (unsigned)((addr - BASE) >> 20) & 0xFu;
    struct call_sample *s;
    (void)m; (void)data; (void)user;
    if (idx != 4u && idx != 0xDu) return;            /* TEST handshake writes are not experimental */
    if (nsamples >= 8u) return;
    s = &samples[nsamples++];
    memset(s, 0, sizeof *s);
    s->idx = idx;
    s->ctl_exp_att = hook_res->w_ctl_exp.attempted; s->ctl_exp_comp = hook_res->w_ctl_exp.completed;
    s->control_written = hook_res->control_written; s->pcr = hook_res->power_cycle_required;
    s->a1_att = hook_res->w_a1.attempted; s->a1_comp = hook_res->w_a1.completed;
    s->a2_att = hook_res->w_a2.attempted; s->a2_comp = hook_res->w_a2.completed;
    s->stop_att = hook_res->w_stop.attempted; s->stop_comp = hook_res->w_stop.completed;
    s->ctl_rest_att = hook_res->w_ctl_restore.attempted; s->ctl_rest_comp = hook_res->w_ctl_restore.completed;
    s->irq_att = hook_res->irq_writes_attempted; s->irq_comp = hook_res->irq_writes_completed;
}

static void run_hooked(struct gbp_mock *m, struct ringlog *rl, struct gbp_initirqa_result *res)
{
    struct gbp_initirqa_config cfg;
    struct gbp_transport t;
    test_config(&cfg);
    m->write_hook = sample_hook;
    hook_res = res;
    nsamples = 0;
    memset(samples, 0, sizeof samples);
    gbp_mock_transport(m, &t);
    ringlog_init(rl, storage, LINE_LEN, LINES);
    gbp_initirqa_probe_run(&t, rl, &cfg, res);
}

static void test_attempted_flags_at_call_time(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    /* nominal: EXP(4), A1(D), A2(D), RESTORE(4), STOP(D) */
    mock_003a(&m);
    run_hooked(&m, &rl, &res);
    CHECK(nsamples == 5);
    CHECK(samples[0].idx == 4 && samples[0].ctl_exp_att == 1 && samples[0].ctl_exp_comp == 0);        /* CONTROL: attempted before, not yet completed */
    CHECK(samples[0].control_written == 1 && samples[0].pcr == 1 && samples[0].irq_att == 0);           /* power cycle already required */
    CHECK(samples[1].idx == 0xD && samples[1].a1_att == 1 && samples[1].a1_comp == 0);                  /* A1 */
    CHECK(samples[1].irq_att == 1 && samples[1].irq_comp == 0 && samples[1].pcr == 1 && samples[1].ctl_exp_comp == 1);
    CHECK(samples[2].idx == 0xD && samples[2].a2_att == 1 && samples[2].a2_comp == 0);                  /* A2 */
    CHECK(samples[2].irq_att == 2 && samples[2].irq_comp == 1 && samples[2].a1_comp == 1);
    CHECK(samples[3].idx == 4 && samples[3].ctl_rest_att == 1 && samples[3].ctl_rest_comp == 0);        /* CONTROL restore */
    CHECK(samples[3].a2_comp == 1 && samples[3].irq_comp == 2 && samples[3].stop_att == 0);
    CHECK(samples[4].idx == 0xD && samples[4].stop_att == 1 && samples[4].stop_comp == 0);              /* STOP */
    CHECK(samples[4].irq_att == 3 && samples[4].irq_comp == 2 && samples[4].pcr == 1 && samples[4].ctl_rest_comp == 1);
    CHECK(res.irq_writes_attempted == 3 && res.irq_writes_completed == 3 && res.uncertain_writes == 0);
    /* A1 returns a timeout: flags were already set when the transport was entered; no A2; teardown attempted */
    mock_003a(&m); m.irq_write_fail_at = 1;
    run_hooked(&m, &rl, &res);
    CHECK(nsamples == 4);                                                                               /* EXP, A1, RESTORE, STOP */
    CHECK(samples[1].idx == 0xD && samples[1].a1_att == 1 && samples[1].a1_comp == 0 && samples[1].irq_att == 1 && samples[1].pcr == 1);
    CHECK(samples[2].idx == 4 && samples[2].a1_att == 1 && samples[2].a1_comp == 0 && samples[2].a2_att == 0 && samples[2].irq_att == 1 && samples[2].irq_comp == 0);
    CHECK(samples[3].idx == 0xD && samples[3].stop_att == 1 && samples[3].irq_att == 2 && samples[3].irq_comp == 0 && samples[3].pcr == 1);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && res.w_a1.attempted == 1 && res.w_a1.completed == 0 && res.w_a2.attempted == 0);
    CHECK(res.power_cycle_required == 1 && res.w_ctl_restore.attempted == 1 && res.w_stop.attempted == 1);
    /* A2 returns a timeout */
    mock_003a(&m); m.irq_write_fail_at = 2;
    run_hooked(&m, &rl, &res);
    CHECK(nsamples == 5);
    CHECK(samples[2].idx == 0xD && samples[2].a2_att == 1 && samples[2].a2_comp == 0 && samples[2].irq_att == 2 && samples[2].irq_comp == 1);
    CHECK(samples[3].idx == 4 && samples[3].a2_att == 1 && samples[3].a2_comp == 0 && samples[3].pcr == 1);
    CHECK(samples[4].idx == 0xD && samples[4].stop_att == 1 && samples[4].irq_att == 3 && samples[4].irq_comp == 1);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && res.w_a2.attempted == 1 && res.w_a2.completed == 0 && res.power_cycle_required == 1);
    /* CONTROL returns a timeout: flags set at entry; no IRQ write at all; restore attempted */
    mock_003a(&m); m.fail_at_op = 12; m.fail_rc = GBP_ERR_TIMEOUT;
    run_hooked(&m, &rl, &res);
    CHECK(nsamples == 2);                                                                               /* EXP, RESTORE */
    CHECK(samples[0].idx == 4 && samples[0].ctl_exp_att == 1 && samples[0].ctl_exp_comp == 0 && samples[0].control_written == 1 && samples[0].pcr == 1);
    CHECK(samples[1].idx == 4 && samples[1].ctl_exp_att == 1 && samples[1].ctl_exp_comp == 0 && samples[1].ctl_rest_att == 1 && samples[1].irq_att == 0 && samples[1].pcr == 1);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && res.w_a1.attempted == 0 && res.w_stop.attempted == 0 && res.power_cycle_required == 1);
    /* STOP returns a timeout: attempted at entry, never completed, the power-cycle flag stays */
    mock_003a(&m); m.irq_write_fail_at = 3;
    run_hooked(&m, &rl, &res);
    CHECK(nsamples == 5 && samples[4].stop_att == 1 && samples[4].stop_comp == 0 && samples[4].irq_att == 3);
    CHECK(res.w_stop.attempted == 1 && res.w_stop.completed == 0 && res.power_cycle_required == 1 && res.uncertain_writes == 1);
    m.write_hook = 0;
}

/* worst-case record widths: the longest status/reason/restore_reason with 10-digit time-base values */
static void test_worst_case_line_lengths(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    mock_003a(&m); m.intmr13_set_after_irq_write = 1;                            /* abort_pi_precondition / intmr13_unmasked_a2pre */
    m.fail_at_op = 29; m.fail_rc = GBP_ERR_TIMEOUT;                              /* IRQSTOPPOST read → irq_stop_readback_failed */
    m.tick = 0xFFFFFF00u; m.intsr = 0x00010000u; m.intmr = 0x000001fau;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQA_ABORT_PI_PRECONDITION && strcmp(res.reason, "intmr13_unmasked_a2pre") == 0);
    CHECK(res.restore_ok == 0 && strcmp(res.restore_reason, "irq_stop_readback_failed") == 0);
    CHECK(rl.truncated == 0 && rl.dropped == 0);
    CHECK(max_line_len(&rl) < LINE_LEN - 1);
    CHECK(count_lines_with(&rl, "INITIRQA end status=abort_pi_precondition reason=intmr13_unmasked_a2pre restore=error restore_reason=irq_stop_readback_failed power_cycle_required=1") == 1);
    CHECK(count_lines_with(&rl, "WRITES control_written=1 irq_attempted=2 irq_completed=2 ctl_exp=1/1 a1=1/1 a2=0/0 stop=1/1 ctl_restore=1/1 uncertain=0 power_cycle_required=1") == 1);
    CHECK(count_lines_with(&rl, "OBSERVED intsr13_seen=") == 1);
}

/* ---- physical fixtures ------------------------------------------------- */
static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb"); long n; char *buf;
    if (!f) return 0;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    buf = (char *)malloc((size_t)n + 1);
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(buf); return 0; }
    buf[n] = '\0'; fclose(f); return buf;
}

/* Physical GBP-attached fixtures (init-0001, initirq-0001): the gate, the
 * PI preconditions, BASE and both shape checks run on the physical bytes;
 * the script is the fixture's own prefix up to its first experimental
 * operation (the CONTROL write of GBP-INIT-001, the handler install of
 * GBP-INIT-002) followed by the fixture's own AR_INFO restore records.
 * operation (the CONTROL write of GBP-INIT-001, the handler install of
 * GBP-INIT-002). GBP-INIT-003A's first experimental write is then
 * unanswered (script exhausted → abort_transport), which proves that
 * nothing before it needed data this hardware did not produce, and that
 * the IRQ register is never written on that path. Every call after that
 * point (CONTROL restore, its readback, the PI check, the AR_INFO
 * restore, FINAL) is likewise unanswered: exactly 8 exhausted calls, no
 * mismatch, the AR_INFO restore reported as failed for that reason only.
 * No GBP-INIT-003A physical data exists and none is appended. */
static void test_hw_gbp_fixture_prefix(const char *path, uint8_t control_byte0)
{
    char *text = read_file(path);
    char *cut_w, *cut_i, *cut, *script;
    struct gbp_replay r; struct gbp_transport t; struct gbp_initirqa_config cfg;
    struct gbp_initirqa_result res; struct ringlog rl;
    unsigned k;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    cut_w = strstr(text, "\nW 01400000");
    cut_i = strstr(text, "\nI i");
    cut = (cut_w && cut_i) ? (cut_w < cut_i ? cut_w : cut_i) : (cut_w ? cut_w : cut_i);
    CHECK(cut != 0);
    if (!cut) { free(text); return; }
    script = (char *)malloc(strlen(text) + 96);
    memcpy(script, text, (size_t)(cut - text));
    script[cut - text] = '\0';
    strcat(script, "\n# --- host test: physical prefix ends here (first experimental operation of the source run) ---\n");
    gbp_replay_init(&r, script);
    gbp_replay_transport(&r, &t);
    gbp_initirqa_config_default(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_initirqa_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.status == GBP_INITIRQA_ABORT_TRANSPORT && strcmp(res.reason, "control_write_failed") == 0);
    CHECK(res.det.verdict == GBP_VERDICT_PRESENT && res.det.vote_ok == 4 && res.det.b1_ok == 4);
    CHECK(res.arinfo_orig == 0x0043 && res.arinfo_exp == 0x005b && res.arinfo_changed == 1);
    CHECK(res.arinfo_final == 0xFFFF && res.arinfo_restore_ok == 0 && res.restore_ok == 0);   /* script exhausted, not physical data */
    CHECK(res.intsr_pre == 0x00010000 && res.intmr_pre == 0x000001fa && res.pi_pre_ok == 1);
    CHECK(res.snap[GBP_INITIRQA_SNAP_BASE].control_vote == 0x90 && res.snap[GBP_INITIRQA_SNAP_BASE].control_b1f == 0x90);
    CHECK(res.snap[GBP_INITIRQA_SNAP_BASE].control[0] == control_byte0);
    for (k = 1; k < GBP_BLOCK_SIZE; k++) CHECK(res.snap[GBP_INITIRQA_SNAP_BASE].control[k] == 0x90);
    CHECK(res.snap[GBP_INITIRQA_SNAP_BASE].irq_disc == 0x8aae && res.snap[GBP_INITIRQA_SNAP_BASE].irq_gbi == 0x8aae);
    CHECK(res.snap[GBP_INITIRQA_SNAP_BASE].has_test && res.snap[GBP_INITIRQA_SNAP_BASE].intmr == 0x000001fa);
    CHECK(res.control_orig == 0x90 && res.control_exp == 0x8c && res.irq_shape_base_ok == 1);
    /* The CONTROL write was issued (the transport was invoked; the replay had no line for it and
     * answered GBP_ERR_BACKEND): attempted=1, completed=0, power cycle required. The IRQ-register
     * write functions were never invoked on this path, so irq_writes_attempted == 0 is the safety
     * state itself (probe counter), not a device-side count. */
    CHECK(res.w_ctl_exp.attempted == 1 && res.w_ctl_exp.completed == 0 && res.control_written == 1 && res.power_cycle_required == 1);
    CHECK(res.irq_writes_attempted == 0 && res.w_a1.attempted == 0 && res.irq_stop_write_ok == -1 && res.uncertain_writes == 2);
    CHECK(res.w_ctl_restore.attempted == 1 && res.w_ctl_restore.completed == 0);   /* teardown attempted, also unanswered */
    CHECK(!res.window_entered);
    CHECK(r.mismatches == 0 && r.exhausted == 8);   /* CTLW exp, CTLW restore, TDCTL, CLEANUPCHK, AR_INFO write, FINAL PI + 2 RAW */
    CHECK(count_lines_with(&rl, "IRQSHAPE tag=BASE disc=8aae gbi=8aae agree=1 masks_ok=1 bit15_ok=1 high_ok=1") == 1);
    CHECK(count_lines_with(&rl, "IRQW") == 0 && count_lines_with(&rl, "CTLW tag=EXP") == 1);
    free(script); free(text);
}

/* Physical no-GBP fixture (init-0001): ABSENT, nothing written, verbatim replay */
static void test_hw_nogbp_fixture(const char *path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_initirqa_config cfg;
    struct gbp_initirqa_result res; struct ringlog rl;
    unsigned k;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    gbp_replay_init(&r, text);
    gbp_replay_transport(&r, &t);
    gbp_initirqa_config_default(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_initirqa_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.status == GBP_INITIRQA_ABORT_NOT_PRESENT && res.det.verdict == GBP_VERDICT_ABSENT);
    CHECK(res.det.run == 4 && res.det.transport_ok == 4 && res.det.vote_ok == 0 && res.det.b1_ok == 0);
    for (k = 0; k < GBP_BLOCK_SIZE; k++) CHECK(res.det.last_resp[k] == 0xc1);
    CHECK(res.control_written == 0 && res.irq_writes_attempted == 0 && res.power_cycle_required == 0);
    CHECK(res.arinfo_restore_ok == 1 && res.arinfo_final == 0x0043);
    CHECK(count_lines_with(&rl, "CTLW") == 0 && count_lines_with(&rl, "SNAP") == 0 && count_lines_with(&rl, "IRQW") == 0);
    CHECK(r.step == 13 && r.exhausted == 0 && r.mismatches == 0);
    free(text);
}

/* ---- modes for the host round trip (tests/host/test_initirqa_replay.py) ---- */
static int dump_log(const char *path)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqa_result res;
    char s[900]; size_t i; FILE *f;
    mock_003a(&m); m.source_assert_after_write = 2; m.source_assert_delay = 300; m.source_assert_bits = 0x0100;
    m.intsr = 0x00010000u; m.intmr = 0x000001fau; m.tick = 1000;
    run(&m, &rl, &res);
    gbp_initirqa_summary(&res, s, sizeof s);
    f = fopen(path, "w");
    if (!f) { fprintf(stderr, "cannot write %s\n", path); return 1; }
    fprintf(f, "# OPENGBP-LOG v1\n# SYNTHETIC: generated by tests/unit/test_gbp_initirqa.c from the host mock (SOURCE_MASK model); NOT physical data\n");
    fprintf(f, "test_id=GBP-INIT-003A\nbuild_id=synthetic\ncommit=none\nsource=host-mock\n");
    fprintf(f, "lines=%u dropped=%u truncated=%u\n# --- records ---\n", (unsigned)rl.count, (unsigned)rl.dropped, (unsigned)rl.truncated);
    for (i = 0; i < rl.count; i++) fprintf(f, "%s\n", ringlog_line(&rl, i));
    fprintf(f, "# --- end --- dropped=%u\n", (unsigned)rl.dropped);
    fclose(f);
    printf("SUMMARY %s\n", s);
    return 0;
}

static int replay_fixture(const char *path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_initirqa_config cfg;
    struct gbp_initirqa_result res; struct ringlog rl; char s[900];
    if (!text) { fprintf(stderr, "cannot read %s\n", path); return 1; }
    gbp_replay_init(&r, text);
    gbp_replay_transport(&r, &t);
    test_config(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_initirqa_probe_run(&t, &rl, &cfg, &res);
    gbp_initirqa_summary(&res, s, sizeof s);
    printf("SUMMARY %s\n", s);
    printf("REPLAY step=%u exhausted=%u mismatches=%u tick_polls=%u timeline=%d log_lines=%u\n", r.step, r.exhausted, r.mismatches,
           r.tick_polls, r.timeline, (unsigned)rl.count);
    free(text);
    return (r.exhausted || r.mismatches) ? 1 : 0;
}

int main(int argc, char **argv)
{
    if (argc == 3 && strcmp(argv[1], "--dump-log") == 0) return dump_log(argv[2]);
    if (argc == 3 && strcmp(argv[1], "--replay") == 0) return replay_fixture(argv[2]);
    test_nominal_no_cause();
    test_cause_after_a2();
    test_cleanup_sticky();
    test_cause_visible_at_a2_0();
    test_bit15_summary();
    test_irq_write_failures();
    test_control_and_arinfo_failures();
    test_irq_shape();
    test_pi_preconditions();
    test_absent_and_inconsistent();
    test_control_shapes();
    test_transport_variants();
    test_line_lengths_and_wrap();
    test_worst_case_line_lengths();
    test_attempted_flags_at_call_time();
    test_layouts();
    if (argc > 3) {
        test_hw_gbp_fixture_prefix(argv[1], 0x98);      /* init-0001: CONTROL 98 90 90 … */
        test_hw_nogbp_fixture(argv[2]);
        test_hw_gbp_fixture_prefix(argv[3], 0x91);      /* initirq-0001: CONTROL 91 90 90 … */
    } else {
        fprintf(stderr, "note: physical fixture paths not given, fixture tests skipped\n");
    }
    printf("test_gbp_initirqa: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
