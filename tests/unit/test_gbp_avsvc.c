/*
 * GBP-AV-SERVICE-001 logic (one delivery → PRESVC → AUDIO/VIDEO whole-block
 * drains → ACK from the PRESVC value → POSTACK → PI clean → re-arm → next
 * cause observed, never delivered) against the mock's SYNTHETIC models: the
 * source/mask IRQ register, the PI latch, the delivery engine running the
 * 003B extended one-shot body, the whole-block read model with its failure
 * knobs, and every deviation the specification enumerates. Plus the physical
 * fixtures as prefixes: GBP-INIT-003A (stops at the install: no interrupt
 * path in that run), GBP-INIT-003B and GBP-INIT-004 cut before their ACK
 * (the delivery and the PRESVC reads are physical; the drain meets a
 * transport without whole-block reads: nothing after a physical record is
 * invented, and NO physical AVSVC fixture exists). Every mock scenario is
 * synthetic and never physical evidence.
 *
 * Modes:  test_gbp_avsvc [initirqa-0001] [initirqb-0001] [initirq4-0001]
 *         test_gbp_avsvc --dump-log <log> <blocks.bin>   (synthetic run, SD-log format + sidecar)
 *         test_gbp_avsvc --replay <fixture> [<blocks.bin>]
 *         test_gbp_avsvc <003A fixture> <003B fixture> <004 fixture> [<AVSVC fixture> <AVSVC blocks.bin>]
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_avsvc_probe.h"
#include "gbp_crc32.h"
#include "gbp_rawlog.h"
#include "gbp_replay.h"
#include "gbp_mock.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

#define LINES 320
#define LINE_LEN 256
static char storage[LINES * LINE_LEN];
static uint8_t audio_buf[0x1000] __attribute__((aligned(32)));
static uint8_t video_buf[0x0F00] __attribute__((aligned(32)));
#define BASE 0x01000000u
#define T_DELIVERY 400u              /* mock ticks; ticks() advances by 10 per call */
#define T_NEXT_CAUSE 2000u

static const uint32_t A1_DL[GBP_INITIRQA_MAX_A1_OBS] = { 50u, 100u };
static const uint32_t A2_DL[GBP_INITIRQA_MAX_A2_OBS] = { 50u, 100u, 200u, 400u, 800u, 1600u };

static int count_lines_with(const struct ringlog *rl, const char *needle)
{
    size_t i; int n = 0;
    for (i = 0; i < rl->count; i++) if (strstr(ringlog_line(rl, i), needle)) n++;
    return n;
}

static size_t max_line_len(const struct ringlog *rl)
{
    size_t i, m = 0, l;
    for (i = 0; i < rl->count; i++) { l = strlen(ringlog_line(rl, i)); if (l > m) m = l; }
    return m;
}

static void test_config(struct gbp_avsvc_config *cfg)
{
    gbp_avsvc_config_default(cfg);
    memcpy(cfg->a.a1_obs_ticks, A1_DL, sizeof A1_DL);
    memcpy(cfg->a.a2_obs_ticks, A2_DL, sizeof A2_DL);
    cfg->t_delivery_ticks = T_DELIVERY;
    cfg->t_next_cause_ticks = T_NEXT_CAUSE;
    cfg->audio_buf = audio_buf; cfg->audio_cap = sizeof audio_buf;
    cfg->video_buf = video_buf; cfg->video_cap = sizeof video_buf;
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

/* IRQ-register write numbering of a full run: A1=1 A2=2 ACK=3 REARM=4 STOP=5 */
#define W_A1 1u
#define W_A2 2u
#define W_ACK 3u
#define W_REARM 4u
#define W_STOP 5u

/* the synthetic device of the nominal scenario: idle 0x8AAE; cause = `bits` 300 ticks after A2; the ACK's
 * W1C clears the sources; the next cause = 0x0500 50 ticks after the re-arm (REARMPOST A, found by polling) */
static void mock_av(struct gbp_mock *m, uint16_t bits)
{
    gbp_mock_init(m);
    m->irq_model = MOCK_IRQ_MODEL_SOURCE_MASK;
    m->isr_ext = 1;
    m->source_assert_after_write = W_A2;
    m->source_assert_delay = 300;
    m->source_assert_bits = bits;
    sched(m, W_REARM, 50, 0x0500);
}

static void run_cfg(struct gbp_mock *m, struct ringlog *rl, struct gbp_avsvc_result *res, struct gbp_avsvc_config *cfg)
{
    struct gbp_transport t;
    gbp_mock_transport(m, &t);
    ringlog_init(rl, storage, LINE_LEN, LINES);
    gbp_avsvc_probe_run(&t, rl, cfg, res);
}

static void run(struct gbp_mock *m, struct ringlog *rl, struct gbp_avsvc_result *res)
{
    struct gbp_avsvc_config cfg;
    test_config(&cfg);
    run_cfg(m, rl, res, &cfg);
}

static int pattern_ok(const uint8_t *buf, unsigned idx, uint8_t seed, uint32_t len)
{
    uint32_t k;
    for (k = 0; k < len; k++) if (buf[k] != gbp_mock_bulk_byte(idx, seed, k)) return 0;
    return 1;
}

/* ---- the "never" properties, every run ---- */
static void check_never(const struct gbp_mock *m, const struct gbp_avsvc_result *res)
{
    unsigned idx, k;
    CHECK(m->intmr_writes == 0);                                             /* INTMR never written directly */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xC) == 0);             /* KEYPAD never written */
    for (idx = 0; idx < 16; idx++) {
        if (idx != 0 && idx != 4 && idx != 0xD) CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, idx) == 0);   /* writes: TEST, CONTROL, IRQ only */
        if (idx != 0 && idx != 4 && idx != 0xD) CHECK(gbp_mock_count_block_ops(m, MOCK_RD, BASE, idx) == 0);   /* 32-byte reads: TEST, CONTROL, IRQ only */
        if (idx != 8 && idx != 1) CHECK(gbp_mock_count_block_ops(m, MOCK_RD_BULK, BASE, idx) == 0);            /* bulk reads: AUDIO, VIDEO only */
    }
    CHECK(gbp_mock_count_block_ops(m, MOCK_RD_BULK, BASE, 8) <= 1 && gbp_mock_count_block_ops(m, MOCK_RD_BULK, BASE, 1) <= 1);   /* one transfer per source */
    CHECK(m->unmask_calls <= 1);                                             /* ONE unmask, ever */
    CHECK(m->deliveries <= 1);                                               /* ONE delivery, ever */
    CHECK(m->intsr_writes <= 2);                                             /* main W1C: POSTACK <= 1, teardown <= 1 */
    CHECK(m->isr_w1c_count <= 1);
    CHECK(m->isr_w1c_count + m->intsr_writes <= 3);                          /* absolute W1C budget */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xD) <= 5);             /* A1 A2 ACK REARM STOP */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 4) <= 2);               /* CONTROL: transform + restore */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0) == 4);               /* handshake only */
    CHECK(gbp_mock_count_block_ops(m, MOCK_IRQ_INSTALL, BASE, 16) <= 1);
    CHECK(m->prepare_calls == 0);                                            /* no generation (003B handler) */
    for (k = 0; k < m->nops; k++) {
        if (m->ops[k].kind == MOCK_IRQ_UNMASK) CHECK((m->ops[k].intsr & GBP_PI_HSP_BIT) != 0);   /* never unmasked without a latched cause */
        if (m->ops[k].kind == MOCK_RD_BULK) {
            CHECK((m->ops[k].intmr & GBP_PI_HSP_BIT) == 0);                                        /* every block DMA with the CPU masked */
            CHECK(m->ops[k].addr == BASE + 0x800000u || m->ops[k].addr == BASE + 0x100000u);        /* the exact block addresses, nothing else */
            CHECK((m->ops[k].addr == BASE + 0x800000u && m->ops[k].len == 0x1000u) || (m->ops[k].addr == BASE + 0x100000u && m->ops[k].len == 0x0F00u));
        }
    }
    CHECK(m->bulk_bad_addr == 0);
    CHECK((m->violation_mask & (GBP_MOCK_VIOL_ISR_W1C_BEFORE_MASK | GBP_MOCK_VIOL_UNMASK_NO_HANDLER | GBP_MOCK_VIOL_INSTALL_TWICE)) == 0);
    if (res->h.mask_ok != 0) CHECK((m->violation_mask & GBP_MOCK_VIOL_DMA_WHILE_UNMASKED) == 0);
    CHECK(res->power_cycle_required == (res->a.control_written ? 1 : 0));
    CHECK(res->deliveries <= 1 && res->acks <= res->deliveries && (unsigned)res->rearm_completed <= res->acks && res->next_cause_found <= res->rearm_completed);
    CHECK(res->unmasks == res->deliveries || (res->unmasks == 1 && res->deliveries == 0));
    CHECK(res->isr_w1c + res->main_w1c + res->teardown_w1c <= 3);
    CHECK(res->drains_attempted <= res->drains_selected && res->drains_completed <= res->drains_attempted);
    if (!res->acked) CHECK(res->rearm_attempted == 0);                        /* no re-arm without a completed ACK */
    if (res->drains_completed != res->drains_selected) CHECK(res->k.w_ack.attempted == 0);   /* no ACK unless every selected drain completed */
}

static int nth(const struct gbp_mock *m, enum gbp_mock_op_kind kind, unsigned n) { return gbp_mock_nth_op(m, kind, BASE, 16, n); }
static int nth_irqw(const struct gbp_mock *m, unsigned n) { return gbp_mock_nth_op(m, MOCK_WR, BASE, 0xD, n); }
static int last_op_before(const struct gbp_mock *m, enum gbp_mock_op_kind kind, unsigned block, int idx)
{
    int k, found = -1;
    for (k = 0; k < idx; k++) if (m->ops[k].kind == kind && (block >= 16u || ((((m->ops[k].addr - BASE) >> 20) & 0xFu) == block))) found = k;
    return found;
}

/* ---- the mandatory order of a full run (spec §35) ---- */
static void check_order_full(const struct gbp_mock *m, int expect_audio, int expect_video)
{
    int ar_exp = gbp_mock_first_op(m, MOCK_AR_W, BASE, 16);
    int ctl_exp = gbp_mock_nth_op(m, MOCK_WR, BASE, 4, 1);
    int ctl_rest = gbp_mock_nth_op(m, MOCK_WR, BASE, 4, 2);
    int a1 = nth_irqw(m, W_A1), a2 = nth_irqw(m, W_A2), ack = nth_irqw(m, W_ACK), rearm = nth_irqw(m, W_REARM), stop = nth_irqw(m, W_STOP);
    int inst = nth(m, MOCK_IRQ_INSTALL, 1), unm = nth(m, MOCK_IRQ_UNMASK, 1);
    int entry = nth(m, MOCK_ISR_ENTRY, 1), imask = nth(m, MOCK_ISR_MASK, 1), iw1c = nth(m, MOCK_ISR_W1C, 1), iexit = nth(m, MOCK_ISR_EXIT, 1);
    int rest = nth(m, MOCK_IRQ_RESTORE, 1), ar_rest = gbp_mock_last_op(m, MOCK_AR_W, BASE, 16);
    int ba = gbp_mock_first_op(m, MOCK_RD_BULK, BASE, 8), bv = gbp_mock_first_op(m, MOCK_RD_BULK, BASE, 1);
    int mmask = -1, k, presvc_irq;
    for (k = unm + 1; k < (int)m->nops; k++) if (m->ops[k].kind == MOCK_IRQ_MASK) { mmask = k; break; }
    CHECK(ar_exp >= 0 && ctl_exp > ar_exp && a1 > ctl_exp && a2 > a1 && inst > a2);
    CHECK(unm > inst && entry > unm && imask > entry && iw1c > imask && iexit > iw1c && mmask > iexit);
    presvc_irq = last_op_before(m, MOCK_RD, 0xD, expect_audio ? ba : bv);   /* the PRESVC IRQ read precedes every drain */
    CHECK(presvc_irq > mmask);
    if (expect_audio) { CHECK(ba > mmask && ba > presvc_irq); }
    else CHECK(ba < 0);
    if (expect_video) { CHECK(bv > mmask && bv > presvc_irq); if (expect_audio) CHECK(bv > ba); }   /* VIDEO after AUDIO completed */
    else CHECK(bv < 0);
    CHECK(ack > mmask && (!expect_audio || ack > ba) && (!expect_video || ack > bv));   /* ACK never before the last selected drain */
    CHECK(rearm > ack);
    CHECK(last_op_before(m, MOCK_RD, 0xD, rearm) > ack);                     /* POSTACK read between ACK and REARM */
    { int w = -1; for (k = ack + 1; k < rearm; k++) if (m->ops[k].kind == MOCK_INTSR_W) w = k; if (w >= 0) CHECK(w < rearm); }   /* PICLEAN before REARM */
    CHECK(stop > rearm && ctl_rest > rearm && stop > ctl_rest && rest > stop && ar_rest > rest);
    CHECK(gbp_mock_count_block_ops(m, MOCK_IRQ_UNMASK, BASE, 16) == 1);
    for (k = rearm + 1; k < (int)m->nops; k++) {                             /* after the re-arm: no unmask, no ISR, no bulk read, no IRQ write but STOP */
        CHECK(m->ops[k].kind != MOCK_IRQ_UNMASK && m->ops[k].kind != MOCK_ISR_ENTRY && m->ops[k].kind != MOCK_RD_BULK);
        if (m->ops[k].kind == MOCK_WR && (((m->ops[k].addr - BASE) >> 20) & 0xFu) == 0xDu) CHECK(k == stop);
    }
}

/* ---- 4/5/6/7/18/26/31: the success paths (audio only, video only, both), REARMPOST A then a delayed next cause ---- */
static void test_success_paths(void)
{
    static const uint16_t causes[3] = { 0x0400, 0x0100, 0x0500 };
    unsigned i;
    for (i = 0; i < 3; i++) {
        struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
        int ea = (causes[i] & 0x0400) ? 1 : 0, ev = (causes[i] & 0x0100) ? 1 : 0;
        mock_av(&m, causes[i]);
        m.bulk_seed = (uint8_t)(0x10 + i);
        run(&m, &rl, &res);
        check_never(&m, &res);
        CHECK(res.status == GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED && strcmp(res.status_name, "ok_service_rearm_cause_observed") == 0);
        CHECK(strcmp(res.status_class, "ok") == 0 && strcmp(res.reason, "-") == 0 && strcmp(res.teardown_variant, "S4B_next_cause_latched") == 0);
        CHECK(res.restore_ok && res.errors == 0 && res.transport_ok && res.uncertain_writes == 0 && res.power_cycle_required);
        CHECK(res.deliveries == 1 && res.unmasks == 1 && res.acks == 1 && res.rearm_completed == 1 && res.next_cause_found == 1 && res.next_cause_immediate == 0);
        CHECK(res.pending_irq == causes[i] && res.drain_mask == causes[i] && res.audio.selected == ea && res.video.selected == ev);
        CHECK(res.drains_selected == (unsigned)(ea + ev) && res.drains_attempted == res.drains_selected && res.drains_completed == res.drains_selected);
        CHECK(res.audio.attempted == ea && res.audio.completed == ea && res.video.attempted == ev && res.video.completed == ev);
        CHECK(res.k.ack_value == (uint16_t)(causes[i] | 0x8000) && res.k.irq_pending == causes[i]);
        CHECK(res.k.postack.irq_gbi == 0x8000 && res.source_after_ack == 0 && res.postack_ok && res.pi_clean && res.k.main_pi_w1c == 0);
        CHECK(res.rearmpost_outcome == GBP_AVSVC_REARMPOST_A_QUIET && res.rearmpost_ok && res.w_rearm.value == 0 && res.w_rearm.completed);
        CHECK(res.dt_rearm_to_next_cause > 0 && res.next_cause_irq == 0x0500 && (res.next_cause_intsr & GBP_PI_HSP_BIT));
        CHECK(res.isr_w1c == 1 && res.main_w1c == 0 && res.teardown_w1c == 1);          /* the latched next cause is closed by the teardown */
        CHECK(res.a.pi_cleanup_performed == 1 && res.pi_sticky_final == 0 && res.a.stop_value == (uint16_t)(0x0500 | 0x8AAA));
        CHECK(m.deliveries == 1 && m.unmask_calls == 1 && m.isr_w1c_count == 1 && m.intsr_writes == 1);
        CHECK((m.intmr & GBP_PI_HSP_BIT) == 0);                                        /* CPU masked at the end */
        check_order_full(&m, ea, ev);
        if (ea) { CHECK(pattern_ok(audio_buf, 8, m.bulk_seed, 0x1000) && res.audio.summarized && res.audio.crc32 == gbp_crc32(audio_buf, 0x1000)); }
        else { CHECK(res.audio.summarized == 0 && res.audio.attempted == 0); }
        if (ev) { CHECK(pattern_ok(video_buf, 1, m.bulk_seed, 0x0F00) && res.video.summarized && res.video.crc32 == gbp_crc32(video_buf, 0x0F00)); }
        else CHECK(res.video.summarized == 0);
        CHECK(count_lines_with(&rl, "AVSVC end status=ok_service_rearm_cause_observed class=ok reason=- restore=ok restore_reason=- teardown=S4B_next_cause_latched power_cycle_required=1 errors=0 transport_ok=1") == 1);
        CHECK(count_lines_with(&rl, "SVC start pending=") == 1 && count_lines_with(&rl, "SVCEND drain=") == 1 && count_lines_with(&rl, "POSTDRAIN observation_only=1") == 1);
        CHECK(count_lines_with(&rl, "IRQW tag=ACK ") == 1 && count_lines_with(&rl, "IRQW tag=REARM ") == 1 && count_lines_with(&rl, "IRQW tag=STOP ") == 1 && count_lines_with(&rl, "IRQW ") == 5);
        CHECK(count_lines_with(&rl, "PICLEAN intsr=") == 1 && count_lines_with(&rl, "REARMPOST t=") == 1 && count_lines_with(&rl, "NEXTCAUSE found=1 immediate=0") == 1);
        CHECK(count_lines_with(&rl, "delivered=0") == 1 && count_lines_with(&rl, "UNMASK t_unmask=") == 1 && count_lines_with(&rl, "PREPARE") == 0);
        CHECK(count_lines_with(&rl, "AUDIOREAD idx=8 addr=01800000 len=1000 selected=") == 1 && count_lines_with(&rl, "VIDEOREAD idx=1 addr=01100000 len=0f00 selected=") == 1);
        CHECK(count_lines_with(&rl, "BLOCK kind=audio") == 1 && count_lines_with(&rl, "BLOCK kind=video") == 1);
        CHECK(count_lines_with(&rl, "BLOCKW kind=audio") == (ea ? 4 : 0) && count_lines_with(&rl, "BLOCKW kind=video") == (ev ? 4 : 0));
        CHECK(count_lines_with(&rl, "TEARDOWNAV variant=S4B_next_cause_latched deliveries=1 drained=") == 1 && count_lines_with(&rl, "pi_policy=unmasked_once") == 1);
        CHECK(count_lines_with(&rl, "CLEANUP performed=1") == 1 && count_lines_with(&rl, "COUNTERS unmasks=1 deliveries=1 acks=1 rearms=1 next_causes=1 unexpected=0000 site=- isr_w1c=1 main_w1c=0 teardown_w1c=1 w1c_total=2") == 1);
        CHECK(rl.dropped == 0 && rl.truncated == 0 && max_line_len(&rl) < LINE_LEN);
        {
            char s[2000];
            CHECK(gbp_avsvc_summary(&res, s, sizeof s) > 0 && (size_t)gbp_avsvc_summary(&res, s, sizeof s) < sizeof s);
            CHECK(strstr(s, "DONE status=ok_service_rearm_cause_observed class=ok reason=- restore=ok") != 0);
            CHECK(strstr(s, "ack=1/1 rearm=1/1 stop=1/1 ctl_restore=1/1 uncertain=0") != 0 && strstr(s, "next_cause=1 immediate=0") != 0);
        }
    }
}

/* ---- 8/9/36: snapshot immutability ---- */
static void test_snapshot_immutability(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    /* PRESVC 0x0400; VIDEO appears during the AUDIO DMA: only AUDIO drained, ACK 0x8400, VIDEO not added */
    mock_av(&m, 0x0400);
    m.bulk_assert_at_read = 1; m.bulk_assert_bits = 0x0100; m.bulk_assert_after = 0;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.pending_irq == 0x0400 && res.drain_mask == 0x0400 && res.audio.completed == 1 && res.video.selected == 0 && res.video.attempted == 0);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_RD_BULK, BASE, 1) == 0 && res.k.ack_value == 0x8400);
    CHECK(res.postdrain.irq_gbi == 0x0500);                                    /* POSTDRAIN saw it: observation only */
    CHECK(res.postdrain_ok && res.acked);
    CHECK(res.k.postack.irq_gbi == 0x8100 && res.source_after_ack == 0x0100);  /* the unacknowledged VIDEO bit stays: data, not an anomaly */
    CHECK(res.postack_ok && res.rearm_completed == 1);
    /* the source that appeared during the drain latched a PI cause (bit 15 was 0): observed at POSTDRAIN, cleared by the one main W1C */
    CHECK(res.relatch_postdrain == 1 && res.relatch_postack == 1 && res.k.main_pi_w1c == 1 && res.pi_clean == 1);
    CHECK(count_lines_with(&rl, "POSTDRAIN observation_only=1 relatch=1 av_after_drain=0500 pending_kept=0400") == 1);
    CHECK(count_lines_with(&rl, "POSTACKAV boundary=pending_av source_after_ack=0100 relatch=1 main_w1c=1 requirement=none") == 1);
    CHECK(count_lines_with(&rl, "VIDEOREAD idx=1 addr=01100000 len=0f00 selected=0 attempted=0 rc=-") == 1);
    /* PRESVC 0x0500; the AUDIO source re-asserts during its own DMA (drain-clears model): both stay selected, ACK 0x8500 */
    mock_av(&m, 0x0500);
    m.bulk_clears_source = 1; m.bulk_assert_at_read = 1; m.bulk_assert_bits = 0x0400; m.bulk_assert_after = 1;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.pending_irq == 0x0500 && res.drain_mask == 0x0500 && res.audio.completed && res.video.completed && res.k.ack_value == 0x8500);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_RD_BULK, BASE, 8) == 1 && gbp_mock_count_block_ops(&m, MOCK_RD_BULK, BASE, 1) == 1);
    CHECK(res.postdrain.irq_gbi == 0x0400);                                    /* video cleared by its drain, audio re-asserted */
    CHECK(res.status == GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED);
    /* the ACK value is the PRESVC one even when POSTDRAIN reads something else: write_hook sees 0x8500 on the wire */
}

/* ---- 10: unexpected sources at each observation point ---- */
static void test_unexpected_sources(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    /* at the first cause (PREUNMASK): observed, no unmask, no drain, no ACK */
    mock_av(&m, 0x0404);
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE && strcmp(res.reason, "unexpected_source_PREUNMASK") == 0 && strcmp(res.status_class, "anomaly") == 0);
    CHECK(res.unexpected == 0x0004 && strcmp(res.unexpected_site, "PREUNMASK") == 0 && res.unmasks == 0 && res.deliveries == 0 && res.drains_attempted == 0 && res.k.w_ack.attempted == 0);
    CHECK(strcmp(res.teardown_variant, "S2_before_unmask") == 0 && m.unmask_calls == 0 && res.a.stop_value == (0x0404 | 0x8AAA));
    /* at PRESVC (appears right after the ISR's W1C via a scheduled assertion after A2 with a longer delay) */
    mock_av(&m, 0x0400);
    sched(&m, W_A2, 340, 0x0010);     /* the sleep source asserts after PREUNMASK's reads and before the PRESVC reads (mock timing) */
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE && strcmp(res.reason, "unexpected_source_PRESVC") == 0);
    CHECK(strcmp(res.unexpected_site, "PRESVC") == 0 && res.unexpected == 0x0010 && res.deliveries == 1 && res.drains_attempted == 0 && res.k.w_ack.attempted == 0);
    CHECK(strcmp(res.teardown_variant, "S3_service_aborted") == 0 && res.presvc_ok == 0 && strcmp(res.presvc_reason, "unexpected_source_PRESVC") == 0);
    /* during the drain (POSTDRAIN): drained, observed, NO ACK, no re-arm */
    mock_av(&m, 0x0500);
    m.bulk_assert_at_read = 2; m.bulk_assert_bits = 0x0040; m.bulk_assert_after = 1;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE && strcmp(res.reason, "unexpected_source_POSTDRAIN") == 0);
    CHECK(res.drains_completed == 2 && res.k.w_ack.attempted == 0 && res.rearm_attempted == 0 && res.unexpected == 0x0040);
    CHECK(count_lines_with(&rl, "ACK before=") == 0 && count_lines_with(&rl, "SNAP tag=POSTDRAIN") == 1);
    /* at POSTACK: acked, no re-arm */
    mock_av(&m, 0x0500);
    sched(&m, W_ACK, 0, 0x0001);
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE && strcmp(res.reason, "unexpected_source_POSTACK") == 0 && res.acked && res.rearm_attempted == 0);
    /* at REARMPOST: D */
    mock_av(&m, 0x0500);
    sched(&m, W_REARM, 0, 0x0004);
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE && strcmp(res.reason, "unexpected_source_REARMPOST") == 0);
    CHECK(res.rearmpost_outcome == GBP_AVSVC_REARMPOST_D_UNEXPECTED && strcmp(res.teardown_variant, "S4C_rearmpost_invalid") == 0 && res.next_cause_found == 0);
    /* at NEXTCAUSE: the next cause carries an unexpected source */
    mock_av(&m, 0x0500);
    m.n_src_sched = 0; sched(&m, W_REARM, 50, 0x0104);
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE && strcmp(res.reason, "unexpected_source_NEXTCAUSE") == 0 && strcmp(res.teardown_variant, "S4B_next_cause_latched") == 0);
    CHECK(res.next_cause_found == 0 && m.deliveries == 1 && (m.intmr & GBP_PI_HSP_BIT) == 0 && res.a.pi_cleanup_performed == 1);
}

/* ---- 11–16/31: DMA failures: no ACK, no re-arm, VIDEO never started after an AUDIO failure ---- */
static void test_dma_failures(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    static const gbp_status rcs[3] = { GBP_ERR_BUSY, GBP_ERR_TIMEOUT, GBP_ERR_BACKEND };
    static const gbp_avsvc_status sa[3] = { GBP_AVSVC_AUDIO_DMA_BUSY, GBP_AVSVC_AUDIO_DMA_TIMEOUT, GBP_AVSVC_AUDIO_DMA_ERROR };
    static const gbp_avsvc_status sv[3] = { GBP_AVSVC_VIDEO_DMA_BUSY, GBP_AVSVC_VIDEO_DMA_TIMEOUT, GBP_AVSVC_VIDEO_DMA_ERROR };
    static const char *na[3] = { "audio_dma_busy", "audio_dma_timeout", "audio_dma_error" };
    static const char *nv[3] = { "video_dma_busy", "video_dma_timeout", "video_dma_error" };
    unsigned i;
    for (i = 0; i < 3; i++) {
        mock_av(&m, 0x0500);
        m.bulk_rc[8] = rcs[i]; m.bulk_partial_on_fail = 1;
        run(&m, &rl, &res);
        check_never(&m, &res);
        CHECK(res.status == sa[i] && strcmp(res.status_name, na[i]) == 0 && strcmp(res.status_class, "dma") == 0 && strcmp(res.reason, "audio_read_failed") == 0);
        CHECK(res.audio.attempted == 1 && res.audio.completed == 0 && res.audio.rc == rcs[i] && res.video.selected == 1 && res.video.attempted == 0);
        CHECK(gbp_mock_count_block_ops(&m, MOCK_RD_BULK, BASE, 1) == 0);      /* VIDEO never started */
        CHECK(res.k.w_ack.attempted == 0 && res.rearm_attempted == 0 && strcmp(res.teardown_variant, "S3_dma_failed") == 0);
        CHECK(res.drain_uncertain == (rcs[i] == GBP_ERR_TIMEOUT ? 1 : 0) && res.errors == 1 && res.transport_ok == 0 && res.uncertain_writes == 0);
        CHECK(res.power_cycle_required == 1 && res.restore_ok == 1 && res.a.stop_value == (0x0500 | 0x8AAA));
        CHECK(count_lines_with(&rl, "AUDIOREAD idx=8 addr=01800000 len=1000 selected=1 attempted=1 completed=0 rc=") == 1);
        CHECK(count_lines_with(&rl, "VIDEOREAD idx=1 addr=01100000 len=0f00 selected=1 attempted=0 rc=-") == 1);
        CHECK(count_lines_with(&rl, "SVCEND drain=0500 selected=2 attempted=1 completed=0 ok=0") == 1);
        CHECK(count_lines_with(&rl, "BLOCK kind=audio idx=8 len=1000 present=1 valid=0 rc=") == 1 && count_lines_with(&rl, "BLOCK kind=video idx=1 len=0f00 present=0 valid=0") == 1);
        CHECK(res.audio.summarized == 0 && res.video.summarized == 0 && count_lines_with(&rl, "BLOCKW") == 0);
        CHECK(count_lines_with(&rl, "ACK before=") == 0 && count_lines_with(&rl, "SNAP tag=POSTDRAIN") == 0);
        m.n_src_sched = 0;
        mock_av(&m, 0x0500);
        m.bulk_rc[1] = rcs[i];
        run(&m, &rl, &res);
        check_never(&m, &res);
        CHECK(res.status == sv[i] && strcmp(res.status_name, nv[i]) == 0 && strcmp(res.reason, "video_read_failed") == 0);
        CHECK(res.audio.completed == 1 && res.video.attempted == 1 && res.video.completed == 0 && res.k.w_ack.attempted == 0 && res.rearm_attempted == 0);
        CHECK(res.audio.summarized == 1 && res.video.summarized == 0);       /* the completed AUDIO block keeps its summary */
        CHECK(strcmp(res.teardown_variant, "S3_dma_failed") == 0 && m.deliveries == 1);
    }
    /* a busy engine before the ACK write itself (fail_at_op on the ACK transfer): ack_write_failed, uncertain */
}

/* ---- 13 + teardown: a bulk timeout that leaves the engine busy — every later transfer is refused, nothing is
 * retried, the teardown stays best-effort and bounded, no ACK / re-arm, power cycle required ---- */
static void test_timeout_then_busy_teardown(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    unsigned k, after = 0, busy_after = 0;
    int bulk = -1;
    mock_av(&m, 0x0500);
    m.bulk_rc[8] = GBP_ERR_TIMEOUT; m.stuck_after_timeout = 1; m.bulk_partial_on_fail = 1;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_AUDIO_DMA_TIMEOUT && res.drain_uncertain == 1 && strcmp(res.teardown_variant, "S3_dma_failed") == 0);
    CHECK(res.audio.attempted == 1 && res.audio.completed == 0 && res.video.attempted == 0 && res.k.w_ack.attempted == 0 && res.rearm_attempted == 0);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_RD_BULK, BASE, 8) == 1 && gbp_mock_count_block_ops(&m, MOCK_RD_BULK, BASE, 1) == 0);   /* no retry, no VIDEO */
    bulk = gbp_mock_first_op(&m, MOCK_RD_BULK, BASE, 8);
    CHECK(bulk >= 0);
    for (k = (unsigned)bulk + 1u; k < m.nops; k++) {
        if (m.ops[k].kind == MOCK_RD || m.ops[k].kind == MOCK_WR || m.ops[k].kind == MOCK_RD_BULK) {
            after++;
            if (m.ops[k].rc == GBP_ERR_BUSY) busy_after++;
        }
    }
    CHECK(after > 0 && busy_after == after);                                 /* every later transfer refused by the busy engine, none started */
    CHECK(after <= 12);                                                      /* the teardown's fixed set of accesses: bounded, no loop */
    CHECK(res.a.w_ctl_restore.attempted == 1 && res.a.w_ctl_restore.completed == 0 && res.a.w_stop.attempted == 1 && res.a.w_stop.completed == 0);
    CHECK(res.restore_ok == 0 && res.uncertain_writes == 2 && res.power_cycle_required == 1 && res.errors > 0 && res.transport_ok == 0);
    CHECK(res.a.pi_cleanup_performed == 0 || res.a.pi_cleanup_performed == 1);        /* PI accesses are not DMA: unaffected either way */
    CHECK(res.h.handler_restored == 1 && res.h.mask_ok == 1 && (m.intmr & GBP_PI_HSP_BIT) == 0);   /* interrupt path restored regardless */
    CHECK(res.audio.summarized == 0 && count_lines_with(&rl, "BLOCK kind=audio idx=8 len=1000 present=1 valid=0 rc=timeout summary=-") == 1);
    CHECK(count_lines_with(&rl, "AVSVC end status=audio_dma_timeout class=dma reason=audio_read_failed restore=error") == 1);
    CHECK(count_lines_with(&rl, "IRQW tag=ACK") == 0 && count_lines_with(&rl, "IRQW tag=REARM") == 0 && count_lines_with(&rl, "IRQW tag=STOP ") == 1);
    {
        struct gbp_avdump_info info;
        CHECK(gbp_avsvc_dump_info(&res, 40500000u, "T", "B", "A", "C", &info) == 0);
        CHECK(info.flags == GBP_AVDUMP_FLAG_AUDIO_PRESENT && info.audio_len == 0x1000 && info.video_len == 0 && info.audio_rc == (uint32_t)GBP_ERR_TIMEOUT);
    }
    /* the same with a VIDEO timeout: AUDIO stays valid, VIDEO present and not valid */
    mock_av(&m, 0x0500);
    m.bulk_rc[1] = GBP_ERR_TIMEOUT; m.stuck_after_timeout = 1;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_VIDEO_DMA_TIMEOUT && res.audio.completed == 1 && res.audio.summarized == 1 && res.video.completed == 0 && res.video.summarized == 0);
    CHECK(res.k.w_ack.attempted == 0 && res.restore_ok == 0 && res.power_cycle_required == 1);
}

/* ---- 17/25/36/37/38: write and restore failures ---- */
static void test_write_failures(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    mock_av(&m, 0x0500);
    m.irq_write_fail_at = W_ACK;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ACK_WRITE_FAILED && strcmp(res.status_class, "transport") == 0 && strcmp(res.teardown_variant, "S4_ack_failed") == 0);
    CHECK(res.k.w_ack.attempted == 1 && res.k.w_ack.completed == 0 && res.uncertain_writes == 1 && res.rearm_attempted == 0 && res.acked == 0);
    CHECK(res.drains_completed == 2 && count_lines_with(&rl, "IRQW tag=ACK ") == 1 && count_lines_with(&rl, "IRQW tag=REARM") == 0);
    mock_av(&m, 0x0500);
    m.irq_write_fail_at = W_REARM;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_REARM_WRITE_FAILED && strcmp(res.teardown_variant, "S4_rearm_failed") == 0);
    CHECK(res.rearm_attempted == 1 && res.rearm_completed == 0 && res.uncertain_writes == 1 && res.next_cause_found == 0 && res.acked == 1);
    CHECK(count_lines_with(&rl, "SNAP tag=REARMPOST") == 0 && count_lines_with(&rl, "NEXTCAUSE") == 0);
    /* STOP failure: the chain completed, the restore did not */
    mock_av(&m, 0x0500);
    m.irq_write_fail_at = W_STOP;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_SERVICE_COMPLETED_WITH_ERRORS && strcmp(res.reason, "uncertain_write") == 0 && strcmp(res.status_class, "errors") == 0);
    CHECK(res.next_cause_found == 1 && res.restore_ok == 0 && strcmp(res.restore_reason, "irq_stop_write_failed") == 0 && res.uncertain_writes == 1);
    /* handler restore failure */
    mock_av(&m, 0x0500);
    m.restore_fails = 1;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_SERVICE_COMPLETED_WITH_ERRORS && strcmp(res.reason, "handler_restore_failed") == 0 && res.h.handler_restored == 0);
    /* AR_INFO restore failure */
    mock_av(&m, 0x0500);
    m.arinfo_write_fail_at = 2;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_SERVICE_COMPLETED_WITH_ERRORS && strcmp(res.reason, "arinfo_restore_failed") == 0 && res.a.arinfo_restore_ok == 0);
}

/* ---- 18–21: the POSTACK readings are data ---- */
static void test_postack_values(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    static const uint16_t re[3] = { 0x0100, 0x0400, 0x0500 };
    unsigned i;
    /* 0x8000: the drain clears the sources (nothing left for the ACK to clear) */
    mock_av(&m, 0x0500);
    m.bulk_clears_source = 1;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED && res.postdrain.irq_gbi == 0x0000 && res.k.postack.irq_gbi == 0x8000 && res.source_after_ack == 0);
    CHECK(count_lines_with(&rl, "POSTACKAV boundary=clean source_after_ack=0000 relatch=0 main_w1c=0 requirement=none") == 1);
    /* 0x8100 / 0x8400 / 0x8500: a source re-asserts right after the ACK — under bit 15 = 1 (level model) no PI cause: data, not anomaly_source_not_cleared */
    for (i = 0; i < 3; i++) {
        mock_av(&m, 0x0500);
        sched(&m, W_ACK, 0, re[i]);
        run(&m, &rl, &res);
        check_never(&m, &res);
        CHECK(res.status == GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED && res.k.postack.irq_gbi == (uint16_t)(0x8000 | re[i]) && res.source_after_ack == re[i]);
        CHECK(res.postack_ok && res.pi_clean && res.k.main_pi_w1c == 0 && res.rearm_completed == 1);
        CHECK(count_lines_with(&rl, "anomaly_source_not_cleared") == 0 && count_lines_with(&rl, "POSTACKAV boundary=pending_av") == 1);
        /* with the source pending at the re-arm and the level model, IRQ := 0 releases the hold: B, immediate next cause */
        CHECK(res.rearmpost_outcome == GBP_AVSVC_REARMPOST_B_LATCHED && res.next_cause_immediate == 1 && res.next_cause_irq == re[i]);
    }
}

/* ---- 22/23/24/40: the PI cleanup budget ---- */
static void test_pi_cleanup(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    /* 22: unnecessary */
    mock_av(&m, 0x0500);
    run(&m, &rl, &res);
    CHECK(res.k.main_pi_w1c == 0 && res.relatch_postack == 0 && count_lines_with(&rl, "MAINPICLEANUP site=POSTACK performed=0") == 1 && m.intsr_writes == 1);
    /* 23: a re-latch during the service (the ISR's W1C cleared bit 13 while the line was up: re-set 40 ticks later) — once, cleared, re-arm proceeds */
    mock_av(&m, 0x0500);
    m.pi_relatch_after_ticks = 40;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED && res.k.main_pi_w1c == 1 && res.relatch_postack == 1 && res.pi_clean == 1 && res.pi_sticky == 0);
    CHECK(res.main_w1c == 1 && res.isr_w1c == 1 && res.teardown_w1c == 1 && res.isr_w1c + res.main_w1c + res.teardown_w1c == 3);   /* 40: the absolute budget, exactly */
    CHECK(m.isr_w1c_count == 1 && m.intsr_writes == 2 && count_lines_with(&rl, "MAINPICLEANUP site=POSTACK performed=1 value=00002000") == 1);
    CHECK(count_lines_with(&rl, "PICLEAN intsr=") == 1 && count_lines_with(&rl, "main_w1c=1 sticky=0 ok=1") == 1);
    CHECK(res.relatch_postdrain == 1 && count_lines_with(&rl, "POSTDRAIN observation_only=1 relatch=1") == 1);
    /* 24: sticky */
    mock_av(&m, 0x0500);
    m.pi_relatch_after_ticks = 40; m.intsr_w1c_ignored = 1;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_PI_STICKY_AFTER_SERVICE && strcmp(res.reason, "pi_sticky_after_service") == 0 && strcmp(res.teardown_variant, "S3_pi_sticky") == 0);
    CHECK(res.pi_sticky == 1 && res.rearm_attempted == 0 && res.acked == 1 && m.intsr_writes <= 2);
    CHECK(count_lines_with(&rl, "IRQW tag=REARM") == 0 && count_lines_with(&rl, "CLEANUP performed=1") == 1);   /* the teardown's own single W1C, sticky again */
    CHECK(res.a.pi_cleanup_sticky == 1 && res.pi_sticky_final == 1 && res.isr_w1c + res.main_w1c + res.teardown_w1c == 3);
}

/* ---- 26–29/30/32: REARMPOST outcomes and the next cause ---- */
static void test_rearmpost_and_next_cause(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    /* 27/30: B — the next cause already latched at REARMPOST (source asserted at the re-arm, bit 15 -> 0 releases it) */
    mock_av(&m, 0x0500);
    m.n_src_sched = 0; sched(&m, W_REARM, 0, 0x0400);
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED && res.rearmpost_outcome == GBP_AVSVC_REARMPOST_B_LATCHED);
    CHECK(res.next_cause_found == 1 && res.next_cause_immediate == 1 && res.next_cause_polls == 0 && res.next_cause_irq == 0x0400 && res.dt_rearm_to_next_cause > 0);
    CHECK(count_lines_with(&rl, "NEXTCAUSE found=1 immediate=1") == 1 && count_lines_with(&rl, "SNAP tag=NEXTCAUSE") == 0);
    /* 28: C — the source visible before the PI latch (latch lags 30 ticks), then found by polling */
    mock_av(&m, 0x0500);
    m.n_src_sched = 0; sched(&m, W_REARM, 0, 0x0100); m.source_pi_delay = 60;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED && res.rearmpost_outcome == GBP_AVSVC_REARMPOST_C_SOURCE_BEFORE_PI);
    CHECK(res.next_cause_found == 1 && res.next_cause_immediate == 0 && res.next_cause_polls > 0 && res.next_cause_irq == 0x0100);
    CHECK(count_lines_with(&rl, "SNAP tag=NEXTCAUSE") == 1 && count_lines_with(&rl, "REARMPOST t=") == 1 && count_lines_with(&rl, "outcome=C_source_before_pi ok=1") == 1);
    /* 29: F — a PI cause with no AV source right after the re-arm (phantom) */
    mock_av(&m, 0x0500);
    m.n_src_sched = 0; m.pi_phantom_after_write = W_REARM; m.pi_phantom_delay = 0;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_REARM_STATE && strcmp(res.reason, "rearmpost_pi_without_source") == 0 && res.rearmpost_outcome == GBP_AVSVC_REARMPOST_F_INCONSISTENT);
    CHECK(strcmp(res.teardown_variant, "S4C_rearmpost_invalid") == 0 && res.next_cause_found == 0 && m.deliveries == 1);
    /* 29b: a phantom during the wait: NEXTCAUSE pi without source */
    mock_av(&m, 0x0500);
    m.n_src_sched = 0; m.pi_phantom_after_write = W_REARM; m.pi_phantom_delay = 80;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_REARM_STATE && strcmp(res.reason, "nextcause_pi_without_source") == 0 && strcmp(res.teardown_variant, "S4B_next_cause_latched") == 0);
    /* E: invalid read-back after IRQ := 0 (a sticky odd bit) */
    mock_av(&m, 0x0500);
    m.rearm_sticky_bits = 0x0002; m.rearm_sticky_from_write = W_REARM;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_REARM_STATE && strcmp(res.reason, "rearm_state_invalid") == 0 && res.rearmpost_outcome == GBP_AVSVC_REARMPOST_E_INVALID);
    /* 32: no next cause within the bound: a VALID physical result, S4A, no W1C in the wait, no unmask */
    mock_av(&m, 0x0500);
    m.n_src_sched = 0;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_NO_NEXT_CAUSE_AFTER_SERVICE && strcmp(res.status_name, "no_next_cause_after_service") == 0 && strcmp(res.status_class, "observation") == 0);
    CHECK(strcmp(res.teardown_variant, "S4A_rearmed_no_next_cause") == 0 && res.next_cause_timed_out == 1 && res.next_cause_found == 0 && res.next_cause_polls > 0);
    CHECK(res.rearm_completed == 1 && res.acked && res.transport_ok && res.restore_ok && m.intsr_writes == 0 && m.unmask_calls == 1);
    CHECK(res.a.stop_value == 0x8AAA && count_lines_with(&rl, "NEXTCAUSE found=0 timed_out=1 t_end=") == 1 && count_lines_with(&rl, "CLEANUP performed=0") == 1);
}

/* ---- 33/34/35: zero second delivery, the latched cause closed by the teardown ---- */
static void test_second_cause_never_delivered(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    unsigned k;
    int rearm, latched = -1;
    mock_av(&m, 0x0500);
    m.n_src_sched = 0; sched(&m, W_REARM, 0, 0x0500);
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED && res.next_cause_immediate == 1);
    rearm = nth_irqw(&m, W_REARM);
    for (k = (unsigned)rearm; k < m.nops; k++) {
        CHECK(m.ops[k].kind != MOCK_IRQ_UNMASK && m.ops[k].kind != MOCK_ISR_ENTRY);   /* 33/34 */
        CHECK((m.ops[k].intmr & GBP_PI_HSP_BIT) == 0);                                /* INTMR bit 13 stays 0 */
        if (latched < 0 && (m.ops[k].intsr & GBP_PI_HSP_BIT)) latched = (int)k;
    }
    CHECK(latched > rearm && m.deliveries == 1 && m.unmask_calls == 1);
    /* 35: the teardown closes it — STOP acknowledges the sources, then exactly one W1C */
    CHECK(res.a.stop_value == (0x0500 | 0x8AAA) && res.a.pi_cleanup_performed == 1 && res.a.pi_cleanup_ok == 1 && res.pi_sticky_final == 0);
    CHECK(m.intsr_writes == 1 && res.teardown_w1c == 1 && (m.intsr & GBP_PI_HSP_BIT) == 0);
    CHECK(count_lines_with(&rl, "CLEANUP performed=1 value=00002000") == 1);
}

/* ---- 1/2/3 and the other early aborts ---- */
static void test_early_aborts(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    mock_av(&m, 0x0500); m.present = 0; m.absent_fill = 0xC1;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ABORT_STAGE_A && strcmp(res.status_name, "abort_not_present") == 0 && res.stage_a_aborted && strcmp(res.teardown_variant, "stage_a") == 0);
    CHECK(res.a.control_written == 0 && res.power_cycle_required == 0 && res.drains_attempted == 0 && count_lines_with(&rl, "AVSVC end status=abort_not_present class=abort") == 1);
    mock_av(&m, 0x0500); m.source_assert_after_write = 0;                   /* 2: no first cause */
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_NO_INITIAL_CAUSE && strcmp(res.teardown_variant, "S2_before_unmask") == 0 && res.unmasks == 0 && strcmp(res.status_class, "observation") == 0);
    mock_av(&m, 0x0500); m.delivery_suppressed = 1;                          /* 3: unmasked, nothing delivered */
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_FIRST_DELIVERY_TIMEOUT && strcmp(res.status_name, "first_delivery_timeout") == 0 && res.d.timed_out && res.deliveries == 0);
    CHECK(strcmp(res.teardown_variant, "S3_service_aborted") == 0 && res.drains_attempted == 0 && res.k.w_ack.attempted == 0);
    mock_av(&m, 0x0500); m.unmask_ignored = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_AVSVC_ABORT_UNMASK);
    mock_av(&m, 0x0500); m.irq_ops_available = 0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_AVSVC_ABORT_HANDLER_INSTALL && strcmp(res.reason, "irq_ops_unavailable") == 0);
    mock_av(&m, 0x0500); m.install_fails = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_AVSVC_ABORT_HANDLER_INSTALL && strcmp(res.reason, "install_failed") == 0);
    mock_av(&m, 0x0500); m.record_dirty_on_install = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_AVSVC_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "record_not_clear") == 0);
    mock_av(&m, 0x0500); m.clear_cause_on_install = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_AVSVC_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "cause_lost") == 0);
    mock_av(&m, 0x0500); m.control_on_install = 0x90;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_CONTROL_CHANGED && strcmp(res.reason, "control_changed_PREUNMASK") == 0);
    /* no whole-block read in the transport: the delivery happens, the drain does not, no ACK */
    mock_av(&m, 0x0500); m.bulk_ops_available = 0;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ABORT_BULK_UNAVAILABLE && strcmp(res.reason, "bulk_read_unavailable") == 0 && strcmp(res.status_class, "abort") == 0);
    CHECK(res.deliveries == 1 && res.presvc_ok == 1 && res.pending_irq == 0x0500 && res.drains_attempted == 0 && res.k.w_ack.attempted == 0);
    CHECK(strcmp(res.teardown_variant, "S3_service_aborted") == 0 && count_lines_with(&rl, "SVC abort reason=bulk_read_unavailable") == 1);
    /* reentry */
    mock_av(&m, 0x0500); m.second_delivery = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_REENTRY && res.drains_attempted == 0);
    /* mask failure after the delivery */
    mock_av(&m, 0x0500); m.mask_ignored_from_call = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_MASK_FAILURE && strcmp(res.reason, "intmr13_still_set_after_remask") == 0 && res.drains_attempted == 0);
    /* CONTROL changes by itself after the ACK: POSTACK */
    mock_av(&m, 0x0500); m.control_change_after_irq_write = W_ACK; m.control_change_value = 0x90;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_CONTROL_CHANGED && strcmp(res.reason, "control_changed_POSTACK") == 0 && res.rearm_attempted == 0 && res.control_ok == 0);
    /* CONTROL changes after the re-arm: REARMPOST */
    mock_av(&m, 0x0500); m.control_change_after_irq_write = W_REARM; m.control_change_value = 0x90;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_CONTROL_CHANGED && strcmp(res.reason, "control_changed_REARMPOST") == 0);
    /* Disc != GBI at PRESVC */
    mock_av(&m, 0x0500); m.irq_disagree_from_write = W_A2 + 1u;   /* from the 3rd write on: never reached; use the install hook instead */
    m.irq_disagree_from_write = 0; m.irq_disagree_on_install = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_AVSVC_ABORT_PRE_UNMASK_STATE && strcmp(res.reason, "semantic_disagree") == 0);
    /* POSTACK shape: bit 15 not retained by the ACK write — no re-arm on an unexpected read-back */
    mock_av(&m, 0x0500); m.bit15_drop_at_write = W_ACK;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_ANOMALY_POSTACK_SHAPE && strcmp(res.reason, "postack_shape") == 0 && res.rearm_attempted == 0 && res.acked == 1);
    CHECK(strcmp(res.postack_reason, "postack_shape") == 0 && strcmp(res.teardown_variant, "S3_service_aborted") == 0 && res.k.postack.irq_gbi == 0x0000);
}

/* ---- 41: attempted before the transport call, completed only on rc ok (seen at the moment of the write) ---- */
struct hook_state { const struct gbp_avsvc_result *res; unsigned writes; int ok; uint16_t values[8]; int att_ack, comp_ack, att_rearm, comp_rearm; };
static void write_hook(struct gbp_mock *m, uint32_t addr, const uint8_t data[GBP_BLOCK_SIZE], void *user)
{
    struct hook_state *h = (struct hook_state *)user;
    (void)m;
    if ((((addr - BASE) >> 20) & 0xFu) != 0xDu) return;
    if (h->writes < 8) h->values[h->writes] = (uint16_t)((data[0x1E] << 8) | data[0x1F]);
    h->writes++;
    if (h->writes == W_ACK) { h->att_ack = h->res->k.w_ack.attempted; h->comp_ack = h->res->k.w_ack.completed; }
    if (h->writes == W_REARM) { h->att_rearm = h->res->w_rearm.attempted; h->comp_rearm = h->res->w_rearm.completed; }
}

static void test_attempted_at_call_time(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res; struct hook_state h;
    memset(&h, 0, sizeof h); h.res = &res;
    mock_av(&m, 0x0500);
    m.write_hook = write_hook; m.write_hook_user = &h;
    run(&m, &rl, &res);
    CHECK(h.writes == 5 && h.att_ack == 1 && h.comp_ack == 0 && h.att_rearm == 1 && h.comp_rearm == 0);
    CHECK(h.values[0] == 0x8aae && h.values[1] == 0x0000 && h.values[2] == 0x8500 && h.values[3] == 0x0000 && h.values[4] == 0x8faa);   /* STOP = read (0x0500 latched) | 0x8AAA */
    CHECK(res.k.w_ack.completed == 1 && res.w_rearm.completed == 1);
    CHECK(res.k.w_ack.raw[0x1e] == 0x85 && res.k.w_ack.raw[0x1f] == 0x00 && res.w_rearm.raw[0] == 0 && res.w_rearm.raw[31] == 0);
}

/* ---- 42: raw buffers preserved (never modified after the DMA, not by the summary, not by the teardown) ---- */
static void test_raw_buffers_preserved(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    uint32_t ca, cv;
    mock_av(&m, 0x0500);
    m.bulk_seed = 0x42;
    run(&m, &rl, &res);
    CHECK(pattern_ok(audio_buf, 8, 0x42, 0x1000) && pattern_ok(video_buf, 1, 0x42, 0x0F00));
    ca = gbp_crc32(audio_buf, 0x1000); cv = gbp_crc32(video_buf, 0x0F00);
    CHECK(res.audio.crc32 == ca && res.video.crc32 == cv);
    gbp_avblock_summarize(&res.audio);                                      /* summarizing again changes nothing */
    CHECK(gbp_crc32(audio_buf, 0x1000) == ca && res.audio.crc32 == ca);
    {
        struct gbp_avdump_info info;
        CHECK(gbp_avsvc_dump_info(&res, 40500000u, "GBP-AV-SERVICE-001", "avsvc-0001", "gbp-av-service-probe", "5ed9d93-dirty", &info) == 0);
        CHECK(info.flags == 0xF && info.audio_len == 0x1000 && info.video_len == 0x0F00 && info.pending_irq == 0x0500 && info.drain_mask == 0x0500);
        CHECK(strcmp(info.test_id, "GBP-AV-SERVICE-001") == 0 && strcmp(info.build_id, "avsvc-0001") == 0 && info.audio_index == 8 && info.video_index == 1);
        CHECK(strcmp(info.app, "gbp-av-service-probe") == 0 && strcmp(info.commit, "5ed9d93-dirty") == 0 && info.identity_error == 0);
        /* an identity that does not fit is never truncated: the description is refused, the serializer refuses */
        CHECK(gbp_avsvc_dump_info(&res, 40500000u, "GBP-AV-SERVICE-001-with-a-much-longer-name", "avsvc-0001", "gbp-av-service-probe", "x", &info) == -1);
        CHECK(info.identity_error == 1 && info.test_id[0] == '\0');
        {
            static uint8_t dump[GBP_AVDUMP_MAX_SIZE];
            CHECK(gbp_avdump_serialize(&info, res.audio.buf, res.video.buf, dump, sizeof dump) == -2);
        }
        CHECK(info.audio_dt_ticks == (uint32_t)(res.audio.t_end - res.audio.t_start) && info.audio_wait_ticks == res.audio.info.ticks && info.tb_hz == 40500000u);
    }
    /* not-attempted blocks are described with length 0 */
    mock_av(&m, 0x0400);
    run(&m, &rl, &res);
    {
        struct gbp_avdump_info info;
        CHECK(gbp_avsvc_dump_info(&res, 40500000u, "T", "B", "A", "C", &info) == 0);
        CHECK(info.flags == (GBP_AVDUMP_FLAG_AUDIO_PRESENT | GBP_AVDUMP_FLAG_AUDIO_VALID) && info.audio_len == 0x1000 && info.video_len == 0 && info.video_dt_ticks == 0);
    }
}

/* ---- 39/48/49: time-base wrap, worst-case lines, ring overflow ---- */
static void test_wrap_lines_and_config(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res; struct gbp_avsvc_config cfg;
    mock_av(&m, 0x0500);
    m.tick = 0xFFFFFF00u;                                                    /* the whole run wraps the 32-bit time base */
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED && res.dt_rearm_to_next_cause > 0 && res.dt_rearm_to_next_cause < 1000);
    CHECK(res.dt_service > 0 && res.dt_service < 2000 && (uint32_t)(res.audio.t_end - res.audio.t_start) > 0);
    CHECK(rl.truncated == 0 && max_line_len(&rl) < LINE_LEN);
    /* worst-case field widths: 10-digit time base, every field populated */
    mock_av(&m, 0x0500); m.tick = 4000000000u; m.pi_relatch_after_ticks = 40; m.irq_byte0_anomaly = 1;
    run(&m, &rl, &res);
    CHECK(rl.truncated == 0 && rl.dropped == 0 && max_line_len(&rl) < LINE_LEN);
    CHECK(max_line_len(&rl) <= 230);
    /* ring overflow: no crash, lines dropped and counted */
    {
        struct gbp_transport t;
        mock_av(&m, 0x0500);
        gbp_mock_transport(&m, &t);
        test_config(&cfg);
        ringlog_init(&rl, storage, LINE_LEN, 40);
        gbp_avsvc_probe_run(&t, &rl, &cfg, &res);
        CHECK(rl.count == 40 && rl.dropped > 0 && res.status == GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED);
    }
    /* config defaults and the physical time base */
    gbp_avsvc_config_default(&cfg);
    CHECK(cfg.t_delivery_ms == 100 && cfg.t_next_cause_ms == 500 && cfg.ack_or == 0x8000 && cfg.av_mask == 0x0500 && cfg.src_mask == 0x0555);
    CHECK(cfg.audio_index == 8 && cfg.audio_len == 0x1000 && cfg.audio_src == 0x0400 && cfg.video_index == 1 && cfg.video_len == 0x0F00 && cfg.video_src == 0x0100);
    CHECK(cfg.t_delivery_ticks == 4050000u && cfg.t_next_cause_ticks == 20250000u);
    gbp_avsvc_config_timebase(&cfg, 1000);
    CHECK(cfg.t_delivery_ticks == 100 && cfg.t_next_cause_ticks == 500);
    CHECK(strcmp(gbp_avsvc_status_name(GBP_AVSVC_ANOMALY_POSTACK_SHAPE), "anomaly_postack_shape") == 0 && strcmp(gbp_avsvc_rearmpost_name(0), "-") == 0);
    CHECK(strcmp(gbp_avsvc_status_class(GBP_AVSVC_AUDIO_DMA_TIMEOUT), "dma") == 0 && strcmp(gbp_avsvc_status_class(GBP_AVSVC_ABORT_TRANSPORT), "transport") == 0);
    /* no buffers configured: the drain cannot start, nothing is acknowledged */
    mock_av(&m, 0x0500);
    test_config(&cfg); cfg.audio_buf = 0; cfg.audio_cap = 0;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.status == GBP_AVSVC_AUDIO_DMA_ERROR && res.audio.attempted == 0 && res.k.w_ack.attempted == 0);
}

/* ---- the 003B extended handler run by the mock, by hand: mask before W1C, one W1C, second read ---- */
static void test_handler_order(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res;
    int entry, imask, iw1c, iexit;
    mock_av(&m, 0x0500);
    run(&m, &rl, &res);
    entry = nth(&m, MOCK_ISR_ENTRY, 1); imask = nth(&m, MOCK_ISR_MASK, 1); iw1c = nth(&m, MOCK_ISR_W1C, 1); iexit = nth(&m, MOCK_ISR_EXIT, 1);
    CHECK(entry >= 0 && imask > entry && iw1c > imask && iexit > iw1c && nth(&m, MOCK_ISR_W1C, 2) < 0 && nth(&m, MOCK_ISR_ENTRY, 2) < 0);
    CHECK(res.d.rec.count == 1 && res.d.rec.fired == 1 && res.d.rec.t_second > res.d.rec.t_entry && res.d.rec.intsr_before_w1c != 0);
    CHECK(count_lines_with(&rl, "HANDLERPI2 t_second=") == 1 && count_lines_with(&rl, "HANDLER fired=1 count=1") == 1);
}

/* ---- physical fixtures as prefixes ---- */
static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb"); long n; char *buf;
    if (!f) return 0;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    buf = (char *)malloc((size_t)n + 1);
    if (!buf) { fclose(f); return 0; }
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(buf); return 0; }
    buf[n] = '\0'; fclose(f);
    return buf;
}

static unsigned count_ops(const char *text)
{
    unsigned n = 0; const char *p = text;
    while (*p) { const char *e = strchr(p, '\n'); size_t len = e ? (size_t)(e - p) : strlen(p);
        while (len && (*p == ' ' || *p == '\t')) { p++; len--; }
        if (len && *p != '#') n++;
        p = e ? e + 1 : p + len; }
    return n;
}

/* cut the script before the Nth occurrence of `marker` (a line start); optionally drop lines starting with `drop` */
static char *cut_before(const char *text, const char *marker, unsigned nth_occ, const char *drop)
{
    const char *p = text, *cut = 0;
    unsigned seen = 0;
    char *out; size_t o = 0;
    while (*p) {
        const char *e = strchr(p, '\n');
        size_t len = e ? (size_t)(e - p) : strlen(p);
        if (strncmp(p, marker, strlen(marker)) == 0 && ++seen == nth_occ) { cut = p; break; }
        p = e ? e + 1 : p + len;
    }
    if (!cut) return 0;
    out = (char *)malloc((size_t)(cut - text) + 200);
    if (!out) return 0;
    p = text;
    while (p < cut) {
        const char *e = strchr(p, '\n');
        size_t len = (e && e < cut) ? (size_t)(e - p + 1) : (size_t)(cut - p);
        if (!(drop && strncmp(p, drop, strlen(drop)) == 0)) { memcpy(out + o, p, len); o += len; }
        p += len;
    }
    memcpy(out + o, "# BOUNDARY: physical prefix ends here (cut before the device ACK); nothing after this line is physical data\n", 108);
    o += 108;
    out[o] = '\0';
    return out;
}

static void test_hw_initirqa_prefix(const char *path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_avsvc_config cfg; struct gbp_avsvc_result res; struct ringlog rl;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    gbp_replay_init(&r, text);
    gbp_replay_transport(&r, &t);
    gbp_avsvc_config_default(&cfg); cfg.audio_buf = audio_buf; cfg.audio_cap = sizeof audio_buf; cfg.video_buf = video_buf; cfg.video_cap = sizeof video_buf;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_avsvc_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.status == GBP_AVSVC_ABORT_HANDLER_INSTALL && strcmp(res.reason, "irq_ops_unavailable") == 0);   /* that run had no interrupt path */
    CHECK(r.exhausted == 0 && r.mismatches == 0 && r.step == count_ops(text) && res.a.t_event == 4155517524u);
    CHECK(res.drains_attempted == 0 && res.k.w_ack.attempted == 0 && res.a.pi_cleanup_performed == 1);
    free(text);
}

/* the 003B run (initirqb-0001) cut before its device ACK: stage, EVENT, install, PREUNMASK, the physical delivery and the
 * PREACK reads (= this probe's PRESVC) are physical; the drain meets a transport with no whole-block read */
static void test_hw_initirqb_prefix(const char *path)
{
    char *text = read_file(path), *cut;
    struct gbp_replay r; struct gbp_transport t; struct gbp_avsvc_config cfg; struct gbp_avsvc_result res; struct ringlog rl;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    cut = cut_before(text, "W 01d00000", 3, 0);            /* the 3rd IRQ write of that run is its ACK */
    CHECK(cut != 0);
    if (!cut) { free(text); return; }
    gbp_replay_init(&r, cut);
    CHECK(r.has_irq_ops == 1 && r.has_bulk_ops == 0);
    gbp_replay_transport(&r, &t);
    gbp_avsvc_config_default(&cfg); cfg.audio_buf = audio_buf; cfg.audio_cap = sizeof audio_buf; cfg.video_buf = video_buf; cfg.video_cap = sizeof video_buf;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_avsvc_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(r.mismatches == 0 && r.exhausted > 0 && r.step == count_ops(cut));  /* every physical operation matched; exhausted only afterwards */
    CHECK(res.status == GBP_AVSVC_ABORT_BULK_UNAVAILABLE && res.deliveries == 1 && res.d.fired == 1 && res.d.rec.count == 1);
    CHECK(res.a.t_event == 3679890204u && res.presvc_ok == 1 && res.pending_irq == 0x0500 && res.drain_mask == 0x0500);
    CHECK(res.presvc.irq_gbi == 0x0500 && res.presvc.irq_disc == 0x0500 && res.presvc.control_vote == 0x8c && (res.presvc.intsr & GBP_PI_HSP_BIT) == 0);
    CHECK(res.audio.selected == 1 && res.video.selected == 1 && res.drains_attempted == 0 && res.k.w_ack.attempted == 0 && res.rearm_attempted == 0);
    CHECK(res.restore_ok == 0 && res.uncertain_writes >= 1);              /* the teardown ran against an exhausted script: reported, never hidden */
    CHECK(count_lines_with(&rl, "SVC start pending=0500 drain=0500 audio=1 video=1 order=audio_then_video ack_value=8500 ack_source=PRESVC") == 1);
    CHECK(count_lines_with(&rl, "SVC abort reason=bulk_read_unavailable") == 1 && count_lines_with(&rl, "IRQW tag=ACK") == 0);
    free(cut); free(text);
}

/* the 004 run (initirq4-0001) the same way; its "I p 0" (a generation publication of the multi-cycle handler, absent
 * from the 003B ext handler) is dropped; the handler record it carries has the same fourteen numbers */
static void test_hw_initirq4_prefix(const char *path)
{
    char *text = read_file(path), *cut;
    struct gbp_replay r; struct gbp_transport t; struct gbp_avsvc_config cfg; struct gbp_avsvc_result res; struct ringlog rl;
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    cut = cut_before(text, "W 01d00000", 3, "I p ");
    CHECK(cut != 0);
    if (!cut) { free(text); return; }
    gbp_replay_init(&r, cut);
    gbp_replay_transport(&r, &t);
    gbp_avsvc_config_default(&cfg); cfg.audio_buf = audio_buf; cfg.audio_cap = sizeof audio_buf; cfg.video_buf = video_buf; cfg.video_cap = sizeof video_buf;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_avsvc_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(r.mismatches == 0 && r.exhausted > 0 && r.step == count_ops(cut));
    CHECK(res.status == GBP_AVSVC_ABORT_BULK_UNAVAILABLE && res.deliveries == 1 && res.a.t_event == 1053111645u);
    CHECK(res.d.rec.t_entry == 1053156665u && res.d.latency_ticks == 89u && res.d.rec.intsr_after_ack == 0x00010000u);
    CHECK(res.presvc.ticks == 1053165161u && res.presvc.irq_gbi == 0x0500 && res.pending_irq == 0x0500 && res.presvc.intsr == 0x00010000u && res.presvc.control_vote == 0x8c);
    CHECK(res.dt_isr_to_presvc == 8496u && res.drains_attempted == 0 && res.k.w_ack.attempted == 0);
    CHECK(count_lines_with(&rl, "PRESVC t=1053165161 intsr13=0,0 intmr13=0,0 control=8c irq=0500/0500 src=0500 av=0500 unexpected=0000 odd=0000 bit15=0 high=0000") == 1);
    free(cut); free(text);
}

/* ---- host round-trip modes (synthetic) ---- */
static int dump_log(const char *path, const char *blocks_path)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_avsvc_result res; char s[2000]; size_t i; FILE *f;
    struct gbp_avdump_info info; static uint8_t dump[GBP_AVDUMP_MAX_SIZE]; long n;
    /* the nominal both-sources scenario with a synthetic re-latch at POSTACK (so the main W1C is part of the round trip),
     * REARMPOST A and a delayed next cause; 10-digit time base */
    mock_av(&m, 0x0500); m.pi_relatch_after_ticks = 40; m.bulk_seed = 0x33;
    m.intsr = 0x00010000u; m.intmr = 0x000001fau; m.tick = 1000;
    run(&m, &rl, &res);
    gbp_avsvc_summary(&res, s, sizeof s);
    f = fopen(path, "w");
    if (!f) { fprintf(stderr, "cannot write %s\n", path); return 1; }
    fprintf(f, "# OPENGBP-LOG v1\n# SYNTHETIC: generated by tests/unit/test_gbp_avsvc.c from the host mock (drained service scenario); NOT physical data\n");
    fprintf(f, "test_id=GBP-AV-SERVICE-001\nbuild_id=synthetic\ncommit=none\nsource=host-mock\n");
    fprintf(f, "lines=%u dropped=%u truncated=%u\n# --- records ---\n", (unsigned)rl.count, (unsigned)rl.dropped, (unsigned)rl.truncated);
    for (i = 0; i < rl.count; i++) fprintf(f, "%s\n", ringlog_line(&rl, i));
    fprintf(f, "# --- end --- dropped=%u\n", (unsigned)rl.dropped);
    fclose(f);
    if (gbp_avsvc_dump_info(&res, 40500000u, "GBP-AV-SERVICE-001", "synthetic", "gbp-av-service-probe", "none", &info) != 0) { fprintf(stderr, "identity rejected\n"); return 1; }
    n = gbp_avdump_serialize(&info, res.audio.buf, res.video.buf, dump, sizeof dump);
    if (n <= 0) { fprintf(stderr, "cannot serialize the sidecar\n"); return 1; }
    f = fopen(blocks_path, "wb");
    if (!f) { fprintf(stderr, "cannot write %s\n", blocks_path); return 1; }
    fwrite(dump, 1, (size_t)n, f);
    fclose(f);
    printf("SUMMARY %s\n", s);
    printf("BLOCKS audio_crc32=%08lx video_crc32=%08lx bytes=%ld\n", (unsigned long)info.audio_crc32, (unsigned long)info.video_crc32, n);
    return 0;
}

struct sidecar { struct gbp_avdump_info info; const uint8_t *audio, *video; uint8_t *raw; unsigned calls; };
static uint32_t sidecar_source(void *ctx, uint32_t base, uint32_t addr, uint32_t len, uint8_t *out)
{
    struct sidecar *sc = (struct sidecar *)ctx;
    unsigned idx = (unsigned)((addr - base) >> 20) & 0xFu;
    sc->calls++;
    if (idx == sc->info.audio_index && sc->audio && sc->info.audio_len == len) { memcpy(out, sc->audio, len); return len; }
    if (idx == sc->info.video_index && sc->video && sc->info.video_len == len) { memcpy(out, sc->video, len); return len; }
    return 0;
}

static int replay_fixture(const char *path, const char *blocks_path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_avsvc_config cfg;
    struct gbp_avsvc_result res; struct ringlog rl; char s[2000];
    struct sidecar sc; static uint8_t raw[GBP_AVDUMP_MAX_SIZE + 64]; long n = 0;
    memset(&sc, 0, sizeof sc);
    if (!text) { fprintf(stderr, "cannot read %s\n", path); return 1; }
    if (blocks_path) {
        FILE *f = fopen(blocks_path, "rb");
        if (!f) { fprintf(stderr, "cannot read %s\n", blocks_path); free(text); return 1; }
        n = (long)fread(raw, 1, sizeof raw, f);
        fclose(f);
        if (gbp_avdump_parse(raw, (size_t)n, &sc.info, &sc.audio, &sc.video) != 0) { fprintf(stderr, "bad sidecar %s\n", blocks_path); free(text); return 1; }
    }
    gbp_replay_init(&r, text);
    if (blocks_path) { r.block_source = sidecar_source; r.block_ctx = &sc; }
    gbp_replay_transport(&r, &t);
    test_config(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_avsvc_probe_run(&t, &rl, &cfg, &res);
    gbp_avsvc_summary(&res, s, sizeof s);
    printf("SUMMARY %s\n", s);
    printf("REPLAY step=%u exhausted=%u mismatches=%u tick_polls=%u timeline=%d log_lines=%u bulk_reads=%u blocks_missing=%u block_crc_mismatches=%u\n",
           r.step, r.exhausted, r.mismatches, r.tick_polls, r.timeline, (unsigned)rl.count, r.bulk_reads, r.blocks_missing, r.block_crc_mismatches);
    free(text);
    return (r.exhausted || r.mismatches || r.blocks_missing || r.block_crc_mismatches) ? 1 : 0;
}

/* ---- the physical GBP-AV-SERVICE-001 fixture (2026-09-16, avsvc-0001, commit d3a6d23) with its block sidecar ---- */
static void test_hw_avsvc_gbp(const char *path, const char *blocks_path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_avsvc_config cfg; struct gbp_avsvc_result res; struct ringlog rl;
    struct sidecar sc; static uint8_t raw[GBP_AVDUMP_MAX_SIZE + 64]; long n; FILE *f; unsigned i, nz = 0, line0_01 = 0, line0_11 = 0;
    memset(&sc, 0, sizeof sc);
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    f = fopen(blocks_path, "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", blocks_path); failures++; free(text); return; }
    n = (long)fread(raw, 1, sizeof raw, f);
    fclose(f);
    CHECK(n == 8204);
    CHECK(gbp_avdump_parse(raw, (size_t)n, &sc.info, &sc.audio, &sc.video) == 0);
    if (!sc.audio || !sc.video) { free(text); return; }
    /* sidecar identity and header: the console's file, format version 2, both blocks valid */
    CHECK(sc.info.version == 2u && sc.info.pending_irq == 0x0500 && sc.info.drain_mask == 0x0500 && sc.info.tb_hz == 40500000u);
    CHECK(strcmp(sc.info.test_id, "GBP-AV-SERVICE-001") == 0 && strcmp(sc.info.build_id, "avsvc-0001") == 0);
    CHECK(strcmp(sc.info.app, "gbp-av-service-probe") == 0 && strcmp(sc.info.commit, "d3a6d23") == 0);
    CHECK(sc.info.audio_index == 8u && sc.info.audio_len == 0x1000u && sc.info.audio_rc == 0u && sc.info.audio_wait_ticks == 2475u && sc.info.audio_dt_ticks == 2692u);
    CHECK(sc.info.video_index == 1u && sc.info.video_len == 0x0F00u && sc.info.video_rc == 0u && sc.info.video_wait_ticks == 2319u && sc.info.video_dt_ticks == 2485u);
    CHECK(sc.info.audio_crc32 == 0xfec5e4e7u && sc.info.video_crc32 == 0xfe45ff08u);
    CHECK(gbp_crc32(sc.audio, 0x1000u) == 0xfec5e4e7u && gbp_crc32(sc.video, 0x0F00u) == 0xfe45ff08u);
    CHECK(sc.info.header_crc32 == 0x6174e52du && sc.info.total_crc32 == 0x18e966cfu);
    /* replay end to end */
    memset(audio_buf, 0xC1, sizeof audio_buf); memset(video_buf, 0xC1, sizeof video_buf);
    gbp_replay_init(&r, text);
    r.block_source = sidecar_source; r.block_ctx = &sc;
    gbp_replay_transport(&r, &t);
    gbp_avsvc_config_default(&cfg); cfg.audio_buf = audio_buf; cfg.audio_cap = sizeof audio_buf; cfg.video_buf = video_buf; cfg.video_cap = sizeof video_buf;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_avsvc_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(r.mismatches == 0 && r.exhausted == 0 && r.step == 132u && r.step == count_ops(text) && r.tick_polls == 0 && r.timeline == 1);
    CHECK(r.bulk_reads == 2u && r.blocks_missing == 0u && r.block_crc_mismatches == 0u && sc.calls == 2u);
    CHECK(res.status == GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED && strcmp(res.status_class, "ok") == 0 && res.restore_ok == 1 && res.errors == 0);
    CHECK(strcmp(res.teardown_variant, "S4B_next_cause_latched") == 0 && res.transport_ok == 1 && res.uncertain_writes == 0 && res.power_cycle_required == 1);
    /* first cause and delivery */
    CHECK(res.a.t_event == 3391329164u && res.cause_irq == 0x0400 && res.preunmask.irq_gbi == 0x0500 && res.preunmask_ok);
    CHECK(res.d.fired == 1 && res.d.reentry == 0 && res.d.rec.t_entry == 3391371694u && res.d.t_unmask == 3391371622u && res.d.latency_ticks == 72u);
    CHECK(res.d.rec.intsr_after_ack == 0x00010000u && res.d.intsr_post_unmask == 0x00010000u && res.d.intmr_post_unmask == 0x000001fau && res.delivered == 1);
    CHECK(res.dt_cause_to_isr == 42530u && res.dt_isr_to_presvc == 7612u);
    /* PRESVC: the authoritative snapshot */
    CHECK(res.presvc.ticks == 3391379306u && res.presvc.irq_gbi == 0x0500 && res.presvc.irq_disc == 0x0500 && res.presvc.control_vote == 0x8c);
    CHECK(res.presvc.intsr == 0x00010000u && res.presvc.intsr2 == 0x00010000u && res.presvc_ok && res.pending_irq == 0x0500 && res.drain_mask == 0x0500);
    /* the two whole-block reads */
    CHECK(res.audio.selected && res.audio.attempted && res.audio.completed && res.audio.rc == GBP_OK && res.audio.addr == 0x01800000u && res.audio.len == 0x1000u);
    CHECK(res.audio.t_start == 3391385098u && res.audio.t_end == 3391387790u);
    CHECK(res.video.selected && res.video.attempted && res.video.completed && res.video.rc == GBP_OK && res.video.addr == 0x01100000u && res.video.len == 0x0F00u);
    CHECK(res.video.t_start == 3391387818u && res.video.t_end == 3391390303u);
    CHECK(res.drains_selected == 2 && res.drains_attempted == 2 && res.drains_completed == 2 && res.drain_uncertain == 0 && res.t_service_end == 3391390303u);
    CHECK(res.dt_service == 10997u && res.dt_presvc_to_ack == 20674u);
    CHECK(memcmp(audio_buf, sc.audio, 0x1000u) == 0 && memcmp(video_buf, sc.video, 0x0F00u) == 0);   /* the sidecar bytes, not a pre-fill */
    CHECK(res.audio.summarized && res.audio.crc32 == 0xfec5e4e7u && res.audio.zeros == 3969u && res.audio.distinct == 3u && res.audio.first_word == 0x01000000u && res.audio.gbi_frame_start == 0);
    CHECK(res.video.summarized && res.video.crc32 == 0xfe45ff08u && res.video.zeros == 0u && res.video.distinct == 2u && res.video.first_word == 0xffffffffu && res.video.gbi_frame_start == 1);
    for (i = 0; i < 0x1000u; i++) if (audio_buf[i]) nz++;
    for (i = 0; i < 0x1000u; i += 32u) { if (audio_buf[i] == 0x01) line0_01++; else if (audio_buf[i] == 0x11) line0_11++; }
    CHECK(nz == 127u && line0_01 == 121u && line0_11 == 2u);                     /* raw positions, not a format */
    CHECK(video_buf[0] == 0xff && video_buf[1] == 0xff && video_buf[2] == 0xff && video_buf[3] == 0xff && video_buf[4] == 0x7f && video_buf[5] == 0x7f && video_buf[6] == 0xff && video_buf[7] == 0xff);
    /* POSTDRAIN (observation), ACK, POSTACK, PI clean */
    CHECK(res.postdrain.ticks == 3391394064u && res.postdrain.irq_gbi == 0x0500 && res.postdrain.intsr == 0x00010000u && res.postdrain_ok && res.relatch_postdrain == 0);
    CHECK(res.k.irq_pending == 0x0500 && res.k.ack_value == 0x8500 && res.k.w_ack.attempted == 1 && res.k.w_ack.completed == 1 && res.k.w_ack.value == 0x8500 && res.k.w_ack.before == 0x0500);
    CHECK(res.k.w_ack.t_after == 3391399980u && res.acked == 1 && res.k.ack_skipped == 0);
    CHECK(res.k.postack.ticks == 3391401028u && res.k.postack.irq_gbi == 0x8000 && res.k.postack.intsr == 0x00010000u && res.k.postack.intsr2 == 0x00010000u && res.k.postack.control_vote == 0x8c);
    CHECK(res.postack_ok && res.source_after_ack == 0x0000 && res.relatch_postack == 0 && res.k.main_pi_w1c == 0 && res.dt_ack_to_postack == 1048u);
    CHECK(res.pi_clean == 1 && res.pi_sticky == 0 && res.pi_clean_intsr == 0x00010000u && res.pi_clean_intmr == 0x000001fau);
    /* re-arm, REARMPOST B, the next cause found at once and never delivered */
    CHECK(res.rearm_attempted == 1 && res.rearm_completed == 1 && res.t_rearm == 3391408218u && res.rearm_before == 0x8000 && res.w_rearm.value == 0x0000 && res.w_rearm.t_after == 3391408974u);
    CHECK(res.dt_postack_to_rearm == 7190u);
    CHECK(res.rearmpost.ticks == 3391409996u && res.rearmpost.intsr == 0x00012000u && res.rearmpost.intsr2 == 0x00012000u && res.rearmpost.intmr == 0x000001fau);
    CHECK(res.rearmpost.irq_gbi == 0x0400 && res.rearmpost.irq_disc == 0x0400 && res.rearmpost.control_vote == 0x8c && res.rearmpost_outcome == GBP_AVSVC_REARMPOST_B_LATCHED && res.rearmpost_ok);
    CHECK(res.next_cause_found == 1 && res.next_cause_immediate == 1 && res.next_cause_timed_out == 0 && res.next_cause_polls == 0);
    CHECK(res.t_next_cause == 3391409996u && res.dt_rearm_to_next_cause == 1778u && res.next_cause_irq == 0x0400 && res.next_cause_intsr == 0x00012000u);
    CHECK(res.unmasks == 1 && res.deliveries == 1 && res.acks == 1 && res.isr_w1c == 1 && res.main_w1c == 0 && res.teardown_w1c == 1 && res.unexpected == 0 && res.control_ok == 1 && res.pi_sticky_final == 0);
    /* the records of the replay are the console's (the poll counters and transport info of a scripted transport aside) */
    CHECK(count_lines_with(&rl, "PRESVC t=3391379306 intsr13=0,0 intmr13=0,0 control=8c irq=0500/0500 src=0500 av=0500 unexpected=0000 odd=0000 bit15=0 high=0000") == 1);
    CHECK(count_lines_with(&rl, "SVC start pending=0500 drain=0500 audio=1 video=1 order=audio_then_video ack_value=8500 ack_source=PRESVC t=3391379306") == 1);
    CHECK(count_lines_with(&rl, "AUDIOREAD idx=8 addr=01800000 len=1000 selected=1 attempted=1 completed=1 rc=ok t_start=3391385098 t_end=3391387790 dt=2692") == 1);
    CHECK(count_lines_with(&rl, "VIDEOREAD idx=1 addr=01100000 len=0f00 selected=1 attempted=1 completed=1 rc=ok t_start=3391387818 t_end=3391390303 dt=2485") == 1);
    CHECK(count_lines_with(&rl, "SVCEND drain=0500 selected=2 attempted=2 completed=2 ok=1 t_end=3391390303 dt_service=10997 audio_rc=ok video_rc=ok") == 1);
    CHECK(count_lines_with(&rl, "POSTDRAIN t=3391394064 intsr13=0,0 intmr13=0,0 control=8c irq=0500/0500 src=0500 av=0500 unexpected=0000 odd=0000 bit15=0 high=0000") == 1);
    CHECK(count_lines_with(&rl, "POSTDRAIN observation_only=1 relatch=0 av_after_drain=0500 pending_kept=0500") == 1);
    CHECK(count_lines_with(&rl, "POSTACKAV t=3391401028 intsr13=0,0 intmr13=0,0 control=8c irq=8000/8000 src=0000 av=0000 unexpected=0000 odd=0000 bit15=1 high=0000") == 1);
    CHECK(count_lines_with(&rl, "PICLEAN intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 main_w1c=0 sticky=0 ok=1") == 1);
    CHECK(count_lines_with(&rl, "REARM t_rearm=3391408218 before=8000 value=0000 layout=gbi-u16-replicated after=drain_ack_pi_clean") == 1);
    CHECK(count_lines_with(&rl, "REARMPOST t=3391409996 since_rearm=1778 intsr13=1,1 intmr13=0,0 control=8c irq=0400/0400 src=0400 av=0400 unexpected=0000 odd=0000 bit15=0 high=0000 outcome=B_latched ok=1") == 1);
    CHECK(count_lines_with(&rl, "NEXTCAUSE found=1 immediate=1 t_next_cause=3391409996 since_rearm=1778 intsr=00012000 control=8c irq=0400/0400 av=0400 unexpected=0000 polls=0 delivered=0") == 1);
    CHECK(count_lines_with(&rl, "TEARDOWNAV variant=S4B_next_cause_latched deliveries=1 drained=2/2 acks=1 rearms=1/1 next_cause=1 unmasks=1") == 1);
    CHECK(count_lines_with(&rl, "IRQSTOP pre rc=ok disc=0500 gbi=0500 stop_or=8aaa stop_value=8faa formula=read|stop_or") == 1);
    CHECK(count_lines_with(&rl, "IRQSTOP post rc=ok disc=8aaa gbi=8aaa write_ok=1 readback_ok=1 masks_readback=1 bit15_readback=1") == 1);
    CHECK(count_lines_with(&rl, "CLEANUP performed=1 value=00002000 rc=ok intsr_before=00012000 intsr_after=00010000 intsr13_after=0 sticky=0 ok=1") == 1);
    CHECK(count_lines_with(&rl, "FINAL arinfo=0043 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 control=00 irq=9090 power_cycle_required=1") == 1);
    CHECK(count_lines_with(&rl, "AVSVC end status=ok_service_rearm_cause_observed class=ok reason=- restore=ok restore_reason=- teardown=S4B_next_cause_latched power_cycle_required=1 errors=0 transport_ok=1") == 1);
    CHECK(count_lines_with(&rl, "SERVICE pass pending=0500 drain=0500 selected=2 attempted=2 completed=2 drain_uncertain=0 ack=1/1 ack_value=8500 source_after_ack=0000") == 1);
    CHECK(count_lines_with(&rl, "SERVICE rearm relatch_postdrain=0 relatch_postack=0 pi_clean=1 pi_sticky=0 rearm=1/1 rearmpost=B_latched next_cause=1 immediate=1 timed_out=0") == 1);
    CHECK(count_lines_with(&rl, "COUNTERS unmasks=1 deliveries=1 acks=1 rearms=1 next_causes=1 unexpected=0000 site=- isr_w1c=1 main_w1c=0 teardown_w1c=1 w1c_total=2 control_ok=1 uncertain=0") == 1);
    CHECK(count_lines_with(&rl, "BLOCK kind=audio idx=8 len=1000 present=1 valid=1 crc32=fec5e4e7 zeros=3969 distinct=3 w_off=0000,0540,0aa0,0fe0 first_word=01000000 gbi_frame_start=0") == 1);
    CHECK(count_lines_with(&rl, "BLOCKW kind=audio off=0000 data=0100000000000000000000000000000000000000000000000000000000000000") == 1);
    CHECK(count_lines_with(&rl, "BLOCK kind=video idx=1 len=0f00 present=1 valid=1 crc32=fe45ff08 zeros=0 distinct=2 w_off=0000,0500,0a00,0ee0 first_word=ffffffff gbi_frame_start=1") == 1);
    CHECK(count_lines_with(&rl, "BLOCKW kind=video off=0000 data=ffffffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff") == 1);
    CHECK(count_lines_with(&rl, "BLOCKW kind=video off=0ee0 data=7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff") == 1);
    CHECK(count_lines_with(&rl, "TIMING cause_to_isr=42530/1050us isr_to_presvc=7612 presvc_to_ack=20674 service=10997/271us ack_to_postack=1048 postack_to_rearm=7190 rearm_to_next_cause=1778/43us") == 1);
    CHECK(count_lines_with(&rl, "RESTOREAV handler_installed=1 handler_restored=1 old_handler=null mask_ok=1 intmr_final=000001fa pi_sticky_final=0 unmasked=1 masked_again=1") == 1);
    CHECK(rl.dropped == 0 && rl.truncated == 0 && rl.count == 179u);
    /* the same script without the sidecar: both blocks reported missing, the pre-fill never passed off as physical bytes */
    memset(audio_buf, 0xC1, sizeof audio_buf); memset(video_buf, 0xC1, sizeof video_buf);
    gbp_replay_init(&r, text);
    gbp_replay_transport(&r, &t);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_avsvc_probe_run(&t, &rl, &cfg, &res);
    CHECK(r.mismatches == 0 && r.exhausted == 0 && r.bulk_reads == 2u && r.blocks_missing == 2u && r.block_crc_mismatches == 0u);
    CHECK(res.audio.crc32 != 0xfec5e4e7u && res.video.crc32 != 0xfe45ff08u);
    free(text);
}

int main(int argc, char **argv)
{
    if (argc == 4 && strcmp(argv[1], "--dump-log") == 0) return dump_log(argv[2], argv[3]);
    if ((argc == 3 || argc == 4) && strcmp(argv[1], "--replay") == 0) return replay_fixture(argv[2], argc == 4 ? argv[3] : 0);
    test_success_paths();
    test_snapshot_immutability();
    test_unexpected_sources();
    test_dma_failures();
    test_timeout_then_busy_teardown();
    test_write_failures();
    test_postack_values();
    test_pi_cleanup();
    test_rearmpost_and_next_cause();
    test_second_cause_never_delivered();
    test_early_aborts();
    test_attempted_at_call_time();
    test_raw_buffers_preserved();
    test_wrap_lines_and_config();
    test_handler_order();
    if (argc > 1) test_hw_initirqa_prefix(argv[1]);
    else fprintf(stderr, "note: physical 003A fixture path not given, prefix test skipped\n");
    if (argc > 2) test_hw_initirqb_prefix(argv[2]);
    else fprintf(stderr, "note: physical 003B fixture path not given, prefix test skipped\n");
    if (argc > 3) test_hw_initirq4_prefix(argv[3]);
    else fprintf(stderr, "note: physical 004 fixture path not given, prefix test skipped\n");
    if (argc > 5) test_hw_avsvc_gbp(argv[4], argv[5]);
    else fprintf(stderr, "note: physical GBP-AV-SERVICE-001 fixture / sidecar paths not given, replay test skipped\n");
    printf("test_gbp_avsvc: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
