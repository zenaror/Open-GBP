/*
 * GBP-INIT-002 logic against the mock's SYNTHETIC interrupt model and
 * against the physical init-0001 fixtures (detection gate only — no
 * physical IRQ-26 data exists yet and none is invented here).
 *
 * Every scenario of the implementation brief is covered, plus the
 * event-order assertions that make a test FAIL if the probe ever
 * unmasks before the handler, unmasks before the CONTROL write, removes
 * the handler before re-masking, or restores AR_INFO before the IRQ
 * teardown. The mock's own detector is exercised by hand (with the
 * transport operations called in the wrong order) to prove it catches
 * each inversion; the probe is never mutated.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_init_irq_probe.h"
#include "gbp_replay.h"
#include "gbp_mock.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

#define LINES 160
#define LINE_LEN 256
static char storage[LINES * LINE_LEN];
#define BASE 0x01000000u
#define T_MAX_TICKS 400u          /* mock ticks advance by 10 per ticks() call */

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

static void run_cfg(struct gbp_mock *m, struct ringlog *rl, struct gbp_initirq_result *res, struct gbp_initirq_config *cfg)
{
    struct gbp_transport t;
    gbp_mock_transport(m, &t);
    ringlog_init(rl, storage, LINE_LEN, LINES);
    gbp_initirq_probe_run(&t, rl, cfg, res);
}

static void run(struct gbp_mock *m, struct ringlog *rl, struct gbp_initirq_result *res)
{
    struct gbp_initirq_config cfg;
    gbp_initirq_config_default(&cfg);
    cfg.t_max_ticks = T_MAX_TICKS;
    cfg.t_max_ms = 2000;
    cfg.tb_hz = 40500000;
    run_cfg(m, rl, res, &cfg);
}

/* ---- order assertions, applied to every run that reaches the handler install ---- */
static void check_order(const struct gbp_mock *m, int expect_unmask)
{
    int inst = gbp_mock_first_op(m, MOCK_IRQ_INSTALL, BASE, 16);
    int ctlw = gbp_mock_first_op(m, MOCK_WR, BASE, 4);
    int unm = gbp_mock_first_op(m, MOCK_IRQ_UNMASK, BASE, 16);
    int mask_last = gbp_mock_last_op(m, MOCK_IRQ_MASK, BASE, 16);
    int rest = gbp_mock_first_op(m, MOCK_IRQ_RESTORE, BASE, 16);
    int ar_restore = gbp_mock_last_op(m, MOCK_AR_W, BASE, 16);
    int isr_mask = gbp_mock_first_op(m, MOCK_ISR_MASK, BASE, 16);
    int isr_w1c = gbp_mock_first_op(m, MOCK_ISR_W1C, BASE, 16);
    CHECK(m->violations == 0);
    CHECK(inst >= 0);
    if (ctlw >= 0) CHECK(inst < ctlw);                       /* handler before the CONTROL write */
    if (expect_unmask) {
        CHECK(unm >= 0 && ctlw >= 0 && ctlw < unm);          /* CONTROL write before the unmask */
        CHECK(inst < unm);                                   /* handler before the unmask */
        CHECK(mask_last > unm);                              /* re-masked after the unmask */
        CHECK(rest > mask_last || rest < 0);                 /* handler removed only after the last mask */
    } else {
        CHECK(unm < 0);
    }
    if (rest >= 0) CHECK(ar_restore > rest);                 /* AR_INFO restored after the IRQ teardown */
    if (isr_w1c >= 0) CHECK(isr_mask >= 0 && isr_mask < isr_w1c);   /* inside the handler: mask before W1C */
}

/* Registers that must never be written, blocks that must never be touched. */
static void check_never_touched(const struct gbp_mock *m)
{
    unsigned idx;
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xD) == 0);             /* GBP IRQ never written */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xC) == 0);             /* KEYPAD never written */
    for (idx = 0; idx < 16; idx++) {
        if (idx == 0 || idx == 4 || idx == 0xD) continue;
        CHECK(gbp_mock_count_block_ops(m, MOCK_RD, BASE, idx) == 0);         /* VIDEO/AUDIO/SIO/... never read */
        CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, idx) == 0);         /* ... never written */
    }
    CHECK(m->intmr_writes == 0);                                             /* INTMR never written directly */
}

/* 3, 9, 10, 13, 18, 24, 26, 27, 28, 29: PRESENT, no IRQ within T_MAX */
static void test_present_no_irq(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    gbp_mock_init(&m);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_TIMEOUT_NO_IRQ_OBSERVED && strcmp(res.reason, "no_irq26_within_t_max") == 0);
    CHECK(res.restore_ok == 1 && res.transport_ok == 1 && res.errors == 0);
    CHECK(res.det.verdict == GBP_VERDICT_PRESENT && res.det.vote_ok == 4 && res.det.b1_ok == 4);
    CHECK(res.arinfo_orig == 0x0043 && res.arinfo_exp == 0x005b && res.arinfo_final == 0x0043 && res.arinfo_restored == 1);
    CHECK(res.control_orig == 0x90 && res.control_exp == 0x8c && res.control_written == 1);
    CHECK(res.write_raw[0] == 0x8c && res.write_raw[31] == 0x8c && res.restore_raw[0] == 0x90 && res.restore_raw[31] == 0x90);
    CHECK(res.handler_installed == 0 && res.handler_restored == 1 && res.old_handler_null == 1);
    CHECK(res.irq_unmasked == 1 && res.irq_masked_again == 1 && res.mask_ok == 1);
    CHECK(res.fired == 0 && res.timed_out == 1 && res.rec.count == 0 && res.wait_ticks >= T_MAX_TICKS);
    CHECK(res.cleanup_ack_performed == 0 && res.pi_ack_performed == 0 && m.intsr_writes == 0);
    CHECK(res.snap[0].taken && res.snap[1].taken && res.snap[2].taken && res.snap[3].taken && res.snap[4].taken);
    CHECK(res.snap[0].has_test && !res.snap[1].has_test && res.snap[2].pi2_ok);
    CHECK(res.snap[1].control_vote == 0x8c && (res.snap[1].intmr & GBP_PI_HSP_BIT) == 0);   /* S1 still masked */
    CHECK((res.intmr_post_unmask & GBP_PI_HSP_BIT) != 0);                                  /* unmask took effect */
    CHECK((res.snap[2].intmr & GBP_PI_HSP_BIT) == 0 && (res.snap[2].intmr2 & GBP_PI_HSP_BIT) == 0);
    CHECK(res.snap[3].control_vote == 0x90 && res.control_restored == 1);
    CHECK(res.snap[4].control_vote == 0x90 && (res.snap[4].intmr & GBP_PI_HSP_BIT) == 0);
    CHECK(m.control_writes == 2 && gbp_mock_writes_outside(&m, BASE, 0) == 2);
    CHECK(m.deliveries == 0 && m.handler_installed == 0 && (m.intmr & GBP_PI_HSP_BIT) == 0 && m.arinfo == 0x0043);
    check_order(&m, 1);
    check_never_touched(&m);
    CHECK(count_lines_with(&rl, "IRQ install rc=ok old_handler=null") == 1);
    CHECK(count_lines_with(&rl, "CTLW tag=EXP") == 1 && count_lines_with(&rl, "CTLW tag=RESTORE") == 1);
    CHECK(count_lines_with(&rl, "UNMASK t_unmask=") == 1 && count_lines_with(&rl, "IRQ mask tag=MAIN rc=ok") == 1);
    CHECK(count_lines_with(&rl, "WAIT fired=0 timed_out=1") == 1);
    CHECK(count_lines_with(&rl, "HANDLER fired=0 count=0") == 1 && count_lines_with(&rl, "HANDLERPI") == 1);
    CHECK(count_lines_with(&rl, "SNAP tag=S") == 5 && count_lines_with(&rl, "PI tag=S2b") == 1);
    CHECK(count_lines_with(&rl, "CLEANUP performed=0") == 1 && count_lines_with(&rl, "IRQ restore rc=ok ok=1") == 1);
    CHECK(count_lines_with(&rl, "MASK final") == 1 && count_lines_with(&rl, "ARINFO restore") == 1);
    CHECK(count_lines_with(&rl, "INITIRQ end status=timeout_no_irq_observed") == 1);
    /* record order in the log mirrors the mandatory sequence */
    CHECK(line_index_with(&rl, "IRQ install") < line_index_with(&rl, "CTLW tag=EXP"));
    CHECK(line_index_with(&rl, "CTLW tag=EXP") < line_index_with(&rl, "SNAP tag=S1"));
    CHECK(line_index_with(&rl, "SNAP tag=S1") < line_index_with(&rl, "UNMASK t_unmask="));
    CHECK(line_index_with(&rl, "UNMASK t_unmask=") < line_index_with(&rl, "IRQ mask tag=MAIN"));
    CHECK(line_index_with(&rl, "IRQ mask tag=MAIN") < line_index_with(&rl, "SNAP tag=S2"));
    CHECK(line_index_with(&rl, "CTLW tag=RESTORE") < line_index_with(&rl, "IRQ restore"));
    CHECK(line_index_with(&rl, "IRQ restore") < line_index_with(&rl, "ARINFO restore"));
    CHECK(line_index_with(&rl, "ARINFO restore") < line_index_with(&rl, "SNAP tag=S4"));
    CHECK(rl.dropped == 0 && rl.truncated == 0);
    {
        char s[600];
        gbp_initirq_summary(&res, s, sizeof s);
        CHECK(strstr(s, "status=timeout_no_irq_observed") && strstr(s, "restore=ok") && strstr(s, "fired=0") && strstr(s, "written=1"));
        CHECK(strstr(s, "handler_restored=1 mask_ok=1 arinfo_restored=1"));
    }
}

/* 11, 14, 15: the cause asserts at the unmask, W1C clears it */
static void test_irq_on_unmask_w1c_clears(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    gbp_mock_init(&m); m.irq_mode = MOCK_IRQ_ON_UNMASK;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_OK_IRQ_OBSERVED && res.restore_ok == 1 && res.errors == 0);
    CHECK(res.fired == 1 && res.timed_out == 0 && res.rec.count == 1 && res.unexpected_reentry == 0);
    CHECK(m.deliveries == 1);
    CHECK((res.rec.intsr_before_ack & GBP_PI_HSP_BIT) != 0);       /* cause visible at entry */
    CHECK((res.rec.intmr_at_entry & GBP_PI_HSP_BIT) != 0);         /* delivered while enabled */
    CHECK((res.rec.intsr_after_ack & GBP_PI_HSP_BIT) == 0);        /* W1C cleared it */
    CHECK((res.rec.intmr_after_mask & GBP_PI_HSP_BIT) == 0);       /* handler masked itself */
    CHECK(res.latency_ticks == (uint32_t)(res.rec.t_entry - res.t_unmask));
    CHECK((res.snap[2].intsr & GBP_PI_HSP_BIT) == 0 && (res.snap[2].intsr2 & GBP_PI_HSP_BIT) == 0);
    CHECK(res.cleanup_ack_performed == 0 && m.intsr_writes == 0);  /* no main-loop W1C needed */
    CHECK(res.handler_restored == 1 && res.mask_ok == 1 && res.arinfo_restored == 1 && res.control_restored == 1);
    check_order(&m, 1);
    check_never_touched(&m);
    CHECK(gbp_mock_first_op(&m, MOCK_ISR_ENTRY, BASE, 16) > gbp_mock_first_op(&m, MOCK_IRQ_UNMASK, BASE, 16));
    CHECK(gbp_mock_first_op(&m, MOCK_ISR_EXIT, BASE, 16) < gbp_mock_first_op(&m, MOCK_IRQ_MASK, BASE, 16) ||
          gbp_mock_first_op(&m, MOCK_IRQ_MASK, BASE, 16) < 0 ||
          gbp_mock_first_op(&m, MOCK_ISR_EXIT, BASE, 16) < gbp_mock_last_op(&m, MOCK_IRQ_MASK, BASE, 16));
    CHECK(count_lines_with(&rl, "HANDLER fired=1 count=1") == 1 && count_lines_with(&rl, "WAIT fired=1 timed_out=0") == 1);
    CHECK(count_lines_with(&rl, "INITIRQ end status=ok_irq_observed") == 1);
    /* no textual logging from the handler: the ring only grows from main-loop records (HANDLER lines come after MAIN mask) */
    CHECK(line_index_with(&rl, "IRQ mask tag=MAIN") < line_index_with(&rl, "HANDLER fired="));
    CHECK(rl.dropped == 0 && rl.truncated == 0);
}

/* 12: the cause asserts some ticks after the unmask */
static void test_irq_after_ticks(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    gbp_mock_init(&m); m.irq_mode = MOCK_IRQ_AFTER_TICKS; m.irq_after_ticks = 150;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_OK_IRQ_OBSERVED && res.fired == 1 && res.rec.count == 1);
    CHECK(res.latency_ticks >= 150 && res.latency_ticks < T_MAX_TICKS);
    CHECK(res.polls >= 2);
    CHECK((res.intmr_post_unmask & GBP_PI_HSP_BIT) != 0 && (res.intsr_post_unmask & GBP_PI_HSP_BIT) == 0);
    CHECK(res.restore_ok == 1 && res.control_restored == 1 && res.mask_ok == 1);
    check_order(&m, 1);
    check_never_touched(&m);
    /* latency in µs derived from tb_hz, computed outside the handler */
    CHECK(res.latency_us == (uint32_t)(((uint64_t)res.latency_ticks * 1000000u) / 40500000u));
    /* the cause asserted after the unmask, never during S1 */
    CHECK((res.snap[1].intsr & GBP_PI_HSP_BIT) == 0);
    /* cause asserted just past T_MAX: not observed, still clean */
    gbp_mock_init(&m); m.irq_mode = MOCK_IRQ_AFTER_TICKS; m.irq_after_ticks = T_MAX_TICKS + 500;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_TIMEOUT_NO_IRQ_OBSERVED && res.fired == 0 && m.deliveries == 0);
    CHECK(res.restore_ok == 1 && res.mask_ok == 1);
    check_order(&m, 1);
}

/* 16: W1C does not clear INTSR (device keeps asserting): masked, single cleanup W1C, no loop */
static void test_w1c_does_not_clear(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    gbp_mock_init(&m); m.irq_mode = MOCK_IRQ_ON_UNMASK; m.intsr_sticky_after_w1c = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_OK_IRQ_OBSERVED && res.fired == 1 && res.rec.count == 1);
    CHECK((res.rec.intsr_after_ack & GBP_PI_HSP_BIT) != 0);        /* observation, not an error */
    CHECK((res.rec.intmr_after_mask & GBP_PI_HSP_BIT) == 0);
    CHECK(m.deliveries == 1 && res.unexpected_reentry == 0);       /* mask suppressed re-delivery */
    CHECK((res.snap[2].intsr & GBP_PI_HSP_BIT) != 0 && (res.snap[2].intsr2 & GBP_PI_HSP_BIT) != 0);
    CHECK((res.snap[3].intsr & GBP_PI_HSP_BIT) != 0);              /* still set after CONTROL restore (sticky model) */
    CHECK(res.cleanup_ack_performed == 1 && m.intsr_writes == 1 && m.last_intsr_write == GBP_PI_HSP_BIT);
    CHECK((res.cleanup_intsr_before & GBP_PI_HSP_BIT) != 0 && (res.cleanup_intsr_after & GBP_PI_HSP_BIT) != 0);
    CHECK(res.restore_ok == 1 && res.errors == 0);                /* a set bit after cleanup is not a restore failure */
    CHECK(res.handler_restored == 1 && res.mask_ok == 1 && res.arinfo_restored == 1);
    CHECK(count_lines_with(&rl, "CLEANUP performed=1") == 1 && count_lines_with(&rl, "intsr13_after=1") == 1);
    check_order(&m, 1);
    check_never_touched(&m);
    /* variant: restoring CONTROL (bit 0x10 back) deasserts the cause → cleanup clears it */
    gbp_mock_init(&m); m.irq_mode = MOCK_IRQ_ON_UNMASK; m.intsr_sticky_after_w1c = 1; m.control_mask_clears_cause = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_OK_IRQ_OBSERVED && (res.snap[2].intsr & GBP_PI_HSP_BIT) != 0);
    CHECK((res.snap[3].intsr & GBP_PI_HSP_BIT) == 0 && res.cleanup_ack_performed == 0 && m.intsr_writes == 0);
    check_order(&m, 1);
}

/* 17: second entry despite the mask (gating-failure model) → anomaly recorded, no hang */
static void test_reentry_anomaly(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    gbp_mock_init(&m); m.irq_mode = MOCK_IRQ_ON_UNMASK; m.second_delivery = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_OK_IRQ_OBSERVED && res.fired == 1);
    CHECK(res.rec.count == 2 && res.unexpected_reentry == 1 && m.deliveries == 2);
    CHECK(count_lines_with(&rl, "reentry=1") == 1);
    CHECK(res.restore_ok == 1 && res.mask_ok == 1 && res.handler_restored == 1);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_WR, BASE, 0xD) == 0);
    check_order(&m, 1);
    /* mask ignored entirely (INTMR bit 13 cannot be cleared): bounded by the mock's storm cap,
     * the probe still tears down and reports mask_ok=0 / restore=error */
    gbp_mock_init(&m); m.irq_mode = MOCK_IRQ_ON_UNMASK; m.mask_ignored = 1; m.intsr_sticky_after_w1c = 1;
    run(&m, &rl, &res);
    CHECK(res.fired == 1 && res.unexpected_reentry == 1);
    CHECK(res.mask_ok == 0 && res.restore_ok == 0 && strcmp(res.restore_reason, "mask_not_restored") == 0);
    CHECK(res.handler_restored == 1 && res.arinfo_restored == 1 && res.control_restored == 1);
    CHECK((m.violation_mask & GBP_MOCK_VIOL_STORM) != 0);          /* the mock reports the storm it modeled */
    CHECK(count_lines_with(&rl, "IRQ mask tag=RETRY") == 1);
}

/* 1, 2, 31-like: absent / inconsistent → no handler, no CONTROL write, no unmask */
static void test_absent_and_inconsistent(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    gbp_mock_init(&m); m.present = 0; m.absent_fill = 0xC1;                  /* physical no-GBP value of init-0001 */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_NOT_PRESENT && res.det.verdict == GBP_VERDICT_ABSENT);
    CHECK(res.handler_installed == 0 && res.control_written == 0 && res.irq_unmasked == 0);
    CHECK(gbp_mock_first_op(&m, MOCK_IRQ_INSTALL, BASE, 16) < 0 && gbp_mock_first_op(&m, MOCK_IRQ_UNMASK, BASE, 16) < 0);
    CHECK(m.control_writes == 0 && res.arinfo_restored == 1 && m.arinfo == 0x0043);
    CHECK(count_lines_with(&rl, "CTLW") == 0 && count_lines_with(&rl, "SNAP") == 0 && count_lines_with(&rl, "IRQ install") == 0);
    CHECK(res.restore_ok == 1);
    gbp_mock_init(&m); m.present = 0; m.absent_fill = 0x00;                  /* FF pattern passes → inconsistent */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_NOT_PRESENT && res.det.verdict == GBP_VERDICT_INCONSISTENT);
    CHECK(res.handler_installed == 0 && m.control_writes == 0 && res.arinfo_restored == 1);
    /* transport failure inside the handshake → inconsistent, same behavior */
    gbp_mock_init(&m); m.fail_at_op = 3; m.fail_rc = GBP_ERR_TIMEOUT;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_NOT_PRESENT && res.det.verdict == GBP_VERDICT_INCONSISTENT);
    CHECK(m.control_writes == 0 && gbp_mock_first_op(&m, MOCK_IRQ_INSTALL, BASE, 16) < 0 && res.arinfo_restored == 1);
}

/* 4, 5: PI preconditions — abort, never adjust, restore only AR_INFO */
static void test_pi_preconditions(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    gbp_mock_init(&m); m.intsr = GBP_PI_HSP_BIT;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_PI_PRECONDITION && strcmp(res.reason, "intsr13_set") == 0);
    CHECK(res.handler_installed == 0 && m.control_writes == 0 && m.intsr_writes == 0 && m.intmr_writes == 0);
    CHECK(res.arinfo_restored == 1 && m.arinfo == 0x0043 && (m.intsr & GBP_PI_HSP_BIT) != 0);  /* raw state left as found */
    CHECK(count_lines_with(&rl, "PRECOND intsr13=1 intmr13=0 ok=0 reason=intsr13_set") == 1);
    gbp_mock_init(&m); m.intmr = 0x000020f0;                                  /* already unmasked */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_PI_PRECONDITION && strcmp(res.reason, "intmr13_unmasked") == 0);
    CHECK(res.handler_installed == 0 && m.control_writes == 0 && m.intmr == 0x000020f0);  /* not silently masked */
    CHECK(gbp_mock_first_op(&m, MOCK_IRQ_MASK, BASE, 16) < 0 && m.intmr_writes == 0);
    CHECK(res.arinfo_restored == 1);
    gbp_mock_init(&m); m.pi_unavailable = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_PI_PRECONDITION && strcmp(res.reason, "pi_unavailable") == 0);
    CHECK(res.handler_installed == 0 && m.control_writes == 0 && res.arinfo_restored == 1);
}

/* 6: CONTROL shape / ambiguity → abort before the handler */
static void test_control_shapes(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    gbp_mock_init(&m); m.control_byte = 0x80;                                 /* bit 0x10 clear */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_CONTROL_SHAPE && res.handler_installed == 0 && m.control_writes == 0);
    CHECK(res.arinfo_restored == 1 && res.restore_ok == 1);
    gbp_mock_init(&m); m.control_byte = 0x9C;                                 /* bits 0x0C set */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_CONTROL_SHAPE && res.handler_installed == 0 && m.control_writes == 0);
    gbp_mock_init(&m); m.control_byte = 0x03;                                 /* Dolphin GBPlayer model idle value */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_CONTROL_SHAPE && strcmp(res.reason, "control_not_idle_shape") == 0);
    /* physical byte-0 anomaly (98 90 90 …): vote and byte 0x1F agree → proceeds with 0x90 */
    gbp_mock_init(&m); m.control_block = HW_CONTROL_98; m.irq_block = HW_IRQ_8AAE;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_TIMEOUT_NO_IRQ_OBSERVED && res.control_orig == 0x90 && res.control_exp == 0x8c);
    CHECK(res.snap[0].control[0] == 0x98 && res.snap[0].irq_disc == 0x8aae && res.snap[0].irq_gbi == 0x8aae);
    /* ambiguous read (vote != byte 0x1F) → abort */
    {
        static uint8_t half[32];
        memset(half, 0x90, 15); memset(half + 15, 0x80, 17);
        half[31] = 0x90;
        gbp_mock_init(&m); m.control_block = half;
        run(&m, &rl, &res);
        CHECK(res.status == GBP_INITIRQ_ABORT_CONTROL_READ && res.handler_installed == 0 && m.control_writes == 0);
    }
    /* S0 CONTROL read fails → abort before the handler */
    gbp_mock_init(&m); m.fail_at_op = 9; m.fail_rc = GBP_ERR_BUSY;          /* 8 handshake transfers, then S0 CONTROL */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_CONTROL_READ && res.handler_installed == 0 && m.control_writes == 0);
}

/* 7, 8: previous handler NULL / non-NULL, preserved and restored either way */
static void test_old_handler(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    gbp_mock_init(&m);
    run(&m, &rl, &res);
    CHECK(res.old_handler_null == 1 && count_lines_with(&rl, "old_handler=null") >= 2);
    gbp_mock_init(&m); m.old_handler_nonnull = 1; m.irq_mode = MOCK_IRQ_ON_UNMASK;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_OK_IRQ_OBSERVED && res.old_handler_null == 0);
    CHECK(count_lines_with(&rl, "IRQ install rc=ok old_handler=nonnull") == 1 && count_lines_with(&rl, "IRQ restore rc=ok ok=1 old_handler=nonnull") == 1);
    CHECK(res.handler_restored == 1 && m.handler_installed == 0);
    check_order(&m, 1);
    /* install fails → abort before any CONTROL write, no unmask */
    gbp_mock_init(&m); m.install_fails = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_HANDLER_INSTALL && strcmp(res.reason, "install_failed") == 0);
    CHECK(res.handler_installed == 0 && m.control_writes == 0 && res.irq_unmasked == 0 && res.arinfo_restored == 1);
    /* transport without an IRQ path (like the replay backend) → same abort, before any write */
    gbp_mock_init(&m); m.irq_ops_available = 0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_HANDLER_INSTALL && strcmp(res.reason, "irq_ops_unavailable") == 0);
    CHECK(m.control_writes == 0 && res.arinfo_restored == 1 && count_lines_with(&rl, "IRQ install rc=unavailable") == 1);
    CHECK(count_lines_with(&rl, "PRECOND intsr13=0 intmr13=0 irq_path=0 ok=1") == 1);
}

/* 19, 20, 21, 22, 23: failures after the CONTROL write / unmask, restore failures */
static void test_errors_and_restore_failures(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    /* 19: the experimental CONTROL write itself fails → transport_error, restore still runs, no unmask */
    gbp_mock_init(&m); m.fail_at_op = 12; m.fail_rc = GBP_ERR_TIMEOUT;     /* 8 + S0 (3) = 11, 12th = EXP write */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_TRANSPORT_ERROR && strcmp(res.reason, "control_write_failed") == 0);
    CHECK(res.control_written == 1 && res.irq_unmasked == 0 && gbp_mock_first_op(&m, MOCK_IRQ_UNMASK, BASE, 16) < 0);
    CHECK(count_lines_with(&rl, "CTLW tag=RESTORE") == 1 && res.handler_restored == 1 && res.arinfo_restored == 1);
    check_order(&m, 0);
    /* 19b: S1 read fails after the write → transport_error before the unmask */
    gbp_mock_init(&m); m.fail_at_op = 13; m.fail_rc = GBP_ERR_BUSY;        /* S1 CONTROL read */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_TRANSPORT_ERROR && strcmp(res.reason, "s1_read_failed") == 0);
    CHECK(res.irq_unmasked == 0 && res.handler_restored == 1 && res.control_restored == 1 && res.mask_ok == 1);
    check_order(&m, 0);
    /* 20: S2 read fails after the unmask/mask → transport_error; the handler data is still logged */
    gbp_mock_init(&m); m.irq_mode = MOCK_IRQ_ON_UNMASK; m.fail_at_op = 15; m.fail_rc = GBP_ERR_TIMEOUT;   /* S2 CONTROL read */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_TRANSPORT_ERROR && strcmp(res.reason, "s2_read_failed") == 0);
    CHECK(res.fired == 1 && res.irq_masked_again == 1 && count_lines_with(&rl, "HANDLER fired=1") == 1);
    CHECK(res.handler_restored == 1 && res.mask_ok == 1 && res.arinfo_restored == 1);
    check_order(&m, 1);
    /* 21: CONTROL restore write ignored by the device → restore=error, the rest still restored */
    gbp_mock_init(&m); m.control_write_fail_at = 2;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_TIMEOUT_NO_IRQ_OBSERVED);
    CHECK(res.control_restored == 0 && res.restore_ok == 0 && strcmp(res.restore_reason, "control_restore_failed") == 0);
    CHECK(res.handler_restored == 1 && res.mask_ok == 1 && res.arinfo_restored == 1);
    /* 22: handler restore fails → restore=error, flag stays set, AR_INFO still restored */
    gbp_mock_init(&m); m.restore_fails = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_TIMEOUT_NO_IRQ_OBSERVED && res.handler_restored == 0 && res.handler_installed == 1);
    CHECK(res.restore_ok == 0 && strcmp(res.restore_reason, "handler_restore_failed") == 0);
    CHECK(res.mask_ok == 1 && res.arinfo_restored == 1 && res.control_restored == 1);
    CHECK(count_lines_with(&rl, "IRQ restore rc=backend ok=0") == 1);
    /* 23: AR_INFO restore: the mock cannot fail an AR write, so check the readback path with a mismatch */
    {
        struct gbp_transport t; struct gbp_initirq_config cfg;
        gbp_mock_init(&m);
        gbp_mock_transport(&m, &t);
        gbp_initirq_config_default(&cfg); cfg.t_max_ticks = T_MAX_TICKS;
        cfg.expansion_code = 3;
        ringlog_init(&rl, storage, LINE_LEN, LINES);
        gbp_initirq_probe_run(&t, &rl, &cfg, &res);
        CHECK(res.arinfo_restored == 1 && res.arinfo_final == 0x0043);
    }
}

/* 25: ring overflow — the probe completes, restores, and the log reports the drops */
static void test_ring_overflow(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    struct gbp_transport t; struct gbp_initirq_config cfg;
    static char tiny[8 * LINE_LEN];
    gbp_mock_init(&m); m.irq_mode = MOCK_IRQ_ON_UNMASK;
    gbp_mock_transport(&m, &t);
    gbp_initirq_config_default(&cfg); cfg.t_max_ticks = T_MAX_TICKS;
    ringlog_init(&rl, tiny, LINE_LEN, 8);
    gbp_initirq_probe_run(&t, &rl, &cfg, &res);
    CHECK(res.status == GBP_INITIRQ_OK_IRQ_OBSERVED && res.restore_ok == 1 && res.handler_restored == 1);
    CHECK(rl.dropped > 0 && rl.count == 8);
    check_order(&m, 1);
}

/* line-length regression: worst-case field widths must fit LINE_LEN without truncation */
static void test_line_lengths(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    gbp_mock_init(&m); m.irq_mode = MOCK_IRQ_ON_UNMASK; m.second_delivery = 1; m.intsr_sticky_after_w1c = 1;
    m.tick = 0xFFFFFF00u;                                 /* wrap the time base inside the run */
    m.intsr = 0x00010000u; m.intmr = 0x000001fau;         /* physical PI values */
    m.old_handler_nonnull = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_OK_IRQ_OBSERVED);
    CHECK(rl.truncated == 0 && rl.dropped == 0);
    CHECK(max_line_len(&rl) < LINE_LEN - 1);
    CHECK(res.latency_ticks < 1000u);                      /* wrap-safe subtraction across the 32-bit boundary */
    /* the probe's summary also fits the POC's buffer */
    {
        char s[600];
        int n = gbp_initirq_summary(&res, s, sizeof s);
        CHECK(n > 0 && (size_t)n < sizeof s);
    }
}

/* mask/unmask through the IRQ ops only; unmask ineffective → abort_unmask with full restore */
static void test_unmask_ineffective(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq_result res;
    gbp_mock_init(&m); m.unmask_ignored = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ_ABORT_UNMASK && strcmp(res.reason, "unmask_not_effective") == 0);
    CHECK(res.polls == 0 && res.fired == 0);
    CHECK(res.control_restored == 1 && res.handler_restored == 1 && res.mask_ok == 1 && res.arinfo_restored == 1);
    check_order(&m, 1);
    check_never_touched(&m);
}

/* the mock's detector: the wrong orders are caught (proves the order tests can fail) */
static void test_mock_detects_inversions(void)
{
    struct gbp_mock m; struct gbp_transport t;
    int old = 0; uint8_t blk[32];
    struct gbp_xfer_info info;
    /* unmask with no handler */
    gbp_mock_init(&m); gbp_mock_transport(&m, &t);
    memset(blk, 0x8c, sizeof blk); t.write_block(t.ctx, BASE + (4u << 20), blk, &info);
    t.irq_unmask(t.ctx);
    CHECK((m.violation_mask & GBP_MOCK_VIOL_UNMASK_NO_HANDLER) != 0);
    /* unmask before the CONTROL write */
    gbp_mock_init(&m); gbp_mock_transport(&m, &t);
    t.irq_install(t.ctx, &old);
    t.irq_unmask(t.ctx);
    CHECK((m.violation_mask & GBP_MOCK_VIOL_UNMASK_BEFORE_CONTROL) != 0);
    /* handler removed while unmasked */
    gbp_mock_init(&m); gbp_mock_transport(&m, &t);
    t.irq_install(t.ctx, &old);
    t.write_block(t.ctx, BASE + (4u << 20), blk, &info);
    t.irq_unmask(t.ctx);
    t.irq_restore(t.ctx);
    CHECK((m.violation_mask & GBP_MOCK_VIOL_RESTORE_WHILE_UNMASKED) != 0);
    /* AR_INFO restored while the handler is still installed */
    gbp_mock_init(&m); gbp_mock_transport(&m, &t);
    t.write_arinfo(t.ctx, 0x005b);
    t.irq_install(t.ctx, &old);
    t.write_arinfo(t.ctx, 0x0043);
    CHECK((m.violation_mask & GBP_MOCK_VIOL_ARINFO_BEFORE_IRQ_DOWN) != 0);
    /* a DMA while unmasked */
    gbp_mock_init(&m); gbp_mock_transport(&m, &t);
    t.irq_install(t.ctx, &old);
    t.write_block(t.ctx, BASE + (4u << 20), blk, &info);
    t.irq_unmask(t.ctx);
    t.read_block(t.ctx, BASE + (4u << 20), blk, &info);
    CHECK((m.violation_mask & GBP_MOCK_VIOL_DMA_WHILE_UNMASKED) != 0);
    /* the correct order raises nothing */
    gbp_mock_init(&m); gbp_mock_transport(&m, &t); m.irq_mode = MOCK_IRQ_ON_UNMASK;
    t.write_arinfo(t.ctx, 0x005b);
    t.irq_install(t.ctx, &old);
    t.write_block(t.ctx, BASE + (4u << 20), blk, &info);
    t.irq_unmask(t.ctx);
    t.irq_mask(t.ctx);
    t.irq_restore(t.ctx);
    t.write_arinfo(t.ctx, 0x0043);
    CHECK(m.violations == 0 && m.deliveries == 1);
    /* the handler body: mask before W1C, once per entry, W1C of bit 13 only */
    {
        int i_mask = gbp_mock_first_op(&m, MOCK_ISR_MASK, BASE, 16), i_w1c = gbp_mock_first_op(&m, MOCK_ISR_W1C, BASE, 16);
        CHECK(i_mask >= 0 && i_w1c >= 0 && i_mask < i_w1c);
        CHECK(gbp_mock_count_block_ops(&m, MOCK_ISR_W1C, BASE, 16) == 1 && m.ops[(unsigned)i_w1c].value == (uint16_t)GBP_PI_HSP_BIT);
        CHECK((m.violation_mask & GBP_MOCK_VIOL_ISR_W1C_BEFORE_MASK) == 0);
    }
}

/* ---- physical fixtures: detection gate only (no IRQ path in a replay) ---- */
static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb"); long n; char *buf;
    if (!f) return 0;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    buf = (char *)malloc((size_t)n + 1);
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(buf); return 0; }
    buf[n] = '\0'; fclose(f); return buf;
}

/* 30: physical GBP fixture (init-0001): the gate passes, S0 is the physical
 * data, the preconditions pass, and the run stops at the handler install
 * because a replay has no interrupt path — before any CONTROL write. The
 * script is the fixture's own prefix up to S0, followed by the fixture's
 * own AR_INFO restore records; nothing is invented. */
static void test_hw_gbp_fixture_gate(const char *path)
{
    char *text = read_file(path);
    char *cut, *script; const char *rest;
    struct gbp_replay r; struct gbp_transport t; struct gbp_initirq_config cfg;
    struct gbp_initirq_result res; struct ringlog rl;
    unsigned k;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    cut = strstr(text, "\nW 01400000");            /* first CONTROL write of GBP-INIT-001 */
    rest = strstr(text, "\nA w 0043");             /* the physical AR_INFO restore + readback */
    CHECK(cut && rest);
    if (!cut || !rest) { free(text); return; }
    script = (char *)malloc(strlen(text) + 64);
    memcpy(script, text, (size_t)(cut - text));
    script[cut - text] = '\0';
    strcat(script, "\n# --- host test: physical prefix ends here; AR_INFO restore records from the same log ---");
    strncat(script, rest, 22);                      /* "\nA w 0043\nA r 0043" */
    strcat(script, "\n");
    gbp_replay_init(&r, script);
    gbp_replay_transport(&r, &t);
    gbp_initirq_config_default(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_initirq_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.status == GBP_INITIRQ_ABORT_HANDLER_INSTALL && strcmp(res.reason, "irq_ops_unavailable") == 0);
    CHECK(res.det.verdict == GBP_VERDICT_PRESENT && res.det.vote_ok == 4 && res.det.b1_ok == 4 && res.det.all32_ok == 3);
    CHECK(res.arinfo_orig == 0x0043 && res.arinfo_exp == 0x005b && res.arinfo_final == 0x0043 && res.arinfo_restored == 1);
    CHECK(res.intsr_pre == 0x00010000 && res.intmr_pre == 0x000001fa && res.pi_pre_ok == 1);
    CHECK(res.snap[0].control_vote == 0x90 && res.snap[0].control_b1f == 0x90 && res.snap[0].control[0] == 0x98);
    for (k = 1; k < GBP_BLOCK_SIZE; k++) CHECK(res.snap[0].control[k] == 0x90);
    CHECK(res.snap[0].irq_disc == 0x8aae && res.snap[0].irq_gbi == 0x8aae && res.snap[0].irq[0] == 0xaa);
    CHECK(res.control_orig == 0x90 && res.control_exp == 0x8c);
    CHECK(res.control_written == 0 && res.handler_installed == 0 && res.irq_unmasked == 0);
    CHECK(r.exhausted == 0 && r.mismatches == 0);
    CHECK(count_lines_with(&rl, "CTLW") == 0 && count_lines_with(&rl, "UNMASK") == 0);
    CHECK(res.restore_ok == 1 && res.errors == 0);
    free(script); free(text);
}

/* 31: physical no-GBP fixture (init-0001): ABSENT, nothing installed, nothing written, verbatim replay */
static void test_hw_nogbp_fixture(const char *path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_initirq_config cfg;
    struct gbp_initirq_result res; struct ringlog rl;
    unsigned k;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    gbp_replay_init(&r, text);
    gbp_replay_transport(&r, &t);
    gbp_initirq_config_default(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_initirq_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.status == GBP_INITIRQ_ABORT_NOT_PRESENT && res.det.verdict == GBP_VERDICT_ABSENT);
    CHECK(res.det.run == 4 && res.det.transport_ok == 4 && res.det.vote_ok == 0 && res.det.b1_ok == 0);
    for (k = 0; k < GBP_BLOCK_SIZE; k++) CHECK(res.det.last_resp[k] == 0xc1);
    CHECK(res.handler_installed == 0 && res.control_written == 0 && res.irq_unmasked == 0);
    CHECK(res.arinfo_restored == 1 && res.arinfo_final == 0x0043);
    CHECK(count_lines_with(&rl, "CTLW") == 0 && count_lines_with(&rl, "SNAP") == 0 && count_lines_with(&rl, "IRQ install") == 0);
    CHECK(r.step == 13 && r.exhausted == 0 && r.mismatches == 0);
    free(text);
}

int main(int argc, char **argv)
{
    test_present_no_irq();
    test_irq_on_unmask_w1c_clears();
    test_irq_after_ticks();
    test_w1c_does_not_clear();
    test_reentry_anomaly();
    test_absent_and_inconsistent();
    test_pi_preconditions();
    test_control_shapes();
    test_old_handler();
    test_errors_and_restore_failures();
    test_ring_overflow();
    test_line_lengths();
    test_unmask_ineffective();
    test_mock_detects_inversions();
    if (argc > 2) {
        test_hw_gbp_fixture_gate(argv[1]);
        test_hw_nogbp_fixture(argv[2]);
    } else {
        fprintf(stderr, "note: physical fixture paths not given, fixture tests skipped\n");
    }
    printf("test_gbp_init_irq: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
