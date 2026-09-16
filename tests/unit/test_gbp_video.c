/*
 * GBP-VIDEO-001 logic — the repeated drained service (CHECK_ADMISSION →
 * PREPARE → UNMASK → CONFIRM → READ → AUDIO → VIDEO → ACK → PICLEAN →
 * REARM → WAIT_NEXT)* — against the mock's SYNTHETIC models: the
 * source/mask IRQ register with a per-re-arm cause sequence, the PI latch,
 * the 003B extended one-shot delivery engine, the whole-block read model
 * with its VIDEO first-four-bytes flag model, a scripted clock for the
 * admission-budget cases, and every deviation the specification enumerates
 * (docs/research/HARDWARE_TESTS.md "Planned tests — GBP-VIDEO-001").
 *
 * The physical GBP-AV-SERVICE-001 fixture (2026-09-16, avsvc-0001, commit
 * d3a6d23) is replayed as the EXACT PREFIX of cycle 0: that physical run is
 * one cycle of this loop, so with max_deliveries = 1 it replays end to end
 * and the second cycle is refused at the admission point — the latched cause
 * it left is acknowledged by the teardown. Nothing after a physical record
 * is invented, and NO physical GBP-VIDEO-001 fixture exists.
 *
 * Every mock scenario is SYNTHETIC and never physical evidence.
 *
 * Modes:  test_gbp_video
 *         test_gbp_video --dump-log <log> <seq.bin>    (synthetic run, SD-log format + sidecar)
 *         test_gbp_video --replay <fixture> [<seq.bin>]
 *         test_gbp_video <AVSVC fixture> <AVSVC blocks.bin>
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_video_probe.h"
#include "gbp_avdump.h"
#include "gbp_crc32.h"
#include "gbp_replay.h"
#include "gbp_mock.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

#define LINES 3000          /* the POC's ring (poc/gbp-video-capture-probe/source/main.c): the tests prove it never drops */
#define LINE_LEN 256
static char storage[LINES * LINE_LEN];
static uint8_t video_raw[GBP_AVSEQ_VIDEO_RAW_BYTES] __attribute__((aligned(32)));
static uint8_t audio_raw[GBP_AVSEQ_AUDIO_RAW_BYTES] __attribute__((aligned(32)));
static struct gbp_avseq_store store;
static uint8_t dump[GBP_AVSEQDUMP_MAX_SIZE];

#define BASE 0x01000000u
#define T_DELIVERY 400u              /* mock ticks; ticks() advances by 10 per call */
#define T_NEXT_CAUSE 2000u
#define BUDGET_BIG 100000000u        /* an admission budget no synthetic run can exhaust */

/* IRQ-register write numbering of a run: A1 = 1, A2 = 2, then ACK / REARM per cycle, STOP last. */
#define W_A1 1u
#define W_A2 2u

static const uint32_t A1_DL[GBP_INITIRQA_MAX_A1_OBS] = { 50u, 100u };
static const uint32_t A2_DL[GBP_INITIRQA_MAX_A2_OBS] = { 50u, 100u, 200u, 400u, 800u, 1600u };

static int count_lines_with(const struct ringlog *rl, const char *needle)
{
    size_t i; int n = 0;
    for (i = 0; i < rl->count; i++) if (strstr(ringlog_line(rl, i), needle)) n++;
    return n;
}

static void test_config(struct gbp_video_config *cfg)
{
    gbp_video_config_default(cfg);
    memcpy(cfg->a.a1_obs_ticks, A1_DL, sizeof A1_DL);
    memcpy(cfg->a.a2_obs_ticks, A2_DL, sizeof A2_DL);
    cfg->t_delivery_ticks = T_DELIVERY;
    cfg->t_next_cause_ticks = T_NEXT_CAUSE;
    cfg->admission_budget_ticks = BUDGET_BIG;
    cfg->store = &store;
}

/* the synthetic device: idle 0x8AAE; the FIRST cause = `bits` 300 ticks after A2; every re-arm
 * arms the same `bits` again `delay` ticks later (one step) — a repeated single-source stream */
static void mock_video(struct gbp_mock *m, uint16_t bits, uint32_t delay)
{
    gbp_mock_init(m);
    m->irq_model = MOCK_IRQ_MODEL_SOURCE_MASK;
    m->isr_ext = 1;
    m->max_deliveries = 1024;                 /* the storm guard: above every scenario's cycle count */
    m->source_assert_after_write = W_A2;
    m->source_assert_delay = 300;
    m->source_assert_bits = bits;
    m->seq_steps[0].bits = bits;
    m->seq_steps[0].delay = delay;
    m->seq_len = 1;
    m->video_first4_model = 1;                /* VIDEO blocks start 7f 7f ff ff unless a flag is scheduled */
    m->bulk_clears_source = 1;                /* the drained source drops: the ACK then re-arms a clean register */
}

/* a source sequence of `n` steps, cycled over the re-arms */
static void mock_seq(struct gbp_mock *m, const uint16_t *bits, const uint32_t *delays, unsigned n)
{
    unsigned i;
    for (i = 0; i < n && i < 16u; i++) { m->seq_steps[i].bits = bits[i]; m->seq_steps[i].delay = delays ? delays[i] : 50u; }
    m->seq_len = (n < 16u) ? n : 16u;
}

static void run_cfg(struct gbp_mock *m, struct ringlog *rl, struct gbp_video_result *res, struct gbp_video_config *cfg)
{
    struct gbp_transport t;
    gbp_mock_transport(m, &t);
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    ringlog_init(rl, storage, LINE_LEN, LINES);
    gbp_video_probe_run(&t, rl, cfg, res);
}

static void run(struct gbp_mock *m, struct ringlog *rl, struct gbp_video_result *res)
{
    struct gbp_video_config cfg;
    test_config(&cfg);
    run_cfg(m, rl, res, &cfg);
}

/* ---- the "never" properties, asserted on every run of this experiment ---- */
static void check_never(const struct gbp_mock *m, const struct gbp_video_result *res)
{
    unsigned idx;
    CHECK(m->intmr_writes == 0);                                             /* INTMR only through the mask API */
    CHECK(m->violation_mask == 0);                                           /* no mock invariant broken */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xC) == 0);             /* KEYPAD never written */
    for (idx = 0; idx < 16; idx++) {
        if (idx != 0 && idx != 4 && idx != 0xD) CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, idx) == 0);   /* writes: TEST, CONTROL, IRQ only */
        if (idx != 0 && idx != 4 && idx != 0xD) CHECK(gbp_mock_count_block_ops(m, MOCK_RD, BASE, idx) == 0);   /* 32-byte reads: TEST, CONTROL, IRQ only */
        if (idx != 8 && idx != 1) CHECK(gbp_mock_count_block_ops(m, MOCK_RD_BULK, BASE, idx) == 0);            /* bulk reads: AUDIO, VIDEO only */
    }
    CHECK(m->installed_calls == (res->h.handler_was_installed ? 1 : 0));    /* the handler is installed ONCE */
    CHECK(m->unmask_calls == res->unmasks);                                  /* one unmask per admitted cycle, never more */
    CHECK(m->deliveries == res->deliveries);                                 /* one handler entry per admitted cycle */
    CHECK(m->isr_w1c_count == res->deliveries && res->isr_w1c == res->deliveries);
    CHECK(m->intsr_writes == res->main_w1c + res->teardown_w1c);             /* main W1C budget: PICLEAN + teardown only */
    CHECK(res->main_w1c <= res->deliveries && res->teardown_w1c <= 1u);
    CHECK(m->audio_reads == res->audio_drains && m->video_reads == res->video_blocks);
    CHECK(m->bulk_bad_addr == 0);                                            /* every bulk read used the exact block address */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 4) <= 2);               /* CONTROL: transform + restore */
    /* IRQ-register writes: A1, A2, one ACK and one re-arm per cycle that got that far, the teardown's stop word */
    CHECK(gbp_mock_count_block_ops(m, MOCK_WR, BASE, 0xD) ==
          (unsigned)(res->a.w_a1.attempted + res->a.w_a2.attempted + res->a.w_stop.attempted) + res->acks + res->rearms);
    CHECK(res->deliveries <= GBP_AVSEQ_MAX_DELIVERIES && res->video_blocks <= GBP_AVSEQ_MAX_VIDEO_BLOCKS);
    CHECK(store.vblocks_n == res->video_blocks && store.ablocks_n == res->audio_drains);
    CHECK(store.cycles_n == res->deliveries);
    /* the shared one-shot record is reset exactly once per ADMITTED cycle after the first (memory only,
     * never while unmasked); a refused cycle never touches it */
    CHECK(m->record_resets == (res->admissions ? res->admissions - 1u : 0u));
}

/* ---- the AVSVC operation order inside one lean cycle ---- */
static int nth_irqw(const struct gbp_mock *m, unsigned n) { return gbp_mock_nth_op(m, MOCK_WR, BASE, 0xD, n); }

/* index in ops[] of the nth bulk read of block `idx` (1-based) */
static int nth_bulk(const struct gbp_mock *m, unsigned idx, unsigned n)
{
    unsigned i, seen = 0;
    for (i = 0; i < m->nops; i++)
        if (m->ops[i].kind == MOCK_RD_BULK && ((m->ops[i].addr - BASE) >> 20) == idx && ++seen == n) return (int)i;
    return -1;
}

/* ---- 1. one cycle, both sources ---- */
static void test_single_cycle(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    mock_video(&m, 0x0500, 50);
    test_config(&cfg);
    cfg.max_deliveries = 1;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.status == GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP && strcmp(res.status_class, "ok") == 0);
    CHECK(res.capture == GBP_AVSEQ_END_DELIVERY_CAP && res.service_ok == 1 && res.restore_ok == 1 && res.errors == 0);
    CHECK(res.deliveries == 1 && res.unmasks == 1 && res.acks == 1 && res.rearms == 1);
    CHECK(res.video_blocks == 1 && res.video_completed == 1 && res.audio_drains == 1 && res.audio_completed == 1);
    CHECK(res.next_cause_at_end == 1 && strcmp(res.refusal, "delivery_cap") == 0 && res.refusals == 1 && res.admissions == 1);
    CHECK(res.deadline_armed == 1 && res.t0 == store.cycles[0].t_unmask);
    CHECK(store.cycles_n == 1 && store.cycles[0].pending == 0x0500 && store.cycles[0].ack_value == 0x8500);
    CHECK(store.cycles[0].audio_selected == 1 && store.cycles[0].video_selected == 1 && store.cycles[0].verify == 1);
    CHECK(store.cycles[0].isr_fired == 1 && store.cycles[0].isr_count == 1 && store.cycles[0].isr_reentry == 0 && store.cycles[0].admitted == 1);
    /* AUDIO is drained BEFORE VIDEO, the references' order */
    CHECK(nth_bulk(&m, 8, 1) >= 0 && nth_bulk(&m, 1, 1) > nth_bulk(&m, 8, 1));
    /* the whole-block lengths */
    CHECK(m.ops[nth_bulk(&m, 8, 1)].len == 0x1000u && m.ops[nth_bulk(&m, 1, 1)].len == 0x0F00u);
    /* the ACK is the whole pending value, never partial; the re-arm is 0x0000 */
    CHECK(nth_irqw(&m, 3) >= 0 && m.ops[nth_irqw(&m, 3)].data[0x1E] == 0x85 && m.ops[nth_irqw(&m, 3)].data[0x1F] == 0x00);
    CHECK(nth_irqw(&m, 4) >= 0 && m.ops[nth_irqw(&m, 4)].data[0x1E] == 0x00 && m.ops[nth_irqw(&m, 4)].data[0x1F] == 0x00);
    CHECK(count_lines_with(&rl, "SVC n=0 pending=0500 audio=1 video=1 order=audio_then_video ack_value=8500") == 1);
    CHECK(count_lines_with(&rl, "MATRIX service=ok") == 1 && count_lines_with(&rl, "capture=delivery_cap") >= 1);
    CHECK(count_lines_with(&rl, "reference_content=offline") >= 1);      /* the content is never a gate on the console */
    CHECK(rl.dropped == 0 && rl.truncated == 0);
}

/* ---- 2. many cycles until the capture target ---- */
static void test_target_reached(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res;
    unsigned i;
    mock_video(&m, 0x0100, 50);                /* VIDEO-only: one block per cycle */
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_VIDEO_OK_SEQUENCE_CAPTURE && res.capture == GBP_AVSEQ_END_TARGET_REACHED);
    CHECK(res.service_ok == 1 && res.restore_ok == 1 && res.errors == 0 && res.transport_ok == 1);
    CHECK(res.video_blocks == GBP_AVSEQ_TARGET_VIDEO_BLOCKS && res.video_completed == GBP_AVSEQ_TARGET_VIDEO_BLOCKS);
    CHECK(res.deliveries == GBP_AVSEQ_TARGET_VIDEO_BLOCKS && res.audio_drains == 0 && res.audio_completed == 0);
    CHECK(res.acks == res.deliveries && res.rearms == res.deliveries && res.unmasks == res.deliveries);
    CHECK(strcmp(res.refusal, "target_reached") == 0 && res.next_cause_at_end == 1);
    CHECK(res.verify_cycles_done == GBP_AVSEQ_VERIFY_CYCLES && res.lean_cycles == res.deliveries - GBP_AVSEQ_VERIFY_CYCLES);
    /* the blocks are contiguous in sequence order, each in its own slot, none overwritten */
    for (i = 0; i < GBP_AVSEQ_TARGET_VIDEO_BLOCKS; i++) {
        CHECK(store.vblocks[i].seq == i && store.vblocks[i].cycle == i && store.vblocks[i].completed == 1);
        CHECK(gbp_avseq_video_bytes(&store, i) == video_raw + i * GBP_AVSEQ_VIDEO_BLOCK_SIZE);
    }
    CHECK(count_lines_with(&rl, "VBLK seq=") == (int)GBP_AVSEQ_TARGET_VIDEO_BLOCKS);
    CHECK(count_lines_with(&rl, "ABLK ") == 0);
    CHECK(count_lines_with(&rl, "CYCU n=") == (int)res.deliveries);       /* one compact record set per cycle */
    CHECK(count_lines_with(&rl, "BOUNDARIES gbi=") == 1 && count_lines_with(&rl, "BOUNDARIES disc=") == 1);
    CHECK(rl.dropped == 0 && rl.truncated == 0);
}

/* ---- 3. the delivery cap: 320 record reuses ---- */
static void test_delivery_cap_320(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res;
    mock_video(&m, 0x0400, 50);                /* AUDIO-only: the VIDEO target is never approached */
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.status == GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP && res.capture == GBP_AVSEQ_END_DELIVERY_CAP);
    CHECK(res.service_ok == 1 && res.restore_ok == 1 && res.errors == 0);
    CHECK(res.deliveries == GBP_AVSEQ_MAX_DELIVERIES && res.audio_drains == GBP_AVSEQ_MAX_DELIVERIES);
    CHECK(res.video_blocks == 0 && res.next_cause_at_end == 1 && strcmp(res.refusal, "delivery_cap") == 0);
    /* the shared one-shot record was reset before every unmask after the first, memory only */
    CHECK(m.record_resets == GBP_AVSEQ_MAX_DELIVERIES - 1u && res.admissions == GBP_AVSEQ_MAX_DELIVERIES);
    CHECK(m.deliveries == GBP_AVSEQ_MAX_DELIVERIES && m.installed_calls == 1);
    CHECK(store.audio_first_kept == GBP_AVSEQ_AUDIO_FIRST_KEPT && store.audio_last_valid >= (int)GBP_AVSEQ_AUDIO_FIRST_KEPT);
    CHECK(gbp_avseq_audio_raw_count(&store) == GBP_AVSEQ_AUDIO_FIRST_KEPT + 1u);
    CHECK(store.audio_drains_completed == GBP_AVSEQ_MAX_DELIVERIES);
}

/* ---- 4. alternating sources, 0x0500 repeatedly, AUDIO-only, VIDEO-only ---- */
static void test_source_patterns(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    static const uint16_t alt[2] = { 0x0400, 0x0100 };
    unsigned i, a = 0, v = 0;
    /* alternating A / V */
    mock_video(&m, 0x0400, 50);
    mock_seq(&m, alt, 0, 2);
    test_config(&cfg);
    cfg.max_deliveries = 24;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.status == GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP && res.deliveries == 24);
    for (i = 0; i < store.cycles_n; i++) {
        if (store.cycles[i].audio_selected) a++;
        if (store.cycles[i].video_selected) v++;
        CHECK(store.cycles[i].audio_selected != store.cycles[i].video_selected);   /* exactly one source per cause */
    }
    CHECK(a == res.audio_drains && v == res.video_blocks && a + v == res.deliveries);
    CHECK(a > 0 && v > 0);
    /* 0x0500 on every cycle */
    mock_video(&m, 0x0500, 50);
    test_config(&cfg);
    cfg.max_deliveries = 20;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.deliveries == 20 && res.audio_drains == 20 && res.video_blocks == 20);
    for (i = 0; i < store.cycles_n; i++) {
        CHECK(store.cycles[i].pending == 0x0500 && store.cycles[i].ack_value == 0x8500);   /* never a partial ACK */
        CHECK(store.cycles[i].audio_selected == 1 && store.cycles[i].video_selected == 1);
    }
    /* VIDEO-only */
    mock_video(&m, 0x0100, 50);
    test_config(&cfg);
    cfg.max_deliveries = 12;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.deliveries == 12 && res.video_blocks == 12 && res.audio_drains == 0);
    /* AUDIO-only */
    mock_video(&m, 0x0400, 50);
    test_config(&cfg);
    cfg.max_deliveries = 12;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.deliveries == 12 && res.video_blocks == 0 && res.audio_drains == 12);
}

/* ---- 5. the READ snapshot is immutable: a source that appears during a drain is not serviced ---- */
static void test_snapshot_immutability(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    mock_video(&m, 0x0400, 50);
    m.bulk_assert_at_read = 1;              /* VIDEO asserts during the FIRST bulk read (the AUDIO drain of cycle 0) */
    m.bulk_assert_bits = 0x0100;
    m.bulk_assert_after = 0;
    test_config(&cfg);
    cfg.max_deliveries = 1;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.status == GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP);
    CHECK(store.cycles[0].pending == 0x0400 && store.cycles[0].ack_value == 0x8400);   /* the ACK is the READ value */
    CHECK(store.cycles[0].video_selected == 0 && store.cycles[0].video_attempted == 0);
    CHECK(res.video_blocks == 0 && res.audio_drains == 1);
    CHECK(store.cycles[0].relatch_postdrain == 1 || store.cycles[0].next_pending == 0x0100);  /* observed, not serviced */
}

/* ---- 6. the frame-start predicates, both, per block ---- */
static void test_flags(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    unsigned i;
    /* (1) a true predicate on the FIRST block */
    mock_video(&m, 0x0100, 50);
    m.video_flag_only_at = 1;
    test_config(&cfg); cfg.max_deliveries = 6;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(store.vblocks[0].flag_gbi == 1 && store.vblocks[0].flag_disc == 1 && store.vblocks[0].flags_agree == 1);
    for (i = 1; i < store.vblocks_n; i++) CHECK(store.vblocks[i].flag_gbi == 0 && store.vblocks[i].flag_disc == 0);
    CHECK(res.b_gbi.count == 1 && res.b_gbi.positions[0] == 0 && res.b_gbi.complete_interval == 0);
    CHECK(res.b_disc.count == 1 && res.b_disc.complete_interval == 0);
    CHECK(res.status == GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP);          /* the main status never depends on the flags */

    /* (2) the worst-case phase 88 still covers: first flag on block 39 (0-based), second on 79 */
    mock_video(&m, 0x0100, 50);
    m.video_flag_period = 40; m.video_flag_phase = 1;      /* reads 40 and 80 → sequence indices 39 and 79 */
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.capture == GBP_AVSEQ_END_TARGET_REACHED && res.video_blocks == 88);
    CHECK(res.b_gbi.count == 2 && res.b_gbi.positions[0] == 39 && res.b_gbi.positions[1] == 79);
    CHECK(res.b_gbi.intervals_n == 1 && res.b_gbi.intervals[0] == 40 && res.b_gbi.complete_interval == 1);
    CHECK(res.b_disc.count == 2 && res.b_disc.complete_interval == 1);

    /* (3) two flags 40 apart from block 0 */
    mock_video(&m, 0x0100, 50);
    m.video_flag_period = 40; m.video_flag_phase = 0;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.b_gbi.count == 3 && res.b_gbi.positions[0] == 0 && res.b_gbi.positions[1] == 40 && res.b_gbi.positions[2] == 80);
    CHECK(res.b_gbi.intervals_n == 2 && res.b_gbi.intervals[0] == 40 && res.b_gbi.intervals[1] == 40 && res.b_gbi.complete_interval == 1);

    /* (4) an interval N != 40: reported as the observation, SERVICE ok, never a failure */
    mock_video(&m, 0x0100, 50);
    m.video_flag_period = 30; m.video_flag_phase = 0;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.service_ok == 1 && res.capture == GBP_AVSEQ_END_TARGET_REACHED && res.status == GBP_VIDEO_OK_SEQUENCE_CAPTURE);
    CHECK(res.b_gbi.count == 3 && res.b_gbi.intervals[0] == 30 && res.b_gbi.intervals[1] == 30 && res.b_gbi.complete_interval == 1);

    /* (5) one flag in 88 blocks: no complete interval, main status unchanged */
    mock_video(&m, 0x0100, 50);
    m.video_flag_only_at = 17;
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.b_gbi.count == 1 && res.b_gbi.positions[0] == 16 && res.b_gbi.complete_interval == 0);
    CHECK(res.status == GBP_VIDEO_OK_SEQUENCE_CAPTURE && res.service_ok == 1);

    /* (6) zero flags in 88 blocks: same */
    mock_video(&m, 0x0100, 50);
    run(&m, &rl, &res);
    check_never(&m, &res);
    CHECK(res.b_gbi.count == 0 && res.b_disc.count == 0 && res.b_gbi.complete_interval == 0 && res.b_disc.complete_interval == 0);
    CHECK(res.status == GBP_VIDEO_OK_SEQUENCE_CAPTURE && res.service_ok == 1);
    CHECK(count_lines_with(&rl, "BOUNDARIES gbi=0 positions=- intervals=- complete_interval=0") == 1);

    /* (7) Disc = 1 with GBI = 0 (byte 1 has bit 7, byte 0 does not): both recorded, no correction */
    mock_video(&m, 0x0100, 50);
    m.video_flag_only_at = 3; m.video_flag_style = 1;
    test_config(&cfg); cfg.max_deliveries = 6;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(store.vblocks[2].flag_disc == 1 && store.vblocks[2].flag_gbi == 0 && store.vblocks[2].flags_agree == 0);
    CHECK(store.vblocks[2].raw_first4[0] == 0x7f && store.vblocks[2].raw_first4[1] == 0xff);   /* raw kept verbatim */
    CHECK(res.b_disc.count == 1 && res.b_disc.positions[0] == 2 && res.b_gbi.count == 0);
    CHECK(res.service_ok == 1);

    /* (8) Disc = 1 and GBI = 1 */
    mock_video(&m, 0x0100, 50);
    m.video_flag_only_at = 3; m.video_flag_style = 0;
    test_config(&cfg); cfg.max_deliveries = 6;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(store.vblocks[2].flag_disc == 1 && store.vblocks[2].flag_gbi == 1 && store.vblocks[2].flags_agree == 1);

    /* (9) byte 0 altered without byte 1: neither predicate moves, the exception is counted */
    mock_video(&m, 0x0100, 50);
    m.video_byte0_extra_at = 4;
    test_config(&cfg); cfg.max_deliveries = 6;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(store.vblocks[3].raw_first4[0] == 0xff && store.vblocks[3].raw_first4[1] == 0x7f);
    CHECK(store.vblocks[3].flag_gbi == 0 && store.vblocks[3].flag_disc == 0 && store.vblocks[3].flags_agree == 1);
    CHECK(store.vblocks[3].byte0_exceptions >= 1);
    CHECK(res.b_gbi.count == 0 && res.b_disc.count == 0);

    /* (10) byte 0 only, flag style 2: both predicates stay 0 — byte 0 never decides */
    mock_video(&m, 0x0100, 50);
    m.video_flag_only_at = 2; m.video_flag_style = 2;
    test_config(&cfg); cfg.max_deliveries = 6;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(store.vblocks[1].raw_first4[0] == 0xff && store.vblocks[1].raw_first4[1] == 0x7f);
    CHECK(store.vblocks[1].flag_gbi == 0 && store.vblocks[1].flag_disc == 0);

    /* (11) GBI = 1 never occurs with Disc = 0, over every captured block of every scenario above */
    mock_video(&m, 0x0100, 50);
    m.video_flag_period = 7;
    run(&m, &rl, &res);
    check_never(&m, &res);
    for (i = 0; i < store.vblocks_n; i++) CHECK(!(store.vblocks[i].flag_gbi && !store.vblocks[i].flag_disc));
    CHECK(res.b_gbi.count == 13 && res.b_disc.count == 13);
}

/* ---- 7. the admission budget ---- */
static void test_admission_budget(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    /* (16) the deadline already reached before the first new cycle after t0: zero further deliveries */
    mock_video(&m, 0x0500, 50);
    test_config(&cfg);
    cfg.admission_budget_ticks = 1;                /* t0 + 1: expired by the time cycle 1 is considered */
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.status == GBP_VIDEO_OK_TARGET_NOT_REACHED_RUNTIME_CAP && res.capture == GBP_AVSEQ_END_RUNTIME_CAP);
    CHECK(res.service_ok == 1 && res.restore_ok == 1 && res.deliveries == 1 && res.acks == 1 && res.rearms == 1);
    CHECK(strcmp(res.refusal, "runtime_cap") == 0 && res.admission_deadline == res.t0 + 1u);
    /* (17)+(22) the deadline expires DURING the AUDIO DMA: VIDEO is still drained, the ACK is the whole value */
    mock_video(&m, 0x0500, 50);
    m.bulk_tick_jump_at_read = 1; m.bulk_tick_jump = 5000;    /* the first bulk read (AUDIO of cycle 0) burns the budget */
    test_config(&cfg);
    cfg.admission_budget_ticks = 1000;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.status == GBP_VIDEO_OK_TARGET_NOT_REACHED_RUNTIME_CAP && res.capture == GBP_AVSEQ_END_RUNTIME_CAP);
    CHECK(res.deliveries == 1 && res.audio_completed == 1 && res.video_completed == 1);   /* the admitted cycle completed in full */
    CHECK(store.cycles[0].ack_completed == 1 && store.cycles[0].ack_value == 0x8500 && store.cycles[0].rearm_completed == 1);
    CHECK(res.acks == 1 && res.rearms == 1 && res.service_ok == 1);
    /* (18) the deadline expires between AUDIO and VIDEO: same property */
    mock_video(&m, 0x0500, 50);
    m.tick_jump_at_rearm = 0;
    m.bulk_tick_jump_at_read = 2; m.bulk_tick_jump = 5000;    /* the jump lands on the VIDEO read of cycle 0 */
    test_config(&cfg);
    cfg.admission_budget_ticks = 1000;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.deliveries == 1 && res.video_completed == 1 && store.cycles[0].ack_value == 0x8500 && res.rearms == 1);
    CHECK(res.capture == GBP_AVSEQ_END_RUNTIME_CAP && res.service_ok == 1);
    /* (20) the next cause is latched before the deadline, the deadline expires before the next unmask */
    mock_video(&m, 0x0500, 10);                   /* the next cause appears quickly after the re-arm */
    m.tick_jump_at_rearm = 1; m.tick_jump_rearm = 0;
    test_config(&cfg);
    cfg.admission_budget_ticks = 600;             /* enough for cycle 0 and its WAIT_NEXT, not for cycle 1 */
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.capture == GBP_AVSEQ_END_RUNTIME_CAP && res.service_ok == 1 && res.restore_ok == 1);
    CHECK(res.next_cause_at_end == 1 && res.deliveries >= 1);
    CHECK(res.a.pi_cleanup_performed == 1 && res.teardown_w1c == 1);   /* the teardown acknowledged the latched cause */
    /* (21) the deadline expires during WAIT_NEXT with no cause: runtime_cap, next_cause_at_end = no */
    mock_video(&m, 0x0500, 50);
    m.seq_stop_after = 1;                          /* only the first re-arm gets a cause */
    test_config(&cfg);
    cfg.admission_budget_ticks = 2500;             /* the budget ends inside the second cycle's WAIT_NEXT */
    cfg.t_next_cause_ticks = 100000u;              /* T_NEXT_CAUSE would not end the wait: the deadline does */
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.capture == GBP_AVSEQ_END_RUNTIME_CAP && res.status == GBP_VIDEO_OK_TARGET_NOT_REACHED_RUNTIME_CAP);
    CHECK(res.next_cause_at_end == 0 && res.service_ok == 1 && res.restore_ok == 1);
    CHECK(store.cycles[store.cycles_n - 1u].next_ended_by == GBP_AVSEQ_NEXT_DEADLINE ||
          store.cycles[store.cycles_n - 1u].next_ended_by == GBP_AVSEQ_NEXT_SINGLE_READ);
    CHECK(res.unmasks == res.deliveries);          /* no additional unmask */
}

/* ---- 8. no next cause within the bound, with budget left ---- */
static void test_no_next_cause(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    mock_video(&m, 0x0500, 50);
    m.seq_stop_after = 3;                          /* three re-arms produce a cause; the fourth does not */
    test_config(&cfg);
    cfg.t_next_cause_ticks = 500;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.status == GBP_VIDEO_OBSERVATION_NO_NEXT_CAUSE && strcmp(res.status_class, "observation") == 0);
    CHECK(res.capture == GBP_AVSEQ_END_NO_NEXT_CAUSE && res.service_ok == 1 && res.restore_ok == 1);
    CHECK(res.deliveries == 4 && res.next_cause_at_end == 0);
    CHECK(store.cycles[3].next_ended_by == GBP_AVSEQ_NEXT_TIMEOUT && store.cycles[3].next_observed == 0);
    CHECK(res.a.pi_cleanup_performed == 0 && res.teardown_w1c == 0);    /* nothing latched: no teardown W1C */
    CHECK(count_lines_with(&rl, "capture=no_next_cause") >= 1);
}

/* ---- 9. the PI latch and the W1C budget between cycles ---- */
static void test_pi_latch_between_cycles(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    unsigned i;
    mock_video(&m, 0x0500, 50);
    test_config(&cfg);
    cfg.max_deliveries = 30;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    /* the mock flags any main-loop INTSR W1C between a re-arm's next cause and the following unmask */
    CHECK((m.violation_mask & GBP_MOCK_VIOL_W1C_BETWEEN_CAUSE_UNMASK) == 0);
    CHECK((m.violation_mask & GBP_MOCK_VIOL_RESET_WHILE_UNMASKED) == 0);
    CHECK((m.violation_mask & GBP_MOCK_VIOL_DMA_WHILE_UNMASKED) == 0);
    CHECK((m.violation_mask & GBP_MOCK_VIOL_INSTALL_TWICE) == 0);
    /* every cycle entered with the cause already latched and left it latched for the next one */
    for (i = 1; i < store.cycles_n; i++) CHECK((store.cycles[i].intsr_prep & GBP_PI_HSP_BIT) != 0);
    for (i = 0; i < store.cycles_n; i++) {
        CHECK(store.cycles[i].isr_count == 1 && store.cycles[i].isr_reentry == 0 && store.cycles[i].mask_ok == 1);
        CHECK((store.cycles[i].intsr_entry & GBP_PI_HSP_BIT) != 0);      /* the ISR saw the cause */
        CHECK((store.cycles[i].intmr_entry & GBP_PI_HSP_BIT) != 0);      /* delivered with bit 13 enabled */
        CHECK((store.cycles[i].intsr_after_w1c & GBP_PI_HSP_BIT) == 0);  /* the ISR's single W1C cleared it */
        CHECK(store.cycles[i].pi_sticky == 0);
    }
    /* the whole-run W1C budget: one per ISR, at most one per PICLEAN, at most one at the teardown */
    CHECK(res.isr_w1c == res.deliveries && res.main_w1c <= res.deliveries && res.teardown_w1c <= 1);
    CHECK(m.intsr_writes == res.main_w1c + res.teardown_w1c);
}

/* ---- 10. anomalies that stop the loop ---- */
static void test_anomalies(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    /* reentry: a second handler entry after the 3rd delivery */
    mock_video(&m, 0x0500, 50);
    m.second_delivery_at = 3;
    test_config(&cfg); cfg.max_deliveries = 20;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.status == GBP_VIDEO_ANOMALY_REENTRY && strcmp(res.status_class, "anomaly") == 0);
    CHECK(res.capture == GBP_AVSEQ_END_EARLY_FAILURE && res.service_ok == 0 && res.restore_ok == 1);
    CHECK(res.deliveries == 3 && strcmp(res.teardown_variant, "S3_service_aborted") == 0);
    CHECK(store.cycles_n == 3 && store.cycles[2].isr_reentry == 1);
    /* missed entry: the 3rd delivery never reaches the CPU */
    mock_video(&m, 0x0500, 50);
    m.suppress_delivery_at = 3;
    test_config(&cfg); cfg.max_deliveries = 20;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.status == GBP_VIDEO_ANOMALY_MISSED_ENTRY && res.capture == GBP_AVSEQ_END_EARLY_FAILURE);
    CHECK(res.deliveries == 2 && res.service_ok == 0 && res.restore_ok == 1 && res.unmasks == 3);
    /* an unexpected source outside 0x0500: observed, never serviced */
    mock_video(&m, 0x0500, 50);
    { static const uint16_t bits[2] = { 0x0500, 0x0504 }; mock_seq(&m, bits, 0, 2); }
    test_config(&cfg); cfg.max_deliveries = 20;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.status == GBP_VIDEO_ANOMALY_UNEXPECTED_SOURCE && res.capture == GBP_AVSEQ_END_EARLY_FAILURE);
    CHECK(res.unexpected == 0x0004 && res.service_ok == 0 && res.restore_ok == 1);
    CHECK(res.acks == res.deliveries - 1u);                               /* the offending cycle was not acknowledged */
    /* a failed VIDEO DMA: no ACK, no re-arm, the slot never valid */
    mock_video(&m, 0x0500, 50);
    m.bulk_fail_at_read = 4; m.bulk_fail_rc = GBP_ERR_TIMEOUT;           /* reads 1,2 = cycle 0; 3,4 = cycle 1 (VIDEO) */
    test_config(&cfg); cfg.max_deliveries = 20;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.status == GBP_VIDEO_VIDEO_DMA_TIMEOUT && strcmp(res.status_class, "dma") == 0);
    CHECK(res.capture == GBP_AVSEQ_END_EARLY_FAILURE && strcmp(res.teardown_variant, "S3_dma_failed") == 0);
    CHECK(res.deliveries == 2 && res.acks == 1 && res.rearms == 1);       /* cycle 1 wrote neither ACK nor re-arm */
    CHECK(store.vblocks_n == 2 && store.vblocks[1].completed == 0 && store.vblocks[1].rc == (uint8_t)GBP_ERR_TIMEOUT);
    CHECK(store.vblocks[1].crc32 == 0 && store.vblocks[1].summarized == 0);
    /* a failed AUDIO DMA: VIDEO is never started */
    mock_video(&m, 0x0500, 50);
    m.bulk_fail_at_read = 3; m.bulk_fail_rc = GBP_ERR_BUSY;
    test_config(&cfg); cfg.max_deliveries = 20;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.status == GBP_VIDEO_AUDIO_DMA_BUSY && res.deliveries == 2 && res.video_blocks == 1);
    CHECK(store.cycles[1].video_attempted == 0 && res.acks == 1);
    /* a PI cause that stays set after the ACK and one main W1C */
    mock_video(&m, 0x0500, 50);
    m.intsr_w1c_ignored = 1; m.pi_relatch_after_ticks = 5;
    test_config(&cfg); cfg.max_deliveries = 20;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.status == GBP_VIDEO_ANOMALY_PI_STICKY || res.status == GBP_VIDEO_ANOMALY_MASK_FAILURE ||
          res.status == GBP_VIDEO_ANOMALY_ISR_STATE);
    CHECK(res.capture == GBP_AVSEQ_END_EARLY_FAILURE && res.service_ok == 0);
    /* an ACK write that does not complete */
    mock_video(&m, 0x0500, 50);
    m.irq_write_fail_at = 5;                                              /* A1, A2, ACK0, REARM0, ACK1 */
    test_config(&cfg); cfg.max_deliveries = 20;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.status == GBP_VIDEO_ACK_WRITE_FAILED && strcmp(res.status_class, "transport") == 0);
    CHECK(res.uncertain_writes >= 1 && strcmp(res.teardown_variant, "S4_ack_failed") == 0 && res.rearms == 1);
    /* a re-arm write that does not complete */
    mock_video(&m, 0x0500, 50);
    m.irq_write_fail_at = 6;
    test_config(&cfg); cfg.max_deliveries = 20;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.status == GBP_VIDEO_REARM_WRITE_FAILED && res.uncertain_writes >= 1);
    CHECK(strcmp(res.teardown_variant, "S4_rearm_failed") == 0 && res.acks == 2);
}

/* ---- 11. the AUDIO ping-pong keeps the last valid capture ---- */
static void test_audio_last_valid(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    unsigned i, completed = 0;
    mock_video(&m, 0x0400, 50);
    test_config(&cfg);
    cfg.max_deliveries = 11;                    /* 8 into the first slots, then the ping-pong pair */
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.audio_drains == 11 && res.audio_completed == 11);
    CHECK(store.audio_first_kept == 8 && store.audio_last_valid == 8);     /* drains 9, 10, 11 → slots 8, 9, 8 */
    CHECK(gbp_avseq_audio_raw_count(&store) == 9);
    for (i = 0; i < 8; i++) CHECK(store.ablocks[i].raw_kept == 1 && store.ablocks[i].raw_index == i);
    CHECK(store.ablocks[10].raw_kept == 1 && store.ablocks[10].raw_index == 8);
    CHECK(store.ablocks[8].raw_kept == 0 && store.ablocks[9].raw_kept == 0);   /* overwritten ping-pong bytes */
    /* (15) the last valid buffer survives a failing drain: the failure lands in the other buffer */
    mock_video(&m, 0x0400, 50);
    m.bulk_fail_at_read = 11; m.bulk_fail_rc = GBP_ERR_TIMEOUT;   /* the 11th AUDIO drain fails */
    test_config(&cfg);
    cfg.max_deliveries = 20;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.status == GBP_VIDEO_AUDIO_DMA_TIMEOUT && res.audio_drains == 11 && res.audio_completed == 10);
    CHECK(store.audio_last_valid == 9);                                   /* drain 10 landed in slot 9; the failed 11th targeted slot 8 */
    CHECK(store.ablocks[10].completed == 0 && store.ablocks[10].raw_kept == 0 && store.ablocks[10].slot == GBP_AVSEQ_SLOT_NONE);
    CHECK(store.ablocks[9].raw_kept == 1 && store.ablocks[9].raw_index == 9 && store.ablocks[9].summarized == 1);
    for (i = 0; i < store.ablocks_n; i++) if (store.ablocks[i].completed) completed++;
    CHECK(completed == 10 && store.audio_drains_completed == 10);
    /* the last valid bytes are the ones the DMA left, not the failed drain's */
    CHECK(gbp_avseq_audio_bytes(&store, 9)[0] == gbp_mock_bulk_byte(8, m.bulk_seed, 0));
}

/* ---- 12. early aborts before any unmask ---- */
static void test_early_aborts(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    struct gbp_transport t;
    /* no store */
    gbp_mock_init(&m);
    gbp_mock_transport(&m, &t);
    test_config(&cfg);
    cfg.store = 0;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_video_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(res.status == GBP_VIDEO_ABORT_STORE_UNAVAILABLE && res.capture == GBP_AVSEQ_END_EARLY_FAILURE);
    CHECK(res.service_ok == 0 && m.transfers == 0 && m.installed_calls == 0);   /* nothing was run */
    /* no whole-block read */
    mock_video(&m, 0x0500, 50);
    m.bulk_ops_available = 0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_VIDEO_ABORT_BULK_UNAVAILABLE && res.unmasks == 0 && res.deliveries == 0);
    CHECK(res.h.handler_was_installed == 0 && res.restore_ok == 1);
    /* no interrupt path */
    mock_video(&m, 0x0500, 50);
    m.irq_ops_available = 0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_VIDEO_ABORT_HANDLER_INSTALL && strcmp(res.reason, "irq_ops_unavailable") == 0);
    CHECK(res.unmasks == 0 && res.restore_ok == 1);
    /* the first cause never arrives */
    mock_video(&m, 0x0500, 50);
    m.source_assert_after_write = 0;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_VIDEO_NO_INITIAL_CAUSE && res.capture == GBP_AVSEQ_END_EARLY_FAILURE);
    CHECK(res.unmasks == 0 && res.deliveries == 0 && res.restore_ok == 1 && res.h.handler_was_installed == 0);
    /* the install leaves a dirty record: aborted before the unmask */
    mock_video(&m, 0x0500, 50);
    m.record_dirty_on_install = 1;
    run(&m, &rl, &res);
    CHECK(res.status == GBP_VIDEO_ABORT_PRE_UNMASK_STATE && res.unmasks == 0 && res.deliveries == 0);
    CHECK(res.h.handler_was_installed == 1 && res.h.handler_restored == 1 && res.restore_ok == 1);
    /* a source outside AV is pending at PREUNMASK */
    mock_video(&m, 0x0004, 50);
    run(&m, &rl, &res);
    CHECK(res.status == GBP_VIDEO_ANOMALY_UNEXPECTED_SOURCE && res.unexpected == 0x0004 && res.unmasks == 0);
    CHECK(strcmp(res.unexpected_site, "PREUNMASK") == 0 && res.restore_ok == 1);
    /* the record reset is unavailable (a transport without it): aborted before the unmask */
    mock_video(&m, 0x0500, 50);
    gbp_mock_transport(&m, &t);
    t.irq_record_reset = 0;
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    test_config(&cfg);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_video_probe_run(&t, &rl, &cfg, &res);
    CHECK(res.status == GBP_VIDEO_ABORT_RESET_UNAVAILABLE && res.unmasks == 0 && res.deliveries == 0);
}

/* ---- 13. the handler is installed once and restored once ---- */
static void test_handler_lifecycle(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    int inst, rest;
    mock_video(&m, 0x0500, 50);
    m.old_handler_nonnull = 1;
    test_config(&cfg);
    cfg.max_deliveries = 40;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(m.installed_calls == 1 && res.h.handler_was_installed == 1 && res.h.handler_restored == 1);
    CHECK(res.h.old_handler_null == 0 && res.h.mask_ok == 1 && res.restore_ok == 1);
    inst = gbp_mock_first_op(&m, MOCK_IRQ_INSTALL, BASE, 16);
    rest = gbp_mock_first_op(&m, MOCK_IRQ_RESTORE, BASE, 16);
    CHECK(inst >= 0 && rest > inst);
    CHECK(gbp_mock_last_op(&m, MOCK_IRQ_INSTALL, BASE, 16) == inst);      /* installed exactly once */
    CHECK(gbp_mock_last_op(&m, MOCK_IRQ_RESTORE, BASE, 16) == rest);      /* restored exactly once */
    /* the install precedes the first unmask and the restore follows the last one */
    CHECK(gbp_mock_first_op(&m, MOCK_IRQ_UNMASK, BASE, 16) > inst);
    CHECK(gbp_mock_last_op(&m, MOCK_IRQ_UNMASK, BASE, 16) < rest);
    CHECK(count_lines_with(&rl, "RESTOREVIDEO handler_installed=1 handler_restored=1 old_handler=nonnull mask_ok=1") == 1);
}

/* ---- 14. the sidecar of a real run ---- */
static void test_sidecar_of_a_run(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    struct gbp_avseqdump_info info, pinfo;
    const uint8_t *cyc, *vt, *at, *vr, *ar;
    long n;
    unsigned i, stored = 0;
    mock_video(&m, 0x0500, 50);
    m.video_flag_period = 40;
    test_config(&cfg);
    cfg.max_deliveries = 45;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.deliveries == 45 && res.video_blocks == 45 && res.audio_drains == 45);
    CHECK(gbp_video_dump_info(&res, 40500000u, "GBP-VIDEO-001", "video-0001", "gbp-video-capture-probe", "abcdef0", &info) == 0);
    CHECK(info.version == 1 && (info.flags & GBP_AVSEQDUMP_FLAG_SERVICE_OK) && (info.flags & GBP_AVSEQDUMP_FLAG_RESTORE_OK));
    CHECK((info.flags & GBP_AVSEQDUMP_FLAG_NEXT_CAUSE_AT_END) && !(info.flags & GBP_AVSEQDUMP_FLAG_PARTIAL));
    CHECK(info.capture_result == GBP_AVSEQ_END_DELIVERY_CAP && info.status_code == (uint16_t)res.status);
    CHECK(info.t0 == res.t0 && info.admission_deadline == res.admission_deadline);
    CHECK(info.boundaries_gbi == res.b_gbi.count && info.boundaries_disc == res.b_disc.count);
    n = gbp_avseqdump_serialize(&info, &store, dump, sizeof dump);
    CHECK(n > 0 && (size_t)n == gbp_avseqdump_size(&store));
    CHECK(gbp_avseqdump_parse(dump, (size_t)n, &pinfo, &cyc, &vt, &at, &vr, &ar) == 0);
    CHECK(pinfo.cycle_count == 45 && pinfo.video_count == 45 && pinfo.audio_count == 45 && pinfo.audio_raw_count == 9);
    CHECK(strcmp(pinfo.test_id, "GBP-VIDEO-001") == 0 && strcmp(pinfo.build_id, "video-0001") == 0);
    /* every cycle record survives the round trip, and every stored VIDEO block is its own bytes */
    for (i = 0; i < pinfo.cycle_count; i++) {
        struct gbp_avseq_cycle c;
        gbp_avseqdump_decode_cycle(cyc + i * GBP_AVSEQDUMP_CYCLE_REC, &c);
        CHECK(c.idx == i && c.pending == store.cycles[i].pending && c.ack_value == store.cycles[i].ack_value);
        CHECK(c.isr_count == 1 && c.isr_reentry == 0 && c.admitted == 1 && c.t_unmask == store.cycles[i].t_unmask);
    }
    for (i = 0; i < pinfo.video_count; i++) {
        struct gbp_avseq_vblock v; uint32_t roff = 0, rlen = 0;
        gbp_avseqdump_decode_vblock(vt + i * GBP_AVSEQDUMP_VIDEO_REC, &v, &roff, &rlen);
        CHECK(v.seq == i && v.completed == 1 && rlen == GBP_AVSEQ_VIDEO_BLOCK_SIZE);
        CHECK(memcmp(dump + roff, gbp_avseq_video_bytes(&store, i), GBP_AVSEQ_VIDEO_BLOCK_SIZE) == 0);
        CHECK(v.flag_gbi == store.vblocks[i].flag_gbi && v.flag_disc == store.vblocks[i].flag_disc);
        stored++;
    }
    CHECK(stored == 45 && pinfo.video_raw_stored == 45);
}

/* ---- 15. the raw buffers are never touched outside their DMA ---- */
static void test_raw_buffers(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    unsigned i;
    mock_video(&m, 0x0100, 50);
    m.bulk_seed = 0x5A;
    test_config(&cfg);
    cfg.max_deliveries = 10;
    run_cfg(&m, &rl, &res, &cfg);
    check_never(&m, &res);
    CHECK(res.video_blocks == 10);
    for (i = 0; i < 10; i++) {
        const uint8_t *b = gbp_avseq_video_bytes(&store, i);
        uint32_t k;
        int ok = 1;
        for (k = 4; k < GBP_AVSEQ_VIDEO_BLOCK_SIZE; k++) if (b[k] != gbp_mock_bulk_byte(1, m.bulk_seed, k)) { ok = 0; break; }
        CHECK(ok);                                      /* the pattern the DMA delivered, byte for byte */
        CHECK(b[0] == 0x7f && b[1] == 0x7f && b[2] == 0xff && b[3] == 0xff);   /* the flag model's first four bytes */
        CHECK(store.vblocks[i].crc32 == gbp_crc32(b, GBP_AVSEQ_VIDEO_BLOCK_SIZE));
    }
    /* the slots beyond the capture are still the pre-fill the probe wrote before the run */
    for (i = 10; i < GBP_AVSEQ_MAX_VIDEO_BLOCKS; i++) {
        const uint8_t *b = video_raw + i * GBP_AVSEQ_VIDEO_BLOCK_SIZE;
        CHECK(b[0] == 0 && b[GBP_AVSEQ_VIDEO_BLOCK_SIZE - 1u] == 0);
    }
}

/* ---- 16. the ring holds a full run without dropping ---- */
static void test_log_capacity(void)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res;
    size_t i, mx = 0;
    mock_video(&m, 0x0500, 50);
    run(&m, &rl, &res);                                 /* the longest run: 88 VIDEO blocks + one AUDIO drain per cycle */
    check_never(&m, &res);
    CHECK(res.capture == GBP_AVSEQ_END_TARGET_REACHED && res.deliveries == 88);
    for (i = 0; i < rl.count; i++) if (strlen(ringlog_line(&rl, i)) > mx) mx = strlen(ringlog_line(&rl, i));
    CHECK(mx < LINE_LEN - 1u && rl.truncated == 0);
    CHECK(rl.dropped == 0);
    CHECK(count_lines_with(&rl, "VBLK seq=") == 88 && count_lines_with(&rl, "ABLK ") == 88);
    CHECK(count_lines_with(&rl, "ADMISSION t0=") == 1 && count_lines_with(&rl, "MATRIX ") == 1);
    CHECK(count_lines_with(&rl, "COUNTERS ") == 1 && count_lines_with(&rl, "TIMING ") == 1 && count_lines_with(&rl, "RESTOREVIDEO ") == 1);
    CHECK(count_lines_with(&rl, "VIDEO start target=88 max_deliveries=320 verify_cycles=4") == 1);
    CHECK(count_lines_with(&rl, "TEARDOWNVIDEO variant=S5_capture_end") == 1);
    /* the WORST reachable demand: 320 deliveries with VIDEO on part of them, so the cycle records,
     * the 320 AUDIO summaries and the VIDEO summaries all pile up. A dropped line would break the
     * log -> fixture -> replay chain of a physical run, so this must hold at the POC's ring size. */
    {
        static const uint16_t pattern[4] = { 0x0400, 0x0400, 0x0400, 0x0500 };
        unsigned k;
        mock_video(&m, 0x0400, 50);
        mock_seq(&m, pattern, 0, 4);
        m.video_flag_period = 1;                    /* every block a boundary: the longest boundary output */
        run(&m, &rl, &res);
        check_never(&m, &res);
        CHECK(res.deliveries == GBP_AVSEQ_MAX_DELIVERIES && res.capture == GBP_AVSEQ_END_DELIVERY_CAP);
        CHECK(res.video_blocks > 0 && res.video_blocks < GBP_AVSEQ_TARGET_VIDEO_BLOCKS);
        CHECK(rl.dropped == 0 && rl.truncated == 0);
        CHECK(rl.count < (size_t)LINES);            /* margin left over the worst case */
        mx = 0;
        for (i = 0; i < rl.count; i++) if (strlen(ringlog_line(&rl, i)) > mx) mx = strlen(ringlog_line(&rl, i));
        CHECK(mx < LINE_LEN - 1u);
        for (k = 0; k < store.cycles_n; k++) CHECK(store.cycles[k].admitted == 1);
    }
}

/* ---- the physical GBP-AV-SERVICE-001 fixture as the exact prefix of cycle 0 ---- */
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

struct sidecar { struct gbp_avdump_info info; const uint8_t *audio, *video; unsigned calls; };
static uint32_t sidecar_source(void *ctx, uint32_t base, uint32_t addr, uint32_t len, uint8_t *out)
{
    struct sidecar *sc = (struct sidecar *)ctx;
    unsigned idx = (unsigned)((addr - base) >> 20) & 0xFu;
    sc->calls++;
    if (idx == sc->info.audio_index && sc->audio && sc->info.audio_len == len) { memcpy(out, sc->audio, len); return len; }
    if (idx == sc->info.video_index && sc->video && sc->info.video_len == len) { memcpy(out, sc->video, len); return len; }
    return 0;
}

static void test_hw_avsvc_as_first_cycle(const char *path, const char *blocks_path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_video_config cfg; struct gbp_video_result res; struct ringlog rl;
    struct sidecar sc; static uint8_t raw[GBP_AVDUMP_MAX_SIZE + 64]; long n; FILE *f;
    memset(&sc, 0, sizeof sc);
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    f = fopen(blocks_path, "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", blocks_path); failures++; free(text); return; }
    n = (long)fread(raw, 1, sizeof raw, f);
    fclose(f);
    CHECK(gbp_avdump_parse(raw, (size_t)n, &sc.info, &sc.audio, &sc.video) == 0);
    if (!sc.audio || !sc.video) { free(text); return; }
    gbp_replay_init(&r, text);
    r.block_source = sidecar_source; r.block_ctx = &sc;
    gbp_replay_transport(&r, &t);
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    gbp_video_config_default(&cfg);
    cfg.store = &store;
    cfg.max_deliveries = 1;            /* the physical run is exactly one cycle of this loop */
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_video_probe_run(&t, &rl, &cfg, &res) == 0);
    /* every physical operation of the AVSVC run is consumed, in order, by this state machine */
    CHECK(r.mismatches == 0 && r.exhausted == 0 && r.step == 132u && r.step == count_ops(text) && r.timeline == 1);
    CHECK(r.bulk_reads == 2u && r.blocks_missing == 0u && r.block_crc_mismatches == 0u && sc.calls == 2u);
    CHECK(r.record_resets == 0);       /* cycle 0 needs no reset: the install cleared the record */
    /* the physical values, unchanged */
    CHECK(res.a.t_event == 3391329164u && res.cause_irq == 0x0400 && res.preunmask.irq_gbi == 0x0500 && res.preunmask_ok == 1);
    CHECK(res.d.fired == 1 && res.d.reentry == 0 && res.d.rec.t_entry == 3391371694u && res.d.t_unmask == 3391371622u);
    CHECK(res.d.latency_ticks == 72u && res.t0 == 3391371622u && res.dt_cause_to_isr_first == 42530u);
    CHECK(store.cycles_n == 1 && store.cycles[0].verify == 1 && store.cycles[0].pending == 0x0500);
    CHECK(store.cycles[0].t_read == 3391379306u && store.cycles[0].irq_disc == 0x0500 && store.cycles[0].irq_gbi == 0x0500);
    CHECK(store.cycles[0].audio_selected == 1 && store.cycles[0].video_selected == 1);
    CHECK(store.cycles[0].t_audio_start == 3391385098u && store.cycles[0].t_audio_end == 3391387790u);
    CHECK(store.cycles[0].t_video_start == 3391387818u && store.cycles[0].t_video_end == 3391390303u);
    CHECK(store.cycles[0].ack_value == 0x8500 && store.cycles[0].ack_completed == 1 && store.cycles[0].t_ack_after == 3391399980u);
    CHECK(store.cycles[0].main_w1c == 0 && store.cycles[0].pi_sticky == 0 && store.cycles[0].intsr_postack == 0x00010000u);
    CHECK(store.cycles[0].t_rearm == 3391408218u && store.cycles[0].rearm_completed == 1 && store.cycles[0].t_rearm_after == 3391408974u);
    /* REARMPOST found the next cause already latched: no poll, the cause is left for the teardown */
    CHECK(store.cycles[0].next_observed == 1 && store.cycles[0].next_ended_by == GBP_AVSEQ_NEXT_CAUSE);
    CHECK(store.cycles[0].t_next == 3391409996u && store.cycles[0].next_polls == 0 && store.cycles[0].next_pending == 0x0400);
    /* the physical blocks, byte for byte from the sidecar */
    CHECK(res.video_blocks == 1 && res.video_completed == 1 && store.vblocks[0].crc32 == 0xfe45ff08u);
    CHECK(res.audio_drains == 1 && res.audio_completed == 1 && store.ablocks[0].crc32 == 0xfec5e4e7u);
    CHECK(memcmp(gbp_avseq_video_bytes(&store, 0), sc.video, 0x0F00u) == 0);
    CHECK(memcmp(gbp_avseq_audio_bytes(&store, 0), sc.audio, 0x1000u) == 0);
    CHECK(store.vblocks[0].raw_first4[0] == 0xff && store.vblocks[0].raw_first4[1] == 0xff);
    CHECK(store.vblocks[0].flag_gbi == 1 && store.vblocks[0].flag_disc == 1 && store.vblocks[0].flags_agree == 1);
    CHECK(res.b_gbi.count == 1 && res.b_gbi.positions[0] == 0 && res.b_gbi.complete_interval == 0);   /* one block: no interval */
    CHECK(res.b_disc.count == 1 && res.b_disc.complete_interval == 0);
    /* the second cycle was refused at the admission point; the latched cause went to the teardown */
    CHECK(res.status == GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP && strcmp(res.status_class, "ok") == 0);
    CHECK(res.capture == GBP_AVSEQ_END_DELIVERY_CAP && strcmp(res.refusal, "delivery_cap") == 0 && res.next_cause_at_end == 1);
    CHECK(res.deliveries == 1 && res.unmasks == 1 && res.acks == 1 && res.rearms == 1 && res.refusals == 1);
    CHECK(res.service_ok == 1 && res.restore_ok == 1 && res.errors == 0 && res.transport_ok == 1 && res.control_ok == 1);
    CHECK(res.isr_w1c == 1 && res.main_w1c == 0 && res.teardown_w1c == 1 && res.pi_sticky_final == 0);
    CHECK(res.h.handler_was_installed == 1 && res.h.handler_restored == 1 && res.h.mask_ok == 1 && res.power_cycle_required == 1);
    CHECK(strcmp(res.teardown_variant, "S5_capture_end") == 0 && res.uncertain_writes == 0);
    /* the records of the replay are the console's */
    CHECK(count_lines_with(&rl, "PRESVC n=0 t=3391379306 intsr13=0,0 intmr13=0,0 control=8c irq=0500/0500 src=0500 av=0500 unexpected=0000 odd=0000 bit15=0 high=0000") == 1);
    CHECK(count_lines_with(&rl, "SVC n=0 pending=0500 audio=1 video=1 order=audio_then_video ack_value=8500 t=3391379306") == 1);
    CHECK(count_lines_with(&rl, "AUDIOREAD idx=8 addr=01800000 len=1000 selected=1 attempted=1 completed=1 rc=ok t_start=3391385098 t_end=3391387790 dt=2692") == 1);
    CHECK(count_lines_with(&rl, "VIDEOREAD idx=1 addr=01100000 len=0f00 selected=1 attempted=1 completed=1 rc=ok t_start=3391387818 t_end=3391390303 dt=2485") == 1);
    CHECK(count_lines_with(&rl, "REARMPOST n=0 t=3391409996 since_rearm=1778") != 0);
    CHECK(count_lines_with(&rl, "outcome=B_latched") == 1);
    CHECK(count_lines_with(&rl, "VBLK seq=0 cyc=0 pend=0500 rc=ok completed=1") == 1);
    CHECK(count_lines_with(&rl, "f4=ffffffff gbi=1 disc=1 agree=1") == 1);
    CHECK(count_lines_with(&rl, "CLEANUP performed=1 value=00002000 rc=ok intsr_before=00012000 intsr_after=00010000 intsr13_after=0 sticky=0 ok=1") == 1);
    CHECK(count_lines_with(&rl, "MATRIX service=ok service_reason=- capture=delivery_cap deliveries=1 video=1/1 audio=1/1 audio_raw=1 next_cause_at_end=1 boundaries_gbi=1 boundaries_disc=1 complete_gbi=0 complete_disc=0 reference_content=offline restore=ok") == 1);
    CHECK(rl.dropped == 0 && rl.truncated == 0);
    /* the same script without the sidecar: the blocks are reported missing, never invented */
    gbp_replay_init(&r, text);
    gbp_replay_transport(&r, &t);
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_video_probe_run(&t, &rl, &cfg, &res);
    CHECK(r.blocks_missing == 2u && store.vblocks[0].crc32 != 0xfe45ff08u);
    free(text);
}

struct seqcar { struct gbp_avseqdump_info info; const uint8_t *vraw, *araw; const uint8_t *vt, *at; unsigned vcalls, acalls, amissing; };
/* The Nth VIDEO read is the Nth stored block (they are contiguous in sequence order). The Nth AUDIO
 * read is the Nth AUDIO record, and only the records whose raw_index is not 0xFFFF have a preserved
 * payload — the first 8 successful drains and the last valid one. For every other drain the source
 * returns nothing, so the replay counts it as a missing block instead of inventing bytes. */
static uint32_t seq_source(void *ctx, uint32_t base, uint32_t addr, uint32_t len, uint8_t *out)
{
    struct seqcar *sc = (struct seqcar *)ctx;
    unsigned idx = (unsigned)((addr - base) >> 20) & 0xFu;
    if (idx == GBP_AVSEQ_VIDEO_INDEX && len == GBP_AVSEQ_VIDEO_BLOCK_SIZE && sc->vraw && sc->vcalls < sc->info.video_raw_stored) {
        memcpy(out, sc->vraw + (size_t)sc->vcalls * GBP_AVSEQ_VIDEO_BLOCK_SIZE, len);
        sc->vcalls++;
        return len;
    }
    if (idx == GBP_AVSEQ_AUDIO_INDEX && len == GBP_AVSEQ_AUDIO_BLOCK_SIZE && sc->at && sc->acalls < sc->info.audio_count) {
        struct gbp_avseq_ablock a;
        unsigned n = sc->acalls++;
        gbp_avseqdump_decode_ablock(sc->at + (size_t)n * GBP_AVSEQDUMP_AUDIO_REC, &a);
        if (a.raw_index != 0xFFFFu && sc->araw && a.raw_index < sc->info.audio_raw_count) {
            memcpy(out, sc->araw + (size_t)a.raw_index * GBP_AVSEQ_AUDIO_BLOCK_SIZE, len);
            return len;
        }
        sc->amissing++;                 /* payload not preserved by design: never invented */
        return 0;
    }
    return 0;
}

/* ---- the physical GBP-VIDEO-001 fixture (2026-09-16, video-0001, commit 6930dde) ---- */
static void test_hw_video_001(const char *path, const char *seq_path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_video_config cfg; struct gbp_video_result res; struct ringlog rl;
    struct seqcar sc; static uint8_t raw[GBP_AVSEQDUMP_MAX_SIZE + 64]; long n; FILE *f;
    unsigned i, starts = 0, disagree = 0, a_only = 0, v_only = 0, both = 0;
    memset(&sc, 0, sizeof sc);
    if (!text) { fprintf(stderr, "cannot read %s\n", path); failures++; return; }
    f = fopen(seq_path, "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", seq_path); failures++; free(text); return; }
    n = (long)fread(raw, 1, sizeof raw, f);
    fclose(f);
    CHECK(n == 403948);
    CHECK(gbp_avseqdump_parse(raw, (size_t)n, &sc.info, 0, &sc.vt, &sc.at, &sc.vraw, &sc.araw) == 0);
    if (!sc.vt || !sc.at) { free(text); return; }
    /* the console's own sidecar: identity, counts and both CRCs */
    CHECK(sc.info.version == 1u && sc.info.tb_hz == 40500000u);
    CHECK(strcmp(sc.info.test_id, "GBP-VIDEO-001") == 0 && strcmp(sc.info.build_id, "video-0001") == 0);
    CHECK(strcmp(sc.info.app, "gbp-video-capture-probe") == 0 && strcmp(sc.info.commit, "6930dde") == 0);
    CHECK(sc.info.cycle_count == 209u && sc.info.video_count == 88u && sc.info.audio_count == 144u);
    CHECK(sc.info.audio_raw_count == 9u && sc.info.video_raw_stored == 88u);
    CHECK(sc.info.capture_result == GBP_AVSEQ_END_TARGET_REACHED && sc.info.boundaries_gbi == 3u && sc.info.boundaries_disc == 3u);
    CHECK(sc.info.header_crc32 == 0x593d4082u && sc.info.total_crc32 == 0xd38bf828u);
    CHECK(sc.info.target_video_blocks == 88u && sc.info.max_deliveries == 320u && sc.info.t0 == 1853935409u);
    /* the sidecar's own tables: the three frame starts, both predicates agreeing on all 88 blocks */
    for (i = 0; i < sc.info.video_count; i++) {
        struct gbp_avseq_vblock v; uint32_t roff = 0, rlen = 0;
        gbp_avseqdump_decode_vblock(sc.vt + (size_t)i * GBP_AVSEQDUMP_VIDEO_REC, &v, &roff, &rlen);
        CHECK(v.seq == i && v.completed == 1 && rlen == GBP_AVSEQ_VIDEO_BLOCK_SIZE);
        CHECK(gbp_crc32(raw + roff, rlen) == v.crc32);                      /* every VIDEO block against its entry */
        CHECK(v.flag_gbi == gbp_avseq_flag_gbi(v.raw_first4) && v.flag_disc == gbp_avseq_flag_disc(v.raw_first4));
        if (v.flag_gbi != v.flag_disc) disagree++;
        if (v.flag_gbi) { CHECK(i == 0 || i == 25 || i == 65); starts++; }
    }
    CHECK(starts == 3 && disagree == 0);
    /* only 9 AUDIO records carry a payload; the other 135 have metadata and no bytes */
    {
        unsigned kept = 0;
        for (i = 0; i < sc.info.audio_count; i++) {
            struct gbp_avseq_ablock a;
            gbp_avseqdump_decode_ablock(sc.at + (size_t)i * GBP_AVSEQDUMP_AUDIO_REC, &a);
            CHECK(a.selected && a.attempted && a.completed && a.rc == 0);
            if (a.raw_index != 0xFFFFu) {
                kept++;
                CHECK(gbp_crc32(raw + sc.info.off_audio_raw + (size_t)a.raw_index * GBP_AVSEQ_AUDIO_BLOCK_SIZE,
                                GBP_AVSEQ_AUDIO_BLOCK_SIZE) == a.crc32);
            } else {
                CHECK(a.crc32 == 0 && a.raw_kept == 0);                     /* never a fabricated measurement */
            }
        }
        CHECK(kept == 9);
    }
    /* replay the whole physical run */
    gbp_replay_init(&r, text);
    r.block_source = seq_source; r.block_ctx = &sc;
    gbp_replay_transport(&r, &t);
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    gbp_video_config_default(&cfg);
    cfg.store = &store;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    CHECK(gbp_video_probe_run(&t, &rl, &cfg, &res) == 0);
    CHECK(r.mismatches == 0 && r.exhausted == 0 && r.step == count_ops(text) && r.timeline == 1);
    CHECK(r.bulk_reads == 232u && r.block_crc_mismatches == 0u);
    CHECK(r.blocks_missing == 135u && sc.amissing == 135u);                 /* the unpreserved AUDIO payloads, never invented */
    CHECK(r.record_resets == 208u);                                          /* one per admitted cycle after the first */
    /* the physical operational result */
    CHECK(res.status == GBP_VIDEO_OK_SEQUENCE_CAPTURE && strcmp(res.status_class, "ok") == 0);
    CHECK(res.capture == GBP_AVSEQ_END_TARGET_REACHED && res.service_ok == 1 && res.restore_ok == 1);
    CHECK(res.deliveries == 209 && res.unmasks == 209 && res.acks == 209 && res.rearms == 209);
    CHECK(res.video_blocks == 88 && res.video_completed == 88 && res.audio_drains == 144 && res.audio_completed == 144);
    CHECK(res.isr_w1c == 209 && res.main_w1c == 0 && res.teardown_w1c == 1);
    CHECK(res.unexpected == 0 && res.uncertain_writes == 0 && res.errors == 0 && res.control_ok == 1 && res.pi_sticky_final == 0);
    CHECK(res.next_cause_at_end == 1 && strcmp(res.refusal, "target_reached") == 0 && res.refusals == 1 && res.admissions == 209);
    CHECK(res.verify_cycles_done == 4 && res.lean_cycles == 205);
    CHECK(res.t0 == 1853935409u && res.admission_deadline == 1853935409u + 40500000u);
    CHECK(res.h.handler_was_installed == 1 && res.h.handler_restored == 1 && res.h.mask_ok == 1 && res.power_cycle_required == 1);
    CHECK(strcmp(res.teardown_variant, "S5_capture_end") == 0);
    /* the source distribution measured in this run */
    for (i = 0; i < store.cycles_n; i++) {
        uint16_t p = store.cycles[i].pending;
        if (p == 0x0400) a_only++; else if (p == 0x0100) v_only++; else if (p == 0x0500) both++;
        CHECK(store.cycles[i].isr_count == 1 && store.cycles[i].isr_reentry == 0 && store.cycles[i].admitted == 1);
        CHECK(store.cycles[i].ack_value == (uint16_t)(p | 0x8000) && store.cycles[i].ack_completed == 1);
        CHECK(store.cycles[i].rearm_completed == 1 && store.cycles[i].main_w1c == 0 && store.cycles[i].pi_sticky == 0);
    }
    CHECK(a_only == 121 && v_only == 65 && both == 23);
    CHECK(a_only + both == 144 && v_only + both == 88);
    /* the boundaries recomputed by the probe from the replayed bytes */
    CHECK(res.b_gbi.count == 3 && res.b_gbi.positions[0] == 0 && res.b_gbi.positions[1] == 25 && res.b_gbi.positions[2] == 65);
    CHECK(res.b_gbi.intervals_n == 2 && res.b_gbi.intervals[0] == 25 && res.b_gbi.intervals[1] == 40 && res.b_gbi.complete_interval == 1);
    CHECK(res.b_disc.count == 3 && res.b_disc.positions[1] == 25 && res.b_disc.positions[2] == 65);
    CHECK(res.b_disc.intervals[1] == 40 && res.b_disc.complete_interval == 1);
    /* the ONE complete physical frame: 40 blocks, semantically uniform apart from its start marker */
    {
        unsigned uniform = 0, k;
        for (i = 25; i <= 64; i++) {
            const uint8_t *b = gbp_avseq_video_bytes(&store, i);
            int ok = 1;
            for (k = (i == 25) ? 4u : 0u; k + 3u < GBP_AVSEQ_VIDEO_BLOCK_SIZE; k += 4u)
                if (b[k + 1u] != 0x7f || b[k + 3u] != 0xff) { ok = 0; break; }
            if (ok) uniform++;
        }
        CHECK(uniform == 40);                                                /* every element 0x7FFF apart from the marker */
        CHECK(gbp_avseq_video_bytes(&store, 25)[1] == 0xff && gbp_avseq_video_bytes(&store, 25)[3] == 0xff);
    }
    /* byte 0 variability: 688 words, always ff/7f, byte 2 never differs from byte 3 */
    {
        unsigned b01 = 0, b23 = 0, ff7f = 0, at0 = 0, k;
        for (i = 0; i < store.vblocks_n; i++) {
            const uint8_t *b = gbp_avseq_video_bytes(&store, i);
            for (k = 0; k + 3u < GBP_AVSEQ_VIDEO_BLOCK_SIZE; k += 4u) {
                if (b[k] != b[k + 1u]) { b01++; if (b[k] == 0xff && b[k + 1u] == 0x7f) ff7f++; if (k % 32u == 0u) at0++; }
                if (b[k + 2u] != b[k + 3u]) b23++;
            }
        }
        CHECK(b01 == 688 && ff7f == 688 && b23 == 0);
        CHECK(at0 == 0);                    /* never the first word of a 32-byte DMA line */
    }
    CHECK(rl.dropped == 0 && rl.truncated == 0);
    free(text);
}

/* ---- host round-trip modes (synthetic) ---- */
static int dump_log(const char *path, const char *seq_path)
{
    struct gbp_mock m; struct ringlog rl; struct gbp_video_result res; struct gbp_video_config cfg;
    char s[2400]; size_t i; FILE *f;
    struct gbp_avseqdump_info info; long n;
    /* a bounded repeated service: both sources every cycle, a frame flag every 3 VIDEO blocks,
     * a re-latch at POSTACK so the single main W1C is part of the round trip, 10-digit time base */
    mock_video(&m, 0x0500, 50);
    m.video_flag_period = 3;
    m.bulk_seed = 0x33;
    m.intsr = 0x00010000u; m.intmr = 0x000001fau; m.tick = 1000;
    test_config(&cfg);
    cfg.max_deliveries = 6;
    run_cfg(&m, &rl, &res, &cfg);
    gbp_video_summary(&res, s, sizeof s);
    f = fopen(path, "w");
    if (!f) { fprintf(stderr, "cannot write %s\n", path); return 1; }
    fprintf(f, "# OPENGBP-LOG v1\n# SYNTHETIC: generated by tests/unit/test_gbp_video.c from the host mock (repeated drained service); NOT physical data\n");
    fprintf(f, "test_id=GBP-VIDEO-001\nbuild_id=synthetic\ncommit=none\nsource=host-mock\n");
    fprintf(f, "lines=%u dropped=%u truncated=%u\n# --- records ---\n", (unsigned)rl.count, (unsigned)rl.dropped, (unsigned)rl.truncated);
    for (i = 0; i < rl.count; i++) fprintf(f, "%s\n", ringlog_line(&rl, i));
    fprintf(f, "# --- end --- dropped=%u\n", (unsigned)rl.dropped);
    fclose(f);
    if (gbp_video_dump_info(&res, 40500000u, "GBP-VIDEO-001", "synthetic", "gbp-video-capture-probe", "none", &info) != 0) {
        fprintf(stderr, "identity rejected\n"); return 1;
    }
    n = gbp_avseqdump_serialize(&info, &store, dump, sizeof dump);
    if (n <= 0) { fprintf(stderr, "cannot serialize the sidecar (rc=%ld)\n", n); return 1; }
    f = fopen(seq_path, "wb");
    if (!f) { fprintf(stderr, "cannot write %s\n", seq_path); return 1; }
    fwrite(dump, 1, (size_t)n, f);
    fclose(f);
    printf("SUMMARY %s\n", s);
    printf("SEQ cycles=%lu video=%lu audio=%lu audio_raw=%lu bytes=%ld total_crc32=%08lx\n",
           (unsigned long)info.cycle_count, (unsigned long)info.video_count, (unsigned long)info.audio_count,
           (unsigned long)info.audio_raw_count, n, (unsigned long)info.total_crc32);
    return 0;
}

static int replay_fixture(const char *path, const char *seq_path)
{
    char *text = read_file(path);
    struct gbp_replay r; struct gbp_transport t; struct gbp_video_config cfg;
    struct gbp_video_result res; struct ringlog rl; char s[2400];
    struct seqcar sc; static uint8_t raw[GBP_AVSEQDUMP_MAX_SIZE + 64]; long n = 0;
    memset(&sc, 0, sizeof sc);
    if (!text) { fprintf(stderr, "cannot read %s\n", path); return 1; }
    if (seq_path) {
        FILE *f = fopen(seq_path, "rb");
        if (!f) { fprintf(stderr, "cannot read %s\n", seq_path); free(text); return 1; }
        n = (long)fread(raw, 1, sizeof raw, f);
        fclose(f);
        if (gbp_avseqdump_parse(raw, (size_t)n, &sc.info, 0, &sc.vt, &sc.at, &sc.vraw, &sc.araw) != 0) {
            fprintf(stderr, "bad sidecar %s\n", seq_path); free(text); return 1;
        }
    }
    gbp_replay_init(&r, text);
    if (seq_path) { r.block_source = seq_source; r.block_ctx = &sc; }
    gbp_replay_transport(&r, &t);
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    test_config(&cfg);
    cfg.max_deliveries = 6;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_video_probe_run(&t, &rl, &cfg, &res);
    gbp_video_summary(&res, s, sizeof s);
    printf("SUMMARY %s\n", s);
    printf("REPLAY step=%u exhausted=%u mismatches=%u tick_polls=%u timeline=%d log_lines=%u bulk_reads=%u blocks_missing=%u block_crc_mismatches=%u record_resets=%u\n",
           r.step, r.exhausted, r.mismatches, r.tick_polls, r.timeline, (unsigned)rl.count, r.bulk_reads, r.blocks_missing,
           r.block_crc_mismatches, r.record_resets);
    free(text);
    return (r.exhausted || r.mismatches || r.blocks_missing || r.block_crc_mismatches) ? 1 : 0;
}

int main(int argc, char **argv)
{
    if (argc == 4 && strcmp(argv[1], "--dump-log") == 0) return dump_log(argv[2], argv[3]);
    if ((argc == 3 || argc == 4) && strcmp(argv[1], "--replay") == 0) return replay_fixture(argv[2], argc == 4 ? argv[3] : 0);
    test_single_cycle();
    test_target_reached();
    test_delivery_cap_320();
    test_source_patterns();
    test_snapshot_immutability();
    test_flags();
    test_admission_budget();
    test_no_next_cause();
    test_pi_latch_between_cycles();
    test_anomalies();
    test_audio_last_valid();
    test_early_aborts();
    test_handler_lifecycle();
    test_sidecar_of_a_run();
    test_raw_buffers();
    test_log_capacity();
    if (argc > 2) test_hw_avsvc_as_first_cycle(argv[1], argv[2]);
    else fprintf(stderr, "note: physical GBP-AV-SERVICE-001 fixture / sidecar paths not given, prefix test skipped\n");
    if (argc > 4) test_hw_video_001(argv[3], argv[4]);
    else fprintf(stderr, "note: physical GBP-VIDEO-001 fixture / sidecar paths not given, replay test skipped\n");
    printf("test_gbp_video: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
