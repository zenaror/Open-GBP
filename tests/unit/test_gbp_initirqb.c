/*
 * GBP-INIT-003B logic (delivery of a latched HSP cause to the CPU) against
 * the mock's SYNTHETIC models: the source/mask IRQ register, the PI cause
 * latch with optional re-latch, and the delivery engine that runs the
 * extended one-shot handler body (gbp_irq_oneshot_service_ext); plus the
 * two physical fixtures: GBP-INIT-003A (2026-09-15) drives the pre-delivery
 * part verbatim up to the EVENT and stops at the install (no interrupt
 * path in that run), and GBP-INIT-003B (2026-09-15, initirqb-0001, commit
 * d3da8cd) replays the whole run including the physical handler record.
 * The mock scenarios stay synthetic and are never physical evidence.
 *
 * Modes:  test_gbp_initirqb [initirqa-0001 fixture] [initirqb-0001 fixture]
 *         test_gbp_initirqb --dump-log <file>   (synthetic delivery scenario, SD-log format)
 *         test_gbp_initirqb --replay <fixture>  (runs the probe on a replay script)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_initirqb_probe.h"
#include "gbp_rawlog.h"
#include "gbp_replay.h"
#include "gbp_mock.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

#define LINES 224
#define LINE_LEN 256
static char storage[LINES * LINE_LEN];
#define BASE 0x01000000u
#define T_DELIVERY 400u              /* mock ticks; the transport's ticks() advances by 10 per call */

static const uint32_t A1_DL[GBP_INITIRQA_MAX_A1_OBS] = { 50u, 100u };
static const uint32_t A2_DL[GBP_INITIRQA_MAX_A2_OBS] = { 50u, 100u, 200u, 400u, 800u, 1600u };

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

static void test_config(struct gbp_initirqb_config *cfg)
{
    gbp_initirqb_config_default(cfg);
    memcpy(cfg->a.a1_obs_ticks, A1_DL, sizeof A1_DL);
    memcpy(cfg->a.a2_obs_ticks, A2_DL, sizeof A2_DL);
    cfg->t_delivery_ticks = T_DELIVERY;
}

/* the synthetic device of the delivery scenarios: idle 0x8AAE, source 0x0400 asserts 300 mock ticks after A2 */
static void mock_003b(struct gbp_mock *m)
{
    gbp_mock_init(m);
    m->irq_model = MOCK_IRQ_MODEL_SOURCE_MASK;
    m->isr_ext = 1;
    m->source_assert_after_write = 2;
    m->source_assert_delay = 300;
    m->source_assert_bits = 0x0400;
}

static void run_cfg(struct gbp_mock *m, struct ringlog *rl, struct gbp_initirqb_result *res, struct gbp_initirqb_config *cfg)
{
    struct gbp_transport t;
    gbp_mock_transport(m, &t);
    ringlog_init(rl, storage, LINE_LEN, LINES);
    gbp_initirqb_probe_run(&t, rl, cfg, res);
}

static void run(struct gbp_mock *m, struct ringlog *rl, struct gbp_initirqb_result *res)
{
    struct gbp_initirqb_config cfg;
    test_config(&cfg);
    run_cfg(m, rl, res, &cfg);
}

/* ---- the "never" properties, every run ---- */
static void check_never(const struct gbp_mock *m)
{
    unsigned idx;
    CHECK(m->intmr_writes == 0);                                             /* INTMR never written directly */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xC) == 0);             /* KEYPAD never written */
    for (idx = 0; idx < 16; idx++) {
        if (idx == 0 || idx == 4 || idx == 0xD) continue;
        CHECK(gbp_mock_count_block_ops(m, MOCK_RD, BASE, idx) == 0);
        CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, idx) == 0);
    }
    CHECK(m->intsr_writes <= 1);                                             /* main-loop W1C: at most one */
    CHECK(m->isr_w1c_count <= 1);                                            /* handler W1C: at most one, whatever the entries */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xD) <= 4);             /* A1, A2, ACK, STOP */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 4) <= 2);
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0) == 4);               /* handshake only */
    CHECK(gbp_mock_count_block_ops(m, MOCK_IRQ_UNMASK, BASE, 16) <= 1);      /* one unmask at most */
}

/* ---- the mandatory order of a run that reached the delivery stage ---- */
static void check_order(const struct gbp_mock *m, const struct gbp_initirqb_result *res)
{
    int ar_exp = gbp_mock_first_op(m, MOCK_AR_W, BASE, 16);
    int ctl_exp = gbp_mock_nth_op(m, MOCK_WR, BASE, 4, 1);
    int ctl_rest = gbp_mock_nth_op(m, MOCK_WR, BASE, 4, 2);
    int a1 = gbp_mock_nth_op(m, MOCK_WR, BASE, 0xD, 1);
    int a2 = gbp_mock_nth_op(m, MOCK_WR, BASE, 0xD, 2);
    int inst = gbp_mock_first_op(m, MOCK_IRQ_INSTALL, BASE, 16);
    int unm = gbp_mock_first_op(m, MOCK_IRQ_UNMASK, BASE, 16);
    int entry = gbp_mock_first_op(m, MOCK_ISR_ENTRY, BASE, 16);
    int imask = gbp_mock_first_op(m, MOCK_ISR_MASK, BASE, 16);
    int iw1c = gbp_mock_first_op(m, MOCK_ISR_W1C, BASE, 16);
    int iexit = gbp_mock_first_op(m, MOCK_ISR_EXIT, BASE, 16);
    int mmask = -1, k;
    int stop = gbp_mock_last_op(m, MOCK_WR, BASE, 0xD);
    int rest = gbp_mock_first_op(m, MOCK_IRQ_RESTORE, BASE, 16);
    int ar_rest = gbp_mock_last_op(m, MOCK_AR_W, BASE, 16);
    int last_rd = gbp_mock_last_op(m, MOCK_RD, BASE, 16);
    for (k = 0; k < (int)m->nops; k++) if (m->ops[k].kind == MOCK_IRQ_MASK && (unm < 0 || k > unm)) { mmask = k; break; }
    CHECK(ar_exp >= 0 && ctl_exp > ar_exp && a1 > ctl_exp && a2 > a1);
    CHECK(inst > a2);                                                        /* CAUSE (after A2) < HANDLER_INSTALL */
    CHECK(inst >= 0 && (unsigned)inst < m->nops);
    if (unm >= 0) {
        CHECK(unm > inst);                                                   /* install before unmask */
        CHECK((m->ops[(unsigned)unm].intsr & GBP_PI_HSP_BIT) != 0);          /* unmask only with the cause latched */
        {   /* PREUNMASK block reads sit between the install and the unmask */
            int last_irq_rd = -1;
            for (k = 0; k < unm; k++) if (m->ops[k].kind == MOCK_RD && (((m->ops[k].addr - BASE) >> 20) & 0xFu) == 0xDu) last_irq_rd = k;
            CHECK(last_irq_rd > inst);
        }
        if (entry >= 0) {
            CHECK(entry > unm && imask > entry);                             /* UNMASK < ISR_ENTRY < ISR_MASK */
            if (iw1c >= 0) CHECK(iw1c > imask);                              /* ISR_MASK < ISR_PI_W1C */
            CHECK(mmask > iexit);                                            /* MAIN_REMASK after the handler */
            if (res->k.w_ack.attempted) {
                int ack = gbp_mock_nth_op(m, MOCK_WR, BASE, 0xD, 3);
                CHECK(ack > mmask && ack > iexit);                           /* device ACK never before fired / re-mask */
                CHECK(ctl_rest > ack);                                       /* CONTROL restore after the device ACK */
                CHECK(stop > ctl_rest);
            }
        } else {
            CHECK(mmask > unm);
        }
    }
    if (ctl_rest >= 0) CHECK(stop > ctl_rest);
    if (rest >= 0) { CHECK(rest > stop); CHECK(ar_rest > rest); }            /* HANDLER_RESTORE < ARINFO_RESTORE */
    CHECK(last_rd > ar_rest);                                                /* FINAL last */
    CHECK(m->violations == 0);
}

/* 9, 11, 12, 13, 17, 18, 20: immediate delivery of the latched cause, W1C clears and stays clear, device ACK clears the source */
static void test_normal_delivery(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res;
    mock_003b(&m);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && strcmp(res.status_name, "ok_delivery_observed") == 0);
    CHECK(res.restore_ok == 1 && res.errors == 0 && res.transport_ok == 1 && res.power_cycle_required == 1);
    /* the 003A stage ran to its EVENT */
    CHECK(res.a.intsr13_seen == 1 && res.a.event_taken == 1 && res.a.snap[GBP_INITIRQA_SNAP_EVENT].irq_gbi == 0x0400);
    CHECK(res.a.w_a1.completed && res.a.w_a2.completed && res.a.control_written == 1);
    /* handler installed after the cause, previous NULL */
    CHECK(res.h.handler_was_installed == 1 && res.h.old_handler_null == 1 && m.installed_calls == 1);
    /* PREUNMASK: cause latched, masked, CONTROL 0x8C, source pending with masks 0 */
    CHECK(res.preunmask_ok == 1 && strcmp(res.preunmask_reason, "-") == 0);
    CHECK((res.preunmask.intsr & GBP_PI_HSP_BIT) && res.preunmask.pi2_ok && (res.preunmask.intsr2 & GBP_PI_HSP_BIT));
    CHECK((res.preunmask.intmr & GBP_PI_HSP_BIT) == 0 && res.preunmask.control_vote == 0x8c && res.preunmask.irq_gbi == 0x0400);
    /* unmask → delivery at once */
    CHECK(res.d.irq_unmasked == 1 && res.d.unmask_rc == GBP_OK && res.d.fired == 1 && res.d.rec.count == 1 && res.d.reentry == 0);
    CHECK(res.d.timed_out == 0 && res.d.polls == 1 && m.deliveries == 1);
    CHECK(res.d.latency_ticks == (uint32_t)(res.d.rec.t_entry - res.d.t_unmask) && res.d.latency_ticks < T_DELIVERY);
    /* entry state as delivered, mask first, one W1C, clear afterwards, still clear at the second read */
    CHECK((res.d.rec.intsr_before_ack & GBP_PI_HSP_BIT) != 0 && (res.d.rec.intmr_at_entry & GBP_PI_HSP_BIT) != 0);
    CHECK((res.d.rec.intmr_after_mask & GBP_PI_HSP_BIT) == 0 && (res.d.rec.intsr_before_w1c & GBP_PI_HSP_BIT) != 0);
    CHECK((res.d.rec.intsr_after_ack & GBP_PI_HSP_BIT) == 0 && (res.d.rec.intsr_second & GBP_PI_HSP_BIT) == 0);
    CHECK((res.d.rec.intmr_second & GBP_PI_HSP_BIT) == 0 && res.d.rec.t_second >= res.d.rec.t_entry + 100u);
    CHECK(m.isr_w1c_count == 1 && (m.violation_mask & GBP_MOCK_VIOL_ISR_W1C_BEFORE_MASK) == 0);
    /* main re-mask verified, record copied while masked */
    CHECK(res.d.irq_masked_again == 1 && res.d.main_mask_ok == 1 && res.d.remask_retry == 0 && (res.d.intmr_remask & GBP_PI_HSP_BIT) == 0);
    /* PREACK: the source is still pending on the device, PI clean, CONTROL 0x8C */
    CHECK(res.k.preack.irq_gbi == 0x0400 && (res.k.preack.intsr & GBP_PI_HSP_BIT) == 0 && res.k.preack.control_vote == 0x8c);
    /* device ACK derived from the read: 0x0400 | 0x8000 */
    CHECK(res.k.ack_skipped == 0 && res.k.irq_pending == 0x0400 && res.k.ack_value == 0x8400);
    CHECK(res.k.w_ack.attempted == 1 && res.k.w_ack.completed == 1 && res.k.w_ack.value == 0x8400 && res.k.w_ack.raw[0] == 0x84 && res.k.w_ack.raw[1] == 0x00);
    /* POSTACK: source cleared, bit 15 set, PI still clean → no main W1C */
    CHECK(res.k.postack.irq_gbi == 0x8000 && (res.k.postack.intsr & GBP_PI_HSP_BIT) == 0);
    CHECK(res.k.main_pi_w1c == 0 && strcmp(res.k.main_pi_w1c_site, "-") == 0 && m.intsr_writes == 0);
    /* teardown */
    CHECK(res.a.control_restore_ok == 1 && res.a.irq_stop_pre.gbi == 0x8000 && res.a.stop_value == 0x8aaa && res.a.irq_stop_post.gbi == 0x8aaa);
    CHECK(res.a.pi_cleanup_performed == 0 && res.h.handler_restored == 1 && res.h.mask_ok == 1 && res.a.arinfo_restore_ok == 1);
    CHECK(res.a.irq_writes_attempted == 4 && res.a.irq_writes_completed == 4 && res.uncertain_writes == 0);
    CHECK(m.handler_installed == 0 && (m.intmr & GBP_PI_HSP_BIT) == 0 && m.arinfo == 0x0043 && m.irq_reg == 0x8aaa);
    check_never(&m);
    check_order(&m, &res);
    /* records */
    CHECK(count_lines_with(&rl, "INITIRQB start ") == 1 && count_lines_with(&rl, "CAUSE t_event=") == 1);
    CHECK(count_lines_with(&rl, "IRQ install rc=ok old_handler=null record_count=0 record_fired=0") == 1 && count_lines_with(&rl, "SNAP tag=PREUNMASK") == 1);
    CHECK(count_lines_with(&rl, "PI tag=PREUNMASKb") == 1 && count_lines_with(&rl, "PREUNMASK ok=1 reason=-") == 1);
    CHECK(count_lines_with(&rl, "UNMASK t_unmask=") == 1 && count_lines_with(&rl, "PI tag=UNMASKPOST") == 1);
    CHECK(count_lines_with(&rl, "IRQ mask tag=MAIN rc=ok") == 1 && count_lines_with(&rl, "WAIT fired=1 timed_out=0 polls=1") == 1);
    CHECK(count_lines_with(&rl, "PI tag=REMASKCHK") == 1 && count_lines_with(&rl, "HANDLER fired=1 count=1") == 1);
    CHECK(count_lines_with(&rl, "HANDLERPI intsr_at_entry=") == 1 && count_lines_with(&rl, "HANDLERPI2 t_second=") == 1);
    CHECK(count_lines_with(&rl, "DELIVERY fired=1 count=1") == 1 && count_lines_with(&rl, "intsr13_after_w1c=0 intsr13_second=0") == 1);
    CHECK(count_lines_with(&rl, "SNAP tag=PREACK") == 1 && count_lines_with(&rl, "ACK before=0400 ack_or=8000 ack_value=8400") == 1);
    CHECK(count_lines_with(&rl, "IRQW tag=ACK ") == 1 && count_lines_with(&rl, "SNAP tag=POSTACK") == 1);
    CHECK(count_lines_with(&rl, "MAINPICLEANUP site=POSTACK performed=0") == 1);
    CHECK(count_lines_with(&rl, "IRQW tag=STOP ") == 1 && count_lines_with(&rl, "CLEANUP performed=0") == 1);
    CHECK(count_lines_with(&rl, "IRQ restore rc=ok ok=1 old_handler=null") == 1 && count_lines_with(&rl, "MASK final intmr=") == 1);
    CHECK(count_lines_with(&rl, "INITIRQB end status=ok_delivery_observed reason=- restore=ok") == 1);
    CHECK(count_lines_with(&rl, "ACKS ack=1/1 ack_value=8400") == 1 && count_lines_with(&rl, "RESTOREB handler_installed=1 handler_restored=1") == 1);
    CHECK(count_lines_with(&rl, "IRQW ") == 4 && count_lines_with(&rl, "layout=gbi-u16-replicated") == 4);
    /* the shared teardown prints this run's real PI policy (build initirqb-0001 printed never_unmasked here: label defect) */
    CHECK(count_lines_with(&rl, "TEARDOWN start control_written=1 irq_attempted=3 irq_completed=3 uncertain_writes=0 intsr13_seen=1 pi_policy=unmasked_once") == 1);
    CHECK(count_lines_with(&rl, "pi_policy=never_unmasked") == 0);
    /* order of the records mirrors the sequence */
    CHECK(line_index_with(&rl, "SNAP tag=EVENT") < line_index_with(&rl, "CAUSE t_event="));
    CHECK(line_index_with(&rl, "CAUSE t_event=") < line_index_with(&rl, "IRQ install"));
    CHECK(line_index_with(&rl, "IRQ install") < line_index_with(&rl, "SNAP tag=PREUNMASK"));
    CHECK(line_index_with(&rl, "PREUNMASK ok=1") < line_index_with(&rl, "UNMASK t_unmask="));
    CHECK(line_index_with(&rl, "UNMASK t_unmask=") < line_index_with(&rl, "IRQ mask tag=MAIN"));
    CHECK(line_index_with(&rl, "IRQ mask tag=MAIN") < line_index_with(&rl, "WAIT fired="));
    CHECK(line_index_with(&rl, "WAIT fired=") < line_index_with(&rl, "HANDLER fired="));
    CHECK(line_index_with(&rl, "DELIVERY fired=") < line_index_with(&rl, "SNAP tag=PREACK"));
    CHECK(line_index_with(&rl, "SNAP tag=PREACK") < line_index_with(&rl, "IRQW tag=ACK"));
    CHECK(line_index_with(&rl, "IRQW tag=ACK") < line_index_with(&rl, "SNAP tag=POSTACK"));
    CHECK(line_index_with(&rl, "SNAP tag=POSTACK") < line_index_with(&rl, "CTLW tag=RESTORE"));
    CHECK(line_index_with(&rl, "CTLW tag=RESTORE") < line_index_with(&rl, "IRQW tag=STOP"));
    CHECK(line_index_with(&rl, "IRQW tag=STOP") < line_index_with(&rl, "PI tag=CLEANUPCHK"));
    CHECK(line_index_with(&rl, "PI tag=CLEANUPCHK") < line_index_with(&rl, "IRQ restore"));
    CHECK(line_index_with(&rl, "IRQ restore") < line_index_with(&rl, "MASK final"));
    CHECK(line_index_with(&rl, "MASK final") < line_index_with(&rl, "ARINFO restore"));
    CHECK(line_index_with(&rl, "ARINFO restore") < line_index_with(&rl, "SNAP tag=FINAL"));
    CHECK(rl.dropped == 0 && rl.truncated == 0);
    {
        char s[1400];
        int n = gbp_initirqb_summary(&res, s, sizeof s);
        CHECK(n > 0 && (size_t)n < sizeof s);
        CHECK(strstr(s, "status=ok_delivery_observed reason=- restore=ok") && strstr(s, "ack=1/1 stop=1/1") && strstr(s, "fired=1 count=1"));
        CHECK(strstr(s, "intsr13_entry=1 intmr13_entry=1 intmr13_after_mask=0 intsr13_after_w1c=0 intsr13_second=0"));
        CHECK(strstr(s, "preack_irq=0400 ack_value=8400 postack_irq=8000 postack_intsr13=0 main_pi_w1c=0"));
        CHECK(strstr(s, "handler_restored=1 mask_ok=1") && strstr(s, "power_cycle_required=1"));
    }
}

/* 14: immediate re-assert (level model: the W1C cannot clear while the device source is pending) */
static void test_level_immediate_reassert(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res;
    mock_003b(&m); m.pi_cause_level = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && res.d.fired == 1 && res.d.rec.count == 1);
    CHECK((res.d.rec.intsr_after_ack & GBP_PI_HSP_BIT) != 0 && (res.d.rec.intsr_second & GBP_PI_HSP_BIT) != 0);   /* observation */
    CHECK((res.d.rec.intmr_after_mask & GBP_PI_HSP_BIT) == 0 && m.deliveries == 1);                              /* masked: no second delivery */
    CHECK((res.k.preack.intsr & GBP_PI_HSP_BIT) != 0 && res.k.preack.irq_gbi == 0x0400);
    CHECK(res.k.ack_value == 0x8400 && (res.k.postack.intsr & GBP_PI_HSP_BIT) == 0);   /* level model: line drops with the ACK */
    CHECK(res.k.main_pi_w1c == 0 && res.restore_ok == 1);
    CHECK(count_lines_with(&rl, "intsr13_after_w1c=1 intsr13_second=1") == 1);
    check_never(&m);
    check_order(&m, &res);
}

/* 15, 21: delayed re-latch (during the handler's wait, and after it) → POSTACK needs the one main-loop W1C */
static void test_delayed_relatch(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res;
    mock_003b(&m); m.pi_relatch_after_ticks = 50;                            /* inside the handler's ≈100-tick wait */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && res.d.fired == 1);
    CHECK((res.d.rec.intsr_after_ack & GBP_PI_HSP_BIT) == 0 && (res.d.rec.intsr_second & GBP_PI_HSP_BIT) != 0);
    CHECK((res.k.preack.intsr & GBP_PI_HSP_BIT) != 0);
    CHECK(res.k.w_ack.completed == 1 && (res.k.postack.intsr & GBP_PI_HSP_BIT) != 0);   /* latched: stays until a W1C */
    CHECK(res.k.main_pi_w1c == 1 && strcmp(res.k.main_pi_w1c_site, "POSTACK") == 0 && res.k.main_w1c_sticky == 0 && m.intsr_writes == 1);
    CHECK(res.a.pi_cleanup_performed == 0 && res.pi_sticky_final == 0 && res.restore_ok == 1);
    CHECK(count_lines_with(&rl, "MAINPICLEANUP site=POSTACK performed=1 value=00002000") == 1);
    CHECK(count_lines_with(&rl, "MAINPICLEANUP result rc=ok") == 1 && count_lines_with(&rl, "sticky=0") >= 1);
    CHECK(count_lines_with(&rl, "PI tag=MAINCLEANUP") == 1 && count_lines_with(&rl, "CLEANUP performed=0") == 1);
    check_never(&m);
    check_order(&m, &res);
    /* re-latch after the handler returned (the handler's second read lies ≈102 mock ticks after its W1C,
     * the main loop's first time-base read after the handler another 10 later): seen at PREACK, same handling */
    mock_003b(&m); m.pi_relatch_after_ticks = 110;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED);
    CHECK((res.d.rec.intsr_after_ack & GBP_PI_HSP_BIT) == 0 && (res.d.rec.intsr_second & GBP_PI_HSP_BIT) == 0);
    CHECK((res.k.preack.intsr & GBP_PI_HSP_BIT) != 0 && res.k.main_pi_w1c == 1 && strcmp(res.k.main_pi_w1c_site, "POSTACK") == 0);
    CHECK(count_lines_with(&rl, "intsr13_after_w1c=0 intsr13_second=0") == 1 && count_lines_with(&rl, "MAINPICLEANUP site=POSTACK performed=1") == 1);
    check_never(&m);
    check_order(&m, &res);
}

/* 22, 23: the budget when the cause is still latched at CLEANUPCHK; sticky after the allowed W1C */
static void test_cleanup_budget(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res;
    /* timeout path: nothing acknowledged the PI before the teardown → the teardown W1C is the main W1C */
    mock_003b(&m); m.delivery_suppressed = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_DELIVERY_TIMEOUT && res.d.fired == 0);
    CHECK(res.k.w_ack.attempted == 0 && res.a.pi_cleanup_performed == 1 && res.k.main_pi_w1c == 1 && strcmp(res.k.main_pi_w1c_site, "CLEANUP") == 0);
    CHECK(m.intsr_writes == 1 && m.isr_w1c_count == 0 && res.k.main_w1c_sticky == 0);
    check_never(&m);
    /* every W1C ignored: handler W1C ineffective, POSTACK W1C sticky, CLEANUPCHK must not spend a second one */
    mock_003b(&m); m.intsr_w1c_ignored = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && res.d.fired == 1);
    CHECK((res.d.rec.intsr_after_ack & GBP_PI_HSP_BIT) != 0 && (res.k.postack.intsr & GBP_PI_HSP_BIT) != 0);
    CHECK(res.k.main_pi_w1c == 1 && strcmp(res.k.main_pi_w1c_site, "POSTACK") == 0 && res.k.main_w1c_sticky == 1);
    CHECK(res.a.pi_cleanup_performed == 0 && res.pi_sticky_final == 1 && m.intsr_writes == 1);
    CHECK(res.restore_ok == 1);                                              /* sticky is an observation */
    CHECK(count_lines_with(&rl, "CLEANUP performed=0") == 1 && count_lines_with(&rl, "reason=budget_spent") == 1);
    CHECK(count_lines_with(&rl, "pi_sticky_final=1") == 1);
    check_never(&m);
    check_order(&m, &res);
}

/* 10: delivery timeout with the mask open; abort_unmask when the mask never opened */
static void test_timeout_and_abort_unmask(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res;
    mock_003b(&m); m.delivery_suppressed = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_DELIVERY_TIMEOUT && strcmp(res.reason, "no_delivery_within_t_delivery") == 0);
    CHECK((res.d.intmr_post_unmask & GBP_PI_HSP_BIT) != 0 && res.d.timed_out == 1 && res.d.wait_ticks >= T_DELIVERY);
    CHECK(res.d.irq_masked_again == 1 && res.d.main_mask_ok == 1 && res.d.rec.count == 0);
    CHECK(res.k.w_ack.attempted == 0 && res.k.ack_skipped == 0);                /* no device ACK on this path */
    CHECK(res.a.stop_value == 0x8eaa && res.a.irq_stop_post.gbi == 0x8aaa);  /* the stop word acknowledges the pending source */
    CHECK(res.h.handler_restored == 1 && res.h.mask_ok == 1 && res.restore_ok == 1 && res.transport_ok == 1);
    CHECK(count_lines_with(&rl, "WAIT fired=0 timed_out=1") == 1 && count_lines_with(&rl, "INITIRQB end status=delivery_timeout") == 1);
    CHECK(count_lines_with(&rl, "IRQW tag=ACK") == 0);
    CHECK(count_lines_with(&rl, "pi_policy=unmasked_once") == 1 && count_lines_with(&rl, "pi_policy=never_unmasked") == 0);   /* the unmask happened */
    check_never(&m);
    check_order(&m, &res);
    mock_003b(&m); m.unmask_ignored = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_UNMASK && strcmp(res.reason, "unmask_not_effective") == 0);
    CHECK((res.d.intmr_post_unmask & GBP_PI_HSP_BIT) == 0 && res.d.fired == 0 && m.deliveries == 0);
    CHECK(res.h.handler_restored == 1 && res.h.mask_ok == 1 && res.k.w_ack.attempted == 0);
    check_never(&m);
}

/* 16: reentry (a second delivery despite the mask) and a mask that does not take */
static void test_reentry_and_mask_failure(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res;
    mock_003b(&m); m.second_delivery = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ANOMALY_REENTRY && res.d.fired == 1 && res.d.rec.count == 2 && res.d.reentry == 1);
    CHECK(m.deliveries == 2 && m.isr_w1c_count == 1);                        /* the second entry did not acknowledge */
    CHECK(res.d.rec.reentry_t != 0 && (res.d.rec.reentry_intsr | res.d.rec.reentry_intmr) != 0);
    CHECK(res.k.w_ack.attempted == 0);                                         /* no device ACK after a reentry */
    CHECK(res.a.irq_stop_write_ok == 1 && res.h.handler_restored == 1 && res.h.mask_ok == 1);
    CHECK(count_lines_with(&rl, "reentry=1") >= 1 && count_lines_with(&rl, "INITIRQB end status=anomaly_reentry") == 1);
    check_never(&m);
    /* the mask has no effect (handler, main, retry): the W1C cleared the cause, so one delivery — mask failure, no ACK */
    mock_003b(&m); m.mask_ignored = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ANOMALY_MASK_FAILURE && res.d.fired == 1 && res.d.rec.count == 1 && m.deliveries == 1);
    CHECK((res.d.rec.intmr_after_mask & GBP_PI_HSP_BIT) != 0 && res.d.main_mask_ok == 0 && res.d.remask_retry == 1 && res.k.w_ack.attempted == 0);
    CHECK(res.h.mask_ok == 0 && res.restore_ok == 0 && strcmp(res.restore_reason, "mask_not_restored") == 0);
    CHECK(res.a.irq_stop_write_ok == 1 && res.a.stop_value == 0x8eaa && res.a.irq_stop_post.gbi == 0x8aaa);
    CHECK(count_lines_with(&rl, "IRQ mask tag=RETRY") == 2 && count_lines_with(&rl, "INITIRQB end status=anomaly_mask_failure") == 1);
    CHECK(count_lines_with(&rl, "IRQW tag=ACK") == 0 && count_lines_with(&rl, "MASK final intmr=000020f0 intmr13=1 orig_intmr13=0 ok=0") == 1);
    check_never(&m);
    /* ... and with a level cause that the W1C cannot clear: the real CPU would loop; the mock's storm cap (1) bounds it */
    mock_003b(&m); m.mask_ignored = 1; m.pi_cause_level = 1; m.max_deliveries = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ANOMALY_MASK_FAILURE && res.d.fired == 1 && res.d.rec.count == 1 && m.deliveries == 1);
    CHECK((m.violation_mask & GBP_MOCK_VIOL_STORM) != 0 && (res.d.rec.intsr_after_ack & GBP_PI_HSP_BIT) != 0);
    CHECK(res.k.w_ack.attempted == 0 && res.h.handler_restored == 1 && res.h.mask_ok == 0 && res.restore_ok == 0);
    CHECK(m.isr_w1c_count == 1 && m.intsr_writes <= 1);
}

/* 6, 7, 8, 27: handler install failure / no IRQ path / state lost before the unmask / old handler non-NULL */
static void test_install_and_preunmask(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res;
    mock_003b(&m); m.install_fails = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_HANDLER_INSTALL && strcmp(res.reason, "install_failed") == 0);
    CHECK(res.d.irq_unmasked == 0 && gbp_mock_first_op(&m, MOCK_IRQ_UNMASK, BASE, 16) < 0 && res.k.w_ack.attempted == 0);
    CHECK(res.a.pi_cleanup_performed == 1 && res.k.main_pi_w1c == 1 && strcmp(res.k.main_pi_w1c_site, "CLEANUP") == 0);   /* latched cause cleared in the teardown */
    CHECK(res.a.irq_stop_write_ok == 1 && res.h.handler_restored == -1 && res.a.arinfo_restore_ok == 1);
    check_never(&m);
    mock_003b(&m); m.irq_ops_available = 0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_HANDLER_INSTALL && strcmp(res.reason, "irq_ops_unavailable") == 0 && res.d.irq_unmasked == 0);
    CHECK(count_lines_with(&rl, "IRQ install rc=unavailable") == 1);
    CHECK(count_lines_with(&rl, "pi_policy=never_unmasked") == 1 && count_lines_with(&rl, "pi_policy=unmasked_once") == 0);
    mock_003b(&m); m.clear_cause_on_install = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "cause_lost") == 0);
    CHECK(res.d.irq_unmasked == 0 && res.h.handler_restored == 1 && res.h.mask_ok == 1 && m.handler_installed == 0);
    CHECK(count_lines_with(&rl, "PREUNMASK ok=0 reason=cause_lost") == 1);
    check_never(&m);
    mock_003b(&m); m.intmr13_set_on_install = 1; m.delivery_suppressed = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "intmr13_unmasked") == 0 && res.d.irq_unmasked == 0);
    CHECK(res.h.mask_ok == 1);                                                 /* the teardown re-masked it */
    mock_003b(&m); m.control_on_install = 0x90;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "control_changed") == 0 && res.d.irq_unmasked == 0);
    mock_003b(&m); m.irq_reg_on_install = 0x8400;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "irq_state_unexpected") == 0 && res.d.irq_unmasked == 0);
    mock_003b(&m); m.irq_disagree_on_install = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "semantic_disagree") == 0 && res.d.irq_unmasked == 0);
    mock_003b(&m); m.record_dirty_on_install = 1;                            /* the record is not clean after the install */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "record_not_clear") == 0 && res.d.irq_unmasked == 0);
    CHECK(res.h.install_count == 1 && res.h.handler_restored == 1 && m.deliveries == 0);
    CHECK(count_lines_with(&rl, "IRQ install rc=ok old_handler=null record_count=1 record_fired=0") == 1);
    check_never(&m);
    mock_003b(&m); m.old_handler_nonnull = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && res.h.old_handler_null == 0 && res.h.handler_restored == 1);
    CHECK(count_lines_with(&rl, "IRQ install rc=ok old_handler=nonnull") == 1 && count_lines_with(&rl, "IRQ restore rc=ok ok=1 old_handler=nonnull") == 1);
    check_order(&m, &res);
}

/* 19, 24, 25, 26, 28: device ACK failure, stop failure, CONTROL restore ignored, handler restore failure, AR_INFO restore failure */
static void test_failures(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res;
    mock_003b(&m); m.irq_write_fail_at = 3;                                  /* the device ACK */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && res.k.w_ack.attempted == 1 && res.k.w_ack.completed == 0);
    CHECK(res.uncertain_writes == 1 && res.transport_ok == 0 && res.a.irq_writes_attempted == 4 && res.a.irq_writes_completed == 3);
    CHECK(res.k.postack.irq_gbi == 0x0400 && res.a.stop_value == 0x8eaa && res.a.irq_stop_post.gbi == 0x8aaa);   /* stop word acknowledged it */
    CHECK(res.restore_ok == 1 && res.power_cycle_required == 1);
    CHECK(count_lines_with(&rl, "ACKS ack=1/0") == 1);
    check_never(&m);
    check_order(&m, &res);
    mock_003b(&m); m.irq_write_fail_at = 4;                                  /* the stop word */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && res.a.irq_stop_write_ok == 0 && res.restore_ok == 0);
    CHECK(strcmp(res.restore_reason, "irq_stop_write_failed") == 0 && res.h.handler_restored == 1 && res.a.arinfo_restore_ok == 1);
    mock_003b(&m); m.control_write_fail_at = 2;
    run(&m, &rl, &res);
    CHECK(res.a.control_restore_ok == 0 && res.restore_ok == 0 && strcmp(res.restore_reason, "control_restore_failed") == 0);
    mock_003b(&m); m.restore_fails = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && res.h.handler_restored == 0 && res.restore_ok == 0);
    CHECK(strcmp(res.restore_reason, "handler_restore_failed") == 0 && res.h.mask_ok == 1 && res.a.arinfo_restore_ok == 1);
    CHECK(count_lines_with(&rl, "IRQ restore rc=backend ok=0") == 1);
    mock_003b(&m); m.arinfo_write_fail_at = 2;
    run(&m, &rl, &res);
    CHECK(res.a.arinfo_restore_ok == 0 && res.restore_ok == 0 && strcmp(res.restore_reason, "arinfo_restore_failed") == 0);
    CHECK(res.h.handler_restored == 1 && res.h.mask_ok == 1);
    /* the PREACK IRQ read (block transfer 39 of this scenario) fails: no device ACK (its value would be invented), the rest proceeds */
    mock_003b(&m); m.fail_at_op = 39; m.fail_rc = GBP_ERR_TIMEOUT;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && res.d.fired == 1 && res.k.preack.irq_rc != GBP_OK);
    CHECK(res.k.ack_skipped == 1 && strcmp(res.k.ack_skip_reason, "irq_read_failed") == 0 && res.k.w_ack.attempted == 0);
    CHECK(res.a.irq_writes_attempted == 3 && res.a.irq_writes_completed == 3 && res.a.stop_value == 0x8eaa);
    CHECK(res.errors >= 1 && res.transport_ok == 0 && res.h.handler_restored == 1 && res.h.mask_ok == 1 && res.restore_ok == 1);
    CHECK(count_lines_with(&rl, "ACK skipped=1 reason=irq_read_failed") == 1 && count_lines_with(&rl, "IRQW tag=ACK") == 0);
    CHECK(count_lines_with(&rl, "ACKS ack=0/0") == 1);
    check_never(&m);
    /* the PREUNMASK IRQ read (transfer 37) fails: read_failed, no unmask */
    mock_003b(&m); m.fail_at_op = 37; m.fail_rc = GBP_ERR_TIMEOUT;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "read_failed") == 0 && res.d.irq_unmasked == 0);
    CHECK(res.h.handler_restored == 1 && res.transport_ok == 0);
    check_never(&m);
}

/* 5, 1, 2, 3, 4: no cause within the bound, and the 003A-stage aborts (nothing of 003B runs) */
static void test_no_cause_and_stage_aborts(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res;
    gbp_mock_init(&m); m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK; m.isr_ext = 1;   /* no source ever asserts */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_NO_CAUSE_WITHIN_TMAX && strcmp(res.status_name, "no_cause_within_tmax") == 0);
    CHECK(res.a.a2_obs_taken == 6 && res.a.intsr13_seen == 0 && m.installed_calls == 0 && res.d.irq_unmasked == 0);
    CHECK(res.a.irq_writes_attempted == 3 && res.a.control_restore_ok == 1 && res.a.arinfo_restore_ok == 1 && res.restore_ok == 1);
    CHECK(res.h.handler_restored == -1 && res.h.mask_ok == -1 && res.transport_ok == 1);
    CHECK(count_lines_with(&rl, "IRQ install") == 0 && count_lines_with(&rl, "UNMASK") == 0);
    CHECK(count_lines_with(&rl, "INITIRQB end status=no_cause_within_tmax reason=no_intsr13_within_t_max") == 1);
    CHECK(count_lines_with(&rl, "pi_policy=never_unmasked") == 1 && count_lines_with(&rl, "pi_policy=unmasked_once") == 0);   /* no unmask on this path */
    check_never(&m);
    gbp_mock_init(&m); m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK; m.isr_ext = 1; m.present = 0; m.absent_fill = 0xC1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_STAGE_A && res.stage_a_aborted == 1 && strcmp(res.status_name, "abort_not_present") == 0);
    CHECK(res.a.control_written == 0 && res.power_cycle_required == 0 && m.installed_calls == 0 && res.a.arinfo_restore_ok == 1);
    CHECK(count_lines_with(&rl, "INITIRQA end status=abort_not_present") == 1 && count_lines_with(&rl, "INITIRQB end status=abort_not_present") == 1);
    CHECK(res.h.handler_restored == -1 && res.h.mask_ok == -1 && res.h.old_handler_null == -1 && res.preunmask_ok == 0);
    {   /* the summary a Dolphin run without an HSP device / with the GBPlayer model produces (stage-A aborts) */
        char s[1400];
        CHECK(gbp_initirqb_summary(&res, s, sizeof s) > 0);
        CHECK(strstr(s, "DONE status=abort_not_present reason=absent restore=ok restore_reason=- verdict=absent det=0/4 written=0 "
                        "irq_attempted=0 irq_completed=0 ctl_exp=0/0 a1=0/0 a2=0/0 ack=0/0 stop=0/0 ctl_restore=0/0 uncertain=0 "
                        "cause=0 t_event=0 handler=0 old=? preunmask=0/- unmasked=0 fired=0 count=0 latency_ticks=0 latency_us=0 "
                        "intsr13_entry=0 intmr13_entry=0 intmr13_after_mask=0 intsr13_after_w1c=0 intsr13_second=0 "
                        "preack_irq=0000 ack_value=0000 postack_irq=0000 postack_intsr13=0 main_pi_w1c=0 site=- sticky=0 "
                        "control_restore_ok=-1 irq_stop_write_ok=-1 stop_post=0000 pi_cleanup=0 handler_restored=-1 mask_ok=-1 "
                        "arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1") != 0);
    }
    check_never(&m);
    gbp_mock_init(&m); m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK; m.isr_ext = 1; m.intsr = GBP_PI_HSP_BIT;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_STAGE_A && strcmp(res.status_name, "abort_pi_precondition") == 0 && strcmp(res.reason, "intsr13_set") == 0);
    CHECK(m.control_writes == 0 && m.intsr_writes == 0 && m.installed_calls == 0);
    gbp_mock_init(&m); m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK; m.isr_ext = 1; m.control_byte = 0x03;
    run(&m, &rl, &res);
    CHECK(strcmp(res.status_name, "abort_control_shape") == 0 && m.control_writes == 0);
    gbp_mock_init(&m); m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK; m.isr_ext = 1; m.irq_reg = 0x0aae;
    run(&m, &rl, &res);
    CHECK(strcmp(res.status_name, "abort_irq_shape") == 0 && m.control_writes == 0);
    check_never(&m);
}

/* 30: attempted/completed sampled at the moment the transport is invoked (the device ACK and the stop) */
struct call_sample { unsigned idx; int ack_att, ack_comp, pcr; unsigned irq_att, irq_comp; };
static struct gbp_initirqb_result *hook_res;
static struct call_sample samples[8];
static unsigned nsamples;

static void sample_hook(struct gbp_mock *m, uint32_t addr, const uint8_t *data, void *user)
{
    unsigned idx = (unsigned)((addr - BASE) >> 20) & 0xFu;
    struct call_sample *s;
    (void)m; (void)data; (void)user;
    if (idx != 0xDu || nsamples >= 8u) return;
    s = &samples[nsamples++];
    s->idx = idx;
    s->ack_att = hook_res->k.w_ack.attempted; s->ack_comp = hook_res->k.w_ack.completed;
    s->pcr = hook_res->a.power_cycle_required;
    s->irq_att = hook_res->a.irq_writes_attempted; s->irq_comp = hook_res->a.irq_writes_completed;
}

static void test_attempted_at_call_time(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res; struct gbp_transport t; struct gbp_initirqb_config cfg;
    mock_003b(&m); m.write_hook = sample_hook; hook_res = &res; nsamples = 0; memset(samples, 0, sizeof samples);
    test_config(&cfg); gbp_mock_transport(&m, &t); ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_initirqb_probe_run(&t, &rl, &cfg, &res);
    CHECK(nsamples == 4);                                                    /* A1, A2, ACK, STOP */
    CHECK(samples[2].ack_att == 1 && samples[2].ack_comp == 0 && samples[2].irq_att == 3 && samples[2].irq_comp == 2 && samples[2].pcr == 1);
    CHECK(samples[3].irq_att == 4 && samples[3].irq_comp == 3 && samples[3].ack_comp == 1);
    /* the ACK fails: attempted stays 1, completed 0, power cycle still required */
    mock_003b(&m); m.write_hook = sample_hook; m.irq_write_fail_at = 3; nsamples = 0;
    gbp_mock_transport(&m, &t); ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_initirqb_probe_run(&t, &rl, &cfg, &res);
    CHECK(samples[2].ack_att == 1 && samples[2].ack_comp == 0 && res.k.w_ack.completed == 0 && res.power_cycle_required == 1);
    m.write_hook = 0;
}

/* 29, 31, 32: wrapping time base, power cycle never cleared, worst-case line widths */
static void test_wrap_and_lines(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res;
    mock_003b(&m); m.pi_relatch_after_ticks = 50; m.intsr_w1c_ignored = 0; m.old_handler_nonnull = 1;
    m.tick = 0xFFFFFF00u; m.intsr = 0x00010000u; m.intmr = 0x000001fau;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && res.d.latency_ticks < 1000u);   /* wrap-safe latency */
    CHECK((uint32_t)(res.d.rec.t_second - res.d.rec.t_entry) >= 100u && (uint32_t)(res.d.rec.t_second - res.d.rec.t_entry) < 1000u);
    CHECK(rl.truncated == 0 && rl.dropped == 0 && max_line_len(&rl) < LINE_LEN - 1);
    CHECK(res.power_cycle_required == 1);
    {
        char s[1400]; int n = gbp_initirqb_summary(&res, s, sizeof s);
        CHECK(n > 0 && (size_t)n < sizeof s);
    }
    /* longest status / reason / restore_reason together with 10-digit ticks */
    mock_003b(&m); m.irq_reg_on_install = 0x8400; m.restore_fails = 1; m.tick = 0xFFFFFF00u; m.intsr = 0x00010000u; m.intmr = 0x000001fau;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQB_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "irq_state_unexpected") == 0);
    CHECK(res.restore_ok == 0 && strcmp(res.restore_reason, "handler_restore_failed") == 0);
    CHECK(rl.truncated == 0 && rl.dropped == 0 && max_line_len(&rl) < LINE_LEN - 1);
    CHECK(count_lines_with(&rl, "INITIRQB end status=abort_pre_unmask_state reason=irq_state_unexpected restore=error restore_reason=handler_restore_failed power_cycle_required=1") == 1);
    mock_003b(&m); m.mask_ignored = 1; m.max_deliveries = 1; m.tick = 0xFFFFFF00u;
    run(&m, &rl, &res);
    CHECK(rl.truncated == 0 && max_line_len(&rl) < LINE_LEN - 1);
    /* power cycle stays set whatever the restores did */
    mock_003b(&m); m.restore_fails = 1; m.control_write_fail_at = 2; m.arinfo_write_fail_at = 2; m.irq_write_fail_at = 4;
    run(&m, &rl, &res);
    CHECK(res.power_cycle_required == 1 && res.restore_ok == 0);
    /* ring overflow: completes, restores, reports the drops */
    {
        static char tiny[8 * LINE_LEN]; struct gbp_transport t; struct gbp_initirqb_config cfg;
        mock_003b(&m); test_config(&cfg); gbp_mock_transport(&m, &t); ringlog_init(&rl, tiny, LINE_LEN, 8);
        gbp_initirqb_probe_run(&t, &rl, &cfg, &res);
        CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && res.h.handler_restored == 1 && rl.dropped > 0 && rl.count == 8);
        check_never(&m);
    }
    /* config: the delivery bound at the console's time base */
    {
        struct gbp_initirqb_config cfg;
        gbp_initirqb_config_default(&cfg);
        CHECK(cfg.t_delivery_ms == 100u && cfg.t_delivery_ticks == 4050000u && cfg.a.a2_obs_ticks[5] == 81000000u);
        CHECK(cfg.ack_or == 0x8000 && cfg.src_mask == 0x0555 && cfg.odd_mask == 0x0AAA && cfg.bit15_mask == 0x8000 && cfg.high_mask == 0x7000);
        gbp_initirqb_config_timebase(&cfg, 81000000u);
        CHECK(cfg.t_delivery_ticks == 8100000u && cfg.a.a1_obs_ticks[0] == 4050u);
    }
}

/* the mock's own extended-handler engine, driven by hand: mask before W1C, exactly one W1C across two entries */
static void test_mock_ext_isr_by_hand(void)
{
    struct gbp_mock m; struct gbp_transport t; int old = 0; uint8_t blk[32]; struct gbp_xfer_info info;
    mock_003b(&m); gbp_mock_transport(&m, &t);
    m.second_delivery = 1;
    t.write_arinfo(t.ctx, 0x005b);
    memset(blk, 0x8c, sizeof blk); t.write_block(t.ctx, BASE + (4u << 20), blk, &info);
    m.intsr |= GBP_PI_HSP_BIT;                                              /* a latched cause */
    t.irq_install(t.ctx, &old);
    t.irq_unmask(t.ctx);
    CHECK(m.deliveries == 2 && m.rec.count == 2 && m.isr_w1c_count == 1 && m.rec.fired == 1);
    CHECK(gbp_mock_first_op(&m, MOCK_ISR_MASK, BASE, 16) < gbp_mock_first_op(&m, MOCK_ISR_W1C, BASE, 16));
    CHECK(gbp_mock_count_block_ops(&m, MOCK_ISR_W1C, BASE, 16) == 1 && gbp_mock_count_block_ops(&m, MOCK_ISR_MASK, BASE, 16) == 2);
    CHECK(m.rec.reentry_t != 0 && m.rec.t_second > m.rec.t_entry && (m.violation_mask & GBP_MOCK_VIOL_ISR_W1C_BEFORE_MASK) == 0);
    t.irq_mask(t.ctx); t.irq_restore(t.ctx); t.write_arinfo(t.ctx, 0x0043);
    CHECK(m.violations == 0);
}

/* ---- the physical GBP-INIT-003A fixture as the real prefix up to the EVENT ---- */
static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb"); long n; char *buf;
    if (!f) return 0;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    buf = (char *)malloc((size_t)n + 1);
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(buf); return 0; }
    buf[n] = '\0'; fclose(f); return buf;
}

/* The physical run of 2026-09-15 (initirqa-0001) drives the whole 003A stage verbatim
 * — same reads, writes, time base and EVENT — and then, because a replay of a run
 * that had no interrupt path exposes no irq_* operations, the probe stops at the
 * handler install and tears down exactly as 003A did: CONTROL restore, stop word,
 * the one physical W1C (charged to the main-loop budget), AR_INFO, FINAL. Every line
 * of the fixture is consumed; nothing after the EVENT is invented. */
static void test_hw_initirqa_prefix(const char *path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_initirqb_config cfg;
    struct gbp_initirqb_result res; struct ringlog rl;
    unsigned ops = 0; const char *p;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    for (p = text; *p; ) { while (*p == ' ') p++; if (*p != '#' && *p != '\n' && *p != '\0') ops++; p = strchr(p, '\n'); if (!p) break; p++; }
    gbp_replay_init(&r, text);
    CHECK(r.has_irq_ops == 0 && r.timeline == 1);
    gbp_replay_transport(&r, &t);
    gbp_initirqb_config_default(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_initirqb_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.status == GBP_INITIRQB_ABORT_HANDLER_INSTALL && strcmp(res.reason, "irq_ops_unavailable") == 0);
    CHECK(res.stage_a_aborted == 0 && res.a.intsr13_seen == 1 && res.a.event_taken == 1 && res.a.t_event == 4155517524u);
    CHECK(res.a.snap[GBP_INITIRQA_SNAP_EVENT].irq_gbi == 0x0400 && res.a.snap[GBP_INITIRQA_SNAP_EVENT].intsr == 0x00012000);
    CHECK(res.a.snap[GBP_INITIRQA_SNAP_BASE].irq_gbi == 0x8aae && res.a.snap[GBP_INITIRQA_SNAP_A1_0].irq_gbi == 0x8aaa);
    CHECK(res.a.w_a1.value == 0x8aae && res.a.w_a2.value == 0 && res.a.t_a2 == 4151253956u);
    CHECK(res.h.handler_was_installed == 0 && res.d.irq_unmasked == 0 && res.k.w_ack.attempted == 0 && res.d.fired == 0);
    CHECK(res.a.irq_stop_pre.gbi == 0x0500 && res.a.stop_value == 0x8faa && res.a.irq_stop_post.gbi == 0x8aaa);
    CHECK(res.a.pi_cleanup_performed == 1 && res.k.main_pi_w1c == 1 && strcmp(res.k.main_pi_w1c_site, "CLEANUP") == 0 && res.pi_sticky_final == 0);
    CHECK(res.a.arinfo_final == 0x0043 && res.a.arinfo_restore_ok == 1 && res.h.handler_restored == -1 && res.h.mask_ok == -1);
    CHECK(res.a.irq_writes_attempted == 3 && res.a.irq_writes_completed == 3 && res.uncertain_writes == 0 && res.restore_ok == 1);
    CHECK(r.exhausted == 0 && r.mismatches == 0 && r.tick_polls == 0 && r.step == ops);
    CHECK(count_lines_with(&rl, "CAUSE t_event=4155517524 since_a2=4263568 intsr=00012000 intmr=000001fa intsr13=1 intmr13=0 control=8c irq=0400") == 1);
    CHECK(count_lines_with(&rl, "IRQ install rc=unavailable") == 1 && count_lines_with(&rl, "UNMASK") == 0 && count_lines_with(&rl, "IRQW tag=ACK") == 0);
    CHECK(count_lines_with(&rl, "WINDOW tag=A1 deadlines=2/2 polls=2 poll_errors=0 intsr13_in_phase=0") == 1);
    CHECK(count_lines_with(&rl, "INITIRQB end status=abort_handler_install reason=irq_ops_unavailable restore=ok") == 1);
    CHECK(rl.dropped == 0 && rl.truncated == 0);
    free(text);
}

/* The physical GBP-INIT-003B run of 2026-09-15 (build initirqb-0001, commit d3da8cd, DOL 821aa2b2…b757,
 * log 17471 bytes sha256 bedb1f01…cf7c): the first delivery of a real HSP cause to a CPU handler as
 * IRQ 26. The fixture drives every transport call verbatim — the 003A sequence, the install after the
 * latched cause, the one unmask with the physical handler record, the main re-mask, the device ACK,
 * the stop word, the handler restore — with the console's time base. Nothing here is synthetic. */
static void test_hw_initirqb_gbp(const char *path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_initirqb_config cfg;
    struct gbp_initirqb_result res; struct ringlog rl;
    const struct gbp_initirqa_snapshot *ev, *fin;
    unsigned ops = 0; const char *p;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    for (p = text; *p; ) { while (*p == ' ') p++; if (*p != '#' && *p != '\n' && *p != '\0') ops++; p = strchr(p, '\n'); if (!p) break; p++; }
    gbp_replay_init(&r, text);
    CHECK(r.has_irq_ops == 1 && r.timeline == 1);
    gbp_replay_transport(&r, &t);
    gbp_initirqb_config_default(&cfg);                                       /* the console's time base, 40.5 MHz */
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_initirqb_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(r.exhausted == 0 && r.mismatches == 0 && r.tick_polls == 0 && r.step == ops && ops == 111u);
    CHECK(res.status == GBP_INITIRQB_OK_DELIVERY_OBSERVED && strcmp(res.status_name, "ok_delivery_observed") == 0);
    CHECK(res.restore_ok == 1 && res.errors == 0 && res.transport_ok == 1 && res.power_cycle_required == 1 && res.stage_a_aborted == 0);
    /* the 003A sequence as it happened again: BASE 90 / 8AAE, A1 8AAE -> 8AAA, A2 0000, EVENT 0x0400 105.29 ms after A2 */
    ev = &res.a.snap[GBP_INITIRQA_SNAP_EVENT];
    fin = &res.a.snap[GBP_INITIRQA_SNAP_FINAL];
    CHECK(res.a.det.vote_ok == 4 && res.a.det.run == 4 && res.a.control_orig == 0x90 && res.a.control_exp == 0x8c);
    CHECK(res.a.snap[GBP_INITIRQA_SNAP_BASE].irq_gbi == 0x8aae && res.a.snap[GBP_INITIRQA_SNAP_A1_0].irq_gbi == 0x8aaa);
    CHECK(res.a.w_a1.value == 0x8aae && res.a.w_a1.completed && res.a.w_a2.value == 0 && res.a.w_a2.completed);
    CHECK(res.a.t_a2 == 3675626133u && res.a.t_event == 3679890204u && (uint32_t)(res.a.t_event - res.a.t_a2) == 4264071u);
    CHECK(res.a.event_taken == 1 && res.a.window_ended_early == 1 && res.a.intsr13_seen == 1);
    CHECK(ev->taken && ev->intsr == 0x00012000u && ev->intmr == 0x000001fau && ev->control_vote == 0x8c && ev->irq_gbi == 0x0400 && ev->irq_disc == 0x0400);
    /* point B: the handler installed after the cause, previous handler NULL, record clean */
    CHECK(res.h.handler_was_installed == 1 && res.h.old_handler_null == 1 && res.h.install_count == 0 && res.h.install_fired == 0);
    /* PREUNMASK 907.6 us after the EVENT: both PI samples latched and masked, CONTROL 8C, the second source had appeared (0x0500) */
    CHECK(res.preunmask_ok == 1 && strcmp(res.preunmask_reason, "-") == 0 && res.preunmask.ticks == 3679926960u);
    CHECK(res.preunmask.intsr == 0x00012000u && res.preunmask.pi2_ok && res.preunmask.intsr2 == 0x00012000u);
    CHECK(res.preunmask.intmr == 0x000001fau && res.preunmask.intmr2 == 0x000001fau && res.preunmask.control_vote == 0x8c);
    CHECK(res.preunmask.irq_gbi == 0x0500 && res.preunmask.irq_disc == 0x0500);
    /* one unmask; the handler ran inside __UnmaskIrq: t_post is after the record's second read */
    CHECK(res.d.intsr_pre_unmask == 0x00012000u && res.d.intmr_pre_unmask == 0x000001fau);
    CHECK(res.d.t_unmask == 3679931504u && res.d.unmask_rc == GBP_OK && res.d.irq_unmasked == 1 && res.d.t_post_unmask == 3679931761u);
    CHECK(res.d.intsr_post_unmask == 0x00010000u && res.d.intmr_post_unmask == 0x000001fau);
    CHECK(res.d.fired == 1 && res.d.rec.count == 1 && res.d.reentry == 0 && res.d.timed_out == 0 && res.d.polls == 1 && res.d.wait_ticks == 1987u);
    CHECK(res.d.rec.t_entry == 3679931582u && res.d.latency_ticks == 78u && res.d.latency_us == 1u);
    CHECK(res.d.rec.intsr_before_ack == 0x00012000u && res.d.rec.intmr_at_entry == 0x000021fau);      /* delivered: cause + mask open */
    CHECK(res.d.rec.intmr_after_mask == 0x000001fau && res.d.rec.intsr_before_w1c == 0x00012000u);    /* mask first, cause still latched */
    CHECK(res.d.rec.intsr_after_ack == 0x00010000u);                                                 /* the ISR's W1C cleared it */
    CHECK(res.d.rec.t_second == 3679931730u && (uint32_t)(res.d.rec.t_second - res.d.rec.t_entry) == 148u);
    CHECK(res.d.rec.intsr_second == 0x00010000u && res.d.rec.intmr_second == 0x000001fau && res.d.rec.reentry_t == 0 && res.d.rec.reentry_intsr == 0);
    CHECK(res.d.irq_masked_again == 1 && res.d.main_mask_ok == 1 && res.d.remask_retry == 0 && res.d.intmr_remask == 0x000001fau);
    /* PREACK 179.7 us after the entry: sources 0x0500 still pending, CONTROL 8C, PI bit 13 clear in both samples (no re-assert) */
    CHECK(res.k.preack.ticks == 3679938859u && res.k.preack.intsr == 0x00010000u && res.k.preack.intsr2 == 0x00010000u);
    CHECK(res.k.preack.intmr == 0x000001fau && res.k.preack.control_vote == 0x8c && res.k.preack.irq_gbi == 0x0500 && res.k.preack.irq_disc == 0x0500);
    /* device ACK IRQ := 0x0500 | 0x8000 = 0x8500, read back 0x8000: sources cleared, bit 15 read 1; PI still clear; no main W1C */
    CHECK(res.k.ack_skipped == 0 && res.k.irq_pending == 0x0500 && res.k.ack_value == 0x8500 && res.k.w_ack.attempted == 1 && res.k.w_ack.completed == 1);
    CHECK(res.k.w_ack.raw[0] == 0x85 && res.k.w_ack.raw[1] == 0x00 && res.k.w_ack.raw[30] == 0x85 && res.k.w_ack.raw[31] == 0x00);
    CHECK(res.k.postack.ticks == 3679944700u && res.k.postack.irq_gbi == 0x8000 && res.k.postack.irq_disc == 0x8000);
    CHECK(res.k.postack.intsr == 0x00010000u && res.k.postack.intsr2 == 0x00010000u && res.k.postack.intmr == 0x000001fau && res.k.postack.control_vote == 0x8c);
    CHECK(res.k.main_pi_w1c == 0 && strcmp(res.k.main_pi_w1c_site, "-") == 0 && res.k.main_w1c_sticky == 0);
    /* teardown: CONTROL 90, sources re-set before the stop (IRQSTOPPRE 0x8500), stop 0x8FAA -> 0x8AAA, no cleanup, handler back, masked */
    CHECK(res.a.control_restore_ok == 1 && res.a.control_restore_vote == 0x90);
    CHECK(res.a.irq_stop_pre.gbi == 0x8500 && res.a.irq_stop_pre.disc == 0x8500 && res.a.stop_value == 0x8faa && res.a.w_stop.completed);
    CHECK(res.a.irq_stop_post.gbi == 0x8aaa && res.a.stop_masks_readback == 1 && res.a.stop_bit15_readback == 1);
    CHECK(res.a.pi_cleanup_performed == 0 && res.a.cleanup_intsr_before == 0x00010000u && res.pi_sticky_final == 0);
    CHECK(res.h.handler_restored == 1 && res.h.handler_restore_rc == GBP_OK && res.h.mask_ok == 1 && res.h.intmr_final == 0x000001fau);
    CHECK(res.a.arinfo_orig == 0x0043 && res.a.arinfo_exp == 0x005b && res.a.arinfo_final == 0x0043 && res.a.arinfo_restore_ok == 1);
    CHECK(fin->taken && fin->control_vote == 0x00 && fin->irq_gbi == 0x9090 && fin->intsr == 0x00010000u && fin->intmr == 0x000001fau);
    CHECK(res.a.irq_writes_attempted == 4 && res.a.irq_writes_completed == 4 && res.uncertain_writes == 0);
    /* records of the corrected probe; the raw log of build initirqb-0001 printed pi_policy=never_unmasked (label defect, documented) */
    CHECK(count_lines_with(&rl, "TEARDOWN start control_written=1 irq_attempted=3 irq_completed=3 uncertain_writes=0 intsr13_seen=1 pi_policy=unmasked_once") == 1);
    CHECK(count_lines_with(&rl, "pi_policy=never_unmasked") == 0);
    CHECK(count_lines_with(&rl, "CAUSE t_event=3679890204 since_a2=4264071 intsr=00012000 intmr=000001fa intsr13=1 intmr13=0 control=8c irq=0400") == 1);
    CHECK(count_lines_with(&rl, "IRQ install rc=ok old_handler=null record_count=0 record_fired=0") == 1);
    CHECK(count_lines_with(&rl, "PREUNMASK ok=1 reason=- intsr13=1,1 intmr13=0,0 control=8c irq=0500/0500 src=0500 odd=0000 bit15=0") == 1);
    CHECK(count_lines_with(&rl, "UNMASK t_unmask=3679931504 rc=ok t_post=3679931761 dt_post=257") == 1);
    CHECK(count_lines_with(&rl, "PI tag=UNMASKPOST rc=ok intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 fired=1") == 1);
    CHECK(count_lines_with(&rl, "WAIT fired=1 timed_out=0 polls=1 wait_ticks=1987 wait_us=49 t_delivery_ms=100 t_delivery_ticks=4050000") == 1);
    CHECK(count_lines_with(&rl, "HANDLER fired=1 count=1 t_entry=3679931582 t_unmask=3679931504 latency_ticks=78 latency_us=1 reentry=0") == 1);
    CHECK(count_lines_with(&rl, "HANDLERPI intsr_at_entry=00012000 intmr_at_entry=000021fa intmr_after_mask=000001fa intsr_before_w1c=00012000 intsr_after_w1c=00010000 reentry_intsr=00000000 reentry_intmr=00000000") == 1);
    CHECK(count_lines_with(&rl, "HANDLERPI2 t_second=3679931730 dt_second=148 intsr_second=00010000 intmr_second=000001fa reentry_t=0") == 1);
    CHECK(count_lines_with(&rl, "DELIVERY fired=1 count=1 latency_ticks=78 latency_us=1 intsr13_entry=1 intmr13_entry=1 intmr13_after_mask=0 intsr13_before_w1c=1 intsr13_after_w1c=0 intsr13_second=0 intmr13_second=0 main_mask_ok=1 reentry=0") == 1);
    CHECK(count_lines_with(&rl, "PREACK intsr13=0,0 intmr13=0 control=8c irq=0500/0500 src_pending=0500") == 1);
    CHECK(count_lines_with(&rl, "ACK before=0500 ack_or=8000 ack_value=8500 formula=read|ack_or") == 1);
    CHECK(count_lines_with(&rl, "POSTACK intsr13=0,0 intmr13=0 control=8c irq=8000/8000 src_pending=0000 bit15=1 ack=1/1") == 1);
    CHECK(count_lines_with(&rl, "MAINPICLEANUP site=POSTACK performed=0 intsr13=0 intmr13=0") == 1);
    CHECK(count_lines_with(&rl, "IRQSTOP pre rc=ok disc=8500 gbi=8500 stop_or=8aaa stop_value=8faa formula=read|stop_or comment=startup-disc-stop-shadow") == 1);
    CHECK(count_lines_with(&rl, "IRQSTOP post rc=ok disc=8aaa gbi=8aaa write_ok=1 readback_ok=1 masks_readback=1 bit15_readback=1") == 1);
    CHECK(count_lines_with(&rl, "CLEANUP performed=0 intsr=00010000 intsr13=0 intmr13=0 reason=intsr13_clear") == 1);
    CHECK(count_lines_with(&rl, "IRQ restore rc=ok ok=1 old_handler=null") == 1 && count_lines_with(&rl, "MASK final intmr=000001fa intmr13=0 orig_intmr13=0 ok=1") == 1);
    CHECK(count_lines_with(&rl, "FINAL arinfo=0043 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 control=00 irq=9090 power_cycle_required=1") == 1);
    CHECK(count_lines_with(&rl, "INITIRQB end status=ok_delivery_observed reason=- restore=ok restore_reason=- power_cycle_required=1 errors=0 transport_ok=1") == 1);
    CHECK(count_lines_with(&rl, "WRITES control_written=1 irq_attempted=4 irq_completed=4 ctl_exp=1/1 a1=1/1 a2=1/1 stop=1/1 ctl_restore=1/1 uncertain=0 power_cycle_required=1 format=attempted/completed") == 1);
    CHECK(count_lines_with(&rl, "ACKS ack=1/1 ack_value=8500 irq_pending=0500 skipped=0 reason=- isr_pi_w1c=1 main_pi_w1c=0 site=- sticky=0 uncertain=0") == 1);
    CHECK(count_lines_with(&rl, "RESTOREB handler_installed=1 handler_restored=1 old_handler=null mask_ok=1 intmr_final=000001fa pi_sticky_final=0 unmasked=1 masked_again=1") == 1);
    CHECK(count_lines_with(&rl, "WINDOW tag=A1 deadlines=2/2 polls=2 poll_errors=0 intsr13_in_phase=0") == 1);
    CHECK(rl.dropped == 0 && rl.truncated == 0);
    {
        char s[1400];
        CHECK(gbp_initirqb_summary(&res, s, sizeof s) > 0);
        CHECK(strstr(s, "DONE status=ok_delivery_observed reason=- restore=ok restore_reason=- verdict=present det=4/4 written=1 "
                        "irq_attempted=4 irq_completed=4 ctl_exp=1/1 a1=1/1 a2=1/1 ack=1/1 stop=1/1 ctl_restore=1/1 uncertain=0 "
                        "cause=1 t_event=3679890204 handler=1 old=null preunmask=1/- unmasked=1 fired=1 count=1 latency_ticks=78 latency_us=1 "
                        "intsr13_entry=1 intmr13_entry=1 intmr13_after_mask=0 intsr13_after_w1c=0 intsr13_second=0 "
                        "preack_irq=0500 ack_value=8500 postack_irq=8000 postack_intsr13=0 main_pi_w1c=0 site=- sticky=0 "
                        "control_restore_ok=1 irq_stop_write_ok=1 stop_post=8aaa pi_cleanup=0 handler_restored=1 mask_ok=1 arinfo_restore_ok=1 "
                        "power_cycle_required=1 errors=0 transport_ok=1") != 0);
    }
    free(text);
}

/* ---- host round-trip modes (synthetic) ---- */
static int dump_log(const char *path)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirqb_result res; char s[1400]; size_t i; FILE *f;
    /* delivery, then a synthetic re-latch seen at PREACK so the main-loop W1C (POSTACK) is part of the round trip */
    mock_003b(&m); m.pi_relatch_after_ticks = 110; m.intsr = 0x00010000u; m.intmr = 0x000001fau; m.tick = 1000;
    run(&m, &rl, &res);
    gbp_initirqb_summary(&res, s, sizeof s);
    f = fopen(path, "w");
    if (!f) { fprintf(stderr, "cannot write %s\n", path); return 1; }
    fprintf(f, "# OPENGBP-LOG v1\n# SYNTHETIC: generated by tests/unit/test_gbp_initirqb.c from the host mock (delivery scenario); NOT physical data\n");
    fprintf(f, "test_id=GBP-INIT-003B\nbuild_id=synthetic\ncommit=none\nsource=host-mock\n");
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
    struct gbp_replay r; struct gbp_transport t; struct gbp_initirqb_config cfg;
    struct gbp_initirqb_result res; struct ringlog rl; char s[1400];
    if (!text) { fprintf(stderr, "cannot read %s\n", path); return 1; }
    gbp_replay_init(&r, text);
    gbp_replay_transport(&r, &t);
    test_config(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_initirqb_probe_run(&t, &rl, &cfg, &res);
    gbp_initirqb_summary(&res, s, sizeof s);
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
    test_normal_delivery();
    test_level_immediate_reassert();
    test_delayed_relatch();
    test_cleanup_budget();
    test_timeout_and_abort_unmask();
    test_reentry_and_mask_failure();
    test_install_and_preunmask();
    test_failures();
    test_no_cause_and_stage_aborts();
    test_attempted_at_call_time();
    test_wrap_and_lines();
    test_mock_ext_isr_by_hand();
    if (argc > 1) test_hw_initirqa_prefix(argv[1]);
    else fprintf(stderr, "note: physical 003A fixture path not given, prefix test skipped\n");
    if (argc > 2) test_hw_initirqb_gbp(argv[2]);
    else fprintf(stderr, "note: physical 003B fixture path not given, fixture test skipped\n");
    printf("test_gbp_initirqb: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
