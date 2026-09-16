/*
 * GBP-INIT-004 logic (repeated service: delivery → ACK → re-arm → next
 * cause, three cycles, one installed handler) against the mock's SYNTHETIC
 * models: the source/mask IRQ register with scheduled (re)assertions, the PI
 * cause latch (optionally lagging the source), the delivery engine running
 * the multi-cycle handler body (gbp_irq_multicycle_service), and every
 * injected deviation the specification enumerates. Plus the two physical
 * fixtures as prefixes: GBP-INIT-003A (2026-09-15) drives the stage verbatim
 * up to its EVENT and stops at the install (no interrupt path in that run);
 * GBP-INIT-003B (2026-09-15, initirqb-0001) drives cycle 0 verbatim up to
 * its POSTACK — the fixture is cut before the CONTROL restore, so the first
 * re-arm meets an exhausted script (nothing of a re-arm was ever recorded
 * physically). Every mock scenario is synthetic and never physical evidence.
 *
 * Modes:  test_gbp_initirq4 [initirqa-0001 fixture] [initirqb-0001 fixture]
 *         test_gbp_initirq4 --dump-log <file>   (synthetic 3-cycle scenario, SD-log format)
 *         test_gbp_initirq4 --replay <fixture>  (runs the probe on a replay script)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_initirq4_probe.h"
#include "gbp_rawlog.h"
#include "gbp_replay.h"
#include "gbp_mock.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

#define LINES 320
#define LINE_LEN 256
static char storage[LINES * LINE_LEN];
#define BASE 0x01000000u
#define T_DELIVERY 400u              /* mock ticks; the transport's ticks() advances by 10 per call */
#define T_NEXT_CAUSE 2000u

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

static void test_config(struct gbp_initirq4_config *cfg)
{
    gbp_initirq4_config_default(cfg);
    memcpy(cfg->a.a1_obs_ticks, A1_DL, sizeof A1_DL);
    memcpy(cfg->a.a2_obs_ticks, A2_DL, sizeof A2_DL);
    cfg->t_delivery_ticks = T_DELIVERY;
    cfg->t_next_cause_ticks = T_NEXT_CAUSE;
}

/* a source that (re)asserts `delay` mock ticks after the Nth IRQ-register write */
static void sched(struct gbp_mock *m, unsigned after_write, uint32_t delay, uint16_t bits)
{
    struct gbp_mock_src_sched *s;
    if (m->n_src_sched >= 8u) return;
    s = &m->src_sched[m->n_src_sched++];
    memset(s, 0, sizeof *s);
    s->after_write = after_write; s->delay = delay; s->bits = bits;
}

/* IRQ-register write numbering of a full run: A1=1 A2=2 ACK0=3 REARM0=4 ACK1=5 REARM1=6 ACK2=7 STOP=8 */
#define W_A1 1u
#define W_A2 2u
#define W_ACK0 3u
#define W_REARM0 4u
#define W_ACK1 5u
#define W_REARM1 6u
#define W_ACK2 7u
#define W_STOP 8u

/* the synthetic device of the three-cycle scenarios: idle 0x8AAE; cause 0 = 0x0500 300 ticks after A2;
 * cause 1 = 0x0500 50 ticks after the first re-arm; cause 2 = 0x0400 50 ticks after the second re-arm */
static void mock_004(struct gbp_mock *m)
{
    gbp_mock_init(m);
    m->irq_model = MOCK_IRQ_MODEL_SOURCE_MASK;
    m->isr_multi = 1;
    m->source_assert_after_write = W_A2;
    m->source_assert_delay = 300;
    m->source_assert_bits = 0x0500;
    sched(m, W_REARM0, 50, 0x0500);
    sched(m, W_REARM1, 50, 0x0400);
}

static void run_cfg(struct gbp_mock *m, struct ringlog *rl, struct gbp_initirq4_result *res, struct gbp_initirq4_config *cfg)
{
    struct gbp_transport t;
    gbp_mock_transport(m, &t);
    ringlog_init(rl, storage, LINE_LEN, LINES);
    gbp_initirq4_probe_run(&t, rl, cfg, res);
}

static void run(struct gbp_mock *m, struct ringlog *rl, struct gbp_initirq4_result *res)
{
    struct gbp_initirq4_config cfg;
    test_config(&cfg);
    run_cfg(m, rl, res, &cfg);
}

/* ---- the "never" properties, every run ---- */
static void check_never(const struct gbp_mock *m, const struct gbp_initirq4_result *res)
{
    unsigned idx, k;
    CHECK(m->intmr_writes == 0);                                             /* INTMR never written directly */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xC) == 0);             /* KEYPAD never written */
    for (idx = 0; idx < 16; idx++) {
        if (idx == 0 || idx == 4 || idx == 0xD) continue;
        CHECK(gbp_mock_count_block_ops(m, MOCK_RD, BASE, idx) == 0);         /* no VIDEO/AUDIO/SIO/other block */
        CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, idx) == 0);
    }
    CHECK(m->intsr_writes <= 4);                                             /* main-loop W1C: one per cycle at most + one in the teardown */
    CHECK(m->isr_w1c_count <= 3);                                            /* handler W1C: one per delivery at most */
    CHECK(m->isr_w1c_count + m->intsr_writes <= 7);
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xD) <= 8);             /* A1 A2 ACK0 REARM0 ACK1 REARM1 ACK2 STOP */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 4) <= 2);               /* CONTROL: the transform and its restore, never per cycle */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0) == 4);               /* handshake only */
    CHECK(gbp_mock_count_block_ops(m, MOCK_IRQ_UNMASK, BASE, 16) <= 3);      /* one unmask per cycle at most */
    CHECK(gbp_mock_count_block_ops(m, MOCK_IRQ_INSTALL, BASE, 16) <= 1);     /* the handler is installed once */
    CHECK(m->prepare_calls <= 3);
    for (k = 0; k < m->nops; k++) {
        if (m->ops[k].kind == MOCK_IRQ_PREPARE) CHECK((m->ops[k].intmr & GBP_PI_HSP_BIT) == 0);   /* never published unmasked */
        if (m->ops[k].kind == MOCK_IRQ_UNMASK) CHECK((m->ops[k].intsr & GBP_PI_HSP_BIT) != 0);     /* never unmasked without a latched cause */
    }
    CHECK((m->violation_mask & (GBP_MOCK_VIOL_PREPARE_WHILE_UNMASKED | GBP_MOCK_VIOL_ISR_W1C_BEFORE_MASK | GBP_MOCK_VIOL_UNMASK_NO_HANDLER |
                                GBP_MOCK_VIOL_INSTALL_TWICE)) == 0);
    /* a mask that never took (synthetic) leaves the teardown's transfers "unmasked" in the mock's eyes: only then is that flag expected */
    if (res->h.mask_ok != 0) CHECK((m->violation_mask & GBP_MOCK_VIOL_DMA_WHILE_UNMASKED) == 0);
    CHECK(res->power_cycle_required == (res->a.control_written ? 1 : 0));
    CHECK(res->cycles_requested == 3);
    CHECK(res->completed_cycles <= res->deliveries && res->acks <= res->deliveries && res->rearms_completed <= res->completed_cycles);
    CHECK(res->rearms_attempted <= 2 && res->next_causes <= res->rearms_completed);
}

/* index in ops[] of the Nth unmask / the Nth handler entry / etc. */
static int nth(const struct gbp_mock *m, enum gbp_mock_op_kind kind, unsigned n) { return gbp_mock_nth_op(m, kind, BASE, 16, n); }
static int nth_irqw(const struct gbp_mock *m, unsigned n) { return gbp_mock_nth_op(m, MOCK_WR, BASE, 0xD, n); }
static int last_irq_read_before(const struct gbp_mock *m, int idx)
{
    int k, found = -1;
    for (k = 0; k < idx; k++) if (m->ops[k].kind == MOCK_RD && (((m->ops[k].addr - BASE) >> 20) & 0xFu) == 0xDu) found = k;
    return found;
}
static int first_intsr_w_between(const struct gbp_mock *m, int a, int b)
{
    int k;
    for (k = a + 1; k < b; k++) if (m->ops[k].kind == MOCK_INTSR_W) return k;
    return -1;
}

/* ---- the mandatory order of a full run (spec §43) ---- */
static void check_order_full(const struct gbp_mock *m)
{
    int ar_exp = gbp_mock_first_op(m, MOCK_AR_W, BASE, 16);
    int ctl_exp = gbp_mock_nth_op(m, MOCK_WR, BASE, 4, 1);
    int ctl_rest = gbp_mock_nth_op(m, MOCK_WR, BASE, 4, 2);
    int a1 = nth_irqw(m, W_A1), a2 = nth_irqw(m, W_A2);
    int inst = nth(m, MOCK_IRQ_INSTALL, 1);
    int stop = nth_irqw(m, W_STOP);
    int rest = nth(m, MOCK_IRQ_RESTORE, 1);
    int ar_rest = gbp_mock_last_op(m, MOCK_AR_W, BASE, 16);
    unsigned n;
    CHECK(ar_exp >= 0 && ctl_exp > ar_exp && a1 > ctl_exp && a2 > a1 && inst > a2);
    CHECK(gbp_mock_count_block_ops(m, MOCK_IRQ_INSTALL, BASE, 16) == 1);
    for (n = 0; n < 3; n++) {
        int prep = nth(m, MOCK_IRQ_PREPARE, n + 1);
        int unm = nth(m, MOCK_IRQ_UNMASK, n + 1);
        int entry = nth(m, MOCK_ISR_ENTRY, n + 1);
        int imask = nth(m, MOCK_ISR_MASK, n + 1);
        int iw1c = nth(m, MOCK_ISR_W1C, n + 1);
        int iexit = nth(m, MOCK_ISR_EXIT, n + 1);
        int ack = nth_irqw(m, W_ACK0 + 2u * n);
        int rearm = (n < 2) ? nth_irqw(m, W_REARM0 + 2u * n) : -1;
        int prev_rearm = n ? nth_irqw(m, W_REARM0 + 2u * (n - 1)) : inst;
        int mmask = -1, k;
        for (k = unm + 1; k < (int)m->nops; k++) if (m->ops[k].kind == MOCK_IRQ_MASK) { mmask = k; break; }
        CHECK(prep > prev_rearm);                                            /* generation published after the previous re-arm (cycle 0: after the install) */
        CHECK(unm > prep);                                                   /* PREPARE < UNMASK */
        CHECK(last_irq_read_before(m, unm) > prep);                          /* PREUNMASK-n reads between PREPARE and UNMASK */
        CHECK(entry > unm && imask > entry && iw1c > imask && iexit > iw1c); /* UNMASK < ISR entry < mask < W1C < exit */
        CHECK(mmask > iexit);                                                /* main re-mask after the handler */
        CHECK(ack > mmask);                                                  /* ACK never before delivery + re-mask */
        CHECK(last_irq_read_before(m, ack) > mmask);                         /* PREACK-n read between the re-mask and the ACK */
        if (n < 2) {
            int postack_rd = last_irq_read_before(m, rearm);
            int next_unm = nth(m, MOCK_IRQ_UNMASK, n + 2);
            CHECK(rearm > ack && postack_rd > ack);                          /* REARM only after the POSTACK read (clean boundary) */
            CHECK(first_intsr_w_between(m, rearm, next_unm) < 0);           /* no W1C at REARMPOST / during the next-cause wait */
            CHECK(nth(m, MOCK_IRQ_PREPARE, n + 2) > rearm);                  /* the next generation only after the re-arm */
            CHECK(next_unm > rearm);
        } else {
            CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xD) == 8 && nth_irqw(m, 8) == stop);   /* no REARM after cycle 2 */
        }
        /* the PI at the unmask had the cause latched; the prepare happened masked */
        CHECK((m->ops[(unsigned)unm].intsr & GBP_PI_HSP_BIT) != 0 && (m->ops[(unsigned)prep].intmr & GBP_PI_HSP_BIT) == 0);
    }
    CHECK(ctl_rest > nth_irqw(m, W_ACK2) && stop > ctl_rest && rest > stop && ar_rest > rest);
    CHECK(gbp_mock_last_op(m, MOCK_RD, BASE, 16) > ar_rest);                 /* FINAL last */
    CHECK(m->violations == 0);
}

/* the cycle-0 values every scenario with a normal first cycle must show */
static void check_cycle0(const struct gbp_mock *m, const struct gbp_initirq4_result *res)
{
    const struct gbp_initirq4_cycle *c = &res->cycles[0];
    CHECK(c->started && c->cause_ready && c->cause_immediate == 0 && c->prepared && c->prepare_rc == GBP_OK);
    CHECK(c->slot_before.count == 0 && c->slot_before.fired == 0 && c->multi_before.expected_gen == 0 && c->multi_before.entries_total == 0);
    CHECK(c->preunmask_ok == 1 && strcmp(c->preunmask_reason, "-") == 0 && c->preunmask.irq_gbi == 0x0500 && c->preunmask.control_vote == 0x8c);
    CHECK(c->d.irq_unmasked && c->d.fired && c->d.rec.count == 1 && c->d.reentry == 0 && c->d.main_mask_ok == 1 && c->delivered == 1);
    CHECK(c->multi_after.expected_gen == 0 && c->multi_after.entries_total == 1 && c->multi_after.generation_errors == 0 && c->multi_after.anomaly.count == 1);
    CHECK((c->d.rec.intsr_before_ack & GBP_PI_HSP_BIT) && (c->d.rec.intmr_at_entry & GBP_PI_HSP_BIT) && !(c->d.rec.intmr_after_mask & GBP_PI_HSP_BIT));
    CHECK(c->k.preack.irq_gbi == 0x0500 && c->k.ack_skipped == 0 && c->k.irq_pending == 0x0500 && c->k.ack_value == 0x8500);
    CHECK(c->k.w_ack.attempted && c->k.w_ack.completed && c->k.w_ack.raw[0x1e] == 0x85 && c->k.w_ack.raw[0x1f] == 0x00 && c->acked);
    CHECK(c->k.postack.irq_gbi == 0x8000 && c->boundary_ok == 1 && c->pi_clean == 1);
    CHECK(m->deliveries >= 1 && m->isr_w1c_count >= 1);
}

/* 1: three cycles, next causes after a quiet REARMPOST (A) */
static void test_three_cycles(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    unsigned n;
    mock_004(&m);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_OK_CYCLES_COMPLETED && strcmp(res.status_name, "ok_cycles_completed") == 0 && strcmp(res.reason, "-") == 0);
    CHECK(res.restore_ok == 1 && res.errors == 0 && res.transport_ok == 1 && res.power_cycle_required == 1 && res.uncertain_writes == 0);
    CHECK(strcmp(res.teardown_variant, "final_cycle") == 0 && res.stage_a_aborted == 0);
    CHECK(res.cycles_requested == 3 && res.cycles_started == 3 && res.completed_cycles == 3 && res.deliveries == 3 && res.acks == 3);
    CHECK(res.rearms_attempted == 2 && res.rearms_completed == 2 && res.next_causes == 2 && res.causes == 3 && res.unmasks == 3);
    CHECK(res.unexpected_sources == 0 && res.reentries == 0 && res.timeouts == 0 && res.generation_errors == 0 && res.entries_total == 3);
    CHECK(res.isr_w1c == 3 && res.main_w1c == 0 && res.teardown_w1c == 0 && res.control_ok == 1 && res.pi_sticky_final == 0);
    CHECK(res.h.handler_was_installed == 1 && res.h.handler_restored == 1 && res.h.mask_ok == 1 && res.h.old_handler_null == 1 && m.installed_calls == 1);
    CHECK(res.multi_final.expected_gen == 2 && res.multi_final.entries_total == 3 && res.multi_final.generation_errors == 0 && res.multi_final.anomaly.count == 1);
    check_cycle0(&m, &res);
    for (n = 0; n < 3; n++) {
        const struct gbp_initirq4_cycle *c = &res.cycles[n];
        CHECK(c->started && c->cause_ready && c->delivered && c->acked && c->boundary_ok && c->d.rec.count == 1);
        CHECK(c->multi_before.expected_gen == n && c->multi_before.entries_total == n && c->multi_after.entries_total == n + 1);
        CHECK(c->k.ack_value == (uint16_t)(c->k.preack.irq_gbi | 0x8000) && c->k.postack.irq_gbi == 0x8000 && c->k.main_pi_w1c == 0);
        CHECK(c->dt_cause_to_isr > 0 && c->dt_isr_second >= 100u && c->dt_isr_to_preack > 0 && c->dt_ack_to_postack > 0);
        if (n < 2) {
            CHECK(c->rearm_attempted && c->rearm_completed && c->w_rearm.value == 0 && c->w_rearm.raw[0x1e] == 0 && c->w_rearm.raw[0x1f] == 0);
            CHECK(c->rearm_before == 0x8000 && c->rearmpost_ok == 1 && c->rearmpost_outcome == GBP_INITIRQ4_REARMPOST_A_QUIET);
            CHECK(c->rearmpost.irq_gbi == 0x0000 && (c->rearmpost.intsr & GBP_PI_HSP_BIT) == 0 && c->rearmpost.control_vote == 0x8c);
            CHECK(c->cause_timed_out == 0 && c->cause_polls >= 1 && c->dt_postack_to_rearm > 0 && c->dt_rearm_to_next_cause >= 50u);
            CHECK((int32_t)(res.cycles[n + 1].t_cause - c->t_rearm) > 0 && res.cycles[n + 1].since_rearm == c->dt_rearm_to_next_cause);
            CHECK(res.cycles[n + 1].cause_immediate == 0 && res.cycles[n + 1].nextcause.taken && res.cycles[n + 1].nextcause.is_event);
        } else {
            CHECK(c->rearm_attempted == 0 && c->rearmpost_outcome == GBP_INITIRQ4_REARMPOST_NONE && c->dt_rearm_to_next_cause == 0);
        }
    }
    CHECK(res.cycles[1].cause_irq == 0x0500 && res.cycles[1].preunmask.irq_gbi == 0x0500 && res.cycles[1].k.ack_value == 0x8500);
    CHECK(res.cycles[2].cause_irq == 0x0400 && res.cycles[2].preunmask.irq_gbi == 0x0400 && res.cycles[2].k.ack_value == 0x8400);
    /* device side: three deliveries, three handler W1Cs, no main W1C, eight IRQ writes, one install, masked and restored */
    CHECK(m.deliveries == 3 && m.isr_w1c_count == 3 && m.intsr_writes == 0 && m.prepare_calls == 3 && m.unmask_calls == 3);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_WR, BASE, 0xD) == 8 && m.handler_installed == 0 && (m.intmr & GBP_PI_HSP_BIT) == 0);
    CHECK(m.arinfo == 0x0043 && m.irq_reg == 0x8aaa && m.isr_entries_multi == 3);
    CHECK(res.a.irq_writes_attempted == 8 && res.a.irq_writes_completed == 8 && res.a.stop_value == 0x8aaa && res.a.irq_stop_pre.gbi == 0x8000);
    check_never(&m, &res);
    check_order_full(&m);
    /* records */
    CHECK(count_lines_with(&rl, "INITIRQ4 start max_cycles=3 max_rearms=2") == 1 && count_lines_with(&rl, "INITIRQ4 policy handler=installed_once") == 1);
    CHECK(count_lines_with(&rl, "CAUSE n=0 t_cause=") == 1 && count_lines_with(&rl, "IRQ install rc=ok old_handler=null record_count=0 record_fired=0") == 1);
    CHECK(count_lines_with(&rl, "MULTI install expected_gen=0 entries_total=0 generation_errors=0 anomaly_count=1 anomaly_fired=0 slots=3") == 1);
    for (n = 0; n < 3; n++) {
        char s[160];
        snprintf(s, sizeof s, "CYCLE n=%u start", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "PREPARE n=%u gen=%u rc=ok intmr13=0 expected_gen=%u entries_total=%u generation_errors=0 slot_count=0 slot_fired=0", n, n, n, n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "SNAP tag=PREUNMASK-%u", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "PREUNMASK n=%u ok=1 reason=-", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "PREUNMASK4 n=%u av=", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "PI tag=UNMASKPRE-%u", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "UNMASK n=%u t_unmask=", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "PI tag=UNMASKPOST-%u", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "IRQ mask tag=MAIN n=%u rc=ok", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "WAIT n=%u fired=1 timed_out=0", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "PI tag=REMASKCHK-%u", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "HANDLER n=%u fired=1 count=1", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "HANDLERPI n=%u intsr_at_entry=", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "HANDLERPI2 n=%u t_second=", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "DELIVERY n=%u fired=1 count=1", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "HANDLER4 n=%u expected_gen=%u entries_total=%u generation_errors=0", n, n, n + 1); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "SNAP tag=PREACK-%u", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "PREACK n=%u intsr13=0,0 intmr13=0 control=8c", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "ACK n=%u before=", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "IRQW tag=ACK-%u ", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "SNAP tag=POSTACK-%u", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "POSTACK n=%u intsr13=0,0 intmr13=0 control=8c irq=8000/8000 src_pending=0000 bit15=1 ack=1/1", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "MAINPICLEANUP n=%u site=POSTACK performed=0", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "PICLEAN n=%u intsr=", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "BOUNDARY n=%u ok=1 completed_cycles=%u", n, n + 1); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "CYCLE n=%u end ", n); CHECK(count_lines_with(&rl, s) == 1);
        snprintf(s, sizeof s, "TIMING n=%u cause_to_isr=", n); CHECK(count_lines_with(&rl, s) == 1);
        if (n < 2) {
            snprintf(s, sizeof s, "REARM n=%u t_rearm=", n); CHECK(count_lines_with(&rl, s) == 1);
            snprintf(s, sizeof s, "IRQW tag=REARM-%u ", n); CHECK(count_lines_with(&rl, s) == 1);
            snprintf(s, sizeof s, "SNAP tag=REARMPOST-%u", n); CHECK(count_lines_with(&rl, s) == 1);
            snprintf(s, sizeof s, "REARMPOST n=%u t=", n); CHECK(count_lines_with(&rl, s) == 1);
            snprintf(s, sizeof s, "outcome=A_quiet ok=1"); CHECK(count_lines_with(&rl, s) == 2);
            snprintf(s, sizeof s, "SNAP tag=NEXTCAUSE-%u", n); CHECK(count_lines_with(&rl, s) == 1);
            snprintf(s, sizeof s, "NEXTCAUSE n=%u found=1 immediate=0", n); CHECK(count_lines_with(&rl, s) == 1);
        } else {
            CHECK(count_lines_with(&rl, "REARM n=2") == 0 && count_lines_with(&rl, "IRQW tag=REARM-2") == 0 && count_lines_with(&rl, "NEXTCAUSE n=2") == 0);
        }
    }
    CHECK(count_lines_with(&rl, "IRQW ") == 8 && count_lines_with(&rl, "layout=gbi-u16-replicated") == 8 + 2);   /* 8 IRQW records + 2 REARM records */
    CHECK(count_lines_with(&rl, "IRQW tag=A1 ") == 1 && count_lines_with(&rl, "IRQW tag=A2 ") == 1 && count_lines_with(&rl, "IRQW tag=STOP ") == 1);
    CHECK(count_lines_with(&rl, "TEARDOWN4 variant=final_cycle cycles_started=3 cycles_completed=3 rearms=2/2 deliveries=3 acks=3 unmasks=3") == 1);
    CHECK(count_lines_with(&rl, "pi_policy=unmasked_per_cycle") == 1 && count_lines_with(&rl, "pi_policy=never_unmasked") == 0);
    CHECK(count_lines_with(&rl, "CLEANUP performed=0") == 1 && count_lines_with(&rl, "IRQ restore rc=ok ok=1 old_handler=null") == 1);
    CHECK(count_lines_with(&rl, "INITIRQ4 end status=ok_cycles_completed reason=- restore=ok restore_reason=- teardown=final_cycle power_cycle_required=1 errors=0 transport_ok=1") == 1);
    CHECK(count_lines_with(&rl, "CYCLES requested=3 completed=3 causes=3 deliveries=3 acks=3 rearms=2 next_causes=2 reentry=0 unexpected=0 timeouts=0 isr_w1c=3 main_w1c=0 teardown_w1c=0") == 1);
    CHECK(count_lines_with(&rl, "MULTI expected_gen=2 entries_total=3 generation_errors=0 anomaly_count=1 anomaly_fired=0 unmasks=3") == 1);
    CHECK(count_lines_with(&rl, "RESTORE4 handler_installed=1 handler_restored=1 old_handler=null mask_ok=1") == 1);
    /* order of the records mirrors the sequence */
    CHECK(line_index_with(&rl, "SNAP tag=EVENT") < line_index_with(&rl, "CAUSE n=0"));
    CHECK(line_index_with(&rl, "CAUSE n=0") < line_index_with(&rl, "IRQ install"));
    CHECK(line_index_with(&rl, "IRQ install") < line_index_with(&rl, "PREPARE n=0"));
    CHECK(line_index_with(&rl, "PREPARE n=0") < line_index_with(&rl, "SNAP tag=PREUNMASK-0"));
    CHECK(line_index_with(&rl, "PREUNMASK n=0 ok=1") < line_index_with(&rl, "UNMASK n=0 t_unmask="));
    CHECK(line_index_with(&rl, "UNMASK n=0 t_unmask=") < line_index_with(&rl, "HANDLER n=0"));
    CHECK(line_index_with(&rl, "DELIVERY n=0") < line_index_with(&rl, "SNAP tag=PREACK-0"));
    CHECK(line_index_with(&rl, "SNAP tag=PREACK-0") < line_index_with(&rl, "IRQW tag=ACK-0"));
    CHECK(line_index_with(&rl, "IRQW tag=ACK-0") < line_index_with(&rl, "SNAP tag=POSTACK-0"));
    CHECK(line_index_with(&rl, "SNAP tag=POSTACK-0") < line_index_with(&rl, "PICLEAN n=0"));
    CHECK(line_index_with(&rl, "PICLEAN n=0") < line_index_with(&rl, "REARM n=0"));
    CHECK(line_index_with(&rl, "REARM n=0") < line_index_with(&rl, "IRQW tag=REARM-0"));
    CHECK(line_index_with(&rl, "IRQW tag=REARM-0") < line_index_with(&rl, "SNAP tag=REARMPOST-0"));
    CHECK(line_index_with(&rl, "REARMPOST n=0") < line_index_with(&rl, "SNAP tag=NEXTCAUSE-0"));
    CHECK(line_index_with(&rl, "NEXTCAUSE n=0 found=1") < line_index_with(&rl, "CYCLE n=1 start"));
    CHECK(line_index_with(&rl, "CYCLE n=1 start") < line_index_with(&rl, "PREPARE n=1"));
    CHECK(line_index_with(&rl, "IRQW tag=REARM-1") < line_index_with(&rl, "UNMASK n=2 t_unmask="));
    CHECK(line_index_with(&rl, "IRQW tag=ACK-2") < line_index_with(&rl, "TEARDOWN4 variant=final_cycle"));
    CHECK(line_index_with(&rl, "TEARDOWN4") < line_index_with(&rl, "CTLW tag=RESTORE"));
    CHECK(line_index_with(&rl, "CTLW tag=RESTORE") < line_index_with(&rl, "IRQW tag=STOP"));
    CHECK(line_index_with(&rl, "IRQW tag=STOP") < line_index_with(&rl, "PI tag=CLEANUPCHK"));
    CHECK(line_index_with(&rl, "PI tag=CLEANUPCHK") < line_index_with(&rl, "IRQ restore"));
    CHECK(line_index_with(&rl, "IRQ restore") < line_index_with(&rl, "MASK final"));
    CHECK(line_index_with(&rl, "MASK final") < line_index_with(&rl, "ARINFO restore"));
    CHECK(line_index_with(&rl, "ARINFO restore") < line_index_with(&rl, "SNAP tag=FINAL"));
    CHECK(rl.dropped == 0 && rl.truncated == 0 && max_line_len(&rl) < LINE_LEN - 1);
    {
        char s[1600];
        int len = gbp_initirq4_summary(&res, s, sizeof s);
        CHECK(len > 0 && (size_t)len < sizeof s);
        CHECK(strstr(s, "DONE status=ok_cycles_completed reason=- restore=ok restore_reason=- teardown=final_cycle verdict=present det=4/4 written=1 "
                        "irq_attempted=8 irq_completed=8 ctl_exp=1/1 a1=1/1 a2=1/1 stop=1/1 ctl_restore=1/1 uncertain=0 cause=1") != 0);
        CHECK(strstr(s, "handler=1 old=null cycles=3/3 completed=3 deliveries=3 acks=3 rearms=2/2 next_causes=2 unexpected=0 reentry=0 timeouts=0 "
                        "gen_errors=0 entries=3 isr_w1c=3 main_w1c=0 teardown_w1c=0 control_ok=1 pi_sticky_final=0 control_restore_ok=1 "
                        "irq_stop_write_ok=1 stop_post=8aaa pi_cleanup=0 handler_restored=1 mask_ok=1 arinfo_restore_ok=1 power_cycle_required=1 "
                        "errors=0 transport_ok=1") != 0);
    }
}

/* 2, 3: the next cause already latched at REARMPOST (B); the source visible before the PI latch (C) */
static void test_rearmpost_b_and_c(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    mock_004(&m); m.n_src_sched = 0; sched(&m, W_REARM0, 0, 0x0500); sched(&m, W_REARM1, 0, 0x0100);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_OK_CYCLES_COMPLETED && res.completed_cycles == 3 && res.next_causes == 2);
    CHECK(res.cycles[0].rearmpost_outcome == GBP_INITIRQ4_REARMPOST_B_LATCHED && res.cycles[1].rearmpost_outcome == GBP_INITIRQ4_REARMPOST_B_LATCHED);
    CHECK(res.cycles[0].rearmpost.irq_gbi == 0x0500 && (res.cycles[0].rearmpost.intsr & GBP_PI_HSP_BIT) != 0);
    CHECK(res.cycles[1].cause_immediate == 1 && res.cycles[1].cause_polls == 0 && res.cycles[1].nextcause.taken == 0);
    CHECK(res.cycles[1].t_cause == res.cycles[0].rearmpost.ticks && (int32_t)(res.cycles[1].t_cause - res.cycles[0].t_rearm) > 0);
    CHECK(res.cycles[2].cause_immediate == 1 && res.cycles[2].cause_irq == 0x0100 && res.cycles[2].k.ack_value == 0x8100);
    CHECK(count_lines_with(&rl, "outcome=B_latched ok=1") == 2 && count_lines_with(&rl, "NEXTCAUSE n=0 found=1 immediate=1") == 1);
    CHECK(count_lines_with(&rl, "SNAP tag=NEXTCAUSE") == 0);                  /* no extra reads for an immediate cause */
    check_never(&m, &res);
    check_order_full(&m);
    /* C: the register shows the source, the PI latches 30 ticks later */
    mock_004(&m); m.n_src_sched = 0; sched(&m, W_REARM0, 0, 0x0400); sched(&m, W_REARM1, 0, 0x0500); m.source_pi_delay = 30;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_OK_CYCLES_COMPLETED && res.completed_cycles == 3);
    CHECK(res.cycles[0].rearmpost_outcome == GBP_INITIRQ4_REARMPOST_C_SOURCE_BEFORE_PI && res.cycles[0].rearmpost.irq_gbi == 0x0400);
    CHECK((res.cycles[0].rearmpost.intsr & GBP_PI_HSP_BIT) == 0 && res.cycles[1].cause_immediate == 0 && res.cycles[1].cause_ready == 1);
    CHECK((res.cycles[1].nextcause.poll_intsr & GBP_PI_HSP_BIT) != 0 && res.cycles[1].nextcause.irq_gbi == 0x0400 && res.cycles[1].since_rearm >= 30u);
    CHECK(res.cycles[1].rearmpost_outcome == GBP_INITIRQ4_REARMPOST_C_SOURCE_BEFORE_PI && res.cycles[2].cause_irq == 0x0500);
    CHECK(count_lines_with(&rl, "outcome=C_source_before_pi ok=1") == 2 && count_lines_with(&rl, "NEXTCAUSE n=0 found=1 immediate=0") == 1);
    check_never(&m, &res);
    check_order_full(&m);
}

/* 4, 5: VIDEO/AUDIO in any order; each accepted source alone */
static void test_source_orders(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    static const uint16_t sets[4][3] = { { 0x0400, 0x0100, 0x0500 }, { 0x0100, 0x0100, 0x0100 }, { 0x0400, 0x0400, 0x0400 }, { 0x0500, 0x0500, 0x0500 } };
    unsigned i;
    for (i = 0; i < 4; i++) {
        mock_004(&m); m.source_assert_bits = sets[i][0]; m.n_src_sched = 0; sched(&m, W_REARM0, 50, sets[i][1]); sched(&m, W_REARM1, 50, sets[i][2]);
        run(&m, &rl, &res);
        CHECK(res.status == GBP_INITIRQ4_OK_CYCLES_COMPLETED && res.completed_cycles == 3 && res.unexpected_sources == 0);
        CHECK(res.cycles[0].k.ack_value == (sets[i][0] | 0x8000) && res.cycles[1].k.ack_value == (sets[i][1] | 0x8000) && res.cycles[2].k.ack_value == (sets[i][2] | 0x8000));
        CHECK(res.cycles[0].cause_irq == sets[i][0] && res.cycles[1].cause_irq == sets[i][1] && res.cycles[2].cause_irq == sets[i][2]);
        check_never(&m, &res);
        check_order_full(&m);
    }
}

/* 6–10: a source outside AV at every observation point: observed, never acknowledged, never a transport failure */
static void test_unexpected_sources(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    uint32_t mid;
    /* PREUNMASK-0: the first cause carries 0x0004 */
    mock_004(&m); m.source_assert_bits = 0x0504;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE && strcmp(res.reason, "unexpected_source_cycle_0") == 0);
    CHECK(res.cycles[0].unexpected == 0x0004 && strcmp(res.cycles[0].unexpected_site, "PREUNMASK") == 0 && res.unexpected_sources == 1);
    CHECK(res.unmasks == 0 && res.deliveries == 0 && m.deliveries == 0 && res.acks == 0 && res.rearms_attempted == 0 && res.transport_ok == 1);
    CHECK(strcmp(res.teardown_variant, "S2_before_unmask") == 0 && res.h.handler_restored == 1 && res.h.mask_ok == 1);
    CHECK(res.a.irq_stop_pre.gbi == 0x0504 && res.a.stop_value == 0x8fae && res.a.irq_stop_post.gbi == 0x8aaa);   /* the stop word, never an ACK */
    CHECK(res.a.pi_cleanup_performed == 1 && res.teardown_w1c == 1 && m.intsr_writes == 1);
    CHECK(count_lines_with(&rl, "PREUNMASK n=0 ok=0 reason=unexpected_source") == 1 && count_lines_with(&rl, "IRQW tag=ACK") == 0);
    CHECK(count_lines_with(&rl, "RAW PREUNMASK-0 idx=d") == 1);                /* the raw block is preserved */
    check_never(&m, &res);
    /* PREACK-0: 0x0004 asserts between the handler's second read and the PREACK read (tick found from the normal run) */
    mock_004(&m); run(&m, &rl, &res);
    mid = res.cycles[0].d.rec.t_second + 25u - res.a.t_a2;
    mock_004(&m); sched(&m, W_A2, mid, 0x0004);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE && strcmp(res.reason, "unexpected_source_cycle_0") == 0);
    CHECK(strcmp(res.cycles[0].unexpected_site, "PREACK") == 0 && res.cycles[0].unexpected == 0x0004 && res.cycles[0].k.preack.irq_gbi == 0x0504);
    CHECK(res.cycles[0].k.ack_skipped == 1 && strcmp(res.cycles[0].k.ack_skip_reason, "unexpected_source") == 0 && res.cycles[0].k.w_ack.attempted == 0);
    CHECK(res.deliveries == 1 && res.acks == 0 && res.rearms_attempted == 0 && res.completed_cycles == 0 && res.transport_ok == 1);
    CHECK(strcmp(res.teardown_variant, "S3_cycle_aborted") == 0 && count_lines_with(&rl, "ACK n=0 skipped=1 reason=unexpected_source") == 1);
    check_never(&m, &res);
    /* POSTACK-0: 0x0010 asserts right at the ACK */
    mock_004(&m); sched(&m, W_ACK0, 0, 0x0010);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE && strcmp(res.cycles[0].unexpected_site, "POSTACK") == 0 && res.cycles[0].unexpected == 0x0010);
    CHECK(res.acks == 1 && res.cycles[0].k.postack.irq_gbi == 0x8010 && res.rearms_attempted == 0 && res.completed_cycles == 0);
    CHECK(count_lines_with(&rl, "IRQW tag=ACK-0") == 1 && count_lines_with(&rl, "IRQW tag=REARM") == 0);
    check_never(&m, &res);
    /* REARMPOST-0: 0x0040 asserts at the re-arm → outcome D, no unmask afterwards */
    mock_004(&m); m.n_src_sched = 0; sched(&m, W_REARM0, 0, 0x0040);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE && strcmp(res.cycles[0].unexpected_site, "REARMPOST") == 0 && res.cycles[0].unexpected == 0x0040);
    CHECK(res.cycles[0].rearmpost_outcome == GBP_INITIRQ4_REARMPOST_D_UNEXPECTED && res.cycles[0].rearmpost_ok == 1 && res.completed_cycles == 1);
    CHECK(res.rearms_completed == 1 && res.unmasks == 1 && res.next_causes == 0 && strcmp(res.teardown_variant, "S4C_rearmpost_invalid") == 0);
    CHECK(res.a.irq_stop_pre.gbi == 0x0040 && res.a.stop_value == 0x8aea && count_lines_with(&rl, "outcome=D_unexpected ok=1") == 1);
    check_never(&m, &res);
    /* NEXTCAUSE-0: the next cause carries 0x0001 */
    mock_004(&m); m.n_src_sched = 0; sched(&m, W_REARM0, 50, 0x0501);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE && strcmp(res.cycles[0].unexpected_site, "NEXTCAUSE") == 0 && res.cycles[0].unexpected == 0x0001);
    CHECK(res.cycles[1].nextcause.irq_gbi == 0x0501 && res.cycles[1].cause_ready == 0 && res.unmasks == 1 && res.next_causes == 0);
    CHECK(strcmp(res.teardown_variant, "S4B_next_cause_latched") == 0 && res.a.pi_cleanup_performed == 1 && res.teardown_w1c == 1);
    CHECK(count_lines_with(&rl, "NEXTCAUSE n=0 found=1 immediate=0") == 1 && count_lines_with(&rl, "unexpected=0001") >= 1);
    /* the S4B teardown, step by step: CPU never unmasked again, no ACK of the latched cause, CONTROL restore, STOP =
     * current | 0x8AAA (0x0501 | 0x8AAA = 0x8FAB), one teardown W1C at most, handler restore, mask verified, AR_INFO */
    {
        int ack0 = nth_irqw(&m, W_ACK0), rearm0 = nth_irqw(&m, W_REARM0), stop = nth_irqw(&m, 5);
        int ctl_rest = gbp_mock_nth_op(&m, MOCK_WR, BASE, 4, 2), rest = nth(&m, MOCK_IRQ_RESTORE, 1), ar_rest = gbp_mock_last_op(&m, MOCK_AR_W, BASE, 16);
        CHECK(gbp_mock_count_block_ops(&m, MOCK_WR, BASE, 0xD) == 5 && res.acks == 1 && res.rearms_completed == 1);   /* A1 A2 ACK0 REARM0 STOP */
        CHECK(nth(&m, MOCK_IRQ_UNMASK, 2) < 0 && m.unmask_calls == 1 && (m.intmr & GBP_PI_HSP_BIT) == 0);          /* no second unmask, masked at the end */
        CHECK(res.a.irq_stop_pre.gbi == 0x0501 && res.a.stop_value == 0x8fab && res.a.w_stop.completed == 1 && res.a.irq_stop_post.gbi == 0x8aaa);
        CHECK(res.a.control_restore_ok == 1 && res.h.handler_restored == 1 && res.h.mask_ok == 1 && res.a.arinfo_restore_ok == 1 && res.restore_ok == 1);
        CHECK(ack0 < rearm0 && rearm0 < ctl_rest && ctl_rest < stop && stop < rest && rest < ar_rest);
        CHECK(first_intsr_w_between(&m, rearm0, stop) < 0 && m.intsr_writes == 1);                                    /* the only main W1C is the teardown's, after the STOP */
        CHECK(count_lines_with(&rl, "IRQW tag=ACK") == 1 && count_lines_with(&rl, "IRQW tag=REARM") == 1 && count_lines_with(&rl, "IRQW tag=STOP") == 1);
        CHECK(count_lines_with(&rl, "TEARDOWN4 variant=S4B_next_cause_latched cycles_started=1 cycles_completed=1 rearms=1/1 deliveries=1 acks=1 unmasks=1") == 1);
    }
    check_never(&m, &res);
}

/* 11, 12: the ACK does not clear the source; the PI stays latched after the cycle's single main W1C */
static void test_source_not_cleared_and_pi_sticky(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    mock_004(&m); m.ack_ignored_at_write = W_ACK0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_SOURCE_NOT_CLEARED && strcmp(res.reason, "source_pending_after_ack_cycle_0") == 0);
    CHECK(res.cycles[0].acked == 1 && res.cycles[0].k.postack.irq_gbi == 0x8500 && res.cycles[0].source_not_cleared == 1 && res.cycles[0].boundary_ok == 0);
    CHECK(res.acks == 1 && res.rearms_attempted == 0 && res.completed_cycles == 0 && gbp_mock_count_block_ops(&m, MOCK_WR, BASE, 0xD) == 4);   /* A1 A2 ACK STOP: no second ACK */
    CHECK(res.a.irq_stop_pre.gbi == 0x8500 && res.a.stop_value == 0x8faa && res.transport_ok == 1);
    check_never(&m, &res);
    mock_004(&m); m.ack_ignored_at_write = W_ACK1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_SOURCE_NOT_CLEARED && strcmp(res.reason, "source_pending_after_ack_cycle_1") == 0 && res.completed_cycles == 1);
    check_never(&m, &res);
    /* every W1C ignored: the handler's, then the POSTACK one (sticky), then the teardown's single one */
    mock_004(&m); m.intsr_w1c_ignored = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_PI_STICKY_AFTER_ACK && strcmp(res.reason, "pi_sticky_after_ack_cycle_0") == 0);
    CHECK(res.cycles[0].k.main_pi_w1c == 1 && res.cycles[0].k.main_w1c_sticky == 1 && res.cycles[0].pi_sticky == 1 && res.cycles[0].pi_clean == 0);
    CHECK(res.main_w1c == 1 && res.isr_w1c == 1 && res.teardown_w1c == 1 && m.intsr_writes == 2 && m.isr_w1c_count == 1);
    CHECK(res.acks == 1 && res.rearms_attempted == 0 && res.pi_sticky_final == 1 && res.restore_ok == 1);
    CHECK(count_lines_with(&rl, "MAINPICLEANUP n=0 site=POSTACK performed=1 value=00002000") == 1 && count_lines_with(&rl, "PICLEAN n=0") == 1);
    check_never(&m, &res);
}

/* 13: invalid state after the re-arm (E: odd / bit 15 / high bits) and INTSR latched without a source (F) */
static void hook_set_pi(struct gbp_mock *m, uint32_t addr, const uint8_t *data, void *user)
{
    (void)data; (void)user;
    if ((((addr - BASE) >> 20) & 0xFu) == 0xDu && m->irq_writes + 1u == W_REARM0) m->intsr |= GBP_PI_HSP_BIT;   /* synthetic PI glitch at the re-arm */
}

static void test_rearm_state(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    static const uint16_t sticky[3] = { 0x0AAA, 0x8000, 0x1000 };
    unsigned i;
    for (i = 0; i < 3; i++) {
        mock_004(&m); m.rearm_sticky_bits = sticky[i]; m.rearm_sticky_from_write = W_REARM0;
        run(&m, &rl, &res);
        CHECK(res.status == GBP_INITIRQ4_ANOMALY_REARM_STATE && strcmp(res.reason, "rearm_state_invalid_cycle_0") == 0);
        CHECK(res.cycles[0].rearmpost_outcome == GBP_INITIRQ4_REARMPOST_E_INVALID && res.cycles[0].rearmpost_ok == 0 && (res.cycles[0].rearmpost.irq_gbi & sticky[i]) == sticky[i]);
        CHECK(res.completed_cycles == 1 && res.rearms_completed == 1 && res.unmasks == 1 && res.next_causes == 0 && res.transport_ok == 1);
        CHECK(strcmp(res.teardown_variant, "S4C_rearmpost_invalid") == 0 && res.h.handler_restored == 1 && res.h.mask_ok == 1);
        CHECK(count_lines_with(&rl, "outcome=E_invalid ok=0") == 1 && count_lines_with(&rl, "IRQW tag=ACK") == 1);
        check_never(&m, &res);
    }
    mock_004(&m); m.write_hook = hook_set_pi;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_REARM_STATE && strcmp(res.reason, "rearmpost_pi_without_source_cycle_0") == 0);
    CHECK(res.cycles[0].rearmpost_outcome == GBP_INITIRQ4_REARMPOST_F_INCONSISTENT && res.cycles[0].rearmpost.irq_gbi == 0 && (res.cycles[0].rearmpost.intsr & GBP_PI_HSP_BIT));
    CHECK(res.unmasks == 1 && res.a.pi_cleanup_performed == 1 && res.teardown_w1c == 1 && count_lines_with(&rl, "outcome=F_inconsistent") == 1);
    check_never(&m, &res);
}

/* 14: no next cause within the bound after a completed re-arm (S4A: stop word from a register that reads 0) */
static void test_no_next_cause(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    mock_004(&m); m.n_src_sched = 0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_NO_NEXT_CAUSE && strcmp(res.reason, "no_next_cause_cycle_0") == 0 && strcmp(res.teardown_variant, "S4A_rearmed_no_next_cause") == 0);
    CHECK(res.cycles[0].rearmpost_outcome == GBP_INITIRQ4_REARMPOST_A_QUIET && res.cycles[0].cause_timed_out == 1 && res.cycles[0].cause_polls >= T_NEXT_CAUSE / 10u - 2u);
    CHECK(res.completed_cycles == 1 && res.rearms_completed == 1 && res.next_causes == 0 && res.unmasks == 1 && res.cycles[1].started == 0);
    CHECK(res.a.irq_stop_pre.gbi == 0x0000 && res.a.stop_value == 0x8aaa && res.a.irq_stop_post.gbi == 0x8aaa);   /* IRQ := 0 | 0x8AAA */
    CHECK(res.a.pi_cleanup_performed == 0 && res.teardown_w1c == 0 && res.restore_ok == 1 && res.transport_ok == 1);
    CHECK(count_lines_with(&rl, "NEXTCAUSE n=0 found=0 timed_out=1 t_end=") == 1 && count_lines_with(&rl, "SNAP tag=NEXTCAUSE") == 0);
    CHECK(count_lines_with(&rl, "INITIRQ4 end status=no_next_cause reason=no_next_cause_cycle_0 restore=ok") == 1);
    check_never(&m, &res);
    /* the next cause late but within the bound */
    mock_004(&m); m.n_src_sched = 0; sched(&m, W_REARM0, T_NEXT_CAUSE - 200u, 0x0500); sched(&m, W_REARM1, 10, 0x0500);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_OK_CYCLES_COMPLETED && res.cycles[1].since_rearm >= T_NEXT_CAUSE - 200u && res.cycles[0].cause_polls > 100u);
    check_never(&m, &res);
    /* no next cause after the second re-arm */
    mock_004(&m); m.n_src_sched = 0; sched(&m, W_REARM0, 50, 0x0500);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_NO_NEXT_CAUSE && strcmp(res.reason, "no_next_cause_cycle_1") == 0 && res.completed_cycles == 2 && res.rearms_completed == 2);
    check_never(&m, &res);
}

/* 15–17: reentry in the same generation, a generation out of range, a slot that already fired */
static void test_reentry_and_generation(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    mock_004(&m); m.second_delivery_at = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_REENTRY && strcmp(res.reason, "reentry_cycle_0") == 0);
    CHECK(res.cycles[0].d.fired == 1 && res.cycles[0].d.rec.count == 2 && res.cycles[0].d.reentry == 1 && res.reentries == 1);
    CHECK(m.deliveries == 2 && m.isr_w1c_count == 1 && res.acks == 0 && res.cycles[0].k.w_ack.attempted == 0 && res.rearms_attempted == 0);
    CHECK(res.cycles[0].multi_after.entries_total == 2 && res.entries_total == 2 && res.h.handler_restored == 1 && res.h.mask_ok == 1);
    check_never(&m, &res);
    mock_004(&m); m.second_delivery_at = 2;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_REENTRY && strcmp(res.reason, "reentry_cycle_1") == 0 && res.completed_cycles == 1 && res.rearms_completed == 1);
    CHECK(res.cycles[1].d.rec.count == 2 && res.cycles[0].d.rec.count == 1 && m.isr_w1c_count == 2 && res.acks == 1);
    check_never(&m, &res);
    /* the published generation corrupted to 7 at the first unmask: the handler counts it, services the poisoned slot without a W1C */
    mock_004(&m); m.force_gen_valid = 1; m.force_expected_gen = 7;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_GENERATION && strcmp(res.reason, "generation_out_of_range_cycle_0") == 0);
    CHECK(res.cycles[0].d.fired == 0 && res.cycles[0].d.timed_out == 1 && res.cycles[0].multi_after.generation_errors == 1);
    /* the poisoned slot took the body's reentry branch: count 2, the reentry fields, fired (as any reentry), NO W1C */
    CHECK(res.cycles[0].multi_after.anomaly.count == 2 && res.cycles[0].multi_after.anomaly.fired == 1 && res.cycles[0].multi_after.anomaly.reentry_t != 0);
    CHECK(res.cycles[0].multi_after.entries_total == 1 && res.cycles[0].d.rec.fired == 0);
    CHECK(m.deliveries == 1 && m.isr_w1c_count == 0 && m.multi.slots[0].count == 0 && m.multi.slots[1].count == 0 && m.multi.slots[2].count == 0);
    CHECK((m.intmr & GBP_PI_HSP_BIT) == 0 && res.deliveries == 0 && res.acks == 0 && res.generation_errors == 1);
    CHECK(res.a.pi_cleanup_performed == 1 && res.teardown_w1c == 1 && m.intsr_writes == 1);       /* the latched cause cleared once, in the teardown */
    check_never(&m, &res);
    /* generation corrupted to 0 at the second unmask: slot 0 already fired → the body's reentry branch, no W1C, no delivery in slot 1 */
    mock_004(&m); m.force_gen_valid = 1; m.force_expected_gen = 0; m.force_gen_at_unmask = 2;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_REENTRY && strcmp(res.reason, "entry_outside_slot_cycle_1") == 0 && res.completed_cycles == 1);
    CHECK(res.cycles[1].d.fired == 0 && res.cycles[1].multi_after.entries_total == 2 && m.multi.slots[0].count == 2 && m.multi.slots[1].count == 0);
    CHECK(m.isr_w1c_count == 1 && res.acks == 1 && res.rearms_completed == 1 && res.reentries == 1);
    check_never(&m, &res);
    /* a slot found dirty at PREPARE-1 (synthetic): generation anomaly, no unmask */
    mock_004(&m); m.record_dirty_on_install = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "record_not_clear") == 0 && res.unmasks == 0);
    CHECK(count_lines_with(&rl, "IRQ install rc=ok old_handler=null record_count=1 record_fired=0") == 1);
    check_never(&m, &res);
}

/* 18, 19: an ACK / a re-arm whose completion the transport did not report (device state uncertain) */
static void test_write_failures(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    static const struct { unsigned at; const char *reason; unsigned completed, acks, rearms_att, rearms_comp; } cases[5] = {
        { W_ACK0, "ack_write_failed_cycle_0", 0, 0, 0, 0 }, { W_ACK1, "ack_write_failed_cycle_1", 1, 1, 1, 1 }, { W_ACK2, "ack_write_failed_cycle_2", 2, 2, 2, 2 },
        { W_REARM0, "rearm_write_failed_cycle_0", 1, 1, 1, 0 }, { W_REARM1, "rearm_write_failed_cycle_1", 2, 2, 2, 1 } };
    unsigned i;
    for (i = 0; i < 5; i++) {
        mock_004(&m); m.irq_write_fail_at = cases[i].at;
        run(&m, &rl, &res);
        CHECK(res.status == GBP_INITIRQ4_ABORT_TRANSPORT && strcmp(res.reason, cases[i].reason) == 0);
        CHECK(res.completed_cycles == cases[i].completed && res.acks == cases[i].acks && res.rearms_attempted == cases[i].rearms_att && res.rearms_completed == cases[i].rearms_comp);
        CHECK(res.uncertain_writes == 1 && res.transport_ok == 0 && res.power_cycle_required == 1 && res.unmasks == cases[i].completed + (cases[i].at & 1u));
        CHECK(res.a.irq_writes_attempted == cases[i].at + 1u && res.a.irq_writes_completed == cases[i].at);   /* + the stop word */
        CHECK(res.h.handler_restored == 1 && res.h.mask_ok == 1 && res.restore_ok == 1 && res.a.irq_stop_write_ok == 1);
        if (cases[i].at & 1u) CHECK(strcmp(res.teardown_variant, "S3_cycle_aborted") == 0 && res.cycles[cases[i].completed].k.w_ack.attempted == 1 && res.cycles[cases[i].completed].k.w_ack.completed == 0);
        else CHECK(strcmp(res.teardown_variant, "S4_rearm_failed") == 0 && res.cycles[cases[i].completed - 1u].w_rearm.attempted == 1 && res.cycles[cases[i].completed - 1u].w_rearm.completed == 0);
        CHECK((unsigned)count_lines_with(&rl, "IRQW tag=REARM") == cases[i].rearms_att && count_lines_with(&rl, "IRQW tag=STOP") == 1);
        check_never(&m, &res);
    }
    /* the stop word fails: the cycles completed, the restore did not */
    mock_004(&m); m.irq_write_fail_at = W_STOP;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_CYCLES_COMPLETED_WITH_ERRORS && strcmp(res.reason, "uncertain_write") == 0 && res.completed_cycles == 3);
    CHECK(res.restore_ok == 0 && strcmp(res.restore_reason, "irq_stop_write_failed") == 0 && res.uncertain_writes == 1 && res.h.handler_restored == 1);
    check_never(&m, &res);
}

/* 20: the mask does not take (cycle 0, and from cycle 1's handler mask on) */
static void test_mask_failure(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    mock_004(&m); m.mask_ignored = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_MASK_FAILURE && strcmp(res.reason, "intmr13_still_set_after_remask_cycle_0") == 0);
    CHECK(res.cycles[0].d.fired == 1 && res.cycles[0].d.main_mask_ok == 0 && res.cycles[0].d.remask_retry == 1 && res.acks == 0 && res.rearms_attempted == 0);
    CHECK(res.h.mask_ok == 0 && res.restore_ok == 0 && strcmp(res.restore_reason, "mask_not_restored") == 0 && m.deliveries == 1);
    check_never(&m, &res);
    mock_004(&m); m.mask_ignored_from_call = 3;                                /* cycle 1: the handler's mask (3rd mask call) and every later one */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_MASK_FAILURE && strcmp(res.reason, "intmr13_still_set_after_remask_cycle_1") == 0 && res.completed_cycles == 1);
    CHECK(res.cycles[0].d.main_mask_ok == 1 && res.cycles[1].d.main_mask_ok == 0 && res.acks == 1 && res.rearms_completed == 1 && m.deliveries == 2);
    check_never(&m, &res);
}

/* 21: CONTROL changes by itself (never rewritten per cycle: observed at the next check, then the teardown) */
static void test_control_changed(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    mock_004(&m); m.control_change_after_irq_write = W_ACK0; m.control_change_value = 0x90;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_CONTROL_CHANGED && strcmp(res.reason, "control_changed_postack_cycle_0") == 0);
    CHECK(res.cycles[0].k.postack.control_vote == 0x90 && res.control_ok == 0 && res.acks == 1 && res.rearms_attempted == 0);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_WR, BASE, 4) == 2 && res.a.control_restore_ok == 1);   /* only the transform and the final restore */
    check_never(&m, &res);
    mock_004(&m); m.control_change_after_irq_write = W_REARM0; m.control_change_value = 0x90;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_CONTROL_CHANGED && strcmp(res.reason, "control_changed_rearmpost_cycle_0") == 0 && res.cycles[0].rearmpost_ok == 0);
    CHECK(strcmp(res.teardown_variant, "S4C_rearmpost_invalid") == 0 && res.unmasks == 1 && res.next_causes == 0);
    check_never(&m, &res);
    mock_004(&m); m.control_on_install = 0x90;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_CONTROL_CHANGED && strcmp(res.reason, "control_changed_preunmask_cycle_0") == 0 && res.unmasks == 0);
    check_never(&m, &res);
    /* seen first at PREUNMASK-1 (the NEXTCAUSE snapshot only records it) */
    mock_004(&m); m.control_change_after_irq_write = W_REARM0; m.control_change_value = 0x8d;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_CONTROL_CHANGED && res.completed_cycles == 1);
    check_never(&m, &res);
}

/* 22, 23: delivery timeout (cycle 0 and cycle 1); the source vanishes before the ACK */
static void test_timeout_and_source_lost(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    mock_004(&m); m.delivery_suppressed = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_DELIVERY_TIMEOUT && strcmp(res.reason, "delivery_timeout_cycle_0") == 0 && res.timeouts == 1);
    CHECK(res.cycles[0].d.timed_out == 1 && res.cycles[0].d.wait_ticks >= T_DELIVERY && res.cycles[0].d.main_mask_ok == 1 && res.deliveries == 0);
    CHECK(res.acks == 0 && res.a.pi_cleanup_performed == 1 && res.teardown_w1c == 1 && res.a.stop_value == 0x8faa && res.h.mask_ok == 1);
    CHECK(count_lines_with(&rl, "WAIT n=0 fired=0 timed_out=1") == 1 && strcmp(res.teardown_variant, "S3_cycle_aborted") == 0);
    check_never(&m, &res);
    mock_004(&m); m.suppress_delivery_at = 2;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_DELIVERY_TIMEOUT && strcmp(res.reason, "delivery_timeout_cycle_1") == 0 && res.completed_cycles == 1 && res.rearms_completed == 1);
    CHECK(res.cycles[1].d.timed_out == 1 && res.deliveries == 1 && res.acks == 1 && m.deliveries == 1 && res.teardown_w1c == 1);
    check_never(&m, &res);
    mock_004(&m); m.unmask_ignored = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_UNMASK && strcmp(res.reason, "unmask_not_effective_cycle_0") == 0 && m.deliveries == 0);
    check_never(&m, &res);
    mock_004(&m); m.source_clear_at_delivery = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_SOURCE_LOST_BEFORE_ACK && strcmp(res.reason, "source_lost_before_ack_cycle_0") == 0);
    CHECK(res.cycles[0].source_lost == 1 && res.cycles[0].k.preack.irq_gbi == 0x0000 && res.cycles[0].k.w_ack.attempted == 0 && res.acks == 0);
    CHECK(strcmp(res.cycles[0].k.ack_skip_reason, "source_lost") == 0 && res.deliveries == 1 && res.transport_ok == 1);
    check_never(&m, &res);
    mock_004(&m); m.source_clear_at_delivery = 3;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_SOURCE_LOST_BEFORE_ACK && strcmp(res.reason, "source_lost_before_ack_cycle_2") == 0 && res.completed_cycles == 2);
    check_never(&m, &res);
}

/* 24–27: no initial cause; the stage-A aborts; install failure / no multi path; PREUNMASK-0 failures */
static void test_early_aborts(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    gbp_mock_init(&m); m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK; m.isr_multi = 1;   /* no source ever asserts */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_NO_INITIAL_CAUSE && strcmp(res.status_name, "no_initial_cause") == 0 && strcmp(res.reason, "no_intsr13_within_t_max") == 0);
    CHECK(res.a.a2_obs_taken == 6 && m.installed_calls == 0 && res.unmasks == 0 && res.cycles[0].started == 0 && res.h.handler_restored == -1);
    CHECK(count_lines_with(&rl, "IRQ install") == 0 && count_lines_with(&rl, "pi_policy=never_unmasked") == 1 && strcmp(res.teardown_variant, "S2_before_unmask") == 0);
    check_never(&m, &res);
    gbp_mock_init(&m); m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK; m.isr_multi = 1; m.present = 0; m.absent_fill = 0xC1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_STAGE_A && res.stage_a_aborted == 1 && strcmp(res.status_name, "abort_not_present") == 0);
    CHECK(res.a.control_written == 0 && res.power_cycle_required == 0 && strcmp(res.teardown_variant, "stage_a") == 0);
    CHECK(count_lines_with(&rl, "INITIRQA end status=abort_not_present") == 1 && count_lines_with(&rl, "INITIRQ4 end status=abort_not_present") == 1);
    {
        char s[1600];
        CHECK(gbp_initirq4_summary(&res, s, sizeof s) > 0);
        CHECK(strstr(s, "DONE status=abort_not_present reason=absent restore=ok restore_reason=- teardown=stage_a verdict=absent det=0/4 written=0 "
                        "irq_attempted=0 irq_completed=0 ctl_exp=0/0 a1=0/0 a2=0/0 stop=0/0 ctl_restore=0/0 uncertain=0 cause=0 t_event=0 handler=0 old=? "
                        "cycles=0/3 completed=0 deliveries=0 acks=0 rearms=0/0 next_causes=0 unexpected=0 reentry=0 timeouts=0 gen_errors=0 entries=0 "
                        "isr_w1c=0 main_w1c=0 teardown_w1c=0 control_ok=1 pi_sticky_final=0 control_restore_ok=-1 irq_stop_write_ok=-1 stop_post=0000 "
                        "pi_cleanup=0 handler_restored=-1 mask_ok=-1 arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1") != 0);
    }
    check_never(&m, &res);
    gbp_mock_init(&m); m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK; m.isr_multi = 1; m.intsr = GBP_PI_HSP_BIT;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_STAGE_A && strcmp(res.status_name, "abort_pi_precondition") == 0 && m.control_writes == 0);
    gbp_mock_init(&m); m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK; m.isr_multi = 1; m.control_byte = 0x03;
    run(&m, &rl, &res);
    CHECK(strcmp(res.status_name, "abort_control_shape") == 0 && m.control_writes == 0);
    gbp_mock_init(&m); m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK; m.isr_multi = 1; m.irq_reg = 0x0aae;
    run(&m, &rl, &res);
    CHECK(strcmp(res.status_name, "abort_irq_shape") == 0 && m.control_writes == 0);
    check_never(&m, &res);
    mock_004(&m); m.install_fails = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_HANDLER_INSTALL && strcmp(res.reason, "install_failed") == 0 && res.unmasks == 0 && res.a.pi_cleanup_performed == 1);
    check_never(&m, &res);
    mock_004(&m); m.irq_ops_available = 0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_HANDLER_INSTALL && strcmp(res.reason, "irq_multi_ops_unavailable") == 0 && count_lines_with(&rl, "IRQ install rc=unavailable multi_path=0") == 1);
    mock_004(&m); m.clear_cause_on_install = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "cause_lost") == 0 && res.unmasks == 0 && res.h.handler_restored == 1);
    /* INTMR bit 13 found set by the two PREUNMASK-0 samples (the install cannot change INTMR on the real backend, ENV-IRQ-002;
     * the EVENT sample is the publication's evidence): no unmask, the teardown re-masks */
    mock_004(&m); m.intmr13_set_on_install = 1; m.delivery_suppressed = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "intmr13_unmasked") == 0 && res.unmasks == 0 && m.prepare_calls == 1);
    CHECK(count_lines_with(&rl, "PREUNMASK n=0 ok=0 reason=intmr13_unmasked") == 1 && res.h.mask_ok == 1 && res.deliveries == 0);
    mock_004(&m); m.irq_reg_on_install = 0x8500;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "irq_state_unexpected") == 0 && res.unmasks == 0);
    mock_004(&m); m.irq_disagree_on_install = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "semantic_disagree") == 0 && res.unmasks == 0);
    mock_004(&m); m.old_handler_nonnull = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_OK_CYCLES_COMPLETED && res.h.old_handler_null == 0 && count_lines_with(&rl, "IRQ restore rc=ok ok=1 old_handler=nonnull") == 1);
    check_never(&m, &res);
    check_order_full(&m);
}

/* 28: readings that disagree at a per-cycle read; failed reads at PREACK / PREUNMASK */
static void test_read_problems(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    mock_004(&m); m.irq_disagree_from_write = W_ACK0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_READ_INCONSISTENT && strcmp(res.reason, "postack_semantic_disagree_cycle_0") == 0 && res.acks == 1 && res.rearms_attempted == 0);
    check_never(&m, &res);
    mock_004(&m); m.irq_disagree_from_write = W_REARM0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ABORT_READ_INCONSISTENT && strcmp(res.reason, "rearmpost_semantic_disagree_cycle_0") == 0 && res.unmasks == 1);
    check_never(&m, &res);
    /* the PREACK-0 IRQ read fails (block transfer number found from a normal run's transfer count) */
    {
        unsigned preack_xfer;
        mock_004(&m); run(&m, &rl, &res);
        preack_xfer = (unsigned)gbp_mock_count_block_ops(&m, MOCK_RD, BASE, 16) + (unsigned)gbp_mock_count_block_ops(&m, MOCK_WR, BASE, 16);
        (void)preack_xfer;
        {
            int idx = last_irq_read_before(&m, nth_irqw(&m, W_ACK0));
            unsigned k, xfer = 0;
            for (k = 0; k <= (unsigned)idx; k++) if (m.ops[k].kind == MOCK_RD || m.ops[k].kind == MOCK_WR) xfer++;
            mock_004(&m); m.fail_at_op = xfer; m.fail_rc = GBP_ERR_TIMEOUT;
            run(&m, &rl, &res);
            CHECK(res.status == GBP_INITIRQ4_ABORT_TRANSPORT && strcmp(res.reason, "preack_read_failed_cycle_0") == 0);
            CHECK(res.cycles[0].k.preack.irq_rc != GBP_OK && res.cycles[0].k.w_ack.attempted == 0 && res.acks == 0 && res.transport_ok == 0);
            check_never(&m, &res);
        }
    }
}

/* 29: attempted/completed sampled at the moment the transport is invoked: ACK and REARM of every cycle */
struct call_sample { int ack_att[3], ack_comp[3], rearm_att[2], rearm_comp[2], pcr; unsigned irq_att, irq_comp, rearms_att, rearms_comp;
                     unsigned completed, deliveries, acks; uint16_t value; };
static struct gbp_initirq4_result *hook_res;
static struct call_sample samples[10];
static unsigned nsamples;

static void sample_hook(struct gbp_mock *m, uint32_t addr, const uint8_t *data, void *user)
{
    struct call_sample *s; unsigned i;
    (void)m; (void)data; (void)user;
    if ((((addr - BASE) >> 20) & 0xFu) != 0xDu || nsamples >= 10u) return;
    s = &samples[nsamples++];
    for (i = 0; i < 3; i++) { s->ack_att[i] = hook_res->cycles[i].k.w_ack.attempted; s->ack_comp[i] = hook_res->cycles[i].k.w_ack.completed; }
    for (i = 0; i < 2; i++) { s->rearm_att[i] = hook_res->cycles[i].w_rearm.attempted; s->rearm_comp[i] = hook_res->cycles[i].w_rearm.completed; }
    s->pcr = hook_res->a.power_cycle_required;
    s->irq_att = hook_res->a.irq_writes_attempted; s->irq_comp = hook_res->a.irq_writes_completed;
    s->rearms_att = hook_res->rearms_attempted; s->rearms_comp = hook_res->rearms_completed;
    s->completed = hook_res->completed_cycles; s->deliveries = hook_res->deliveries; s->acks = hook_res->acks;
    s->value = (uint16_t)((data[0x1e] << 8) | data[0x1f]);
}

static void test_attempted_at_call_time(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res; struct gbp_transport t; struct gbp_initirq4_config cfg;
    mock_004(&m); m.write_hook = sample_hook; hook_res = &res; nsamples = 0; memset(samples, 0, sizeof samples);
    test_config(&cfg); gbp_mock_transport(&m, &t); ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_initirq4_probe_run(&t, &rl, &cfg, &res);
    CHECK(nsamples == 8);                                                    /* A1 A2 ACK0 REARM0 ACK1 REARM1 ACK2 STOP */
    CHECK(samples[2].ack_att[0] == 1 && samples[2].ack_comp[0] == 0 && samples[2].irq_att == 3 && samples[2].irq_comp == 2 && samples[2].pcr == 1);
    CHECK(samples[3].rearm_att[0] == 1 && samples[3].rearm_comp[0] == 0 && samples[3].rearms_att == 1 && samples[3].rearms_comp == 0 && samples[3].irq_att == 4 && samples[3].irq_comp == 3);
    CHECK(samples[4].ack_att[1] == 1 && samples[4].ack_comp[1] == 0 && samples[4].rearm_comp[0] == 1 && samples[4].rearms_comp == 1 && samples[4].irq_att == 5 && samples[4].irq_comp == 4);
    CHECK(samples[5].rearm_att[1] == 1 && samples[5].rearm_comp[1] == 0 && samples[5].rearms_att == 2 && samples[5].rearms_comp == 1 && samples[5].irq_att == 6 && samples[5].irq_comp == 5);
    CHECK(samples[6].ack_att[2] == 1 && samples[6].ack_comp[2] == 0 && samples[6].rearm_comp[1] == 1 && samples[6].irq_att == 7 && samples[6].irq_comp == 6);
    CHECK(samples[7].ack_comp[2] == 1 && samples[7].irq_att == 8 && samples[7].irq_comp == 7 && samples[7].rearm_att[1] == 1);
    /* 5 logical call sites, 8 executions: the value sequence of a complete run, and the cycle / re-arm counters at the moment
     * of each call (no off-by-one; a REARM after cycle 2 would appear as a ninth write of 0000 before the STOP) */
    {
        static const uint16_t values[8] = { 0x8aae, 0x0000, 0x8500, 0x0000, 0x8500, 0x0000, 0x8400, 0x8aaa };
        static const unsigned completed[8] = { 0, 0, 0, 1, 1, 2, 2, 3 }, rearms_comp[8] = { 0, 0, 0, 0, 1, 1, 2, 2 };
        static const unsigned rearms_att[8] = { 0, 0, 0, 1, 1, 2, 2, 2 }, deliveries[8] = { 0, 0, 1, 1, 2, 2, 3, 3 }, acks[8] = { 0, 0, 0, 1, 1, 2, 2, 3 };
        unsigned i;
        for (i = 0; i < 8; i++) {
            CHECK(samples[i].value == values[i]);
            CHECK(samples[i].completed == completed[i] && samples[i].rearms_comp == rearms_comp[i] && samples[i].rearms_att == rearms_att[i]);
            CHECK(samples[i].deliveries == deliveries[i] && samples[i].acks == acks[i]);
        }
        CHECK(res.completed_cycles == 3 && res.rearms_completed == 2 && res.rearms_attempted == 2 && samples[7].value == 0x8aaa);
    }
    /* the first re-arm fails: attempted 1, completed 0 at call time and afterwards; no unmask follows */
    mock_004(&m); m.write_hook = sample_hook; m.irq_write_fail_at = W_REARM0; nsamples = 0;
    gbp_mock_transport(&m, &t); ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_initirq4_probe_run(&t, &rl, &cfg, &res);
    CHECK(nsamples == 5 && samples[3].rearm_att[0] == 1 && samples[3].rearm_comp[0] == 0 && res.cycles[0].w_rearm.completed == 0 && res.unmasks == 1);
    m.write_hook = 0;
}

/* 30–33: wrapping time base, worst-case line widths, ring overflow, power cycle never cleared, config */
static void test_wrap_lines_and_config(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res;
    mock_004(&m); m.old_handler_nonnull = 1; m.tick = 0xFFFFFF00u; m.intsr = 0x00010000u; m.intmr = 0x000001fau;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_OK_CYCLES_COMPLETED && res.cycles[0].d.latency_ticks < 1000u && res.cycles[1].since_rearm < 1000u && res.cycles[2].since_rearm < 1000u);
    CHECK(res.cycles[0].dt_cause_to_isr < 5000u && res.cycles[1].dt_rearm_to_next_cause < 1000u);
    CHECK(rl.truncated == 0 && rl.dropped == 0 && max_line_len(&rl) < LINE_LEN - 1 && res.power_cycle_required == 1);
    /* longest status / reason / restore_reason / teardown variant with 10-digit ticks and worst-case values */
    mock_004(&m); m.rearm_sticky_bits = 0x0AAA; m.rearm_sticky_from_write = W_REARM0; m.restore_fails = 1; m.tick = 0xFFFFFF00u; m.intsr = 0x00010000u; m.intmr = 0x000001fau;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_REARM_STATE && res.restore_ok == 0 && strcmp(res.restore_reason, "handler_restore_failed") == 0);
    CHECK(rl.truncated == 0 && rl.dropped == 0 && max_line_len(&rl) < LINE_LEN - 1);
    CHECK(count_lines_with(&rl, "INITIRQ4 end status=anomaly_rearm_state reason=rearm_state_invalid_cycle_0 restore=error restore_reason=handler_restore_failed teardown=S4C_rearmpost_invalid power_cycle_required=1") == 1);
    mock_004(&m); m.n_src_sched = 0; m.tick = 0xFFFFFF00u;                    /* S4A with a wrapping time base: the wait spans the wrap */
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_NO_NEXT_CAUSE && rl.truncated == 0 && max_line_len(&rl) < LINE_LEN - 1 && res.cycles[0].cause_polls < T_NEXT_CAUSE);
    mock_004(&m); m.intsr_w1c_ignored = 1; m.mask_ignored = 1; m.max_deliveries = 1; m.tick = 0xFFFFFF00u;
    run(&m, &rl, &res);
    CHECK(rl.truncated == 0 && max_line_len(&rl) < LINE_LEN - 1);
    mock_004(&m); m.ack_ignored_at_write = W_ACK2; m.restore_fails = 1; m.control_write_fail_at = 2; m.arinfo_write_fail_at = 2; m.tick = 0xFFFFFF00u;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_ANOMALY_SOURCE_NOT_CLEARED && res.power_cycle_required == 1 && res.restore_ok == 0 && rl.truncated == 0 && max_line_len(&rl) < LINE_LEN - 1);
    /* restore failures never clear power_cycle_required and never change a completed status silently */
    mock_004(&m); m.restore_fails = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_CYCLES_COMPLETED_WITH_ERRORS && strcmp(res.reason, "handler_restore_failed") == 0 && res.completed_cycles == 3 && res.power_cycle_required == 1);
    CHECK(count_lines_with(&rl, "IRQ restore rc=backend ok=0") == 1 && res.h.handler_restored == 0 && res.h.mask_ok == 1 && res.a.arinfo_restore_ok == 1);
    mock_004(&m); m.arinfo_write_fail_at = 2;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_CYCLES_COMPLETED_WITH_ERRORS && strcmp(res.reason, "arinfo_restore_failed") == 0 && res.h.handler_restored == 1);
    mock_004(&m); m.control_write_fail_at = 2;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_INITIRQ4_CYCLES_COMPLETED_WITH_ERRORS && strcmp(res.reason, "control_restore_failed") == 0 && res.a.control_restore_ok == 0);
    /* ring overflow: completes, restores, reports the drops */
    {
        static char tiny[8 * LINE_LEN]; struct gbp_transport t; struct gbp_initirq4_config cfg;
        mock_004(&m); test_config(&cfg); gbp_mock_transport(&m, &t); ringlog_init(&rl, tiny, LINE_LEN, 8);
        gbp_initirq4_probe_run(&t, &rl, &cfg, &res);
        CHECK(res.status == GBP_INITIRQ4_OK_CYCLES_COMPLETED && res.h.handler_restored == 1 && rl.dropped > 0 && rl.count == 8);
        check_never(&m, &res);
    }
    /* config: the bounds at the console's time base */
    {
        struct gbp_initirq4_config cfg;
        gbp_initirq4_config_default(&cfg);
        CHECK(cfg.t_delivery_ms == 100u && cfg.t_delivery_ticks == 4050000u && cfg.t_next_cause_ms == 500u && cfg.t_next_cause_ticks == 20250000u);
        CHECK(cfg.ack_or == 0x8000 && cfg.src_mask == 0x0555 && cfg.av_mask == 0x0500 && cfg.odd_mask == 0x0AAA && cfg.bit15_mask == 0x8000 && cfg.high_mask == 0x7000);
        CHECK(cfg.max_cycles == 3 && cfg.max_rearms == 2 && cfg.a.a2_obs_ticks[5] == 81000000u);
        gbp_initirq4_config_timebase(&cfg, 81000000u);
        CHECK(cfg.t_delivery_ticks == 8100000u && cfg.t_next_cause_ticks == 40500000u && cfg.a.a1_obs_ticks[0] == 4050u);
        CHECK(strcmp(gbp_initirq4_status_name(GBP_INITIRQ4_ANOMALY_PI_STICKY_AFTER_ACK), "anomaly_pi_sticky_after_ack") == 0);
        CHECK(strcmp(gbp_initirq4_rearmpost_name(GBP_INITIRQ4_REARMPOST_F_INCONSISTENT), "F_inconsistent") == 0 && strcmp(gbp_initirq4_rearmpost_name(0), "-") == 0);
    }
}

/* 34: the mock's multi-cycle handler engine driven by hand: generations, reentry, out of range */
static void test_mock_multi_isr_by_hand(void)
{
    struct gbp_mock m; struct gbp_transport t; int old = 0; uint8_t blk[32]; struct gbp_xfer_info info; struct gbp_irq_record r; struct gbp_irq_multi_status st;
    mock_004(&m); gbp_mock_transport(&m, &t);
    t.write_arinfo(t.ctx, 0x005b);
    memset(blk, 0x8c, sizeof blk); t.write_block(t.ctx, BASE + (4u << 20), blk, &info);
    m.intsr |= GBP_PI_HSP_BIT;
    t.irq_install(t.ctx, &old);
    CHECK(m.multi.anomaly.count == 1 && m.multi.expected_gen == 0 && t.irq_prepare(t.ctx, 3) == GBP_ERR_PARAM);
    CHECK(t.irq_prepare(t.ctx, 1) == GBP_OK && m.prepare_calls == 2 && m.last_prepare_gen == 1);
    t.irq_unmask(t.ctx);                                                     /* delivered into slot 1 */
    CHECK(m.deliveries == 1 && m.multi.slots[1].count == 1 && m.multi.slots[1].fired == 1 && m.multi.slots[0].count == 0 && m.isr_w1c_count == 1);
    CHECK(t.irq_record_slot(t.ctx, 1, &r) == GBP_OK && r.fired == 1 && t.irq_record_slot(t.ctx, 0, &r) == GBP_OK && r.fired == 0 && t.irq_record_slot(t.ctx, 3, &r) == GBP_ERR_PARAM);
    CHECK(t.irq_multi_status(t.ctx, &st) == GBP_OK && st.expected_gen == 1 && st.entries_total == 1 && st.generation_errors == 0);
    CHECK(gbp_mock_first_op(&m, MOCK_ISR_MASK, BASE, 16) < gbp_mock_first_op(&m, MOCK_ISR_W1C, BASE, 16));
    t.irq_mask(t.ctx);
    m.intsr |= GBP_PI_HSP_BIT;                                              /* the same generation again: reentry branch, no W1C */
    t.irq_unmask(t.ctx);
    CHECK(m.deliveries == 2 && m.multi.slots[1].count == 2 && m.isr_w1c_count == 1 && m.multi.slots[1].reentry_t != 0 && st.generation_errors == 0);
    t.irq_mask(t.ctx);
    m.multi.expected_gen = 9;                                                /* out of range: counted, the poisoned slot serviced without a W1C */
    t.irq_unmask(t.ctx);
    CHECK(m.deliveries == 3 && m.multi.generation_errors == 1 && m.multi.anomaly.count == 2 && m.multi.anomaly.fired == 1 && m.multi.anomaly.reentry_t != 0 && m.isr_w1c_count == 1);
    CHECK(m.multi.slots[0].count == 0 && m.multi.slots[1].count == 2 && m.multi.slots[2].count == 0);
    t.irq_mask(t.ctx);
    m.intmr |= GBP_PI_HSP_BIT;                                              /* a prepare while unmasked is a violation */
    t.irq_prepare(t.ctx, 2);
    CHECK((m.violation_mask & GBP_MOCK_VIOL_PREPARE_WHILE_UNMASKED) != 0);
    m.intmr &= ~GBP_PI_HSP_BIT;
    t.write_intsr(t.ctx, GBP_PI_HSP_BIT);
    t.irq_restore(t.ctx); t.write_arinfo(t.ctx, 0x0043);
}

/* ---- the physical fixtures as prefixes ---- */
static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb"); long n; char *buf;
    if (!f) return 0;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    buf = (char *)malloc((size_t)n + 1);
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(buf); return 0; }
    buf[n] = '\0'; fclose(f); return buf;
}

static unsigned count_ops(const char *text)
{
    unsigned ops = 0; const char *p;
    for (p = text; *p; ) { while (*p == ' ') p++; if (*p != '#' && *p != '\n' && *p != '\0') ops++; p = strchr(p, '\n'); if (!p) break; p++; }
    return ops;
}

/* The physical GBP-INIT-003A run (initirqa-0001) drives the stage verbatim up to the EVENT; a replay
 * of a run without an interrupt path exposes no irq_* operations, so the probe stops at the install
 * and tears down as 003A did (one physical W1C, charged to the teardown). Nothing after the EVENT is invented. */
static void test_hw_initirqa_prefix(const char *path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_initirq4_config cfg; struct gbp_initirq4_result res; struct ringlog rl;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    gbp_replay_init(&r, text);
    CHECK(r.has_irq_ops == 0 && r.timeline == 1);
    gbp_replay_transport(&r, &t);
    CHECK(gbp_transport_has_irq_multi_path(&t) == 0);
    gbp_initirq4_config_default(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_initirq4_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.status == GBP_INITIRQ4_ABORT_HANDLER_INSTALL && strcmp(res.reason, "irq_multi_ops_unavailable") == 0 && strcmp(res.teardown_variant, "S2_before_unmask") == 0);
    CHECK(res.stage_a_aborted == 0 && res.a.event_taken == 1 && res.a.t_event == 4155517524u && res.cycles[0].t_cause == 4155517524u && res.cycles[0].cause_irq == 0x0400);
    CHECK(res.cycles[0].started == 0 && res.unmasks == 0 && res.deliveries == 0 && res.h.handler_was_installed == 0);
    CHECK(res.a.irq_stop_pre.gbi == 0x0500 && res.a.stop_value == 0x8faa && res.a.irq_stop_post.gbi == 0x8aaa && res.a.pi_cleanup_performed == 1 && res.teardown_w1c == 1);
    CHECK(res.a.arinfo_final == 0x0043 && res.restore_ok == 1 && res.a.irq_writes_attempted == 3 && res.a.irq_writes_completed == 3);
    CHECK(r.exhausted == 0 && r.mismatches == 0 && r.tick_polls == 0 && r.step == count_ops(text));
    CHECK(count_lines_with(&rl, "CAUSE n=0 t_cause=4155517524 since_a2=4263568 intsr=00012000 intmr=000001fa intsr13=1 intmr13=0 control=8c irq=0400/0400 av=0400 unexpected=0000") == 1);
    CHECK(count_lines_with(&rl, "IRQ install rc=unavailable multi_path=0") == 1 && rl.dropped == 0 && rl.truncated == 0);
    free(text);
}

/* The physical GBP-INIT-003B run (initirqb-0001, commit d3da8cd, DOL 821aa2b2…b757, log sha256
 * bedb1f01…cf7c) is the real prefix of cycle 0: the stage, the install after the latched cause, the
 * generation published (no "I p" line in a 003B fixture: consumed nothing), PREUNMASK-0, the one
 * unmask with the physical handler record, the re-mask, PREACK-0, the device ACK 0x8500, POSTACK-0.
 * The fixture is CUT before the 003B CONTROL restore ("W 01400000 ok"): a re-arm was never recorded
 * physically, so REARM-0 meets an exhausted script — an abort_transport, not a mismatch — and the
 * continuation is not invented. The cycle-0 values are the 003B ones (tests/unit/test_gbp_initirqb.c). */
static void test_hw_initirqb_prefix(const char *path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_initirq4_config cfg; struct gbp_initirq4_result res; struct ringlog rl;
    const struct gbp_initirq4_cycle *c;
    char *cut;
    unsigned ops;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    cut = strstr(text, "\nW 01400000 ok");                                    /* the first CONTROL write is the transform (before A1)… */
    CHECK(cut != 0);
    if (cut) cut = strstr(cut + 1, "\nW 01400000 ok");                        /* …the second is the 003B restore: cut there */
    CHECK(cut != 0);
    if (!cut) { free(text); return; }
    cut[1] = '\0';
    {   /* the boundary marker (a comment: the replay ignores it) makes the cut explicit in the script itself */
        static const char marker[] = "# BOUNDARY: physical prefix (GBP-INIT-003B initirqb-0001) ends here, before the first GBP-INIT-004 re-arm;\n"
                                     "# every operation after this line is unavailable (exhausted script), NOT physical data\n";
        char *text2 = (char *)malloc(strlen(text) + sizeof marker);
        strcpy(text2, text); strcat(text2, marker); free(text); text = text2;
    }
    ops = count_ops(text);
    gbp_replay_init(&r, text);
    CHECK(r.has_irq_ops == 1 && r.timeline == 1);
    gbp_replay_transport(&r, &t);
    CHECK(gbp_transport_has_irq_multi_path(&t) == 1);
    gbp_initirq4_config_default(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_initirq4_probe_run(&t, &rl, &cfg, &res) == 0);
    c = &res.cycles[0];
    /* PHYSICAL PREFIX ENDS BEFORE THE FIRST RE-ARM VARIABLE: every recorded operation was consumed (step == ops, 0 mismatches),
     * the first unrecorded operations are REARM-0's time-base read and its write, which the transport answers as unavailable
     * (rc=backend, exhausted). rearm_attempted = 1 is the probe's bookkeeping of a write it issued to a transport that had no
     * physical record left — a synthetic boundary, NOT physical evidence of a re-arm; rearms_completed stays 0. */
    CHECK(r.mismatches == 0 && r.step == ops && r.exhausted > 0 && r.tick_polls >= 1);
    CHECK(res.status == GBP_INITIRQ4_ABORT_TRANSPORT && strcmp(res.reason, "rearm_write_failed_cycle_0") == 0 && strcmp(res.teardown_variant, "S4_rearm_failed") == 0);
    CHECK(res.completed_cycles == 1 && res.deliveries == 1 && res.acks == 1 && res.rearms_attempted == 1 && res.rearms_completed == 0 && res.next_causes == 0);
    CHECK(c->rearm_attempted == 1 && c->rearm_completed == 0 && c->w_rearm.rc == GBP_ERR_BACKEND && c->w_rearm.value == 0 && c->rearm_before == 0x8000 && res.uncertain_writes >= 1);
    CHECK(res.unmasks == 1 && res.cycles[1].started == 0 && count_lines_with(&rl, "SNAP tag=REARMPOST") == 0 && count_lines_with(&rl, "NEXTCAUSE") == 0);
    /* cycle 0 as it physically happened (the 003B values) */
    CHECK(res.a.t_a2 == 3675626133u && res.a.t_event == 3679890204u && c->t_cause == 3679890204u && c->cause_irq == 0x0400 && c->cause_intsr == 0x00012000u);
    CHECK(res.h.handler_was_installed == 1 && res.h.old_handler_null == 1 && res.h.install_count == 0 && res.h.install_fired == 0);
    CHECK(c->prepared == 1 && c->multi_before.expected_gen == 0 && c->multi_before.entries_total == 0 && c->slot_before.count == 0);
    CHECK(c->preunmask_ok == 1 && c->preunmask.ticks == 3679926960u && c->preunmask.intsr == 0x00012000u && c->preunmask.intsr2 == 0x00012000u);
    CHECK(c->preunmask.intmr == 0x000001fau && c->preunmask.control_vote == 0x8c && c->preunmask.irq_gbi == 0x0500 && c->preunmask.irq_disc == 0x0500);
    CHECK(c->d.t_unmask == 3679931504u && c->d.t_post_unmask == 3679931761u && c->d.fired == 1 && c->d.rec.count == 1 && c->d.reentry == 0);
    CHECK(c->d.rec.t_entry == 3679931582u && c->d.latency_ticks == 78u && c->d.latency_us == 1u && c->d.wait_ticks == 1987u && c->d.polls == 1);
    CHECK(c->d.rec.intsr_before_ack == 0x00012000u && c->d.rec.intmr_at_entry == 0x000021fau && c->d.rec.intmr_after_mask == 0x000001fau);
    CHECK(c->d.rec.intsr_before_w1c == 0x00012000u && c->d.rec.intsr_after_ack == 0x00010000u && c->d.rec.t_second == 3679931730u && c->d.rec.intsr_second == 0x00010000u);
    CHECK(c->d.main_mask_ok == 1 && c->d.remask_retry == 0 && c->d.intmr_remask == 0x000001fau && c->delivered == 1);
    CHECK(c->multi_after.expected_gen == 0 && c->multi_after.entries_total == 1 && c->multi_after.generation_errors == 0 && c->multi_after.anomaly.count == 1);
    CHECK(c->k.preack.ticks == 3679938859u && c->k.preack.intsr == 0x00010000u && c->k.preack.irq_gbi == 0x0500 && c->k.preack.control_vote == 0x8c);
    CHECK(c->k.ack_skipped == 0 && c->k.irq_pending == 0x0500 && c->k.ack_value == 0x8500 && c->k.w_ack.completed == 1 && c->k.w_ack.raw[0x1e] == 0x85);
    CHECK(c->k.postack.ticks == 3679944700u && c->k.postack.irq_gbi == 0x8000 && c->k.postack.intsr == 0x00010000u && c->k.postack.intsr2 == 0x00010000u);
    CHECK(c->k.main_pi_w1c == 0 && c->pi_clean == 1 && c->boundary_ok == 1 && c->pi_sticky == 0);
    CHECK(c->dt_cause_to_isr == 3679931582u - 3679890204u && c->dt_isr_second == 148u && c->dt_isr_to_preack == 3679938859u - 3679931582u);
    CHECK(c->dt_ack_to_postack == 3679944700u - 3679943682u);               /* POSTACK ticks - the ACK's t_after */
    CHECK(count_lines_with(&rl, "CAUSE n=0 t_cause=3679890204 since_a2=4264071 intsr=00012000 intmr=000001fa intsr13=1 intmr13=0 control=8c irq=0400/0400 av=0400 unexpected=0000") == 1);
    CHECK(count_lines_with(&rl, "PREPARE n=0 gen=0 rc=ok intmr13=0 expected_gen=0 entries_total=0 generation_errors=0 slot_count=0 slot_fired=0") == 1);
    CHECK(count_lines_with(&rl, "PREUNMASK n=0 ok=1 reason=- intsr13=1,1 intmr13=0,0 control=8c irq=0500/0500 src=0500 odd=0000 bit15=0") == 1);
    CHECK(count_lines_with(&rl, "UNMASK n=0 t_unmask=3679931504 rc=ok t_post=3679931761 dt_post=257") == 1);
    CHECK(count_lines_with(&rl, "HANDLER n=0 fired=1 count=1 t_entry=3679931582 t_unmask=3679931504 latency_ticks=78 latency_us=1 reentry=0") == 1);
    CHECK(count_lines_with(&rl, "HANDLERPI n=0 intsr_at_entry=00012000 intmr_at_entry=000021fa intmr_after_mask=000001fa intsr_before_w1c=00012000 intsr_after_w1c=00010000 reentry_intsr=00000000 reentry_intmr=00000000") == 1);
    CHECK(count_lines_with(&rl, "HANDLERPI2 n=0 t_second=3679931730 dt_second=148 intsr_second=00010000 intmr_second=000001fa reentry_t=0") == 1);
    CHECK(count_lines_with(&rl, "PREACK n=0 intsr13=0,0 intmr13=0 control=8c irq=0500/0500 src_pending=0500") == 1);
    CHECK(count_lines_with(&rl, "ACK n=0 before=0500 ack_or=8000 ack_value=8500 formula=read|ack_or") == 1);
    CHECK(count_lines_with(&rl, "POSTACK n=0 intsr13=0,0 intmr13=0 control=8c irq=8000/8000 src_pending=0000 bit15=1 ack=1/1") == 1);
    CHECK(count_lines_with(&rl, "PICLEAN n=0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 main_w1c=0 sticky=0 ok=1") == 1);
    CHECK(count_lines_with(&rl, "BOUNDARY n=0 ok=1 completed_cycles=1 deliveries=1 acks=1 main_w1c=0") == 1);
    CHECK(count_lines_with(&rl, "REARM n=0 t_rearm=") == 1 && count_lines_with(&rl, "IRQW tag=REARM-0 addr=01d00000 before=8000 write=0000 layout=gbi-u16-replicated rc=backend") == 1);
    CHECK(count_lines_with(&rl, "INITIRQ4 end status=abort_transport reason=rearm_write_failed_cycle_0") == 1 && count_lines_with(&rl, "SNAP tag=REARMPOST") == 0);
    CHECK(count_lines_with(&rl, "CYCLES requested=3 completed=1 causes=1 deliveries=1 acks=1 rearms=0 next_causes=0 reentry=0 unexpected=0 timeouts=0 isr_w1c=1 main_w1c=0") == 1);
    CHECK(rl.dropped == 0 && rl.truncated == 0);
    free(text);
}

/* ---- host round-trip modes (synthetic) ---- */
static int dump_log(const char *path)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_initirq4_result res; char s[1600]; size_t i; FILE *f;
    /* three cycles; cycle 1 immediate (B), cycle 2 after a quiet re-arm (A); a synthetic re-latch at PREACK-1 so the
     * main-loop W1C (POSTACK) is part of the round trip; 10-digit time base */
    mock_004(&m); m.n_src_sched = 0; sched(&m, W_REARM0, 0, 0x0500); sched(&m, W_REARM1, 50, 0x0400);
    m.intsr = 0x00010000u; m.intmr = 0x000001fau; m.tick = 1000;
    run(&m, &rl, &res);
    gbp_initirq4_summary(&res, s, sizeof s);
    f = fopen(path, "w");
    if (!f) { fprintf(stderr, "cannot write %s\n", path); return 1; }
    fprintf(f, "# OPENGBP-LOG v1\n# SYNTHETIC: generated by tests/unit/test_gbp_initirq4.c from the host mock (three-cycle scenario); NOT physical data\n");
    fprintf(f, "test_id=GBP-INIT-004\nbuild_id=synthetic\ncommit=none\nsource=host-mock\n");
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
    struct gbp_replay r; struct gbp_transport t; struct gbp_initirq4_config cfg;
    struct gbp_initirq4_result res; struct ringlog rl; char s[1600];
    if (!text) { fprintf(stderr, "cannot read %s\n", path); return 1; }
    gbp_replay_init(&r, text);
    gbp_replay_transport(&r, &t);
    test_config(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_initirq4_probe_run(&t, &rl, &cfg, &res);
    gbp_initirq4_summary(&res, s, sizeof s);
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
    test_three_cycles();
    test_rearmpost_b_and_c();
    test_source_orders();
    test_unexpected_sources();
    test_source_not_cleared_and_pi_sticky();
    test_rearm_state();
    test_no_next_cause();
    test_reentry_and_generation();
    test_write_failures();
    test_mask_failure();
    test_control_changed();
    test_timeout_and_source_lost();
    test_early_aborts();
    test_read_problems();
    test_attempted_at_call_time();
    test_wrap_lines_and_config();
    test_mock_multi_isr_by_hand();
    if (argc > 1) test_hw_initirqa_prefix(argv[1]);
    else fprintf(stderr, "note: physical 003A fixture path not given, prefix test skipped\n");
    if (argc > 2) test_hw_initirqb_prefix(argv[2]);
    else fprintf(stderr, "note: physical 003B fixture path not given, prefix test skipped\n");
    printf("test_gbp_initirq4: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
