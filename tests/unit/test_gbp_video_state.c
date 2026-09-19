/*
 * test_gbp_video_state.c — GBP-VIDEO-002 end to end against the mock's
 * SYNTHETIC device models: the long service loop, the three clocks, the stop
 * precedence, the immediate teardown, the bounded records and the streamed
 * sidecar with its strict parser.
 *
 * EVERY SCENARIO IS SYNTHETIC. There is no physical GBP-VIDEO-002 fixture and
 * nothing here is physical evidence. The properties GBP-VIDEO-001 validated
 * physically are asserted again on every run, because they remain
 * requirements: one ISR entry per delivery, no reentry, no W1C between the
 * next cause and the next unmask, the whole ACK value, a re-arm per cycle,
 * and a teardown that restores everything.
 *
 * Modes:  test_gbp_video_state
 *         test_gbp_video_state --long        (the ~639 000-delivery scan; slow)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gbp_vstate_probe.h"
#include "gbp_vstatedump.h"
#include "gbp_vcolor.h"
#include "gbp_rawlog.h"
#include "gbp_crc32.h"
#include "gbp_mock.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

#define LINES 1024          /* the POC's ring: the tests prove it never drops a line */
#define LINE_LEN 256
static char storage[LINES * LINE_LEN];

static struct gbp_vstate_frame frames[GBP_VSTATE_MAX_FRAMES];
static struct gbp_vstate_event events[GBP_VSTATE_MAX_EVENTS];
static uint8_t raw_ring[GBP_VSTATE_RAW_RING_BYTES] __attribute__((aligned(32)));
static uint8_t episode_raw[GBP_VSTATE_EPISODE_RAW_BYTES] __attribute__((aligned(32)));
static uint8_t audio_raw[GBP_VSTATE_AUDIO_RAW_BYTES] __attribute__((aligned(32)));
static struct gbp_vstate_cycle cyc_first[GBP_VSTATE_CYC_FIRST];
static struct gbp_vstate_cycle cyc_last[GBP_VSTATE_CYC_LAST];
static struct gbp_vstate_cycle cyc_anomaly[GBP_VSTATE_CYC_ANOMALY];
static struct gbp_vstate_cycle cyc_episode[GBP_VSTATE_CYC_EPISODE];
static struct gbp_vstate vstate;
static uint8_t chunk[GBP_VSTATEDUMP_CHUNK];

/* The synthetic time base of these tests: 1 000 000 ticks per second, so 120 s = 1.2e8 ticks and
 * a frame is 40 blocks of BLOCK_TICKS. Small enough to run, large enough that the 32-bit wrap
 * (0xFFFFFFFF ticks) is crossed by the long scan and by the scripted-origin cases. */
#define TB_HZ 1000000u
#define BLOCK_TICKS 417u                 /* 40 x 417 = 16 680 ticks/frame = 59.95 Hz at TB_HZ */
#define T_DELIVERY 4000u
#define T_NEXT_CAUSE 4000u

static const uint32_t A1_DL[GBP_INITIRQA_MAX_A1_OBS] = { 50u, 100u };
static const uint32_t A2_DL[GBP_INITIRQA_MAX_A2_OBS] = { 50u, 100u, 200u, 400u, 800u, 1600u };

/* ---- the synthetic screen schedule the VIDEO fill hook plays ---------- */
struct screens {
    unsigned change_at[8];    /* VIDEO read number (1-based) where the screen changes */
    uint8_t value[8];         /* the payload byte from that point on */
    unsigned n;
    unsigned chaos_from;      /* from this read on the screen changes every frame: an episode that
                               * opens and never stabilises, which is what keeps one OPEN when the
                               * scientific target arrives */
};
static struct screens sched;

static uint8_t screen_for(unsigned read_n)
{
    uint8_t v = 0xFFu;
    unsigned i;
    for (i = 0; i < sched.n; i++) if (read_n >= sched.change_at[i]) v = sched.value[i];
    if (sched.chaos_from && read_n >= sched.chaos_from) v = (uint8_t)(0x80u + (((read_n - 1u) / 40u) % 90u));
    return v;
}

/* One VIDEO block: `hh hh ll ll` per pixel, the frame-start bit on every 40th read.
 * memset-based so a 286 000-block run stays practical; the bytes are synthetic either way. */
static void fill_video(struct gbp_mock *m, uint8_t *out, uint32_t len, unsigned read_n, void *user)
{
    uint8_t lo = screen_for(read_n);
    uint32_t k;
    (void)m; (void)user;
    for (k = 0; k + 3u < len; k += 4u) { out[k] = 0x7F; out[k + 1] = 0x7F; out[k + 2] = lo; out[k + 3] = lo; }
    if ((read_n - 1u) % 40u == 0u) { out[0] = 0xFF; out[1] = 0xFF; }   /* both predicates: a frame start */
}

static void sched_reset(uint8_t first)
{
    memset(&sched, 0, sizeof sched);
    sched.change_at[0] = 1u;
    sched.value[0] = first;
    sched.n = 1u;
}

static void sched_change(unsigned at_read, uint8_t value)
{
    if (sched.n >= 8u) return;
    sched.change_at[sched.n] = at_read;
    sched.value[sched.n] = value;
    sched.n++;
}

/* ---- the mock device -------------------------------------------------- */
static void mock_vstate(struct gbp_mock *m, const uint16_t *bits, unsigned n, uint32_t delay)
{
    unsigned i;
    gbp_mock_init(m);
    m->irq_model = MOCK_IRQ_MODEL_SOURCE_MASK;
    m->isr_ext = 1;
    m->max_deliveries = 4000000u;              /* the storm guard, above every scenario */
    m->source_assert_after_write = 2u;         /* A2 */
    m->source_assert_delay = 300;
    m->source_assert_bits = bits[0];
    for (i = 0; i < n && i < 16u; i++) { m->seq_steps[i].bits = bits[i]; m->seq_steps[i].delay = delay; }
    m->seq_len = (n < 16u) ? n : 16u;
    m->bulk_clears_source = 1;
    m->video_fill = fill_video;
    m->bulk_tick_advance[1] = BLOCK_TICKS;     /* the modelled inter-block cadence */
}

static void cfg_default(struct gbp_vstate_config *cfg)
{
    gbp_vstate_config_default(cfg);
    gbp_vstate_config_timebase(cfg, TB_HZ);
    memcpy(cfg->a.a1_obs_ticks, A1_DL, sizeof A1_DL);
    memcpy(cfg->a.a2_obs_ticks, A2_DL, sizeof A2_DL);
    cfg->a.tb_hz = TB_HZ;
    cfg->t_delivery_ticks = T_DELIVERY;
    cfg->t_next_cause_ticks = T_NEXT_CAUSE;
    cfg->st = &vstate;
    cfg->cyc_first = cyc_first;
    cfg->cyc_last = cyc_last;
    cfg->cyc_anomaly = cyc_anomaly;
    cfg->cyc_episode = cyc_episode;
}

/* ---- the teardown-ordering witness ----------------------------------- */
struct order_witness {
    struct ringlog *rl;
    uint32_t base;
    int saw_report_before_teardown;
    size_t lines_at_last_control_write;
};
static struct order_witness witness;

static int log_has(const struct ringlog *rl, size_t upto, const char *needle)
{
    size_t i;
    for (i = 0; i < upto && i < rl->count; i++) if (strstr(ringlog_line(rl, i), needle)) return 1;
    return 0;
}

/* Runs at the entry of EVERY block write, before the mock decides anything: the exact moment the
 * teardown's CONTROL restore reaches the transport. If any report record had already been
 * formatted by then, the immediate-teardown rule would be broken. */
static void on_write(struct gbp_mock *m, uint32_t addr, const uint8_t data[GBP_BLOCK_SIZE], void *user)
{
    struct order_witness *w = (struct order_witness *)user;
    (void)m; (void)data;
    if (addr == w->base + (4u << 20)) {        /* the CONTROL register window */
        w->lines_at_last_control_write = w->rl->count;
        if (log_has(w->rl, w->rl->count, "MATRIX ") || log_has(w->rl, w->rl->count, "CLOCKS ") ||
            log_has(w->rl, w->rl->count, "FRAMECAP ") || log_has(w->rl, w->rl->count, "SIGCOST "))
            w->saw_report_before_teardown = 1;
    }
}

static int line_index(const struct ringlog *rl, const char *needle)
{
    size_t i;
    for (i = 0; i < rl->count; i++) if (strstr(ringlog_line(rl, i), needle)) return (int)i;
    return -1;
}

/* the bounded disagreement store every scenario attaches (§R3.15) */
static struct gbp_vstate_diag diag_store[GBP_VSTATE_MAX_DISAGREEMENTS];

/* GBP-VIDEO-003 needs a FOUR-slot ring and its own state, so the colour success
 * trace does not disturb the vstate harness above (which stays at three). */
static uint8_t colour_ring[GBP_VSTATE_RAW_RING_BYTES_4] __attribute__((aligned(32)));
static struct gbp_vstate colour_vstate;
static struct gbp_vstate_frame colour_frames_store[GBP_VSTATE_MAX_FRAMES];
static struct gbp_vstate_event colour_events_store[GBP_VSTATE_MAX_EVENTS];
static struct gbp_vstate_diag colour_diag_store[GBP_VSTATE_MAX_DISAGREEMENTS];

static void run_cfg_colour(struct gbp_mock *m, struct ringlog *rl, struct gbp_vstate_result *res,
                           struct gbp_vstate_config *cfg)
{
    struct gbp_transport t;
    gbp_mock_transport(m, &t);
    gbp_vstate_init(&colour_vstate, colour_frames_store, GBP_VSTATE_MAX_FRAMES,
                    colour_events_store, GBP_VSTATE_MAX_EVENTS,
                    colour_ring, sizeof colour_ring, episode_raw, sizeof episode_raw,
                    audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&colour_vstate, colour_diag_store, GBP_VSTATE_MAX_DISAGREEMENTS);
    cfg->st = &colour_vstate;
    ringlog_init(rl, storage, LINE_LEN, LINES);
    memset(&witness, 0, sizeof witness);
    witness.rl = rl;
    witness.base = gbp_internal_size_from_arinfo(m->arinfo);
    m->write_hook = on_write;
    m->write_hook_user = &witness;
    gbp_vstate_probe_run(&t, rl, cfg, res);
}

static void run_cfg(struct gbp_mock *m, struct ringlog *rl, struct gbp_vstate_result *res, struct gbp_vstate_config *cfg)
{
    struct gbp_transport t;
    gbp_mock_transport(m, &t);
    gbp_vstate_init(&vstate, frames, GBP_VSTATE_MAX_FRAMES, events, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&vstate, diag_store, GBP_VSTATE_MAX_DISAGREEMENTS);
    cfg->st = &vstate;
    ringlog_init(rl, storage, LINE_LEN, LINES);
    memset(&witness, 0, sizeof witness);
    witness.rl = rl;
    witness.base = gbp_internal_size_from_arinfo(m->arinfo);
    m->write_hook = on_write;
    m->write_hook_user = &witness;
    gbp_vstate_probe_run(&t, rl, cfg, res);
}

/* ---- the properties asserted on every run ---------------------------- */
static void check_invariants(const struct gbp_mock *m, const struct gbp_vstate_result *res, struct ringlog *rl)
{
    /* the physically validated GBP-VIDEO-001 properties, still requirements */
    CHECK(m->violation_mask == 0u);                       /* no mock invariant was violated */
    CHECK(res->h.handler_was_installed == 1);
    CHECK(m->installed_calls == 1);                       /* installed exactly ONCE */
    CHECK(res->h.handler_restored == 1);
    CHECK(res->isr_w1c == res->deliveries);               /* one ISR W1C per delivery */
    CHECK(res->acks == res->deliveries || !res->service_ok);
    CHECK(res->rearms == res->deliveries || !res->service_ok);
    CHECK(res->h.mask_ok == 1);
    CHECK(res->a.arinfo_restore_ok == 1);
    CHECK(res->power_cycle_required == 1);
    /* the log never dropped a line: the POC's ring is sized for the worst reachable run */
    CHECK(rl->dropped == 0);
    CHECK(rl->truncated == 0);
    /* teardown BEFORE any report record, proven at the hardware moment and again on the log */
    CHECK(witness.saw_report_before_teardown == 0);
    {
        int td = line_index(rl, "TEARDOWNVSTATE ");
        int tdstart = line_index(rl, "TEARDOWN start");
        int matrix = line_index(rl, "MATRIX ");
        int clocks = line_index(rl, "CLOCKS ");
        int framecap = line_index(rl, "FRAMECAP ");
        CHECK(td >= 0);
        /* the probe's own status line now comes AFTER the validated 003A teardown, so between the
         * stop decision and the first hardware write the probe formats nothing at all */
        CHECK(tdstart < 0 || td > tdstart);
        CHECK(matrix > td);
        CHECK(clocks > td);
        CHECK(framecap < 0 || framecap > td);
    }
    /* the epoch is reconstructed and CHECKED, never fabricated */
    CHECK(res->epoch_ok == 1 || res->epoch_ok == -1);
    if (res->a.control_written) {
        CHECK(res->epoch_ok == 1);
        CHECK(res->t_control_transform > 0u);
        CHECK(res->t_capture_start >= res->t_control_transform);
    }
}

/* ===================================================================== */
static void test_nominal_negative(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- the scientific target reached with no episode: ok_no_change_nominal_interval\n");
    cfg_default(&cfg);
    /* a short target so the scenario runs in a moment; the mechanism is identical at 120 s */
    cfg.min_valid_observation_s = 0u;
    cfg.min_valid_observation_ticks = (uint64_t)BLOCK_TICKS * 39u * 6u;   /* six counted frames */
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(res.stop == GBP_VSTATE_STOP_NOMINAL_NEGATIVE);
    CHECK(res.status == GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL);
    CHECK(vstate.baseline_valid == 1);
    CHECK(vstate.episode_count == 0u);
    CHECK(res.valid_observation_elapsed >= cfg.min_valid_observation_ticks);
    CHECK(res.baseline_elapsed > 0u);
    CHECK(res.capture_elapsed > res.valid_observation_elapsed);   /* the baseline lengthens the capture */
    CHECK(res.t_control_transform > 0u);
    CHECK(res.t_capture_start >= res.t_control_transform);
    CHECK(res.safety_elapsed > res.capture_elapsed);              /* the safety clock starts earlier */
    CHECK(vstate.frames_complete > 0u);
    CHECK(vstate.boundaries_disc == vstate.boundaries_gbi);       /* the fill sets both predicates */
    CHECK(vstate.disagreements_total == 0u);
    check_invariants(&m, &res, &rl);
    printf("   frames=%lu counted=%lu deliveries=%lu valid=%llu\n", (unsigned long)vstate.frames_n,
           (unsigned long)vstate.frames_counted, (unsigned long)res.deliveries,
           (unsigned long long)res.valid_observation_elapsed);
}

static void test_safety_budget_before_target(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- the hard safety cap before the target: inconclusive, NEVER nominal_negative\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;    /* unreachable */
    cfg.hard_wallclock_ticks = 200000u;                     /* fires early */
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(res.stop == GBP_VSTATE_STOP_SAFETY_BUDGET);
    CHECK(res.status == GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE);
    CHECK(res.status != GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL);
    CHECK(res.valid_observation_elapsed < cfg.min_valid_observation_ticks);
    CHECK(res.safety_elapsed >= cfg.hard_wallclock_ticks);
    CHECK(line_index(&rl, "type=safety_budget") >= 0);
    check_invariants(&m, &res, &rl);
}

static void test_safety_wins_over_open_episode(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- the hard safety cap fires with an episode open: it wins, and the episode is truncated\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.hard_wallclock_ticks = 260000u;
    sched_reset(0xFFu);
    sched_change(241u, 0xF0u);        /* the screen changes and then keeps changing: never stabilises */
    sched_change(281u, 0xE0u);
    sched_change(321u, 0xD0u);
    sched_change(361u, 0xC0u);
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.stop == GBP_VSTATE_STOP_SAFETY_BUDGET);
    CHECK(res.status == GBP_VSTATE_OK_STRUCTURED_CHANGE_OBSERVED);   /* an episode WAS observed */
    CHECK(vstate.episode_count >= 1u);
    CHECK(vstate.episode_open == 0);
    CHECK(vstate.tail_active == 0);
    CHECK(vstate.episodes_n >= 1u);
    CHECK((vstate.episodes[vstate.episodes_n - 1u].flags & GBP_VSTATE_EPF_TRUNCATED_BY_SAFETY) != 0u);
    check_invariants(&m, &res, &rl);
}

static void test_episodes_and_no_early_stop(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- the failure mode that removed the early stop: an intermediate screen, then another\n");
    cfg_default(&cfg);
    /* the run ends on the delivery guard, so the scientific target can never pre-empt the second
     * episode: the point of the scenario is that NOTHING stops the probe at the first stable state */
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 1600u;                       /* 40 frames */
    sched_reset(0xFFu);
    sched_change(241u, 0xF0u);        /* frame 6: the INTERMEDIATE stable screen */
    sched_change(1041u, 0xA0u);       /* twenty frames later: the one the withdrawn rule would lose */
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(res.stop == GBP_VSTATE_STOP_DELIVERY_CAP);
    CHECK(vstate.episode_count >= 2u);                   /* BOTH were observed */
    CHECK(vstate.stable_episodes >= 2u);
    CHECK(vstate.episodes_n >= 2u);
    CHECK(vstate.episodes[0].final_sig[0] != vstate.episodes[1].final_sig[0]);
    CHECK(vstate.original_baseline_sig[0] != vstate.current_reference_sig[0]);
    CHECK(vstate.reference_updates >= 2u);
    CHECK(res.status == GBP_VSTATE_OK_STRUCTURED_CHANGE_OBSERVED);
    /* raw preserved for both, and the episode cycle records exist */
    CHECK(vstate.episodes[0].raw_frames >= 2u);
    CHECK(vstate.episodes[1].raw_frames >= 2u);
    CHECK(res.cyc_episode_n > 0u);
    /* P2 (GBP-HW-145). A frame that CLOSES an episode as stable must carry
     * F_EPISODE_STABLE and must NOT carry F_MAJORITY_EXTRA. Until 2026-09-18
     * the two shared bit 0x1000, and the first physical stream run refused 324
     * complete frames because of it. This scenario produces stable episodes, so
     * it is the right place to assert the separation end to end — and it does
     * so on the real assembler, not on a synthesised flag word. */
    {
        uint32_t i, stable_frames = 0;
        for (i = 0; i < vstate.frames_n; i++) {
            const uint16_t fl = vstate.frames[i].flags;
            if (fl & GBP_VSTATE_F_EPISODE_STABLE) {
                stable_frames++;
                CHECK((fl & GBP_VSTATE_F_MAJORITY_EXTRA) == 0u);
                /* and the stream path must consider it publishable */
                CHECK(gbp_vqueue_classify(vstate.frames[i].blocks, fl,
                                          (int)(i % 4u)) != GBP_VQUEUE_REJECT_QUARANTINED);
            }
            /* no frame in this scenario is a genuine majority-extra */
            CHECK((fl & GBP_VSTATE_F_MAJORITY_EXTRA) == 0u);
        }
        CHECK(stable_frames >= 2u);            /* the scenario really produced them */
    }
    check_invariants(&m, &res, &rl);
    printf("   episodes=%lu stable=%lu frames=%lu stop=%s status=%s deliveries=%lu video=%lu valid=%llu target=%llu\n",
           (unsigned long)vstate.episode_count, (unsigned long)vstate.stable_episodes, (unsigned long)vstate.frames_n,
           gbp_vstate_stop_name(res.stop), res.status_name, (unsigned long)res.deliveries,
           (unsigned long)res.video_completed, (unsigned long long)res.valid_observation_elapsed,
           (unsigned long long)cfg.min_valid_observation_ticks);
}

static void test_target_with_episode_open(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- the target arrives with an episode OPEN: a bounded tail, then nominal_negative\n");
    cfg_default(&cfg);
    /* Each counted frame is worth about 39 blocks of cadence plus the clock reads the cycle makes,
     * so the target is expressed in frames and measured against what the run really accumulated. */
    cfg.min_valid_observation_ticks = (uint64_t)BLOCK_TICKS * 39u * 20u;
    sched_reset(0xFFu);
    sched.chaos_from = 241u;          /* from frame 6 on the screen changes every frame: never stable */
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(res.stop == GBP_VSTATE_STOP_NOMINAL_NEGATIVE);
    CHECK(res.valid_observation_at_target >= cfg.min_valid_observation_ticks);
    CHECK(vstate.tail_frames > 0u);                                  /* a tail really ran */
    CHECK(vstate.tail_frames <= GBP_VSTATE_EPISODE_MAX_FRAMES);      /* and it is bounded */
    CHECK(vstate.tail_ticks > 0u);
    CHECK(vstate.episode_count >= 1u);
    CHECK(res.status == GBP_VSTATE_OK_STRUCTURED_CHANGE_OBSERVED);
    check_invariants(&m, &res, &rl);
    printf("   tail_frames=%lu tail_ticks=%llu episodes=%lu frames=%lu stop=%s video=%lu\n",
           (unsigned long)vstate.tail_frames, (unsigned long long)vstate.tail_ticks,
           (unsigned long)vstate.episode_count, (unsigned long)vstate.frames_n,
           gbp_vstate_stop_name(res.stop), (unsigned long)res.video_completed);
}

static void test_no_next_cause(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- the device stops producing causes: observation_no_next_cause, nothing fabricated\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    m.seq_stop_after = 20u;                  /* only the first 20 re-arms get a cause */
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(res.stop == GBP_VSTATE_STOP_NO_NEXT_CAUSE);
    CHECK(res.status == GBP_VSTATE_OBSERVATION_NO_NEXT_CAUSE);
    CHECK(res.next_cause_at_end == 0);
    CHECK(res.deliveries == 21u);
    check_invariants(&m, &res, &rl);
}

static void test_delivery_cap(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- the delivery guard: a normal end, never a transport failure\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 50u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(res.stop == GBP_VSTATE_STOP_DELIVERY_CAP);
    CHECK(res.deliveries == 50u);
    CHECK(res.next_cause_at_end == 1);        /* the cause stays latched for the teardown */
    CHECK(res.a.pi_cleanup_performed == 1);
    check_invariants(&m, &res, &rl);
}

static void test_audio_policy(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[2] = { 0x0500u, 0x0400u };
    printf("-- AUDIO: always drained, aggregate counters only, no record per drain\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 120u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 2u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(res.audio_drains == 120u);                       /* every cycle carried AUDIO */
    CHECK(vstate.audio.completed == 120u);
    CHECK(vstate.audio.failures == 0u);
    CHECK(vstate.audio.bytes == (uint64_t)120u * GBP_VSTATE_AUDIO_BLOCK_SIZE);
    CHECK(gbp_vstate_audio_raw_count(&vstate) == 2u);      /* the first and the last, and nothing else */
    printf("   deliveries=%lu video=%lu audio=%lu\n", (unsigned long)res.deliveries,
           (unsigned long)res.video_completed, (unsigned long)res.audio_drains);
    CHECK(res.video_completed >= 55u && res.video_completed <= 65u);   /* VIDEO on about half the cycles */
    /* no per-delivery record anywhere: the bounded tables are the only cycle records */
    CHECK(res.cyc_first_n == GBP_VSTATE_CYC_FIRST);
    CHECK(res.cyc_last_n == GBP_VSTATE_CYC_LAST);
    CHECK(res.cyc_first_n + res.cyc_last_n + res.cyc_anomaly_n + res.cyc_episode_n < res.deliveries);
    CHECK(vstate.events_n < res.deliveries / 4u);
    check_invariants(&m, &res, &rl);
}

static void test_disagreement_and_intervals(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- a predicate disagreement is recorded; segmentation stays on the Disc predicate\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 200u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    m.video_fill = 0;                          /* use the mock's own flag model instead of the hook */
    m.video_first4_model = 1;
    m.video_flag_period = 40u;
    m.video_flag_style = 0;
    m.video_flag_only_at = 0;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(vstate.boundaries_disc == 5u);
    CHECK(vstate.boundaries_gbi == 5u);
    CHECK(vstate.disagreements_total == 0u);
    CHECK(vstate.frames_complete == 4u);
    CHECK(line_index(&rl, "INTERVALS ") > 0);

    printf("-- Disc = 1 with GBI = 0 on one block: counted, raw kept, no boundary fabricated for GBI\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 200u;
    mock_vstate(&m, bits, 1u, 50u);
    m.video_fill = 0;
    m.video_first4_model = 1;
    m.video_flag_period = 40u;
    m.video_flag_style = 1;                    /* byte 1 only: Disc = 1, GBI = 0 on every boundary */
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(vstate.boundaries_disc == 5u);
    CHECK(vstate.boundaries_gbi == 0u);        /* not one GBI boundary was invented */
    CHECK(vstate.disagreements_total == 5u);
    CHECK(vstate.disagreement_seen == 1);
    CHECK(vstate.disagreement_first4[1] == 0xFFu);
    CHECK(vstate.disagreement_first4[0] == 0x7Fu);
    CHECK(line_index(&rl, "PREDICATES ") > 0);
    check_invariants(&m, &res, &rl);
}

static void test_byte0_opens_no_episode(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- byte-0 variation across a frame changes no signature and opens no episode\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 400u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    m.video_fill = 0;
    m.video_first4_model = 1;
    m.video_flag_period = 40u;
    m.video_flag_style = 0;
    m.video_byte0_extra_at = 205u;             /* one block's byte 0 gets the extra bit, byte 1 untouched */
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(vstate.episode_count == 0u);         /* nothing opened: byte 0 is not in the signature */
    CHECK(vstate.baseline_valid == 1);
    CHECK(vstate.disagreements_total == 0u);   /* byte 0 alone makes neither predicate true */
    check_invariants(&m, &res, &rl);
}

/* ---- the sidecar ------------------------------------------------------ */
struct memsink { uint8_t *buf; size_t cap, n; int fail_after; int failed; };

static int sink_mem(void *ctx, const uint8_t *data, uint32_t len)
{
    struct memsink *s = (struct memsink *)ctx;
    if (s->fail_after && (int)s->n >= s->fail_after) { s->failed = 1; return -1; }
    if (s->n + len > s->cap) { s->failed = 1; return -1; }
    memcpy(s->buf + s->n, data, len);
    s->n += len;
    return 0;
}

static uint8_t sidecar[16u * 1024u * 1024u];

static void test_sidecar(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vstatedump_info info, parsed;
    struct memsink sink;
    const uint16_t bits[1] = { 0x0500u };
    const uint8_t *fr = 0, *ev = 0, *ep = 0, *cy = 0, *vr = 0, *ar = 0;
    long n;
    uint64_t written = 0;
    printf("-- the sidecar: streamed, deterministic, strictly parsed, larger than 1 MiB\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 3000u;                /* 3000 VIDEO blocks = 75 frames, plus the preserved raw */
    sched_reset(0xFFu);
    sched_change(241u, 0xF0u);                 /* three separated, stabilising screens: three episodes */
    sched_change(1041u, 0xA0u);
    sched_change(1841u, 0x50u);
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(vstate.episode_count >= 3u);

    memset(&info, 0, sizeof info);
    CHECK(gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "e581778-dirty") == 0);
    sink.buf = sidecar; sink.cap = sizeof sidecar; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    n = gbp_vstatedump_stream(&info, &vstate, &res, &cfg, chunk, sizeof chunk, sink_mem, &sink, &written);
    CHECK(n > 0);
    CHECK((uint64_t)n == written);
    CHECK((uint64_t)n == info.total_size);
    CHECK(n > 1024 * 1024);                    /* comfortably larger than 1 MiB */
    CHECK(sink.n == (size_t)n);
    printf("   sidecar %ld bytes, %lu frames, %lu events, %lu episodes, %lu cycles, %lu raw frames\n",
           n, (unsigned long)info.frame_count, (unsigned long)info.event_count,
           (unsigned long)info.episode_count, (unsigned long)info.cycle_count, (unsigned long)info.video_raw_frames);

    /* determinism: the same state serializes to the same bytes */
    {
        static uint8_t again[sizeof sidecar];
        struct memsink s2;
        struct gbp_vstatedump_info info2;
        long n2;
        memset(&info2, 0, sizeof info2);
        gbp_vstatedump_set_identity(&info2, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "e581778-dirty");
        s2.buf = again; s2.cap = sizeof again; s2.n = 0; s2.fail_after = 0; s2.failed = 0;
        n2 = gbp_vstatedump_stream(&info2, &vstate, &res, &cfg, chunk, sizeof chunk, sink_mem, &s2, 0);
        CHECK(n2 == n);
        CHECK(memcmp(again, sidecar, (size_t)n) == 0);
        CHECK(info2.total_crc32 == info.total_crc32);
    }
    /* a chunk size that does not divide any section still produces the same bytes */
    {
        static uint8_t again[sizeof sidecar];
        static uint8_t small_chunk[1553];
        struct memsink s3;
        struct gbp_vstatedump_info info3;
        long n3;
        memset(&info3, 0, sizeof info3);
        gbp_vstatedump_set_identity(&info3, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "e581778-dirty");
        s3.buf = again; s3.cap = sizeof again; s3.n = 0; s3.fail_after = 0; s3.failed = 0;
        n3 = gbp_vstatedump_stream(&info3, &vstate, &res, &cfg, small_chunk, sizeof small_chunk, sink_mem, &s3, 0);
        CHECK(n3 == n);
        CHECK(memcmp(again, sidecar, (size_t)n) == 0);
    }

    /* the strict parser */
    CHECK(gbp_vstatedump_parse(sidecar, (size_t)n, &parsed, &fr, &ev, &ep, &cy, &vr, &ar) == 0);
    CHECK(parsed.version == GBP_VSTATEDUMP_VERSION);
    CHECK(parsed.frame_count == info.frame_count);
    CHECK(parsed.event_count == info.event_count);
    CHECK(parsed.episode_count == info.episode_count);
    CHECK(parsed.total_crc32 == info.total_crc32);
    CHECK(strcmp(parsed.test_id, "GBP-VIDEO-002") == 0);
    CHECK(parsed.version == GBP_VSTATEDUMP_VERSION);
    CHECK(parsed.valid_observation_elapsed == res.valid_observation_elapsed);
    CHECK(parsed.t_control_transform == res.t_control_transform);
    CHECK(parsed.hard_wallclock_ticks == cfg.hard_wallclock_ticks);
    {
        struct gbp_vstate_frame f0;
        struct gbp_vstate_event e0;
        struct gbp_vstate_episode p0;
        struct gbp_vstate_cycle c0;
        uint32_t off[GBP_VSTATE_EPISODE_RAW_SLOTS];
        gbp_vstatedump_decode_frame(fr, &f0);
        CHECK(f0.index == frames[0].index);
        CHECK(f0.blocks == frames[0].blocks);
        CHECK(memcmp(f0.sig, frames[0].sig, sizeof f0.sig) == 0);
        gbp_vstatedump_decode_event(ev, &e0);
        CHECK(e0.seq == events[0].seq);
        CHECK(e0.t == events[0].t);
        gbp_vstatedump_decode_episode(ep, &p0, off);
        CHECK(p0.index == vstate.episodes[0].index);
        CHECK(p0.raw_frames == vstate.episodes[0].raw_frames);
        CHECK(off[0] == parsed.off_video_raw);
        gbp_vstatedump_decode_cycle(cy, &c0);
        CHECK(c0.index == cyc_first[0].index);
        /* the preserved raw really is the bytes the ring held */
        CHECK(memcmp(sidecar + off[0], gbp_vstate_episode_block(&vstate, vstate.episodes[0].raw_slot, 0u),
                     GBP_VSTATE_VIDEO_BLOCK_SIZE) == 0);
    }

    printf("-- corruption and truncation are detected, never parsed through\n");
    {
        static uint8_t bad[sizeof sidecar];
        memcpy(bad, sidecar, (size_t)n);
        CHECK(gbp_vstatedump_parse(bad, (size_t)n - 1u, 0, 0, 0, 0, 0, 0, 0) == -1);        /* truncated */
        CHECK(gbp_vstatedump_parse(bad, 32u, 0, 0, 0, 0, 0, 0, 0) == -1);                   /* far too short */
        bad[0] = 'X';
        CHECK(gbp_vstatedump_parse(bad, (size_t)n, 0, 0, 0, 0, 0, 0, 0) == -1);             /* bad magic */
        memcpy(bad, sidecar, (size_t)n);
        bad[0x009] = 9u;
        CHECK(gbp_vstatedump_parse(bad, (size_t)n, 0, 0, 0, 0, 0, 0, 0) == -2);             /* version */
        memcpy(bad, sidecar, (size_t)n);
        bad[0x010] ^= 0x01u;
        CHECK(gbp_vstatedump_parse(bad, (size_t)n, 0, 0, 0, 0, 0, 0, 0) == -3);             /* header CRC */
        memcpy(bad, sidecar, (size_t)n);
        bad[GBP_VSTATEDUMP_HEADER_SIZE + 4u] ^= 0x80u;
        CHECK(gbp_vstatedump_parse(bad, (size_t)n, 0, 0, 0, 0, 0, 0, 0) == -6);             /* payload CRC */
        memcpy(bad, sidecar, (size_t)n);
        bad[info.off_footer] = 'Z';
        CHECK(gbp_vstatedump_parse(bad, (size_t)n, 0, 0, 0, 0, 0, 0, 0) == -5);             /* footer magic */
        memcpy(bad, sidecar, (size_t)n);
        bad[0x1E0] = 1u;
        CHECK(gbp_vstatedump_parse(bad, (size_t)n, 0, 0, 0, 0, 0, 0, 0) == -3);             /* reserved byte changes the CRC first */
    }

    printf("-- an identity that does not fit is an error, never a truncation\n");
    {
        struct gbp_vstatedump_info bad_id;
        memset(&bad_id, 0, sizeof bad_id);
        CHECK(gbp_vstatedump_set_identity(&bad_id, "GBP-VIDEO-002", "vstate-0001",
                                          "an-application-name-far-too-long-for-the-field", "abc") != 0);
        CHECK(bad_id.identity_error == 1);
        sink.n = 0; sink.failed = 0;
        CHECK(gbp_vstatedump_stream(&bad_id, &vstate, &res, &cfg, chunk, sizeof chunk, sink_mem, &sink, 0) == -2);
        CHECK(sink.n == 0);
    }

    printf("-- a save failure after a successful teardown leaves hardware_result intact\n");
    {
        gbp_vstate_status before_status = res.status;
        int before_restore = res.restore_ok;
        uint64_t before_valid = res.valid_observation_elapsed;
        struct gbp_vstatedump_info info4;
        long rc;
        memset(&info4, 0, sizeof info4);
        gbp_vstatedump_set_identity(&info4, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "e581778-dirty");
        sink.n = 0; sink.failed = 0; sink.fail_after = 300000;      /* the card dies part way */
        rc = gbp_vstatedump_stream(&info4, &vstate, &res, &cfg, chunk, sizeof chunk, sink_mem, &sink, &written);
        CHECK(rc == -4);
        CHECK(written > 0 && written < (uint64_t)n);                /* a partial save, named exactly */
        CHECK(res.status == before_status);                         /* the hardware result is untouched */
        CHECK(res.restore_ok == before_restore);
        CHECK(res.valid_observation_elapsed == before_valid);
        CHECK(vstate.frames_n == info.frame_count);                 /* and so is everything in RAM */
        sink.fail_after = 0;
    }
}



/* Section 13: the two readings, pinned exactly as they are, on synthetic windows.
 * NOTHING here changes the algorithm; these cases document it and would fail if it moved. */
static void fill_window(uint8_t w[GBP_BLOCK_SIZE], uint8_t hi, uint8_t lo)
{
    unsigned k;
    for (k = 0; k < 8u; k++) { w[4*k] = hi; w[4*k+1] = hi; w[4*k+2] = lo; w[4*k+3] = lo; }
}

static void test_read_semantics(void)
{
    uint8_t w[GBP_BLOCK_SIZE];
    unsigned k;
    printf("-- the two readings of the 32-byte IRQ window, pinned\n");

    /* A: all eight replicas identical -> agree */
    fill_window(w, 0x05, 0x00);
    CHECK(gbp_irq_value_disc(w) == 0x0500u);
    CHECK(gbp_irq_value_gbi(w) == 0x0500u);

    /* B: deviations ONLY on offsets 0 and 2 - the bytes neither reading consumes. This is the
     * historical case: 220 such deviations across every physical log, none ever disagreed. */
    fill_window(w, 0x05, 0x00);
    for (k = 0; k < 8u; k++) { w[4*k] ^= 0x80u; w[4*k+2] ^= 0x5Au; }
    CHECK(gbp_irq_value_disc(w) == 0x0500u);
    CHECK(gbp_irq_value_gbi(w) == 0x0500u);
    CHECK(gbp_irq_value_disc(w) == gbp_irq_value_gbi(w));

    /* C: the LAST replica differs on a consumed byte, the majority holds - the shape of the
     * physical abort of cycle 51750 */
    fill_window(w, 0x05, 0x00);
    w[0x1F] ^= 0x01u;
    CHECK(gbp_irq_value_disc(w) == 0x0501u);        /* the Disc reads exactly that byte */
    CHECK(gbp_irq_value_gbi(w) == 0x0500u);         /* GBI votes it down 7 to 1 */
    CHECK(gbp_irq_value_disc(w) != gbp_irq_value_gbi(w));
    fill_window(w, 0x05, 0x00);
    w[0x1D] ^= 0x80u;                                /* the high byte of the last replica */
    CHECK(gbp_irq_value_disc(w) == 0x8500u);
    CHECK(gbp_irq_value_gbi(w) == 0x0500u);

    /* D: the majority itself moves, the last replica stays - they disagree the other way */
    fill_window(w, 0x05, 0x00);
    for (k = 0; k < 7u; k++) w[4*k+3] = 0x02u;      /* seven of eight low replicas change */
    CHECK(gbp_irq_value_disc(w) == 0x0500u);
    CHECK(gbp_irq_value_gbi(w) == 0x0502u);

    /* E: the vote is BITWISE and a tie at four resolves to 0, so the result need not equal any
     * replica that was actually read. This is a property of the algorithm, not a choice made here. */
    fill_window(w, 0x00, 0x00);
    for (k = 0; k < 4u; k++) w[4*k+3] = 0x0Fu;      /* exactly four of eight carry bits 0..3 */
    CHECK(gbp_irq_value_gbi(w) == 0x0000u);         /* a tie is not a majority */
    fill_window(w, 0x00, 0x00);
    for (k = 0; k < 5u; k++) w[4*k+3] = 0x0Fu;      /* five of eight */
    CHECK(gbp_irq_value_gbi(w) == 0x000Fu);
    fill_window(w, 0x00, 0x00);
    for (k = 0; k < 4u; k++) w[4*k+3] = 0x0Fu;      /* four carry the low nibble ... */
    for (k = 4; k < 8u; k++) w[4*k+3] = 0xF0u;      /* ... and four the high nibble */
    CHECK(gbp_irq_value_gbi(w) == 0x0000u);         /* neither half wins: a value no replica held */
    CHECK(gbp_irq_value_disc(w) == 0x00F0u);        /* while the Disc simply reads the last one */

    /* the offsets each reading touches, stated as a test rather than as a comment */
    {
        unsigned disc_sensitive = 0, gbi_sensitive = 0;
        for (k = 0; k < GBP_BLOCK_SIZE; k++) {
            uint8_t a[GBP_BLOCK_SIZE], b[GBP_BLOCK_SIZE];
            fill_window(a, 0x05, 0x00);
            memcpy(b, a, sizeof b);
            b[k] ^= 0xFFu;
            if (gbp_irq_value_disc(a) != gbp_irq_value_disc(b)) disc_sensitive |= 1u << (k & 3u);
            if (gbp_irq_value_gbi(a) != gbp_irq_value_gbi(b)) gbi_sensitive |= 1u << (k & 3u);
        }
        CHECK(disc_sensitive == ((1u << 1) | (1u << 3)));   /* only offsets 1 and 3 mod 4 ... */
        CHECK(gbi_sensitive == 0u);                          /* ... and GBI survives ANY single byte */
    }
}

/* ===================================================================== */
/* U-GBP-032: the semantic-disagreement diagnostic. Purely observational. */
/* ===================================================================== */

/* How many block reads of the IRQ window the mock performed. */
static unsigned irq_reads(const struct gbp_mock *m)
{
    uint32_t base = gbp_internal_size_from_arinfo(m->arinfo);
    return gbp_mock_count_block_ops(m, MOCK_RD, base, GBP_IDX_IRQ);
}

static void test_historical_deviation_does_not_disagree(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- the historical case: deviations on bytes NEITHER reading consumes stay agreeing\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 60u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    m.irq_byte0_anomaly = 1;                 /* byte 0 of every group carries extra bits */
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);              /* 220 such deviations are on record; none ever disagreed */
    CHECK(res.stop == GBP_VSTATE_STOP_DELIVERY_CAP);
    CHECK(vstate.diags_n == 0u);             /* nothing to diagnose */
    CHECK(vstate.sem.disagreements_total == 0u);
    check_invariants(&m, &res, &rl);
}

static void test_majority_is_exhaustively_the_rule(void)
{
    uint8_t w[GBP_BLOCK_SIZE];
    unsigned subset, bit, k, mismatches = 0, cases = 0;
    printf("-- the majority rule, exhaustively: all 256 replica subsets x 8 bit positions\n");
    for (bit = 0; bit < 8u; bit++) {
        for (subset = 0; subset < 256u; subset++) {
            unsigned popcount = 0, expect;
            uint16_t lo, hi;
            memset(w, 0, sizeof w);
            for (k = 0; k < 8u; k++) {
                if (subset & (1u << k)) {
                    w[4u * k + 3u] = (uint8_t)(1u << bit);   /* low byte of replica k */
                    w[4u * k + 1u] = (uint8_t)(1u << bit);   /* high byte of the same replica */
                    popcount++;
                }
            }
            expect = (popcount > 4u) ? (1u << bit) : 0u;
            lo = (uint16_t)(gbp_irq_value_gbi(w) & 0xFFu);
            hi = (uint16_t)((gbp_irq_value_gbi(w) >> 8) & 0xFFu);
            if (lo != expect || hi != expect) mismatches++;
            cases++;
        }
    }
    CHECK(mismatches == 0u);
    CHECK(cases == 2048u);
    printf("   %u cases, %u mismatches; a tie at four is never a majority\n", cases, mismatches);
}

/* Section 10: exactly one record is kept, and the attempt counter saturates instead of wrapping. */
/* ===================================================================== */
/* GBP-VIDEO-002-R3: the semantic-disagreement policy, every branch.      */
/* Every scenario here is SYNTHETIC. Nothing in this file is evidence     */
/* about the device.                                                     */
/* ===================================================================== */


static void put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }

/* A 32-byte window carrying `value` in all eight replicas, then the eighth
 * replica overridden with `last` - the physical shape of both observed events. */
static void window_split(uint8_t *w, uint16_t value, uint16_t last)
{
    unsigned k;
    for (k = 0; k < 8u; k++) {
        w[4 * k + 0] = (uint8_t)(value >> 8);
        w[4 * k + 1] = (uint8_t)(value >> 8);
        w[4 * k + 2] = (uint8_t)value;
        w[4 * k + 3] = (uint8_t)value;
    }
    w[0x1D] = (uint8_t)(last >> 8);
    w[0x1F] = (uint8_t)last;
}

/* The classification and the composition, on their own: pure functions, no run. */
static void test_classification_is_the_normative_one(void)
{
    printf("-- the three classes, on the masks the versioned contract defines\n");
    CHECK(gbp_vstate_classify(0x0500u, 0x0500u) == GBP_VSTATE_DIS_NONE);
    /* difference confined to the two serviced sources */
    CHECK(gbp_vstate_classify(0x0500u, 0x0100u) == GBP_VSTATE_DIS_SOURCE_SERVICED);
    CHECK(gbp_vstate_classify(0x0100u, 0x0500u) == GBP_VSTATE_DIS_SOURCE_SERVICED);
    CHECK(gbp_vstate_classify(0x0400u, 0x0100u) == GBP_VSTATE_DIS_SOURCE_SERVICED);
    /* a source slot with no drain in this probe */
    CHECK(gbp_vstate_classify(0x0104u, 0x0100u) == GBP_VSTATE_DIS_SOURCE_OTHER);
    CHECK(gbp_vstate_classify(0x0101u, 0x0100u) == GBP_VSTATE_DIS_SOURCE_OTHER);
    CHECK(gbp_vstate_classify(0x0110u, 0x0100u) == GBP_VSTATE_DIS_SOURCE_OTHER);
    CHECK(gbp_vstate_classify(0x0140u, 0x0100u) == GBP_VSTATE_DIS_SOURCE_OTHER);
    /* anything outside SRC_MASK wins over everything: odd, bit 15, high */
    CHECK(gbp_vstate_classify(0x0102u, 0x0100u) == GBP_VSTATE_DIS_NON_SOURCE);
    CHECK(gbp_vstate_classify(0x8100u, 0x0100u) == GBP_VSTATE_DIS_NON_SOURCE);
    CHECK(gbp_vstate_classify(0x1100u, 0x0100u) == GBP_VSTATE_DIS_NON_SOURCE);
    /* and a non-source difference is NON_SOURCE even when a source differs too */
    CHECK(gbp_vstate_classify(0x0502u, 0x0100u) == GBP_VSTATE_DIS_NON_SOURCE);

    printf("-- the authoritative value: majority for sources, the AGREED bits elsewhere\n");
    CHECK(gbp_vstate_authoritative(0x0500u, 0x0100u) == 0x0100u);
    CHECK(gbp_vstate_authoritative(0x0100u, 0x0500u) == 0x0500u);
    /* the non-source bits are identical in both readings by the time this runs,
     * so taking them is taking the agreed value, not a vote */
    CHECK(gbp_vstate_authoritative(0x8500u, 0x8100u) == 0x8100u);
    CHECK(gbp_vstate_authoritative(0x0AAA | 0x0500u, 0x0AAA | 0x0100u) == (0x0AAAu | 0x0100u));
    {   /* exhaustive over the source bits: the composition never invents a bit */
        unsigned a, b, bad = 0;
        for (a = 0; a < 64u; a++) for (b = 0; b < 64u; b++) {
            uint16_t da = 0, gb = 0; unsigned k;
            for (k = 0; k < 6u; k++) {
                if (a & (1u << k)) da |= (uint16_t)(1u << (2u * k));
                if (b & (1u << k)) gb |= (uint16_t)(1u << (2u * k));
            }
            if (gbp_vstate_authoritative(da, gb) != gb) bad++;
        }
        CHECK(bad == 0u);
    }
}

/* Section R3.6 step 5: the pending guard is INDEPENDENT of the delta. */
static void test_unexpected_source_guard_is_independent(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- an agreed source with no drain is still fatal: Disc = GBI = 0x0104\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 400u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    m.irq_extra_source_from_write = 40u;          /* both readings carry 0x0004 */
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 0);
    CHECK(res.status == GBP_VSTATE_ANOMALY_UNEXPECTED_SOURCE);
    CHECK(strstr(res.reason, "unexpected_source") != 0);
    /* delta was zero, so nothing was classified as a disagreement at all - and
     * §34: the abort therefore preserves NO record, which is the documented
     * consequence of the normative order of §R3.6 and not an accident */
    CHECK(vstate.sem.disagreements_total == 0u);
    CHECK(vstate.diags_n == 0u);
    CHECK(vstate.sem.diagnostics_preserved == 0u && vstate.sem.diagnostics_not_preserved == 0u);
    CHECK(vstate.diag_wait == -1);
    CHECK(res.unexpected == 0x0004u);
    printf("   reason=%s unexpected=%04x disagreements=%lu\n", res.reason, res.unexpected,
           (unsigned long)vstate.sem.disagreements_total);
}

/* The two fatal classes, through a whole run. */
static void test_fatal_classes(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    unsigned i;
    static const struct { const char *name; uint16_t xor_last; unsigned cls; const char *frag; } cases[] = {
        { "source_other 0x0004", 0x0004u, GBP_VSTATE_DIS_SOURCE_OTHER, "source_other" },
        { "non_source odd",      0x0002u, GBP_VSTATE_DIS_NON_SOURCE,   "non_source" },
        { "non_source bit15",    0x8000u, GBP_VSTATE_DIS_NON_SOURCE,   "non_source" },
        { "non_source high",     0x1000u, GBP_VSTATE_DIS_NON_SOURCE,   "non_source" },
    };
    printf("-- SOURCE_OTHER and NON_SOURCE stay fatal, and the reason names the class\n");
    for (i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        cfg_default(&cfg);
        cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
        cfg.max_deliveries = 400u;
        sched_reset(0xFFu);
        mock_vstate(&m, bits, 1u, 50u);
        m.irq_last_replica_xor = cases[i].xor_last;
        m.irq_last_replica_from_write = 40u;
        run_cfg(&m, &rl, &res, &cfg);
        CHECK(res.service_ok == 0);
        CHECK(res.status == GBP_VSTATE_ABORT_READ_INCONSISTENT);
        CHECK(strstr(res.reason, cases[i].frag) != 0);
        CHECK(res.semantic_failed == 1);
        CHECK(vstate.sem.disagreements_total == 1u);
        CHECK(vstate.diags_n == 1u);
        CHECK(vstate.diags[0].classification == cases[i].cls);
        /* a fatal record never claims an ACK it did not write */
        CHECK((vstate.diags[0].record_flags & GBP_VSTATE_DF_ACK_WRITTEN) == 0u);
        CHECK(vstate.diags[0].ack_value == 0u);
        printf("   %-22s -> %s (class %s)\n", cases[i].name, res.reason,
               gbp_vstate_class_name(vstate.diags[0].classification));
    }
}

/* The survivable class, in both directions. */
static void test_source_serviced_is_nonfatal(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- Disc extra AUDIO: VIDEO serviced, ACK 0x8100, the run CONTINUES\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 200u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    /* from write 40 on, the pending is 0x0100 but the LAST replica says 0x0500 */
    m.irq_force_value_from_write = 40u;
    m.irq_forced_value = 0x0100u;
    m.irq_last_replica_xor = 0x0400u;
    m.irq_last_replica_from_write = 40u;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);                       /* NOT a service failure */
    CHECK(res.stop == GBP_VSTATE_STOP_DELIVERY_CAP);
    CHECK(res.semantic_failed == 0);
    CHECK(vstate.sem.disagreements_total > 0u);
    CHECK(vstate.sem.source_serviced == vstate.sem.disagreements_total);
    CHECK(vstate.sem.source_other == 0u && vstate.sem.non_source == 0u);
    CHECK(vstate.sem.disc_extra_events > 0u);
    CHECK(vstate.sem.majority_extra_events == 0u);
    CHECK(vstate.diags_n > 0u);
    CHECK(vstate.diags[0].classification == GBP_VSTATE_DIS_SOURCE_SERVICED);
    CHECK(vstate.diags[0].disc_extra_sources == 0x0400u);
    CHECK(vstate.diags[0].majority_extra_sources == 0u);
    CHECK(vstate.diags[0].authoritative_value == 0x0100u);
    CHECK(vstate.diags[0].ack_value == 0x8100u);       /* the AUDIO bit is NOT written as 1 */
    CHECK(vstate.diags[0].service_selected == 0x0100u);
    CHECK((vstate.diags[0].record_flags & GBP_VSTATE_DF_ACK_WRITTEN) != 0u);
    CHECK((vstate.diags[0].record_flags & GBP_VSTATE_DF_REARM_WRITTEN) != 0u);
    printf("   %lu disagreements, run reached stop=%s, ack=%04x svc=%04x\n",
           (unsigned long)vstate.sem.disagreements_total, res.stop_name,
           vstate.diags[0].ack_value, vstate.diags[0].service_selected);
    check_invariants(&m, &res, &rl);
}

/* The direction never observed on hardware: the majority carries a source the
 * Disc reading does not. Service happens, and the VIDEO it produced is
 * quarantined out of every scientific use. */
static void test_majority_extra_video_is_quarantined(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    uint32_t i, quarantined = 0, counted_q = 0, baseline_q = 0;
    printf("-- majority extra VIDEO: served, flagged, and kept out of the science\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 300u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    m.irq_force_value_from_write = 40u;
    m.irq_forced_value = 0x0500u;      /* the majority says both */
    m.irq_last_replica_xor = 0x0100u;  /* the last replica drops VIDEO */
    m.irq_last_replica_from_write = 40u;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(vstate.sem.majority_extra_events > 0u);
    CHECK(vstate.sem.disc_extra_events == 0u);
    CHECK(vstate.sem.majority_extra_video_services > 0u);
    CHECK(vstate.sem.frames_quarantined > 0u);
    CHECK(res.video_completed > 0u);                    /* the service really happened */
    for (i = 0; i < vstate.frames_n; i++) {
        if (vstate.frames[i].flags & GBP_VSTATE_F_MAJORITY_EXTRA) {
            quarantined++;
            CHECK((vstate.frames[i].flags & GBP_VSTATE_F_ANOMALY) != 0u);
            if (vstate.frames[i].flags & GBP_VSTATE_F_COUNTED) counted_q++;
            if (vstate.frames[i].flags & GBP_VSTATE_F_BASELINE) baseline_q++;
        }
    }
    CHECK(quarantined > 0u);
    CHECK(counted_q == 0u);                             /* never counted */
    CHECK(baseline_q == 0u);                            /* never a baseline */
    CHECK(vstate.episode_count == 0u);                  /* never structural evidence */
    /* the payload diagnostic of the block that only the majority asked for */
    CHECK((vstate.diags[0].record_flags & GBP_VSTATE_DF_PAYLOAD_VALID) != 0u);
    CHECK(vstate.diags[0].payload_source == GBP_VSTATE_SRC_VIDEO);
    CHECK((vstate.diags[0].record_flags & GBP_VSTATE_DF_FRAME_QUARANTINED) != 0u);
    printf("   %lu frames quarantined, %lu counted, %lu baseline; payload src=%04x crc=%08lx\n",
           (unsigned long)quarantined, (unsigned long)counted_q, (unsigned long)baseline_q,
           vstate.diags[0].payload_source, (unsigned long)vstate.diags[0].payload_crc32);
}

/* The mirror: the majority omits VIDEO. Nothing is drained and nothing is faked. */
static void test_disc_extra_video_fabricates_nothing(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    uint32_t before_video, deferred = 0, i;
    printf("-- Disc extra VIDEO: no drain, no fabricated block, only a marker\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 200u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    m.irq_force_value_from_write = 40u;
    m.irq_forced_value = 0x0400u;      /* majority: AUDIO only */
    m.irq_last_replica_xor = 0x0100u;  /* the last replica also claims VIDEO */
    m.irq_last_replica_from_write = 40u;
    before_video = m.bulk_reads;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(vstate.sem.disc_extra_events > 0u);
    CHECK(vstate.diags[0].disc_extra_sources == 0x0100u);
    CHECK(vstate.diags[0].service_selected == 0x0400u);   /* VIDEO was NOT selected */
    CHECK(vstate.diags[0].ack_value == 0x8400u);
    CHECK(vstate.sem.frames_quarantined == 0u);
    for (i = 0; i < vstate.frames_n; i++)
        if (vstate.frames[i].flags & GBP_VSTATE_F_SOURCE_DEFERRED) deferred++;
    /* the marker exists only where a frame was open; it is never invented */
    CHECK(deferred + (vstate.cur_flags & GBP_VSTATE_F_SOURCE_DEFERRED ? 1u : 0u) ==
          vstate.sem.frames_source_deferred ||
          vstate.sem.frames_source_deferred >= deferred);
    CHECK(m.bulk_reads > before_video);
    printf("   %lu deferred markers, %lu quarantined, svc=%04x\n",
           (unsigned long)vstate.sem.frames_source_deferred, (unsigned long)vstate.sem.frames_quarantined,
           vstate.diags[0].service_selected);
}

/* The follow-up lifecycle, including three consecutive disagreements. */
static void test_followup_lifecycle(void)
{
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_diag store2[8];
    uint8_t w[GBP_BLOCK_SIZE];
    int a, b, c;
    printf("-- one read closes the previous record and opens the next, never the wrong one\n");
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 8u);

    window_split(w, 0x0100u, 0x0500u);
    a = gbp_vstate_diag_open(&st2, 10u, 1000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                             GBP_VSTATE_DIS_SOURCE_SERVICED);
    CHECK(a == 0);
    CHECK(st2.diags[0].followup_state == GBP_VSTATE_FU_PENDING);
    /* §R4.6: opening does NOT arm the waiter. Until the re-arm is written, no
     * next cause has been invited and nothing may claim one is expected. */
    CHECK(st2.diag_wait == -1);
    CHECK(gbp_vstate_diag_arm_followup(&st2, a) == 0);      /* no re-arm yet: refused */
    CHECK(st2.diag_wait == -1);
    gbp_vstate_diag_service(&st2, a, 0x0100u, 0x0100u, 0u);
    gbp_vstate_diag_ack(&st2, a, 0x8100u, 1100u);
    gbp_vstate_diag_rearm(&st2, a, 1200u);
    CHECK(gbp_vstate_diag_arm_followup(&st2, a) == 1);
    CHECK(st2.diag_wait == 0);

    /* cycle 11 also disagrees: FIRST close 10, THEN open 11 */
    CHECK(gbp_vstate_diag_followup(&st2, 2000u, 0x0400u, 0x0400u) == 1);
    CHECK(st2.diags[0].followup_state == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT);
    CHECK(st2.diags[0].t_next_cause == 2000u);
    CHECK((st2.diags[0].record_flags & GBP_VSTATE_DF_FOLLOWUP_FILLED) != 0u);
    CHECK(st2.diag_wait == -1);                            /* filled, and cleared */
    b = gbp_vstate_diag_open(&st2, 11u, 2000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                             GBP_VSTATE_DIS_SOURCE_SERVICED);
    CHECK(b == 1);
    gbp_vstate_diag_service(&st2, b, 0x0100u, 0x0100u, 0u);
    gbp_vstate_diag_ack(&st2, b, 0x8100u, 2100u);
    gbp_vstate_diag_rearm(&st2, b, 2200u);
    CHECK(gbp_vstate_diag_arm_followup(&st2, b) == 1);
    CHECK(st2.diag_wait == 1);
    CHECK(st2.diags[0].followup_state == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT);  /* untouched */
    /* and record 0 keeps the ACK of ITS OWN cycle, not record 1's */
    CHECK(st2.diags[0].t_ack == 1100u && st2.diags[0].t_rearm == 1200u);

    /* cycle 12: close 11 with the source ABSENT, then open 12 */
    CHECK(gbp_vstate_diag_followup(&st2, 3000u, 0x0100u, 0x0100u) == 1);
    CHECK(st2.diags[1].followup_state == GBP_VSTATE_FU_SOURCE_ABSENT_NEXT);
    c = gbp_vstate_diag_open(&st2, 12u, 3000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                             GBP_VSTATE_DIS_SOURCE_SERVICED);
    CHECK(c == 2);
    gbp_vstate_diag_service(&st2, c, 0x0100u, 0x0100u, 0u);
    gbp_vstate_diag_ack(&st2, c, 0x8100u, 3100u);
    gbp_vstate_diag_rearm(&st2, c, 3200u);
    CHECK(gbp_vstate_diag_arm_followup(&st2, c) == 1);
    /* the run ends here: the last record must not stay pending */
    gbp_vstate_diag_close(&st2, 0u);
    CHECK(st2.diags[2].followup_state == GBP_VSTATE_FU_NO_NEXT_CAUSE);
    CHECK(st2.diag_wait == -1);
    CHECK(st2.diags[0].cycle == 10u && st2.diags[1].cycle == 11u && st2.diags[2].cycle == 12u);
    CHECK(st2.sem.followup_present == 1u && st2.sem.followup_absent == 1u && st2.sem.followup_no_next == 1u);

    printf("-- an observational site carries no service narrative\n");
    {
        int o = gbp_vstate_diag_open(&st2, 13u, 4000u, w, 0x0500u, 0x0100u,
                                     GBP_VSTATE_DIAG_READ_POSTACK, GBP_VSTATE_DIS_SOURCE_SERVICED);
        CHECK(o == 3);
        CHECK(st2.diags[3].followup_state == GBP_VSTATE_FU_UNKNOWN);
        CHECK(st2.diags[3].followup_reason == GBP_VSTATE_FUR_OBSERVATIONAL);
        CHECK(st2.diag_wait == -1);                      /* never waits */
        CHECK(st2.sem.observational_disagreements == 1u);
    }
    printf("-- §38: a cycle whose ONLY disagreement is observational arms nothing\n");
    {
        /* A is armed and waiting; the next cycle's ordinary read closes it, and
         * the observational disagreement that cycle also produces must neither
         * take A's place nor become a waiter of its own. */
        gbp_vstate_diag_handle a2, obs;
        a2 = gbp_vstate_diag_open(&st2, 20u, 6000u, w, 0x0500u, 0x0100u,
                                  GBP_VSTATE_DIAG_READ_LEAN, GBP_VSTATE_DIS_SOURCE_SERVICED);
        CHECK(a2 == 4);
        gbp_vstate_diag_service(&st2, a2, 0x0100u, 0x0100u, 0u);
        gbp_vstate_diag_ack(&st2, a2, 0x8100u, 6100u);
        gbp_vstate_diag_rearm(&st2, a2, 6200u);
        CHECK(gbp_vstate_diag_arm_followup(&st2, a2) == 1);
        CHECK(st2.diag_wait == 4);
        /* the next cycle: the read closes A first (§R3.8) */
        CHECK(gbp_vstate_diag_followup(&st2, 7000u, 0x0400u, 0x0400u) == 1);
        CHECK(st2.diag_wait == -1);
        CHECK(st2.diags[4].followup_state == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT);
        /* and only a POSTACK read of that cycle disagrees */
        obs = gbp_vstate_diag_open(&st2, 21u, 7100u, w, 0x0500u, 0x0100u,
                                   GBP_VSTATE_DIAG_READ_POSTACK, GBP_VSTATE_DIS_SOURCE_SERVICED);
        CHECK(obs == 5);
        CHECK(st2.diag_wait == -1);                       /* B never waits */
        CHECK(st2.diags[5].followup_state == GBP_VSTATE_FU_UNKNOWN);
        CHECK(st2.diags[5].followup_reason == GBP_VSTATE_FUR_OBSERVATIONAL);
        CHECK(gbp_vstate_diag_arm_followup(&st2, obs) == 0);   /* and cannot be armed */
        CHECK(st2.diag_wait == -1);
        /* A is untouched by any of it */
        CHECK(st2.diags[4].t_ack == 6100u && st2.diags[4].t_rearm == 6200u);
        CHECK(st2.diags[4].t_next_cause == 7000u);
    }
    printf("-- a run that aborts BEFORE its re-arm still closes the record\n");
    {
        /* This record never becomes the waiter - its transaction ended before the
         * re-arm - so only the teardown SWEEP can close it. FU_PENDING may not
         * reach a file by any path (§R3.14). */
        int r = gbp_vstate_diag_open(&st2, 14u, 5000u, w, 0x0500u, 0x0100u,
                                     GBP_VSTATE_DIAG_READ_LEAN, GBP_VSTATE_DIS_SOURCE_SERVICED);
        CHECK(r == 6);
        CHECK(st2.diags_n == 7u);
        CHECK(st2.diag_wait == -1);
        CHECK(st2.diags[6].followup_state == GBP_VSTATE_FU_PENDING);
        gbp_vstate_diag_close(&st2, 1u);
        CHECK(st2.diags[6].followup_state == GBP_VSTATE_FU_UNKNOWN);
        CHECK(st2.diags[6].followup_reason == GBP_VSTATE_FUR_RUN_ABORTED);
        CHECK((st2.diags[6].record_flags & GBP_VSTATE_DF_REARM_WRITTEN) == 0u);
    }
    printf("   7 records, states: %s %s %s %s %s %s %s\n",
           gbp_vstate_fu_name(st2.diags[0].followup_state), gbp_vstate_fu_name(st2.diags[1].followup_state),
           gbp_vstate_fu_name(st2.diags[2].followup_state), gbp_vstate_fu_name(st2.diags[3].followup_state),
           gbp_vstate_fu_name(st2.diags[4].followup_state), gbp_vstate_fu_name(st2.diags[5].followup_state),
           gbp_vstate_fu_name(st2.diags[6].followup_state));
}

/* The bounded store, its cap, and the record still waiting when it fills. */
static void test_store_is_bounded_and_the_last_record_still_closes(void)
{
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_diag store2[4];
    uint8_t w[GBP_BLOCK_SIZE];
    unsigned i;
    printf("-- the store caps without overwriting, and the run does not stop for it\n");
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 4u);
    window_split(w, 0x0100u, 0x0500u);
    for (i = 0; i < 4u; i++) {
        gbp_vstate_diag_handle h = gbp_vstate_diag_open(&st2, i, 100u + i, w, 0x0500u, 0x0100u,
                                                        GBP_VSTATE_DIAG_READ_LEAN,
                                                        GBP_VSTATE_DIS_SOURCE_SERVICED);
        CHECK(h == (gbp_vstate_diag_handle)i);
        gbp_vstate_diag_service(&st2, h, 0x0100u, 0x0100u, 0u);
        gbp_vstate_diag_ack(&st2, h, 0x8100u, 110u + i);
        gbp_vstate_diag_rearm(&st2, h, 120u + i);
        CHECK(gbp_vstate_diag_arm_followup(&st2, h) == 1);
        if (i + 1u < 4u) CHECK(gbp_vstate_diag_followup(&st2, 200u + i, 0x0400u, 0x0400u) == 1);
    }
    CHECK(st2.diags_n == 4u);
    CHECK(st2.diag_wait == 3);                       /* the last one is still waiting */
    CHECK(st2.sem.store_capped == 0u);
    /* the fifth and sixth are counted, never stored, and never overwrite. Every
     * current-cycle setter is then called with the INVALID handle they returned:
     * §R4.5 / §40 - not one byte of the store may move. */
    for (i = 4u; i < 6u; i++) {
        struct gbp_vstate_diag before[4];
        gbp_vstate_diag_handle h;
        memcpy(before, store2, sizeof before);
        h = gbp_vstate_diag_open(&st2, i, 100u + i, w, 0x0500u, 0x0100u,
                                 GBP_VSTATE_DIAG_READ_LEAN, GBP_VSTATE_DIS_SOURCE_SERVICED);
        CHECK(h == GBP_VSTATE_DIAG_INVALID);
        CHECK(gbp_vstate_diag_handle_valid(&st2, h) == 0);
        CHECK(gbp_vstate_diag_at(&st2, h) == 0);
        gbp_vstate_diag_context(&st2, h, 0xAAAAAAAAu, 0xBBBBBBBBu, 0xCCCCCCCCu, 0xDDDDDDDDu,
                                0xEEEEu, 0);
        gbp_vstate_diag_service(&st2, h, 0x0100u, 0x0100u, 0u);
        gbp_vstate_diag_service_incomplete(&st2, h);
        gbp_vstate_diag_payload(&st2, h, GBP_VSTATE_SRC_VIDEO, 0xAAAAu, 0xBBBBu);
        gbp_vstate_diag_ack(&st2, h, 0x8100u, 777u);
        gbp_vstate_diag_rearm(&st2, h, 888u);
        gbp_vstate_diag_quarantined(&st2, h);
        gbp_vstate_diag_deferred(&st2, h);
        CHECK(gbp_vstate_diag_arm_followup(&st2, h) == 0);
        CHECK(memcmp(before, store2, sizeof before) == 0);   /* byte for byte */
    }
    CHECK(st2.diags_n == 4u);
    CHECK(st2.sem.store_capped == 1u);
    CHECK(st2.sem.diagnostics_not_preserved == 2u);
    CHECK(st2.sem.diagnostics_preserved == 4u);
    CHECK(st2.sem.disagreements_total == 6u);
    CHECK(st2.diags[0].cycle == 0u && st2.diags[3].cycle == 3u);   /* nothing moved */
    /* and the record that was waiting when the store filled STILL gets closed */
    CHECK(st2.diag_wait == 3);
    CHECK(gbp_vstate_diag_followup(&st2, 9999u, 0x0400u, 0x0400u) == 1);
    CHECK(st2.diags[3].followup_state == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT);
    CHECK(st2.diags[3].t_next_cause == 9999u);
    printf("   4 preserved, %lu not preserved, capped=%lu, last record closed after the cap\n",
           (unsigned long)st2.sem.diagnostics_not_preserved, (unsigned long)st2.sem.store_capped);
}

/* The histogram index, exhaustively over all 64 combinations. */
static void test_histogram_index_is_exhaustive(void)
{
    unsigned i, bad = 0;
    printf("-- the six source bits compressed to six index bits, all 64 combinations\n");
    for (i = 0; i < 64u; i++) {
        uint16_t v = 0;
        unsigned k;
        for (k = 0; k < 6u; k++) if (i & (1u << k)) v |= (uint16_t)(1u << (2u * k));
        if (gbp_vstate_hist_index(v) != i) bad++;
    }
    CHECK(bad == 0u);
    CHECK(gbp_vstate_hist_index(0x0000u) == 0u);
    CHECK(gbp_vstate_hist_index(0x0001u) == 1u);
    CHECK(gbp_vstate_hist_index(0x0004u) == 2u);
    CHECK(gbp_vstate_hist_index(0x0010u) == 4u);
    CHECK(gbp_vstate_hist_index(0x0040u) == 8u);
    CHECK(gbp_vstate_hist_index(0x0100u) == 16u);
    CHECK(gbp_vstate_hist_index(0x0400u) == 32u);
    CHECK(gbp_vstate_hist_index(0x0500u) == 48u);
    /* bits outside SRC_MASK are ignored, never folded in */
    CHECK(gbp_vstate_hist_index(0xFFFFu) == 63u);
    printf("   64 of 64 exact, and the pinned examples match the design\n");
}

/* Gap statistics: what they measure, and what they refuse to be. */
static void test_gap_statistics(void)
{
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_diag store2[4];
    uint8_t w[GBP_BLOCK_SIZE];
    printf("-- cause -> cause, per source; the first occurrence produces no gap\n");
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 4u);
    CHECK(st2.sem.gap[5].count == 0u);
    CHECK(st2.sem.gap[5].min_ticks == GBP_VSTATE_GAP_NONE);
    gbp_vstate_gap_observe(&st2, 0x0400u, 1000u);
    CHECK(st2.sem.gap[5].count == 0u);                 /* one cause, no gap */
    CHECK(st2.sem.gap[5].min_ticks == GBP_VSTATE_GAP_NONE);
    gbp_vstate_gap_observe(&st2, 0x0400u, 1300u);
    CHECK(st2.sem.gap[5].count == 1u && st2.sem.gap[5].min_ticks == 300u && st2.sem.gap[5].max_ticks == 300u);
    gbp_vstate_gap_observe(&st2, 0x0400u, 1450u);
    CHECK(st2.sem.gap[5].count == 2u && st2.sem.gap[5].min_ticks == 150u && st2.sem.gap[5].max_ticks == 300u);
    CHECK(st2.sem.gap[5].last_ticks == 150u);
    /* a different source keeps its own statistic */
    CHECK(st2.sem.gap[4].count == 0u);
    gbp_vstate_gap_observe(&st2, 0x0100u, 2000u);
    gbp_vstate_gap_observe(&st2, 0x0100u, 2999u);
    CHECK(st2.sem.gap[4].count == 1u && st2.sem.gap[4].min_ticks == 999u);
    /* saturation instead of a silent wrap */
    gbp_vstate_gap_observe(&st2, 0x0010u, 1u);
    gbp_vstate_gap_observe(&st2, 0x0010u, 0x100000000ull);
    CHECK(st2.sem.gap[2].last_ticks == GBP_VSTATE_GAP_SAT);

    printf("-- the per-record snapshot is the OMITTED source's statistic, as it stood BEFORE\n");
    window_split(w, 0x0100u, 0x0500u);
    CHECK(gbp_vstate_diag_open(&st2, 1u, 5000u, w, 0x0500u, 0x0100u,
                               GBP_VSTATE_DIAG_READ_LEAN, GBP_VSTATE_DIS_SOURCE_SERVICED) == 0);
    CHECK(st2.diags[0].gap_min_before_ticks == 150u);   /* AUDIO's minimum so far */
    CHECK(st2.diags[0].gap_count_before == 2u);
    {   /* a source with no statistic yet uses the sentinel, never 0 */
        struct gbp_vstate st3;
        static struct gbp_vstate_diag store3[2];
        gbp_vstate_init(&st3, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                        raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
        gbp_vstate_diag_store(&st3, store3, 2u);
        CHECK(gbp_vstate_diag_open(&st3, 1u, 1u, w, 0x0500u, 0x0100u,
                                   GBP_VSTATE_DIAG_READ_LEAN, GBP_VSTATE_DIS_SOURCE_SERVICED) == 0);
        CHECK(store3[0].gap_min_before_ticks == GBP_VSTATE_GAP_NONE);
        CHECK(store3[0].gap_count_before == 0u);
    }
    printf("   AUDIO n=%lu min=%lu max=%lu; VIDEO n=%lu min=%lu; saturation ok\n",
           (unsigned long)st2.sem.gap[5].count, (unsigned long)st2.sem.gap[5].min_ticks,
           (unsigned long)st2.sem.gap[5].max_ticks, (unsigned long)st2.sem.gap[4].count,
           (unsigned long)st2.sem.gap[4].min_ticks);
}

/* The 32 bytes, and the whole record, survive RAM -> serializer -> parser.
 * The file carries TWO records, because v5 has two record shapes and they must
 * coexist in one file: an OBSERVATIONAL one whose 32 bytes are all distinct (a
 * byte swap anywhere would change a reading), and a SERVICE-SELECTING one with
 * the full narrative - service, ACK, re-arm, payload and a filled follow-up. */
static void test_v5_record_round_trip(void)
{
    static uint8_t file[1u << 20];
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_result r2;
    static struct gbp_vstate_diag store2[4];
    struct gbp_vstate_config c2;
    struct gbp_vstatedump_info info, parsed;
    struct gbp_vstate_diag back;
    struct gbp_vstate_semantic sem;
    struct memsink sink;
    const uint8_t *dg = 0, *sb = 0;
    uint8_t pattern[GBP_BLOCK_SIZE];
    unsigned i, j;
    long n;
    printf("-- 32 distinct bytes and every v4 field survive the round trip, in order\n");
    for (i = 0; i < GBP_BLOCK_SIZE; i++) pattern[i] = (uint8_t)(0x11u + i * 7u);
    for (i = 0; i < GBP_BLOCK_SIZE; i++)
        for (j = i + 1u; j < GBP_BLOCK_SIZE; j++) CHECK(pattern[i] != pattern[j]);
    memset(&r2, 0, sizeof r2);
    cfg_default(&c2);
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 4u);
    gbp_vstate_gap_observe(&st2, 0x0400u, 100u);
    gbp_vstate_gap_observe(&st2, 0x0400u, 700u);
    /* Record 0: observational, 32 distinct bytes. Its classification is the one
     * the bytes THEMSELVES produce - v5 recomputes it and a hardcoded value
     * would simply be refused. It claims nothing about service. */
    CHECK(gbp_vstate_diag_open(&st2, 4242u, 0x00000001FFFFFFFFULL, pattern,
                               gbp_irq_value_disc(pattern), gbp_irq_value_gbi(pattern),
                               GBP_VSTATE_DIAG_READ_POSTDRAIN,
                               gbp_vstate_classify(gbp_irq_value_disc(pattern),
                                                   gbp_irq_value_gbi(pattern))) == 0);
    /* Record 1: the MAJORITY-extra direction - the majority carries AUDIO the
     * Disc reading does not - so the AUDIO block it drained exists only because
     * of the majority and carries a payload diagnostic. */
    {
        uint8_t w2[GBP_BLOCK_SIZE];
        gbp_vstate_diag_handle h;
        window_split(w2, 0x0500u, 0x0100u);           /* seven 0x0500, last 0x0100 */
        h = gbp_vstate_diag_open(&st2, 4243u, 0x1122334455667700ULL, w2, 0x0100u, 0x0500u,
                                 GBP_VSTATE_DIAG_READ_PRESVC, GBP_VSTATE_DIS_SOURCE_SERVICED);
        CHECK(h == 1);
        gbp_vstate_diag_service(&st2, h, 0x0500u, 0x0500u, 0u);
        gbp_vstate_diag_payload(&st2, h, GBP_VSTATE_SRC_AUDIO, 0xDEADBEEFu, 0xCAFEBABEu);
        gbp_vstate_diag_ack(&st2, h, 0x8500u, 0x1122334455667788ULL);
        gbp_vstate_diag_rearm(&st2, h, 0x1122334455667799ULL);
        /* the majority omitted nothing, so there is nothing to look for next */
        CHECK(gbp_vstate_diag_arm_followup(&st2, h) == 0);
    }
    /* Record 2: the DISC-extra direction - the physical one - with the whole
     * follow-up narrative: the omitted AUDIO returned in the next read. */
    {
        uint8_t w3[GBP_BLOCK_SIZE];
        gbp_vstate_diag_handle h;
        window_split(w3, 0x0100u, 0x0500u);           /* seven 0x0100, last 0x0500 */
        h = gbp_vstate_diag_open(&st2, 4244u, 0x1122334455668800ULL, w3, 0x0500u, 0x0100u,
                                 GBP_VSTATE_DIAG_READ_LEAN, GBP_VSTATE_DIS_SOURCE_SERVICED);
        CHECK(h == 2);
        gbp_vstate_diag_service(&st2, h, 0x0100u, 0x0100u, 0u);
        gbp_vstate_diag_ack(&st2, h, 0x8100u, 0x1122334455668888ULL);
        gbp_vstate_diag_rearm(&st2, h, 0x1122334455668899ULL);
        CHECK(gbp_vstate_diag_arm_followup(&st2, h) == 1);
        CHECK(gbp_vstate_diag_followup(&st2, 0x11223344556688AAULL, 0x0400u, 0x0400u) == 1);
    }
    gbp_vstate_diag_close(&st2, 0u);

    memset(&info, 0, sizeof info);
    CHECK(gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "synthetic") == 0);
    sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    n = gbp_vstatedump_stream(&info, &st2, &r2, &c2, chunk, sizeof chunk, sink_mem, &sink, 0);
    CHECK(n > 0);
    CHECK(info.version == 5u);                        /* what this build WRITES */
    CHECK(info.diag_rec_size == GBP_VSTATEDUMP_DIAG_REC_V5);
    CHECK(GBP_VSTATEDUMP_DIAG_REC_V5 == GBP_VSTATEDUMP_DIAG_REC_V4);   /* same layout */
    CHECK(info.diag_count == 3u);
    CHECK(info.semantic_size == GBP_VSTATEDUMP_SEMANTIC_SIZE);
    CHECK(info.off_semantic == info.off_cycles + info.cycle_count * GBP_VSTATEDUMP_CYCLE_REC);
    CHECK(info.off_diag == info.off_semantic + GBP_VSTATEDUMP_SEMANTIC_SIZE);
    CHECK(info.off_video_raw == info.off_diag + 3u * GBP_VSTATEDUMP_DIAG_REC_V5);

    /* Every entry point judges the file by ITS OWN version: the v4-era name and
     * the v5 name give the same verdict on the same bytes, and both apply the v5
     * rules because the file says v5. */
    CHECK(gbp_vstatedump_parse_v4(file, (size_t)n, 0, 0, 0, 0, 0, 0, 0, 0, 0) == 0);
    CHECK(gbp_vstatedump_parse_v5(file, (size_t)n, &parsed, 0, 0, 0, 0, &sb, &dg, 0, 0) == 0);
    CHECK(parsed.version == 5u);
    CHECK(dg != 0 && sb != 0);
    CHECK(gbp_vstatedump_decode_diag_v4(dg, &back) == 1);
    for (i = 0; i < GBP_BLOCK_SIZE; i++) CHECK(back.raw[i] == pattern[i]);
    CHECK(memcmp(dg + 0x18, pattern, GBP_BLOCK_SIZE) == 0);       /* verbatim ON THE WIRE */
    CHECK(back.t == 0x00000001FFFFFFFFULL);
    CHECK(back.cycle == 4242u);
    CHECK(back.read_kind == GBP_VSTATE_DIAG_READ_POSTDRAIN);
    CHECK(back.classification == gbp_vstate_classify(back.disc_value, back.gbi_value));
    CHECK(back.delta == (uint16_t)(back.disc_value ^ back.gbi_value));
    CHECK(back.authoritative_value == gbp_vstate_authoritative(back.disc_value, back.gbi_value));
    /* the observational contract, on the wire */
    CHECK(back.service_selected == 0u && back.ack_value == 0u);
    CHECK(back.t_ack == 0u && back.t_rearm == 0u && back.t_next_cause == 0u);
    CHECK((back.record_flags & (GBP_VSTATE_DF_SERVICE_WRITTEN | GBP_VSTATE_DF_ACK_WRITTEN |
                                GBP_VSTATE_DF_REARM_WRITTEN | GBP_VSTATE_DF_PAYLOAD_VALID)) == 0u);
    CHECK(back.followup_state == GBP_VSTATE_FU_UNKNOWN);
    CHECK(back.followup_reason == GBP_VSTATE_FUR_OBSERVATIONAL);
    CHECK(back.reserved1 == 0u);
    /* record 1: the majority-extra direction, with the payload it justifies */
    CHECK(gbp_vstatedump_decode_diag_v4(dg + GBP_VSTATEDUMP_DIAG_REC_V5, &back) == 1);
    CHECK(back.cycle == 4243u);
    CHECK(back.read_kind == GBP_VSTATE_DIAG_READ_PRESVC);
    CHECK(back.disc_value == 0x0100u && back.gbi_value == 0x0500u);
    CHECK(back.majority_extra_sources == GBP_VSTATE_SRC_AUDIO);
    CHECK(back.authoritative_value == 0x0500u);
    CHECK(back.service_selected == 0x0500u);
    CHECK((back.record_flags & GBP_VSTATE_DF_SERVICE_WRITTEN) != 0u);
    CHECK(back.ack_value == 0x8500u && back.t_ack == 0x1122334455667788ULL);
    CHECK(back.t_rearm == 0x1122334455667799ULL);
    CHECK(back.payload_source == GBP_VSTATE_SRC_AUDIO);
    CHECK(back.payload_crc32 == 0xDEADBEEFu && back.payload_first_word == 0xCAFEBABEu);
    CHECK((back.record_flags & GBP_VSTATE_DF_PAYLOAD_VALID) != 0u);
    CHECK((back.record_flags & GBP_VSTATE_DF_ACK_WRITTEN) != 0u);
    CHECK((back.record_flags & GBP_VSTATE_DF_REARM_WRITTEN) != 0u);
    /* nothing was omitted, so there is no follow-up narrative and the next
     * fields stay at their invalid encoding */
    CHECK(back.followup_state == GBP_VSTATE_FU_UNKNOWN);
    CHECK(back.followup_reason == GBP_VSTATE_FUR_NOT_APPLICABLE);
    CHECK(back.t_next_cause == 0u && back.next_pending_gbi == 0u);
    /* record 2: the physical direction, with the follow-up filled */
    CHECK(gbp_vstatedump_decode_diag_v4(dg + 2u * GBP_VSTATEDUMP_DIAG_REC_V5, &back) == 1);
    CHECK(back.cycle == 4244u);
    CHECK(back.read_kind == GBP_VSTATE_DIAG_READ_LEAN);
    CHECK(back.disc_value == 0x0500u && back.gbi_value == 0x0100u);
    CHECK(back.disc_extra_sources == GBP_VSTATE_SRC_AUDIO);
    CHECK(back.authoritative_value == 0x0100u && back.service_selected == 0x0100u);
    CHECK(back.ack_value == 0x8100u && back.t_ack == 0x1122334455668888ULL);
    CHECK(back.t_rearm == 0x1122334455668899ULL);
    CHECK(back.t_next_cause == 0x11223344556688AAULL);
    CHECK(back.followup_state == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT);
    CHECK((back.record_flags & GBP_VSTATE_DF_FOLLOWUP_FILLED) != 0u);
    CHECK((back.record_flags & GBP_VSTATE_DF_PAYLOAD_VALID) == 0u);
    CHECK(back.gap_count_before == 1u && back.gap_min_before_ticks == 600u);
    CHECK(gbp_vstatedump_decode_semantic(sb, &sem) == 0);
    CHECK(sem.disagreements_total == 3u);
    CHECK(sem.diagnostics_preserved == 3u);
    CHECK(sem.observational_disagreements == 1u);
    CHECK(sem.service_selecting_disagreements == 2u);
    CHECK(sem.gap[5].count == 1u && sem.gap[5].min_ticks == 600u);
    /* The index keeps only the six SOURCE bits, so record 0's delta (0xDCA8,
     * whose source part is also AUDIO) lands in the same bucket as the other
     * two: three records, one bucket. The histogram indexes sources, not
     * values, and this is what that means. */
    CHECK(gbp_vstate_hist_index(0xDCA8u) == gbp_vstate_hist_index(0x0400u));
    CHECK(sem.delta_hist[gbp_vstate_hist_index(back.delta)] == 3u);

    printf("-- every one of the 160 bytes is covered by the CRC\n");
    {
        static uint8_t bad[1u << 20];
        unsigned k, undetected = 0;
        for (k = 0; k < GBP_VSTATEDUMP_DIAG_REC_V5; k++) {
            memcpy(bad, file, (size_t)n);
            bad[info.off_diag + k] ^= 0x01u;
            if (gbp_vstatedump_parse_v5(bad, (size_t)n, 0, 0, 0, 0, 0, 0, 0, 0, 0) == 0) undetected++;
        }
        CHECK(undetected == 0u);
        printf("   160 of 160 flipped one at a time, %u undetected\n", undetected);
    }
    printf("   record %u bytes, semantic block %u bytes, file %ld bytes\n",
           (unsigned)GBP_VSTATEDUMP_DIAG_REC_V4, (unsigned)GBP_VSTATEDUMP_SEMANTIC_SIZE, n);
}

/* §R3.14 / §40: with no disagreement the device stream is EXACTLY vstate-0002's. */
static void test_normal_path_is_untouched(void)
{
    struct gbp_mock a, b;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    unsigned i, diffs = 0;
    printf("-- no disagreement: the operation stream is untouched, bookkeeping is RAM only\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 120u;
    sched_reset(0xFFu);
    mock_vstate(&a, bits, 1u, 50u);
    run_cfg(&a, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(vstate.sem.disagreements_total == 0u);
    CHECK(vstate.diags_n == 0u);
    sched_reset(0xFFu);
    mock_vstate(&b, bits, 1u, 50u);
    b.irq_last_replica_from_write = 100000u;      /* armed far beyond the end */
    b.irq_last_replica_xor = 0x0400u;
    run_cfg(&b, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(a.nops == b.nops);
    for (i = 0; i < a.nops && i < b.nops; i++) {
        const struct gbp_mock_op *p = &a.ops[i], *q = &b.ops[i];
        if (p->kind != q->kind || p->addr != q->addr || p->len != q->len || p->rc != q->rc ||
            memcmp(p->data, q->data, GBP_BLOCK_SIZE) != 0) diffs++;
    }
    CHECK(diffs == 0);
    CHECK(a.bulk_reads == b.bulk_reads && a.irq_writes == b.irq_writes && a.transfers == b.transfers);
    printf("   %u operations compared, %u differences\n", a.nops, diffs);
}

/* §41: in a disagreement the ONLY hardware difference is the selection the
 * majority dictates - never an extra read, retry, ACK, re-arm or snapshot. */
static void test_disagreement_adds_no_operation(void)
{
    struct gbp_mock maj, disc;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    unsigned reads_maj, reads_ref;
    printf("-- a disagreement costs no extra device operation of any kind\n");
    /* reference: the majority value present in EVERY replica, no disagreement */
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 150u;
    sched_reset(0xFFu);
    mock_vstate(&disc, bits, 1u, 50u);
    disc.irq_force_value_from_write = 40u;
    disc.irq_forced_value = 0x0100u;
    run_cfg(&disc, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(vstate.sem.disagreements_total == 0u);
    reads_ref = irq_reads(&disc);
    /* the same run, with the LAST replica claiming an extra AUDIO the majority
     * votes down: the service selection is identical, so the stream must be too */
    sched_reset(0xFFu);
    mock_vstate(&maj, bits, 1u, 50u);
    maj.irq_force_value_from_write = 40u;
    maj.irq_forced_value = 0x0100u;
    maj.irq_last_replica_from_write = 40u;
    maj.irq_last_replica_xor = 0x0400u;
    run_cfg(&maj, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(vstate.sem.disagreements_total > 0u);
    reads_maj = irq_reads(&maj);
    CHECK(reads_maj == reads_ref);                 /* not one extra read */
    CHECK(maj.nops == disc.nops);
    CHECK(maj.bulk_reads == disc.bulk_reads);
    CHECK(maj.irq_writes == disc.irq_writes);
    CHECK(maj.transfers == disc.transfers);
    CHECK(maj.violation_mask == 0u);
    printf("   %u IRQ reads and %u operations either way, with %lu disagreements handled\n",
           reads_maj, maj.nops, (unsigned long)vstate.sem.disagreements_total);
}

/* §R3.19 / §47: what the strict v4 parser must refuse. Every case recomputes
 * BOTH CRCs, so only a structural or semantic rule can do the refusing. */
static void test_v4_strictness(void)
{
    static uint8_t file[1u << 20];
    static uint8_t bad[1u << 20];
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_result r2;
    static struct gbp_vstate_diag store2[4];
    struct gbp_vstate_config c2;
    struct gbp_vstatedump_info info, parsed;
    struct memsink sink;
    uint8_t w[GBP_BLOCK_SIZE];
    long n;
    unsigned i;
    printf("-- the strict v5 parser, with both CRCs recomputed after every tamper\n");
    memset(&r2, 0, sizeof r2);
    cfg_default(&c2);
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 4u);
    window_split(w, 0x0100u, 0x0500u);
    CHECK(gbp_vstate_diag_open(&st2, 7u, 7000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                               GBP_VSTATE_DIS_SOURCE_SERVICED) == 0);
    /* a COMPLETE transaction, so the record carries every current-cycle flag a
     * v5 file can hold and the tampers below have something real to lie about */
    gbp_vstate_diag_service(&st2, 0, 0x0100u, 0x0100u, 0u);
    gbp_vstate_diag_ack(&st2, 0, 0x8100u, 7100u);
    gbp_vstate_diag_rearm(&st2, 0, 7200u);
    CHECK(gbp_vstate_diag_arm_followup(&st2, 0) == 1);
    gbp_vstate_diag_close(&st2, 0u);
    CHECK(st2.diags[0].followup_state == GBP_VSTATE_FU_NO_NEXT_CAUSE);
    memset(&info, 0, sizeof info);
    gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "synthetic");
    sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    n = gbp_vstatedump_stream(&info, &st2, &r2, &c2, chunk, sizeof chunk, sink_mem, &sink, 0);
    CHECK(n > 0);
    CHECK(gbp_vstatedump_parse_v4(file, (size_t)n, &parsed, 0, 0, 0, 0, 0, 0, 0, 0) == 0);

#define REFIX(b) do { put32((b) + 0x1FC, gbp_crc32((b), 0x1FCu)); \
                      put32((b) + info.off_footer + 8u, gbp_crc32((b), info.off_footer)); } while (0)
#define TAMPER(stmt, want, label) do { \
        int rc_; memcpy(bad, file, (size_t)n); { stmt; } REFIX(bad); \
        rc_ = gbp_vstatedump_parse_v4(bad, (size_t)n, &parsed, 0, 0, 0, 0, 0, 0, 0, 0); \
        CHECK(rc_ == (want)); if (rc_ != (want)) printf("   %s: rc=%d, wanted %d\n", label, rc_, want); \
    } while (0)

    TAMPER(put16(bad + 0x008, 6u), -2, "unknown version 6");
    TAMPER(put16(bad + 0x008, 1u), -2, "version 1 belongs to another format");
    /* A v5 file relabelled as v4 is NOT a structural error - the two layouts are
     * identical - so it parses, and that is exactly why the version must be
     * trusted for the PRODUCER contract and nothing else: under the v4 label the
     * cross-field rules no longer run, and bit 8 of record_flags becomes illegal.
     * Both directions are pinned here. */
    TAMPER(put16(bad + 0x008, 4u), -8, "v5 relabelled v4: DF_SERVICE_WRITTEN is not a v4 flag");
    /* a v5 file relabelled as v3 is refused by v3's own reserved-area rule:
     * 0x1EA..0x1FB carry diag_flags, off_semantic and semantic_size, which v3
     * requires to be zero. The versions cannot read each other by accident. */
    TAMPER(put16(bad + 0x008, 3u), -8, "v5 claiming to be v3");
    TAMPER(put32(bad + 0x1E4, 257u), -9, "diag_count 257");
    TAMPER(put16(bad + 0x1E8, 96u), -2, "rec_size 96 in a v4 file");
    TAMPER(put16(bad + 0x1E8, 159u), -2, "rec_size 159");
    TAMPER(put32(bad + 0x1F0, 1023u), -2, "semantic_size 1023");
    TAMPER(put16(bad + 0x1EA, 0x0002u), -8, "unknown diag_flags bit");
    TAMPER(bad[0x1F4] = 1u, -8, "header reserved not zero");
    TAMPER(put32(bad + 0x1EC, info.off_semantic + 16u), -4, "off_semantic moved");
    TAMPER(put32(bad + 0x1E0, info.off_diag + 16u), -4, "off_diag moved");
    TAMPER(put32(bad + info.off_semantic, 0u), -9, "semantic tag wrong");
    TAMPER(put16(bad + info.off_semantic + 4u, 2u), -2, "semantic block_version 2");
    TAMPER(put16(bad + info.off_semantic + 6u, 0x0002u), -8, "unknown semantic flag");
    TAMPER(bad[info.off_semantic + 0x05C] = 1u, -8, "semantic reserved not zero");
    TAMPER(put16(bad + info.off_semantic + 0x070, 0x0002u), -9, "gap slot bit wrong");
    TAMPER(bad[info.off_semantic + 0x084] = 1u, -8, "gap slot reserved not zero");
    TAMPER(bad[info.off_diag + 0x5C] = 1u, -8, "record reserved0 not zero");
    TAMPER(bad[info.off_diag + 0x9E] = 1u, -8, "record reserved1 not zero");
    TAMPER(put16(bad + info.off_diag + 0x6E, 0x0200u), -8, "unknown record flag 0x0200");
    /* 0x0100 IS a v5 flag, so it is not a structural error - it is a LIE about
     * this record, and the cross-field rules are what catch it: a service
     * decision whose service_selected is not authoritative & AV_MASK. */
    TAMPER(put16(bad + info.off_diag + 0x6E, GBP_VSTATE_DF_SERVICE_WRITTEN), -10,
           "service_written on a record that recorded no decision");
    TAMPER(put16(bad + info.off_diag + 0x66, 0u), -9, "classification 0");
    TAMPER(put16(bad + info.off_diag + 0x66, 4u), -9, "classification 4");
    TAMPER(bad[info.off_diag + 0x8C] = 0u, -9, "FU_PENDING in the file");
    TAMPER(bad[info.off_diag + 0x8C] = 5u, -9, "followup_state 5");
    TAMPER(bad[info.off_diag + 0x8D] = 5u, -9, "followup_reason 5");
    TAMPER(put16(bad + info.off_diag + 0x8E, 0x0010u), -9, "payload_source 0x0010");
    TAMPER(put16(bad + info.off_diag + 0x6E, GBP_VSTATE_DF_PAYLOAD_VALID), -9, "payload_valid with no source");
    TAMPER(put16(bad + info.off_diag + 0x6E, GBP_VSTATE_DF_FOLLOWUP_FILLED), -9, "filled with NO_NEXT state");
    TAMPER(put32(bad + info.off_diag + 0x98, 0u), -9, "gap sentinel with count 0");
#undef TAMPER
#undef REFIX
    /* and a CRC-only corruption is still caught by the CRC */
    for (i = 0; i < 4u; i++) {
        memcpy(bad, file, (size_t)n);
        bad[info.off_semantic + 0x100 + i] ^= 0x01u;
        CHECK(gbp_vstatedump_parse(bad, (size_t)n, 0, 0, 0, 0, 0, 0, 0) != 0);
    }
    printf("   28 structural tampers refused, histogram corruption caught by the CRC\n");
}

/*
 * §47 (GBP-VIDEO-003): THE COLOUR CAPTURE COSTS NO DEVICE OPERATION.
 *
 * The colour probe reuses this service loop rather than reimplementing it, and
 * the only thing it adds is RAM bookkeeping per closed frame. The way to prove
 * that is not to read the code: it is to run the SAME mock scenario twice, once
 * with the capture attached and once without, and require the device streams to
 * be identical - reads, whole-block drains, IRQ writes, operations, transfers.
 *
 * The capture is attached WITHOUT a raw buffer here, so it can never certify and
 * can never end the run early: both halves then stop on the same delivery cap
 * and the comparison is over the whole run rather than a prefix.
 */
/*
 * §35 / §15 / §13 of the second microaudit: the COLOUR SUCCESS TRACE, which is a
 * different question from the operation-equivalence test below.
 *
 * A still picture, the real probe, the real teardown. What must be true:
 *   - certification happens in the frame-close hook, between the ACK and the
 *     RE-ARM of the transaction that closed the third frame;
 *   - that transaction still ACKs, still RE-ARMs, still arms its follow-up and
 *     still runs WAIT_NEXT;
 *   - NO FURTHER SERVICE TRANSACTION follows: no IRQ-data read, no drain, no
 *     ACK, no RE-ARM, no gbp_vstate_block, and the ring does not advance;
 *   - the teardown does not touch one byte of A, B or C.
 */
static void test_colour_success_trace_and_raw_immutability(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vcolor colour;
    static struct gbp_vcolor_frame ctab[64];
    static uint8_t snap[GBP_VCOLOR_CERT_FRAMES][GBP_VCOLOR_FRAME_BYTES];
    const uint16_t bits[1] = { 0x0500u };
    unsigned k, slots, cur;
    printf("-- the colour success trace: certify, finish the transaction, stop, and keep the bytes\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 60;   /* the vstate target must not fire */
    cfg.max_deliveries = 4000u;
    gbp_vcolor_init(&colour, ctab, 64u);
    cfg.color = &colour;
    cfg.color_search_ticks = 0u;
    sched_reset(0xFFu);                                    /* a STILL picture */
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg_colour(&m, &rl, &res, &cfg);

    /* it certified, and the run ended because of that and nothing else */
    CHECK(colour.certified == 1);
    CHECK(colour.cert_n == GBP_VCOLOR_CERT_FRAMES);
    CHECK(res.stop == GBP_VSTATE_STOP_COLOR_CERTIFIED);
    CHECK(res.service_ok == 1);
    CHECK(res.restore_ok == 1);
    /* §14: a cause WAS pending at the stop, and that is normal, not an error */
    CHECK(res.next_cause_at_end == 1);
    CHECK(res.a.power_cycle_required == 1);
    CHECK(res.h.handler_restored == 1);
    CHECK(res.h.mask_ok == 1);

    /* §13: the certifying transaction completed - every ACK has its RE-ARM */
    CHECK(res.acks == res.rearms);
    CHECK(res.deliveries == res.acks);
    CHECK(res.isr_w1c == res.deliveries);
    /* the third certified frame is the LAST frame the model closed: no frame was
     * assembled after certification, so no VIDEO block was drained after it */
    CHECK(colour.cert[2].frame_index == colour_vstate.frames_n - 1u);
    CHECK(colour_vstate.cur_blocks == 1u);                 /* only D's boundary block */

    /* §4: the relation, at whatever rotation this run happened to reach */
    slots = gbp_vstate_ring_slots(&colour_vstate);
    cur = gbp_vstate_current_slot(&colour_vstate);
    CHECK(slots == 4u);
    CHECK(colour.cert[1].ring_slot == (colour.cert[0].ring_slot + 1u) % slots);
    CHECK(colour.cert[2].ring_slot == (colour.cert[1].ring_slot + 1u) % slots);
    CHECK(cur == (colour.cert[2].ring_slot + 1u) % slots);
    CHECK(gbp_vcolor_slots_ok(&colour, &colour_vstate) == 1);

    /* §15: the bytes are the ones the DMA wrote, AFTER the whole teardown ran */
    for (k = 0; k < GBP_VCOLOR_CERT_FRAMES; k++) {
        const uint8_t *r = gbp_vstate_ring_frame(&colour_vstate, colour.cert[k].ring_slot);
        CHECK(r != 0);
        memcpy(snap[k], r, GBP_VCOLOR_FRAME_BYTES);
    }
    CHECK(memcmp(snap[0], snap[1], GBP_VCOLOR_FRAME_BYTES) == 0);
    CHECK(memcmp(snap[0], snap[2], GBP_VCOLOR_FRAME_BYTES) == 0);
    /* and they are what the mock painted: byte 1 and byte 3 of every group */
    CHECK(snap[0][1] == 0xFFu);                            /* block 0 carries the boundary */
    CHECK(snap[0][GBP_VSTATE_VIDEO_BLOCK_SIZE + 3u] == 0xFFu);
    printf("   certified at frame %lu, slots %u/%u/%u, filling %u, %lu deliveries, %lu acks = %lu rearms\n",
           (unsigned long)colour.cert[2].frame_index, colour.cert[0].ring_slot,
           colour.cert[1].ring_slot, colour.cert[2].ring_slot, cur,
           (unsigned long)res.deliveries, (unsigned long)res.acks, (unsigned long)res.rearms);
}

/*
 * The PRE-HANDLER MASKED WAIT diagnostic. Three properties, and the first is the
 * one that matters: with the wait at zero the probe must be the probe that was
 * physically validated, to the operation.
 */
static void test_prehandler_wait_default_changes_nothing(void)
{
    struct gbp_mock ref, off;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    unsigned ref_reads, ref_ops, ref_bulk, ref_irqw, ref_deliveries;
    printf("-- the pre-handler wait at 0: the same device stream, to the operation\n");
    /* reference: the config exactly as gbp_vstate_config_default leaves it */
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 200u;
    CHECK(cfg.prehandler_wait_ms == 0u);          /* the default IS zero */
    sched_reset(0xFFu);
    mock_vstate(&ref, bits, 1u, 50u);
    run_cfg(&ref, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    ref_reads = irq_reads(&ref); ref_ops = ref.nops; ref_bulk = ref.bulk_reads;
    ref_irqw = ref.irq_writes; ref_deliveries = res.deliveries;
    CHECK(res.prehandler_wait_ms == 0u);
    CHECK(res.prehandler_wait_iters == 0u);
    CHECK(res.prehandler_wait_done == 0);
    CHECK(res.t_prehandler_wait_begin == 0u && res.t_prehandler_wait_end == 0u);

    /* explicitly zero: byte for byte the same run */
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 200u;
    cfg.prehandler_wait_ms = 0u;
    sched_reset(0xFFu);
    mock_vstate(&off, bits, 1u, 50u);
    run_cfg(&off, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(irq_reads(&off) == ref_reads);
    CHECK(off.nops == ref_ops);
    CHECK(off.bulk_reads == ref_bulk);
    CHECK(off.irq_writes == ref_irqw);
    CHECK(off.violation_mask == 0u);
    CHECK(res.deliveries == ref_deliveries);
    printf("   %u IRQ reads, %u operations, %u bulk, %u IRQ writes: identical\n",
           ref_reads, ref_ops, ref_bulk, ref_irqw);
}

static void test_prehandler_wait_waits_then_serves_normally(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    uint64_t want, elapsed;
    printf("-- the pre-handler wait at 2 ms: it waits, then the run proceeds normally\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 200u;
    cfg.prehandler_wait_ms = 2u;                  /* small: the mock clock moves 10 ticks a call */
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    /* the run still completes, and the service path is untouched */
    CHECK(res.service_ok == 1);
    CHECK(res.deliveries > 0u);
    CHECK(res.acks == res.rearms);
    CHECK(res.deliveries == res.acks);
    CHECK(m.violation_mask == 0u);
    CHECK(res.h.handler_was_installed == 1);
    CHECK(res.restore_ok == 1);
    /* and the wait really happened, for at least the time asked */
    want = ((uint64_t)cfg.a.tb_hz * 2u) / 1000u;
    elapsed = res.t_prehandler_wait_end - res.t_prehandler_wait_begin;
    CHECK(res.prehandler_wait_ms == 2u);
    CHECK(res.prehandler_wait_done == 1);         /* the bound, not the iteration cap */
    CHECK(res.prehandler_wait_iters > 0u);
    CHECK(elapsed >= want);
    /* it happened BEFORE the capture: the wait ends before the first unmask */
    CHECK(res.t_prehandler_wait_end <= res.t_capture_start);
    CHECK(res.t_prehandler_wait_begin >= res.t_control_transform);
    printf("   waited %llu ticks (asked %llu) in %lu iterations, then %lu deliveries, acks == rearms\n",
           (unsigned long long)elapsed, (unsigned long long)want,
           (unsigned long)res.prehandler_wait_iters, (unsigned long)res.deliveries);
}

static void test_prehandler_wait_records_fit_the_logger(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    int a, b;
    printf("-- the pre-handler records fit the logger at the PHYSICAL magnitudes\n");
    /* THE DEFECT THIS REPRODUCES. As one line, the pre-handler record reached 266
     * characters on hardware and the logger cut it at 255, setting truncated=1 in
     * the vstate-prewait-5000 and color-0001 logs. The widths are what did it, so
     * this scenario uses the physical ones and nothing smaller: the real 40.5 MHz
     * time base, the real 5000 ms wait, and a 64-bit clock origin high enough that
     * both timestamps print at full width. The earlier wait tests run at 2 ms on a
     * small clock, where the single line still fit - which is exactly why they
     * never caught it. */
    cfg_default(&cfg);
    cfg.a.tb_hz = GBP_TIME64_NOMINAL_HZ;
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 200u;
    cfg.prehandler_wait_ms = 5000u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    m.tick64_origin = (uint64_t)0x8000000000000000ull;   /* begin/end print 16 hex digits */
    run_cfg(&m, &rl, &res, &cfg);
    /* the run really carried the physical magnitudes */
    CHECK(res.prehandler_wait_ms == 5000u);
    CHECK(res.prehandler_wait_done == 1);
    CHECK(res.t_prehandler_wait_begin >= (uint64_t)0x8000000000000000ull);
    CHECK(gbp_time64_delta(res.t_prehandler_wait_begin, res.t_prehandler_wait_end)
          >= ((uint64_t)GBP_TIME64_NOMINAL_HZ * 5000u) / 1000u);
    CHECK(res.prehandler_wait_iters > 1000000u);
    /* and NOTHING the run wrote was cut or lost */
    CHECK(rl.truncated == 0);
    CHECK(rl.dropped == 0);
    /* the two records exist, separately, and in order */
    a = line_index(&rl, "PREHANDLERWAIT ");
    b = line_index(&rl, "PREHANDLERWAITSTATE ");
    CHECK(a >= 0);
    CHECK(b >= 0);
    CHECK(b > a);
    /* each carries its own subject and neither carries the other's */
    CHECK(strstr(ringlog_line(&rl, (size_t)a), "elapsed=") != 0);
    CHECK(strstr(ringlog_line(&rl, (size_t)a), "control_pre=") == 0);
    CHECK(strstr(ringlog_line(&rl, (size_t)b), "intmr_post=") != 0);
    CHECK(strstr(ringlog_line(&rl, (size_t)b), "want_ticks=") == 0);
    /* the service path is still untouched by any of this */
    CHECK(res.service_ok == 1);
    CHECK(res.acks == res.rearms);
    CHECK(m.violation_mask == 0u);
    printf("   %lu iterations, both records written, longest line %u chars, truncated=%u\n",
           (unsigned long)res.prehandler_wait_iters,
           (unsigned)strlen(ringlog_line(&rl, (size_t)b)), (unsigned)rl.truncated);
}

static void test_prehandler_wait_cannot_be_reached_without_a_clock(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_transport t;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- the wait can never spin blind: no 64-bit clock aborts the run before it\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 40u;
    cfg.prehandler_wait_ms = 5000u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    gbp_mock_transport(&m, &t);
    t.ticks64 = 0;                                /* a transport without the 64-bit clock */
    gbp_vstate_init(&vstate, frames, GBP_VSTATE_MAX_FRAMES, events, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&vstate, diag_store, GBP_VSTATE_MAX_DISAGREEMENTS);
    cfg.st = &vstate;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    memset(&witness, 0, sizeof witness);
    witness.rl = &rl;
    witness.base = gbp_internal_size_from_arinfo(m.arinfo);
    m.write_hook = on_write; m.write_hook_user = &witness;
    gbp_vstate_probe_run(&t, &rl, &cfg, &res);
    /* the probe already refuses this transport BEFORE stage A, so the wait is
     * not merely skipped - it is unreachable, and no loop ever runs */
    CHECK(res.status == GBP_VSTATE_ABORT_TIME64_UNAVAILABLE);
    CHECK(res.prehandler_wait_iters == 0u);
    CHECK(res.t_prehandler_wait_begin == 0u);
    CHECK(res.h.handler_was_installed == 0);
    printf("   aborted with time64_unavailable; the wait loop was never entered\n");
}


/*
 * §V3.28: the colour capture opens AFTER the fixed pre-handler wait, and no
 * colour state exists before it. The ordering is the whole point - a capture
 * that opened during the wait would be capturing the AGB's boot, which is what
 * the wait exists to avoid.
 */
static void test_colour_capture_starts_after_the_prehandler_wait(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vcolor colour;
    static struct gbp_vcolor_frame ctab[64];
    const uint16_t bits[1] = { 0x0500u };
    uint64_t want;
    printf("-- the colour capture opens only after the pre-handler wait, with no state before it\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 60;
    cfg.max_deliveries = 4000u;
    gbp_vcolor_init(&colour, ctab, 64u);
    cfg.color = &colour;
    cfg.color_search_ticks = 0u;
    cfg.prehandler_wait_ms = 2u;              /* small: the mock clock moves 10 ticks a call */
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg_colour(&m, &rl, &res, &cfg);

    /* the wait happened, and it happened in the validated position */
    want = ((uint64_t)cfg.a.tb_hz * 2u) / 1000u;
    CHECK(res.prehandler_wait_ms == 2u);
    CHECK(res.prehandler_wait_done == 1);
    CHECK(res.t_prehandler_wait_end - res.t_prehandler_wait_begin >= want);
    /* THE ORDER, end to end */
    CHECK(res.t_control_transform <= res.t_prehandler_wait_begin);
    CHECK(res.t_prehandler_wait_begin < res.t_prehandler_wait_end);
    CHECK(res.t_prehandler_wait_end <= res.t_capture_start);   /* capture opens AFTER the wait */
    CHECK(res.t_capture_start > 0u);
    /* the handler was installed after the wait, never before */
    CHECK(res.h.handler_was_installed == 1);
    /* and the run still worked */
    CHECK(res.service_ok == 1);
    CHECK(res.deliveries > 0u);
    CHECK(res.acks == res.rearms);
    CHECK(m.violation_mask == 0u);
    printf("   control %llu -> wait [%llu..%llu] -> capture %llu, %lu deliveries\n",
           (unsigned long long)res.t_control_transform,
           (unsigned long long)res.t_prehandler_wait_begin,
           (unsigned long long)res.t_prehandler_wait_end,
           (unsigned long long)res.t_capture_start, (unsigned long)res.deliveries);
}

/* The same run, but asking what the colour module had done by the time the wait
 * ended. The answer must be: nothing at all. */
static void test_no_colour_state_exists_before_capture_start(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vcolor colour, fresh;
    static struct gbp_vcolor_frame ctab[64];
    const uint16_t bits[1] = { 0x0500u };
    printf("-- nothing in the colour capture exists before the capture opens\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 60;
    cfg.max_deliveries = 1u;                  /* stop at the very first admitted cycle */
    gbp_vcolor_init(&colour, ctab, 64u);
    gbp_vcolor_init(&fresh, 0, 0u);           /* what "untouched" looks like */
    cfg.color = &colour;
    cfg.color_search_ticks = 0u;
    cfg.prehandler_wait_ms = 2u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg_colour(&m, &rl, &res, &cfg);

    /* one delivery cannot close a 40-block frame, so the hook never ran */
    CHECK(colour.frames_total == 0u);
    CHECK(colour.frames_eligible == 0u);
    CHECK(colour.run_len == 0u);
    CHECK(colour.certified == 0);
    CHECK(colour.cert_n == 0u);
    CHECK(colour.resets == 0u);
    CHECK(colour.sig_mismatches == 0u);
    CHECK(colour.t_certified == 0u);
    {   /* the reference signature vector is still all zero: no signature was taken */
        unsigned i, nonzero = 0;
        for (i = 0; i < GBP_VSTATE_FRAME_SIGS; i++) if (colour.ref_sig[i]) nonzero++;
        CHECK(nonzero == 0u);
        CHECK(memcmp(colour.ref_sig, fresh.ref_sig, sizeof fresh.ref_sig) == 0);
    }
    /* and the state model owns no closed frame yet, so no ring slot is evidence */
    CHECK(colour_vstate.frames_n == 0u);
    CHECK(gbp_vcolor_slots_ok(&colour, &colour_vstate) == 0);
    printf("   0 frames, 0 eligible, run_len 0, ref_sig untouched, no slot owned\n");
}

static void test_colour_capture_adds_no_operation(void)
{
    struct gbp_mock ref, col;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vcolor colour;
    const uint16_t bits[1] = { 0x0500u };
    unsigned ref_reads, col_reads, ref_deliveries;
    printf("-- the colour capture attached: the same device stream, to the operation\n");
    /* The screen changes every frame in BOTH runs. That is what keeps the
     * comparison meaningful since the timing fix: with a still picture the
     * capture would certify at the third frame and stop the run early, which is
     * a scientific stop, not a device-operation difference. Here neither run can
     * certify, so both end on the same delivery cap and every operation of one
     * has to match the other. */
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 200u;
    sched_reset(0xFFu);
    sched.chaos_from = 1u;
    mock_vstate(&ref, bits, 1u, 50u);
    run_cfg(&ref, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    ref_reads = irq_reads(&ref);
    ref_deliveries = res.deliveries;

    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 200u;
    gbp_vcolor_init(&colour, 0, 0u);             /* counts, keeps no table */
    cfg.color = &colour;
    cfg.color_search_ticks = 0u;                 /* no search deadline in this comparison */
    sched_reset(0xFFu);
    sched.chaos_from = 1u;
    mock_vstate(&col, bits, 1u, 50u);
    run_cfg(&col, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    col_reads = irq_reads(&col);

    CHECK(col_reads == ref_reads);
    CHECK(col.nops == ref.nops);
    CHECK(col.bulk_reads == ref.bulk_reads);
    CHECK(col.irq_writes == ref.irq_writes);
    CHECK(col.transfers == ref.transfers);
    CHECK(col.violation_mask == 0u);
    CHECK(res.deliveries == ref_deliveries);
    /* and the capture did see the frames: a changing picture simply never gives
     * it three in a row, so it observes everything and certifies nothing */
    CHECK(colour.frames_total > 0u);
    CHECK(colour.frames_eligible > 0u);
    CHECK(colour.certified == 0);
    CHECK(colour.sig_mismatches > 0u);           /* every frame broke the previous run */
    {   /* the reasons partition the frames exactly once each */
        unsigned k, sum = 0;
        for (k = 0; k < GBP_VCOLOR_REASONS; k++) sum += colour.frames_refused[k];
        CHECK(sum == colour.frames_total);
        CHECK(colour.frames_refused[GBP_VCOLOR_RETIRED_PRE_BASELINE] == 0u);
    }
    printf("   %u IRQ reads, %u operations, %u bulk reads either way, %lu frames observed\n",
           col_reads, col.nops, col.bulk_reads, (unsigned long)colour.frames_total);
}

/*
 * §12 / §35: OWNERSHIP AT THE API LEVEL, INCLUDING A STORE THAT RUNS OUT MID
 * TRANSACTION. A transaction opens its service record A and then, later in the
 * SAME transaction, one or two observational records. The markers that belong to
 * the transaction must reach A and only A - even when B and C could not be
 * preserved at all, which is precisely when a "latest record" rule would have
 * written them into whatever record happened to be last.
 */
static void test_ownership_survives_a_store_that_runs_out(void)
{
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_diag store2[6];
    struct gbp_vstate_diag snapshot[6];
    uint8_t w[GBP_BLOCK_SIZE];
    unsigned slots;
    printf("-- service record A keeps its markers when B and C do not fit\n");
    for (slots = 1u; slots <= 4u; slots++) {
        /* cap 4, and `slots - 1` free when the transaction starts: the four cases
         * are 0 free (nothing fits at all), 1 free (only A fits), 2 free (A and B
         * fit, C does not) and 3 free (all three fit). */
        gbp_vstate_diag_handle a, b, c;
        unsigned prefill = 4u - (slots - 1u);     /* 3, 2 and 1 records already stored */
        unsigned i;
        gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                        raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
        gbp_vstate_diag_store(&st2, store2, 4u);
        window_split(w, 0x0500u, 0x0100u);        /* majority-extra AUDIO: a payload is justified */
        for (i = 0; i < prefill; i++) {
            gbp_vstate_diag_handle h = gbp_vstate_diag_open(&st2, 100u + i, 1000u + i, w, 0x0100u, 0x0500u,
                                                            GBP_VSTATE_DIAG_READ_LEAN,
                                                            GBP_VSTATE_DIS_SOURCE_SERVICED);
            CHECK(h == (gbp_vstate_diag_handle)i);
            gbp_vstate_diag_service(&st2, h, 0x0500u, 0x0500u, 0u);
            gbp_vstate_diag_ack(&st2, h, 0x8500u, 1010u + i);
            gbp_vstate_diag_rearm(&st2, h, 1020u + i);
        }
        /* the transaction: A at the READ, B at POSTDRAIN, C at POSTACK */
        a = gbp_vstate_diag_open(&st2, 200u, 2000u, w, 0x0100u, 0x0500u, GBP_VSTATE_DIAG_READ_LEAN,
                                 GBP_VSTATE_DIS_SOURCE_SERVICED);
        gbp_vstate_diag_service(&st2, a, 0x0500u, 0x0500u, 0u);
        b = gbp_vstate_diag_open(&st2, 200u, 2010u, w, 0x0100u, 0x0500u, GBP_VSTATE_DIAG_READ_POSTDRAIN,
                                 GBP_VSTATE_DIS_SOURCE_SERVICED);
        c = gbp_vstate_diag_open(&st2, 200u, 2020u, w, 0x0100u, 0x0500u, GBP_VSTATE_DIAG_READ_POSTACK,
                                 GBP_VSTATE_DIS_SOURCE_SERVICED);
        /* how many of the three fitted is exactly how many slots there were */
        CHECK((a != GBP_VSTATE_DIAG_INVALID) == (slots >= 2u));
        CHECK((b != GBP_VSTATE_DIAG_INVALID) == (slots >= 3u));
        CHECK((c != GBP_VSTATE_DIAG_INVALID) == (slots >= 4u));
        /* whatever fitted, the rest of the transaction belongs to A */
        memcpy(snapshot, store2, sizeof snapshot[0] * 4u);
        gbp_vstate_diag_payload(&st2, a, GBP_VSTATE_SRC_AUDIO, 0xABCDEF01u, 0x11223344u);
        gbp_vstate_diag_ack(&st2, a, 0x8500u, 2100u);
        gbp_vstate_diag_rearm(&st2, a, 2200u);
        gbp_vstate_diag_quarantined(&st2, a);
        gbp_vstate_diag_deferred(&st2, a);
        if (a == GBP_VSTATE_DIAG_INVALID) {
            /* nothing fitted: not one byte of the store may have moved */
            CHECK(memcmp(snapshot, store2, sizeof snapshot[0] * 4u) == 0);
        } else {
            const struct gbp_vstate_diag *da = gbp_vstate_diag_at(&st2, a);
            CHECK(da != 0);
            CHECK(da->cycle == 200u);
            CHECK(da->payload_source == GBP_VSTATE_SRC_AUDIO);
            CHECK(da->payload_crc32 == 0xABCDEF01u);
            CHECK(da->ack_value == 0x8500u && da->t_ack == 2100u);
            CHECK(da->t_rearm == 2200u);
            CHECK((da->record_flags & (GBP_VSTATE_DF_FRAME_QUARANTINED | GBP_VSTATE_DF_SOURCE_DEFERRED |
                                       GBP_VSTATE_DF_PAYLOAD_VALID | GBP_VSTATE_DF_SERVICE_WRITTEN)) ==
                  (GBP_VSTATE_DF_FRAME_QUARANTINED | GBP_VSTATE_DF_SOURCE_DEFERRED |
                   GBP_VSTATE_DF_PAYLOAD_VALID | GBP_VSTATE_DF_SERVICE_WRITTEN));
            /* every OTHER record is byte-identical to the snapshot: neither the
             * witnesses nor the records of earlier transactions moved */
            for (i = 0; i < 4u; i++) {
                if (i == (unsigned)a) continue;
                CHECK(memcmp(&snapshot[i], &store2[i], sizeof snapshot[0]) == 0);
            }
            if (b != GBP_VSTATE_DIAG_INVALID) {
                const struct gbp_vstate_diag *db = gbp_vstate_diag_at(&st2, b);
                CHECK(db->read_kind == GBP_VSTATE_DIAG_READ_POSTDRAIN);
                CHECK(db->service_selected == 0u && db->ack_value == 0u && db->t_rearm == 0u);
                CHECK((db->record_flags & (GBP_VSTATE_DF_SERVICE_WRITTEN | GBP_VSTATE_DF_ACK_WRITTEN |
                                           GBP_VSTATE_DF_REARM_WRITTEN | GBP_VSTATE_DF_PAYLOAD_VALID |
                                           GBP_VSTATE_DF_FRAME_QUARANTINED |
                                           GBP_VSTATE_DF_SOURCE_DEFERRED)) == 0u);
            }
        }
        /* and the aggregate counters moved for all three, preserved or not */
        CHECK(st2.sem.disagreements_total == prefill + 3u);
        CHECK(st2.sem.diagnostics_preserved + st2.sem.diagnostics_not_preserved ==
              st2.sem.disagreements_total);
        gbp_vstate_diag_close(&st2, 0u);
        printf("   %u free slot(s): A=%d B=%d C=%d, preserved=%lu not_preserved=%lu\n",
               slots - 1u, a, b, c, (unsigned long)st2.sem.diagnostics_preserved,
               (unsigned long)st2.sem.diagnostics_not_preserved);
    }
}

/*
 * §18: THE TEARDOWN SWEEP MAY TOUCH ONLY THE FOLLOW-UP. A completed record is
 * snapshotted byte for byte, the run is closed, and every byte outside the
 * follow-up block must be identical. A record that was already closed must not
 * change at all.
 */
static void test_diag_close_touches_only_the_followup(void)
{
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_diag store2[4];
    struct gbp_vstate_diag before[4];
    uint8_t w[GBP_BLOCK_SIZE];
    gbp_vstate_diag_handle closed, waiting, pending;
    printf("-- diag_close() may move follow-up bytes and nothing else\n");
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 4u);
    window_split(w, 0x0100u, 0x0500u);
    /* 0: a record whose follow-up was already filled - it is FINISHED */
    closed = gbp_vstate_diag_open(&st2, 1u, 1000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                                  GBP_VSTATE_DIS_SOURCE_SERVICED);
    gbp_vstate_diag_service(&st2, closed, 0x0100u, 0x0100u, 0u);
    gbp_vstate_diag_ack(&st2, closed, 0x8100u, 1100u);
    gbp_vstate_diag_rearm(&st2, closed, 1200u);
    CHECK(gbp_vstate_diag_arm_followup(&st2, closed) == 1);
    CHECK(gbp_vstate_diag_followup(&st2, 1300u, 0x0400u, 0x0400u) == 1);
    /* 1: a record armed and still waiting when the run ends */
    waiting = gbp_vstate_diag_open(&st2, 2u, 2000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                                   GBP_VSTATE_DIS_SOURCE_SERVICED);
    gbp_vstate_diag_service(&st2, waiting, 0x0100u, 0x0100u, 0u);
    gbp_vstate_diag_ack(&st2, waiting, 0x8100u, 2100u);
    gbp_vstate_diag_rearm(&st2, waiting, 2200u);
    CHECK(gbp_vstate_diag_arm_followup(&st2, waiting) == 1);
    /* 2: a record whose transaction died before its re-arm - only the sweep can
     *    close it, and it must close ONLY its follow-up */
    pending = gbp_vstate_diag_open(&st2, 3u, 3000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                                   GBP_VSTATE_DIS_SOURCE_SERVICED);
    gbp_vstate_diag_service(&st2, pending, 0x0100u, 0x0100u, 0u);
    gbp_vstate_diag_ack(&st2, pending, 0x8100u, 3100u);
    CHECK(st2.diags_n == 3u);

    memcpy(before, store2, sizeof before);
    gbp_vstate_diag_close(&st2, 1u);

    {
        /* the follow-up block is the only region allowed to move: t_next_cause
         * (0x80) through followup_reason (0x8D), plus bit 0 of record_flags. */
        unsigned i;
        for (i = 0; i < 3u; i++) {
            const uint8_t *a = (const uint8_t *)&before[i];
            const uint8_t *b = (const uint8_t *)&store2[i];
            size_t off;
            for (off = 0; off < sizeof before[0]; off++) {
                int in_followup = (off >= 0x80u && off < 0x8Eu);
                int in_flags = (off == 0x6Eu || off == 0x6Fu);
                if (a[off] == b[off]) continue;
                CHECK(in_followup || in_flags);
                if (!(in_followup || in_flags))
                    printf("   record %u byte 0x%02X changed: %02x -> %02x\n",
                           i, (unsigned)off, a[off], b[off]);
            }
        }
        /* the ALREADY-CLOSED record must not have changed by a single byte */
        CHECK(memcmp(&before[0], &store2[0], sizeof before[0]) == 0);
    }
    /* and the two open ones are resolved, with the right reasons */
    CHECK(store2[1].followup_state == GBP_VSTATE_FU_UNKNOWN);
    CHECK(store2[1].followup_reason == GBP_VSTATE_FUR_RUN_ABORTED);
    CHECK(store2[2].followup_state == GBP_VSTATE_FU_UNKNOWN);
    CHECK(store2[2].followup_reason == GBP_VSTATE_FUR_RUN_ABORTED);
    CHECK(store2[2].t_next_cause == 0u && store2[2].next_pending_gbi == 0u);
    /* current-cycle fields of all three are exactly what their own cycle wrote */
    CHECK(store2[0].t_ack == 1100u && store2[1].t_ack == 2100u && store2[2].t_ack == 3100u);
    CHECK(store2[0].t_rearm == 1200u && store2[1].t_rearm == 2200u && store2[2].t_rearm == 0u);
    printf("   3 records: closed untouched, waiting -> run_aborted, pending swept, no other byte moved\n");
}

/*
 * §9 / §31: a disagreement where the MAJORITY carried the extra source omits
 * nothing, so there is nothing to follow up. Such a record must never wait, must
 * never be armed, and must never reach a file as FU_PENDING.
 */
static void test_majority_extra_only_never_waits(void)
{
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_diag store2[4];
    uint8_t w[GBP_BLOCK_SIZE];
    gbp_vstate_diag_handle h;
    printf("-- majority-extra only: nothing was omitted, so nothing is waited for\n");
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 4u);
    window_split(w, 0x0500u, 0x0100u);            /* Disc 0100, majority 0500 */
    h = gbp_vstate_diag_open(&st2, 1u, 1000u, w, 0x0100u, 0x0500u, GBP_VSTATE_DIAG_READ_LEAN,
                             GBP_VSTATE_DIS_SOURCE_SERVICED);
    CHECK(h == 0);
    CHECK(store2[0].disc_extra_sources == 0u);
    CHECK(store2[0].majority_extra_sources == GBP_VSTATE_SRC_AUDIO);
    /* closed at open, with the reason that says exactly why */
    CHECK(store2[0].followup_state == GBP_VSTATE_FU_UNKNOWN);
    CHECK(store2[0].followup_reason == GBP_VSTATE_FUR_NOT_APPLICABLE);
    CHECK(st2.diag_wait == -1);
    gbp_vstate_diag_service(&st2, h, 0x0500u, 0x0500u, 0u);
    gbp_vstate_diag_ack(&st2, h, 0x8500u, 1100u);
    gbp_vstate_diag_rearm(&st2, h, 1200u);
    /* a written re-arm does NOT arm it: there is no omitted source to look for */
    CHECK(gbp_vstate_diag_arm_followup(&st2, h) == 0);
    CHECK(st2.diag_wait == -1);
    gbp_vstate_diag_close(&st2, 0u);
    CHECK(store2[0].followup_state == GBP_VSTATE_FU_UNKNOWN);
    CHECK(store2[0].followup_reason == GBP_VSTATE_FUR_NOT_APPLICABLE);   /* unchanged by the sweep */
    CHECK(store2[0].t_next_cause == 0u && store2[0].next_pending_gbi == 0u);
    printf("   disc_extra=0000 -> unknown/not_applicable, never a waiter\n");
}

/*
 * §31: THE V5 PARSER REFUSES THE DEFECT THE V4 FILE CARRIES.
 *
 * A valid v5 file is built and then tampered into each shape the physical v4 file
 * actually has, with both CRCs recomputed so that ONLY the cross-field rule can
 * refuse it. If any of these were accepted, a v5 file could carry the very defect
 * this revision exists to remove.
 */
static uint16_t get_u16_at(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }

static void put64(uint8_t *p, uint64_t v)
{
    unsigned k;
    for (k = 0; k < 8u; k++) p[k] = (uint8_t)(v >> (56u - 8u * k));
}

static void test_v5_rejects_the_v4_defect(void)
{
    static uint8_t file[1u << 20];
    static uint8_t bad[1u << 20];
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_result r2;
    static struct gbp_vstate_diag store2[4];
    struct gbp_vstate_config c2;
    struct gbp_vstatedump_info info, parsed;
    struct memsink sink;
    uint8_t w[GBP_BLOCK_SIZE];
    uint32_t r0, r1;
    long n;
    printf("-- a v5 file tampered into the v4 producer defect is REFUSED, four ways\n");
    memset(&r2, 0, sizeof r2);
    cfg_default(&c2);
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 4u);
    window_split(w, 0x0100u, 0x0500u);            /* the physical shape: Disc 0500, majority 0100 */
    {
        gbp_vstate_diag_handle h = gbp_vstate_diag_open(&st2, 900u, 1000u, w, 0x0500u, 0x0100u,
                                                        GBP_VSTATE_DIAG_READ_LEAN,
                                                        GBP_VSTATE_DIS_SOURCE_SERVICED);
        CHECK(h == 0);
        gbp_vstate_diag_service(&st2, h, 0x0100u, 0x0100u, 0u);
        gbp_vstate_diag_ack(&st2, h, 0x8100u, 1100u);
        gbp_vstate_diag_rearm(&st2, h, 1200u);
        CHECK(gbp_vstate_diag_arm_followup(&st2, h) == 1);
        CHECK(gbp_vstate_diag_followup(&st2, 1300u, 0x0400u, 0x0400u) == 1);
        /* and an observational witness from a later read */
        CHECK(gbp_vstate_diag_open(&st2, 901u, 1400u, w, 0x0500u, 0x0100u,
                                   GBP_VSTATE_DIAG_READ_POSTACK,
                                   GBP_VSTATE_DIS_SOURCE_SERVICED) == 1);
    }
    gbp_vstate_diag_close(&st2, 0u);
    memset(&info, 0, sizeof info);
    CHECK(gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "synthetic") == 0);
    sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    n = gbp_vstatedump_stream(&info, &st2, &r2, &c2, chunk, sizeof chunk, sink_mem, &sink, 0);
    CHECK(n > 0);
    CHECK(info.diag_count == 2u);
    r0 = info.off_diag;
    r1 = info.off_diag + GBP_VSTATEDUMP_DIAG_REC_V5;
    /* the untampered file is valid: every refusal below is caused by the tamper */
    CHECK(gbp_vstatedump_parse_v5(file, (size_t)n, &parsed, 0, 0, 0, 0, 0, 0, 0, 0) == 0);

#define REFIX(b) do { put32((b) + 0x1FC, gbp_crc32((b), 0x1FCu)); \
                      put32((b) + info.off_footer + 8u, gbp_crc32((b), info.off_footer)); } while (0)
#define CASE(stmt, label) do { \
        int rc_; memcpy(bad, file, (size_t)n); { stmt; } REFIX(bad); \
        rc_ = gbp_vstatedump_parse_v5(bad, (size_t)n, 0, 0, 0, 0, 0, 0, 0, 0, 0); \
        CHECK(rc_ == -10); if (rc_ != -10) printf("   %s: rc=%d, wanted -10\n", label, rc_); \
    } while (0)

    /* A: the authority of a LATER cycle - 22 of the 23 physical records look
     *    exactly like this: authoritative sources that are not the majority. */
    CASE({ put16(bad + r0 + 0x68, 0x0400u); put16(bad + r0 + 0x6C, 0x0400u);
           put16(bad + r0 + 0x6A, 0x8400u); }, "A: authority is not the majority");
    /* B: the timing of a LATER cycle - the re-arm lands after the next cause,
     *    which is the inversion measured in 23 of 23 physical records. */
    CASE(put64(bad + r0 + 0x80, 1150u), "B: next cause before the re-arm");
    CASE(put64(bad + r0 + 0x70, 1250u), "B2: ACK after the re-arm");
    /* C: an ACK that is not the authoritative value with bit 15 */
    CASE(put16(bad + r0 + 0x6A, 0x8101u), "C: ack != authoritative | 0x8000");
    /* D: an observational record claiming a current-service effect */
    CASE(put16(bad + r1 + 0x6E, GBP_VSTATE_DF_ACK_WRITTEN), "D: observational record with an ACK");
    CASE(put16(bad + r1 + 0x6C, 0x0100u), "D2: observational record with a service decision");
    /* and the recomputation itself: a stored reading that the bytes do not produce */
    CASE(put16(bad + r0 + 0x12, 0x0400u), "E: gbi_value is not what raw[32] recomputes");
    CASE(put16(bad + r0 + 0x66, 3u), "F: classification is not the normative one");
    /* §27: a service decision nobody recorded - the zero that must not be
     *      ambiguous, in both directions */
    CASE(put16(bad + r0 + 0x6E, (uint16_t)(get_u16_at(bad + r0 + 0x6E) & ~GBP_VSTATE_DF_SERVICE_WRITTEN)),
         "H: service_selected set with SERVICE_WRITTEN clear");
    CASE({ put16(bad + r1 + 0x6E, GBP_VSTATE_DF_SERVICE_WRITTEN); put16(bad + r1 + 0x6C, 0x0100u); },
         "I: an observational record with a service decision");
    CASE(put64(bad + r0 + 0x78, 0u), "G: a re-arm flag with an invalid timestamp");
#undef CASE
#undef REFIX
    printf("   11 producer lies refused by the cross-field rules, CRCs recomputed every time\n");
}

/* §8: a disagreement can omit MORE THAN ONE source. The aggregate state must
 * never let a partial recovery read as a full one, and the per-bit truth must be
 * derivable from stored fields alone. */
static void test_followup_is_per_source_bit(void)
{
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_diag store2[8];
    uint8_t w[GBP_BLOCK_SIZE];
    printf("-- two omitted sources, one back and one not: that is NOT 'present'\n");
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 8u);
    /* the Disc reading has BOTH sources, the majority has neither */
    window_split(w, 0x0000u, 0x0500u);
    CHECK(gbp_vstate_diag_open(&st2, 1u, 100u, w, 0x0500u, 0x0000u, GBP_VSTATE_DIAG_READ_LEAN,
                               GBP_VSTATE_DIS_SOURCE_SERVICED) == 0);
    gbp_vstate_diag_service(&st2, 0, 0x0000u, 0x0000u, 0u);
    gbp_vstate_diag_ack(&st2, 0, 0x8000u, 100u + 10u);
    gbp_vstate_diag_rearm(&st2, 0, 100u + 20u);
    CHECK(gbp_vstate_diag_arm_followup(&st2, 0) == 1);
    CHECK(st2.diags[0].disc_extra_sources == 0x0500u);
    /* the next cause carries VIDEO only: AUDIO did NOT come back */
    CHECK(gbp_vstate_diag_followup(&st2, 200u, 0x0100u, 0x0100u) == 1);
    CHECK(st2.diags[0].followup_state == GBP_VSTATE_FU_SOURCE_ABSENT_NEXT);
    CHECK(st2.sem.followup_partial == 1u);
    {   /* and the exact split is derivable from the two stored fields */
        uint16_t next_sources = (uint16_t)(st2.diags[0].next_pending_gbi & GBP_VSTATE_SRC_MASK);
        uint16_t present = (uint16_t)(st2.diags[0].disc_extra_sources & next_sources);
        uint16_t absent = (uint16_t)(st2.diags[0].disc_extra_sources & ~next_sources);
        CHECK(present == 0x0100u);
        CHECK(absent == 0x0400u);
    }
    printf("-- both back: only then is it 'present'\n");
    CHECK(gbp_vstate_diag_open(&st2, 2u, 300u, w, 0x0500u, 0x0000u, GBP_VSTATE_DIAG_READ_LEAN,
                               GBP_VSTATE_DIS_SOURCE_SERVICED) == 1);
    gbp_vstate_diag_service(&st2, 1, 0x0000u, 0x0000u, 0u);
    gbp_vstate_diag_ack(&st2, 1, 0x8000u, 300u + 10u);
    gbp_vstate_diag_rearm(&st2, 1, 300u + 20u);
    CHECK(gbp_vstate_diag_arm_followup(&st2, 1) == 1);
    CHECK(gbp_vstate_diag_followup(&st2, 400u, 0x0500u, 0x0500u) == 1);
    CHECK(st2.diags[1].followup_state == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT);
    CHECK(st2.sem.followup_partial == 1u);              /* unchanged */
    printf("-- the DISC value of the next read is stored but never decides\n");
    CHECK(gbp_vstate_diag_open(&st2, 3u, 500u, w, 0x0500u, 0x0000u, GBP_VSTATE_DIAG_READ_LEAN,
                               GBP_VSTATE_DIS_SOURCE_SERVICED) == 2);
    gbp_vstate_diag_service(&st2, 2, 0x0000u, 0x0000u, 0u);
    gbp_vstate_diag_ack(&st2, 2, 0x8000u, 500u + 10u);
    gbp_vstate_diag_rearm(&st2, 2, 500u + 20u);
    CHECK(gbp_vstate_diag_arm_followup(&st2, 2) == 1);
    /* the next read's Disc claims both, its majority claims neither: ABSENT */
    CHECK(gbp_vstate_diag_followup(&st2, 600u, 0x0000u, 0x0500u) == 1);
    CHECK(st2.diags[2].followup_state == GBP_VSTATE_FU_SOURCE_ABSENT_NEXT);
    CHECK(st2.diags[2].next_pending_disc == 0x0500u);   /* preserved, not consulted */
    CHECK(st2.diags[2].next_pending_gbi == 0x0000u);
    printf("   partial=%lu present=%lu absent=%lu\n", (unsigned long)st2.sem.followup_partial,
           (unsigned long)st2.sem.followup_present, (unsigned long)st2.sem.followup_absent);
}

/* §36 and §38: the v4 file with no record at all, and a card that dies at each
 * of the new sections. */
static void test_v4_count_zero_and_partial_saves(void)
{
    static uint8_t file[1u << 20];
    static uint8_t bad[1u << 20];
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_result r2;
    static struct gbp_vstate_diag store2[4];
    struct gbp_vstate_config c2;
    struct gbp_vstatedump_info info, parsed;
    struct memsink sink;
    static uint8_t small[1024];
    uint64_t written;
    long full, rc;
    unsigned i;
    const struct gbp_vstate_semantic *sem;
    printf("-- a v4 file with NO diagnostic still carries the semantic block\n");
    memset(&r2, 0, sizeof r2);
    cfg_default(&c2);
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 4u);
    memset(&info, 0, sizeof info);
    gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "synthetic");
    sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    full = gbp_vstatedump_stream(&info, &st2, &r2, &c2, chunk, sizeof chunk, sink_mem, &sink, 0);
    CHECK(full > 0);
    CHECK(info.diag_count == 0u);
    CHECK(info.diag_rec_size == GBP_VSTATEDUMP_DIAG_REC_V4);   /* stated even with no record */
    CHECK(info.semantic_size == GBP_VSTATEDUMP_SEMANTIC_SIZE);
    CHECK(info.off_diag == info.off_semantic + GBP_VSTATEDUMP_SEMANTIC_SIZE);
    CHECK(info.off_video_raw == info.off_diag);                /* a zero-length array */
    {
        const uint8_t *sb = 0, *dg = (const uint8_t *)1;
        struct gbp_vstate_semantic back;
        CHECK(gbp_vstatedump_parse_v4(file, (size_t)full, &parsed, 0, 0, 0, 0, &sb, &dg, 0, 0) == 0);
        CHECK(dg == 0);                                        /* no record to point at */
        CHECK(sb != 0);                                        /* the block is always there */
        CHECK(gbp_vstatedump_decode_semantic(sb, &back) == 0);
        CHECK(back.disagreements_total == 0u);
        CHECK(back.gap[0].min_ticks == GBP_VSTATE_GAP_NONE);   /* sentinels survive */
        sem = &back;
        (void)sem;
    }

    printf("-- a card that dies at each new section: partial, refused, result intact\n");
    {
        uint8_t w[GBP_BLOCK_SIZE];
        window_split(w, 0x0100u, 0x0500u);
        CHECK(gbp_vstate_diag_open(&st2, 3u, 300u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                                   GBP_VSTATE_DIS_SOURCE_SERVICED) == 0);
        gbp_vstate_diag_close(&st2, 0u);
        memset(&info, 0, sizeof info);
        gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "synthetic");
        sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.failed = 0; sink.fail_after = 0;
        full = gbp_vstatedump_stream(&info, &st2, &r2, &c2, small, sizeof small, sink_mem, &sink, 0);
        CHECK(full > 0);
    }
    {   /* the card refuses from the very first byte */
        struct gbp_vstate_diag before = st2.diags[0];
        struct gbp_vstatedump_info i2;
        memset(&i2, 0, sizeof i2);
        gbp_vstatedump_set_identity(&i2, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "synthetic");
        sink.buf = bad; sink.cap = 0; sink.n = 0; sink.failed = 0; sink.fail_after = 0;
        written = 0xDEADBEEFu;
        rc = gbp_vstatedump_stream(&i2, &st2, &r2, &c2, small, sizeof small, sink_mem, &sink, &written);
        CHECK(rc == -4);
        CHECK(written == 0u);
        CHECK(memcmp(&before, &st2.diags[0], sizeof before) == 0);
    }
    /* Then at each new section. The sink refuses a whole buffer, so the injection
     * point is the last 1 KiB boundary at or before the offset; the last usable
     * one is clamped to the final whole buffer of the file. */
    {
        long last = (full / (long)sizeof small) * (long)sizeof small;
        long points[4];
        points[0] = (long)info.off_semantic;          /* the block is due */
        points[1] = (long)info.off_semantic + 512;    /* part way through it */
        points[2] = (long)info.off_diag + 40;         /* part way through the record */
        points[3] = (long)info.off_footer;            /* the footer is due */
        for (i = 0; i < 4u; i++) {
            struct gbp_vstate_diag before = st2.diags[0];
            struct gbp_vstatedump_info i2;
            long fa = (points[i] / (long)sizeof small) * (long)sizeof small;
            if (fa > last) fa = last;
            if (fa < (long)sizeof small) fa = (long)sizeof small;
            memset(&i2, 0, sizeof i2);
            gbp_vstatedump_set_identity(&i2, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "synthetic");
            sink.buf = bad; sink.cap = sizeof bad; sink.n = 0; sink.failed = 0;
            sink.fail_after = (int)fa;
            written = 0;
            rc = gbp_vstatedump_stream(&i2, &st2, &r2, &c2, small, sizeof small, sink_mem, &sink, &written);
            CHECK(rc == -4);
            CHECK(written == (uint64_t)sink.n);
            CHECK(written == (uint64_t)fa);
            CHECK(written < (uint64_t)full);
            CHECK(memcmp(&before, &st2.diags[0], sizeof before) == 0);  /* RAM untouched */
            CHECK(gbp_vstatedump_parse_v4(bad, (size_t)sink.n, &parsed, 0, 0, 0, 0, 0, 0, 0, 0) < 0);
        }
    }
    printf("   count=0 file valid, 5 injection points refused, the record never moved\n");
}

/* §14/§15: the quarantine must land on the frame that CONSUMES the block, even
 * when that block is itself a frame boundary. This test fails if the flag is
 * applied before the boundary closes the previous frame. */
static void test_quarantine_lands_on_the_consuming_frame(void)
{
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    struct gbp_vstate_step step;
    uint8_t first4_plain[4] = { 0x00, 0x00, 0x00, 0x00 };
    uint8_t first4_bound[4] = { 0x80, 0x80, 0x00, 0x00 };   /* both predicates: a boundary */
    unsigned i;
    printf("-- a majority-extra block that IS a boundary quarantines the NEW frame\n");
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    /* frame 0: a clean 40-block interval opened by a boundary */
    gbp_vstate_block(&st2, 0, 0, first4_bound, 1000u, 0x1111u, 0u, &step);
    for (i = 1; i < 40u; i++)
        gbp_vstate_block(&st2, 0, 0, first4_plain, 1000u + i, 0x1111u, 0u, &step);
    CHECK(st2.frames_n == 0u);                      /* not closed until the next boundary */
    /* the next boundary block is the suspect one */
    gbp_vstate_block_majority_extra(&st2);
    gbp_vstate_block(&st2, 0, 0, first4_bound, 2000u, 0x2222u, 0u, &step);
    CHECK(st2.frames_n == 1u);                      /* frame 0 closed here */
    /* frame 0 must be untouched: it never contained the suspect block */
    CHECK((st2.frames[0].flags & GBP_VSTATE_F_MAJORITY_EXTRA) == 0u);
    CHECK(st2.frames[0].completeness == GBP_VSTATE_FRAME_COMPLETE_40);
    /* and the frame being assembled now - the one that DID consume it - is flagged */
    CHECK((st2.cur_flags & GBP_VSTATE_F_MAJORITY_EXTRA) != 0u);
    CHECK((st2.cur_flags & GBP_VSTATE_F_ANOMALY) != 0u);
    CHECK(st2.sem.frames_quarantined == 1u);
    /* close it and confirm it is out of the science */
    for (i = 1; i < 40u; i++)
        gbp_vstate_block(&st2, 0, 0, first4_plain, 2000u + i, 0x2222u, 0u, &step);
    gbp_vstate_block(&st2, 0, 0, first4_bound, 3000u, 0x3333u, 0u, &step);
    CHECK(st2.frames_n == 2u);
    CHECK((st2.frames[1].flags & GBP_VSTATE_F_MAJORITY_EXTRA) != 0u);
    CHECK((st2.frames[1].flags & GBP_VSTATE_F_ANOMALY) != 0u);
    CHECK((st2.frames[1].flags & GBP_VSTATE_F_COUNTED) == 0u);
    CHECK((st2.frames[1].flags & GBP_VSTATE_F_BASELINE) == 0u);

    printf("-- a partially built frame is invalidated as a whole by a late suspect block\n");
    {
        struct gbp_vstate st3;
        static struct gbp_vstate_frame f3[GBP_VSTATE_MAX_FRAMES];
        static struct gbp_vstate_event e3[GBP_VSTATE_MAX_EVENTS];
        gbp_vstate_init(&st3, f3, GBP_VSTATE_MAX_FRAMES, e3, GBP_VSTATE_MAX_EVENTS,
                        raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
        gbp_vstate_block(&st3, 0, 0, first4_bound, 1000u, 0x4444u, 0u, &step);
        for (i = 1; i < 20u; i++)
            gbp_vstate_block(&st3, 0, 0, first4_plain, 1000u + i, 0x4444u, 0u, &step);
        gbp_vstate_block_majority_extra(&st3);         /* block 21 is the suspect one */
        gbp_vstate_block(&st3, 0, 0, first4_plain, 1020u, 0x4444u, 0u, &step);
        for (i = 21; i < 40u; i++)
            gbp_vstate_block(&st3, 0, 0, first4_plain, 1000u + i, 0x4444u, 0u, &step);
        gbp_vstate_block(&st3, 0, 0, first4_bound, 2000u, 0x5555u, 0u, &step);
        CHECK(st3.frames_n == 1u);
        CHECK(st3.frames[0].blocks == 40u);
        CHECK((st3.frames[0].flags & GBP_VSTATE_F_MAJORITY_EXTRA) != 0u);
        CHECK((st3.frames[0].flags & GBP_VSTATE_F_ANOMALY) != 0u);
        CHECK((st3.frames[0].flags & GBP_VSTATE_F_COUNTED) == 0u);   /* the 20 clean blocks do not save it */
        CHECK((st3.frames[0].flags & GBP_VSTATE_F_BASELINE) == 0u);
    }
    printf("   boundary case and mid-frame case both invalidate the right frame\n");
}

/* §11: the record of N must be completed from N+1's read even when N+1 is fatal. */
static void test_pending_record_survives_a_fatal_next_read(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- N nonfatal, N+1 fatal: N still gets its follow-up from N+1's read\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 400u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    /* from write 40: the last replica claims an extra AUDIO (SOURCE_SERVICED);
     * from write 42: it also flips an odd bit, which is NON_SOURCE and fatal */
    m.irq_force_value_from_write = 40u;
    m.irq_forced_value = 0x0100u;
    m.irq_last_replica_from_write = 40u;
    m.irq_last_replica_xor = 0x0400u;
    m.irq_nonsource_from_write = 42u;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 0);
    CHECK(res.status == GBP_VSTATE_ABORT_READ_INCONSISTENT);
    CHECK(strstr(res.reason, "non_source") != 0);
    CHECK(vstate.diags_n >= 2u);
    /* the record before the fatal one is resolved, not lost and not pending */
    {
        uint32_t i, pending = 0;
        for (i = 0; i < vstate.diags_n; i++)
            if (vstate.diags[i].followup_state == GBP_VSTATE_FU_PENDING) pending++;
        CHECK(pending == 0u);
    }
    CHECK(vstate.diags[0].classification == GBP_VSTATE_DIS_SOURCE_SERVICED);
    CHECK((vstate.diags[0].record_flags & GBP_VSTATE_DF_FOLLOWUP_FILLED) != 0u);
    CHECK(vstate.diags[vstate.diags_n - 1u].classification == GBP_VSTATE_DIS_NON_SOURCE);
    {   /* §34: the fatal record ends its transaction where it happened, so it can
         * carry no service decision, no ACK and no re-arm - and the v5 parser
         * refuses a file that says otherwise */
        const struct gbp_vstate_diag *f = &vstate.diags[vstate.diags_n - 1u];
        CHECK((f->record_flags & (GBP_VSTATE_DF_SERVICE_WRITTEN | GBP_VSTATE_DF_ACK_WRITTEN |
                                  GBP_VSTATE_DF_REARM_WRITTEN)) == 0u);
        CHECK(f->service_selected == 0u && f->ack_value == 0u);
        CHECK(f->t_ack == 0u && f->t_rearm == 0u);
        CHECK(f->followup_state != GBP_VSTATE_FU_PENDING);
    }
    printf("   %lu records, last class %s, first follow-up %s\n", (unsigned long)vstate.diags_n,
           gbp_vstate_class_name(vstate.diags[vstate.diags_n - 1u].classification),
           gbp_vstate_fu_name(vstate.diags[0].followup_state));
}

/* §20: a flag may never claim a write that did not happen. */
static void test_ack_and_rearm_flags_are_honest(void)
{
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_diag store2[4];
    uint8_t w[GBP_BLOCK_SIZE];
    printf("-- a record with no ACK and no re-arm says so, and its times stay zero\n");
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 4u);
    window_split(w, 0x0100u, 0x0500u);
    CHECK(gbp_vstate_diag_open(&st2, 1u, 100u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                               GBP_VSTATE_DIS_SOURCE_SERVICED) == 0);
    CHECK((st2.diags[0].record_flags & GBP_VSTATE_DF_ACK_WRITTEN) == 0u);
    CHECK((st2.diags[0].record_flags & GBP_VSTATE_DF_REARM_WRITTEN) == 0u);
    CHECK(st2.diags[0].t_ack == 0u && st2.diags[0].t_rearm == 0u && st2.diags[0].ack_value == 0u);
    /* the run ends here: no re-arm happened, so there can be no next cause */
    gbp_vstate_diag_close(&st2, 1u);
    CHECK(st2.diags[0].followup_state == GBP_VSTATE_FU_UNKNOWN);
    CHECK(st2.diags[0].followup_reason == GBP_VSTATE_FUR_RUN_ABORTED);
    /* and when they do happen the flags follow the writes, one at a time */
    CHECK(gbp_vstate_diag_open(&st2, 2u, 200u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                               GBP_VSTATE_DIS_SOURCE_SERVICED) == 1);
    gbp_vstate_diag_service(&st2, 1, 0x0100u, 0x0100u, 0u);
    gbp_vstate_diag_ack(&st2, 1, 0x8100u, 250u);
    CHECK((st2.diags[1].record_flags & GBP_VSTATE_DF_ACK_WRITTEN) != 0u);
    CHECK((st2.diags[1].record_flags & GBP_VSTATE_DF_REARM_WRITTEN) == 0u);
    CHECK(st2.diags[1].t_rearm == 0u);
    gbp_vstate_diag_rearm(&st2, 1, 260u);
    CHECK((st2.diags[1].record_flags & GBP_VSTATE_DF_REARM_WRITTEN) != 0u);
    printf("   flags track the writes, never the intention\n");
}

/*
 * §R4.1 / §15: THE DIRECT REGRESSION OF THE PHYSICAL DEFECT.
 *
 * vstate-0003 wrote the authoritative value, service decision, ACK and re-arm of
 * EVERY cycle into "the newest record", so a record kept absorbing later cycles
 * until the next disagreement opened a new one (GBP-HW-104). Its signature in the
 * physical file is unmistakable and measurable from the file alone: `t_ack` of
 * record i falls AFTER `t_next_cause` of record i - in 23 records out of 23 - and
 * lands just before the read of disagreement i+1.
 *
 * This scenario reproduces exactly that shape - isolated disagreements with many
 * ordinary cycles between them - and requires the opposite of it.
 */
static void test_current_cycle_fields_survive_later_cycles(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    uint32_t i, gaps = 0;
    printf("-- a record keeps the ACK and re-arm of ITS OWN cycle, whatever runs after it\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 400u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    m.irq_force_value_from_write = 40u;
    m.irq_forced_value = 0x0100u;
    m.irq_last_replica_xor = 0x0400u;
    m.irq_last_replica_from_write = 40u;
    m.irq_last_replica_period = 40u;      /* one disagreement every 20 cycles */
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(vstate.diags_n >= 3u);          /* several isolated events */
    for (i = 0; i < vstate.diags_n; i++) {
        const struct gbp_vstate_diag *d = &vstate.diags[i];
        CHECK(d->classification == GBP_VSTATE_DIS_SOURCE_SERVICED);
        /* the values of ITS OWN cycle, recomputed from ITS OWN bytes */
        CHECK(d->authoritative_value == gbp_vstate_authoritative(d->disc_value, d->gbi_value));
        CHECK(d->service_selected == (uint16_t)(d->authoritative_value & GBP_VSTATE_AV_MASK));
        CHECK(d->ack_value == (uint16_t)(d->authoritative_value | GBP_VSTATE_BIT15_MASK));
        CHECK((d->record_flags & GBP_VSTATE_DF_SERVICE_WRITTEN) != 0u);
        /* the chain of one transaction, in order */
        CHECK(d->t <= d->t_ack);
        CHECK(d->t_ack <= d->t_rearm);
        /* THE PHYSICAL SIGNATURE, which must be absent: in the v4 file t_ack came
         * AFTER the next cause, because it belonged to a later cycle. */
        if (d->followup_state == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT ||
            d->followup_state == GBP_VSTATE_FU_SOURCE_ABSENT_NEXT) {
            CHECK(d->t_ack <= d->t_next_cause);
            CHECK(d->t_rearm <= d->t_next_cause);
        }
        if (i + 1u < vstate.diags_n) {
            const struct gbp_vstate_diag *nx = &vstate.diags[i + 1u];
            /* many ordinary cycles ran in between - and none of them touched it */
            CHECK(nx->cycle > d->cycle + 1u);
            gaps++;
            CHECK(d->t_ack < nx->t);
            CHECK(d->t_rearm < nx->t);
            CHECK(d->t_next_cause < nx->t);
        }
    }
    check_invariants(&m, &res, &rl);
    printf("   %lu isolated records, %lu gaps of many cycles, every ACK inside its own cycle\n",
           (unsigned long)vstate.diags_n, (unsigned long)gaps);

    /* §41: the same property over a LONG run with ONE event near the start. This
     * is the exact shape of the physical file - 23 events in 1 114 007 cycles -
     * and the one where the old defect was most visible: record 0's t_ack sat
     * seconds after its own read, because it belonged to the last cycle before
     * the next disagreement. Here it must sit inside its own cycle, with the
     * whole rest of the run happening after it. */
    printf("-- one event, then thousands of ordinary cycles: the record does not move\n");
    {
        uint64_t own_cycle, after;
        cfg_default(&cfg);
        cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
        cfg.max_deliveries = 3000u;
        sched_reset(0xFFu);
        mock_vstate(&m, bits, 1u, 50u);
        m.irq_force_value_from_write = 40u;
        m.irq_forced_value = 0x0100u;
        m.irq_last_replica_xor = 0x0400u;
        m.irq_last_replica_from_write = 40u;
        m.irq_last_replica_period = 1u << 20;     /* exactly one event in the run */
        run_cfg(&m, &rl, &res, &cfg);
        CHECK(res.service_ok == 1);
        CHECK(vstate.diags_n == 1u);
        CHECK(res.deliveries >= 2000u);           /* thousands of cycles really ran */
        CHECK(vstate.diags[0].cycle < 100u);      /* the event was near the start */
        CHECK(vstate.diags[0].authoritative_value == 0x0100u);
        CHECK(vstate.diags[0].service_selected == 0x0100u);
        CHECK(vstate.diags[0].ack_value == 0x8100u);
        CHECK((vstate.diags[0].record_flags & GBP_VSTATE_DF_ACK_WRITTEN) != 0u);
        CHECK((vstate.diags[0].record_flags & GBP_VSTATE_DF_REARM_WRITTEN) != 0u);
        /* the mock holds the register at 0x0100 for the rest of the run, so the
         * omitted AUDIO never comes back: ABSENT is the honest verdict, and the
         * per-bit split says exactly which source it was */
        CHECK(vstate.diags[0].followup_state == GBP_VSTATE_FU_SOURCE_ABSENT_NEXT);
        CHECK((vstate.diags[0].disc_extra_sources &
               ~(vstate.diags[0].next_pending_gbi & GBP_VSTATE_SRC_MASK) & 0xFFFFu) == 0x0400u);
        CHECK((vstate.diags[0].record_flags & GBP_VSTATE_DF_FOLLOWUP_FILLED) != 0u);
        own_cycle = vstate.diags[0].t_rearm - vstate.diags[0].t;
        after = res.t_stop - vstate.diags[0].t_rearm;
        {
            /* §19, at BYTE level. The record is reconstructed from its own
             * cycle's values and compared field by field against what survived
             * 3000 later cycles; the follow-up block is the only region those
             * cycles were allowed to write, and they wrote it exactly once. */
            const struct gbp_vstate_diag *d = &vstate.diags[0];
            CHECK(d->disc_value == 0x0500u && d->gbi_value == 0x0100u);
            CHECK(d->delta == 0x0400u && d->disc_extra_sources == 0x0400u);
            CHECK(d->majority_extra_sources == 0u);
            CHECK(d->classification == GBP_VSTATE_DIS_SOURCE_SERVICED);
            CHECK(d->read_kind == GBP_VSTATE_DIAG_READ_LEAN);
            CHECK(d->attempts == 1u);
            CHECK(d->payload_source == 0u && d->payload_crc32 == 0u && d->payload_first_word == 0u);
            CHECK((d->record_flags & (GBP_VSTATE_DF_PAYLOAD_VALID | GBP_VSTATE_DF_PAYLOAD_SECOND |
                                      GBP_VSTATE_DF_FRAME_QUARANTINED | GBP_VSTATE_DF_SOURCE_DEFERRED |
                                      GBP_VSTATE_DF_SERVICE_INCOMPLETE)) == 0u);
            CHECK(d->record_flags == (GBP_VSTATE_DF_FOLLOWUP_FILLED | GBP_VSTATE_DF_ACK_WRITTEN |
                                      GBP_VSTATE_DF_REARM_WRITTEN | GBP_VSTATE_DF_SERVICE_WRITTEN));
            /* the raw bytes still recompute to the readings the record stores */
            CHECK(gbp_irq_value_disc(d->raw) == d->disc_value);
            CHECK(gbp_irq_value_gbi(d->raw) == d->gbi_value);
        }
        /* the record's whole narrative fits inside ONE cycle, and the run went on
         * for orders of magnitude longer without touching it */
        CHECK(vstate.diags[0].t_ack >= vstate.diags[0].t);
        CHECK(vstate.diags[0].t_rearm >= vstate.diags[0].t_ack);
        CHECK(vstate.diags[0].t_next_cause >= vstate.diags[0].t_rearm);
        CHECK(after > own_cycle * 100u);
        printf("   1 record, %lu deliveries; its cycle spans %lu ticks, the run went on for %lu\n",
               (unsigned long)res.deliveries, (unsigned long)own_cycle, (unsigned long)after);
    }
}

/*
 * §34: the operation stream under EVERY direction of disagreement, against a
 * reference run that selects the same sources without disagreeing. The handle
 * fix is RAM bookkeeping: if any of these streams differed by one operation, it
 * would not be.
 */
static void test_every_direction_costs_no_operation(void)
{
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    unsigned k;
    /* forced value, last-replica XOR, expected direction */
    static const struct { uint16_t forced, xorv; const char *what; } cases[] = {
        { 0x0100u, 0x0400u, "Disc-extra AUDIO (0500 vs 0100)" },
        { 0x0500u, 0x0400u, "majority-extra AUDIO (0100 vs 0500)" },
        { 0x0500u, 0x0100u, "majority-extra VIDEO (0400 vs 0500)" },
        { 0x0400u, 0x0100u, "Disc-extra VIDEO (0500 vs 0400)" },
    };
    printf("-- every direction of disagreement: the same device stream as agreeing on the same value\n");
    for (k = 0; k < sizeof cases / sizeof cases[0]; k++) {
        struct gbp_mock ref, dis;
        struct ringlog rl;
        static struct gbp_vstate_result res;
        unsigned ref_reads, dis_reads;
        uint32_t total;
        cfg_default(&cfg);
        cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
        cfg.max_deliveries = 150u;
        /* the reference agrees on the value the POLICY will service - the
         * majority - so the selection, the drains, the ACK and the re-arm are
         * the same by construction and only the disagreement differs */
        sched_reset(0xFFu);
        mock_vstate(&ref, bits, 1u, 50u);
        ref.irq_force_value_from_write = 40u;
        ref.irq_forced_value = cases[k].forced;
        run_cfg(&ref, &rl, &res, &cfg);
        CHECK(res.service_ok == 1);
        CHECK(vstate.sem.disagreements_total == 0u);
        ref_reads = irq_reads(&ref);
        sched_reset(0xFFu);
        mock_vstate(&dis, bits, 1u, 50u);
        dis.irq_force_value_from_write = 40u;
        dis.irq_forced_value = cases[k].forced;
        dis.irq_last_replica_from_write = 40u;
        dis.irq_last_replica_xor = cases[k].xorv;
        run_cfg(&dis, &rl, &res, &cfg);
        CHECK(res.service_ok == 1);
        total = vstate.sem.disagreements_total;
        CHECK(total > 0u);
        dis_reads = irq_reads(&dis);
        CHECK(dis_reads == ref_reads);
        CHECK(dis.nops == ref.nops);
        CHECK(dis.bulk_reads == ref.bulk_reads);
        CHECK(dis.irq_writes == ref.irq_writes);
        CHECK(dis.transfers == ref.transfers);
        CHECK(dis.violation_mask == 0u);
        printf("   %-34s %u reads, %u ops, %lu disagreements, identical stream\n",
               cases[k].what, dis_reads, dis.nops, (unsigned long)total);
    }
}

/*
 * §36 / §37: the quarantine, the deferral and the payload provenance belong to
 * the record that SELECTED the service. An observational record opened later in
 * the same transaction must receive none of them - under the old "latest record"
 * rule it would have received all three.
 */
static void test_markers_land_on_the_service_record_only(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    uint32_t i, marked = 0, observational = 0;
    printf("-- majority-extra VIDEO with witnesses in the same cycle: only the owner is marked\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 8u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    /* the last replica drops VIDEO: the majority carries it and the Disc reading
     * does not, so the VIDEO block drained this cycle is quarantined */
    m.irq_last_replica_xor = 0x0100u;
    m.irq_last_replica_from_write = 4u;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    CHECK(vstate.sem.majority_extra_video_services > 0u);
    CHECK(vstate.sem.frames_quarantined > 0u);
    for (i = 0; i < vstate.diags_n; i++) {
        const struct gbp_vstate_diag *d = &vstate.diags[i];
        int is_obs = (d->read_kind == GBP_VSTATE_DIAG_READ_POSTDRAIN ||
                      d->read_kind == GBP_VSTATE_DIAG_READ_POSTACK);
        if (is_obs) {
            observational++;
            /* not one marker of the transaction reached the witness */
            CHECK((d->record_flags & (GBP_VSTATE_DF_FRAME_QUARANTINED | GBP_VSTATE_DF_SOURCE_DEFERRED |
                                      GBP_VSTATE_DF_PAYLOAD_VALID | GBP_VSTATE_DF_PAYLOAD_SECOND |
                                      GBP_VSTATE_DF_SERVICE_WRITTEN)) == 0u);
            CHECK(d->payload_source == 0u && d->payload_crc32 == 0u);
        } else if (d->record_flags & GBP_VSTATE_DF_FRAME_QUARANTINED) {
            marked++;
            /* and the marker is only ever on a record whose OWN majority-extra
             * sources contain VIDEO: the provenance is the record's own */
            CHECK((d->majority_extra_sources & GBP_VSTATE_SRC_VIDEO) != 0u);
            CHECK((d->record_flags & GBP_VSTATE_DF_PAYLOAD_VALID) != 0u);
            CHECK(d->payload_source == GBP_VSTATE_SRC_VIDEO);
        }
    }
    CHECK(observational > 0u);
    CHECK(marked > 0u);
    check_invariants(&m, &res, &rl);
    printf("   %lu quarantined owners, %lu witnesses, none of them marked\n",
           (unsigned long)marked, (unsigned long)observational);
}

/*
 * §13: THE FAILURE LIFECYCLE. An ACK or a re-arm that did not complete may not
 * leave a flag saying it did, and a record whose transaction died before the
 * re-arm must never be armed as though a next cause were expected. The run ends
 * either way; what is being checked is what the record then says about itself.
 */
static void test_ack_and_rearm_failures_leave_no_false_claim(void)
{
    unsigned at, saw_ack_fail = 0, saw_rearm_fail = 0;
    printf("-- a write that did not complete never becomes a flag that says it did\n");
    for (at = 41u; at <= 44u; at++) {
        struct gbp_mock m;
        struct ringlog rl;
        static struct gbp_vstate_result res;
        struct gbp_vstate_config cfg;
        const uint16_t bits[1] = { 0x0500u };
        const struct gbp_vstate_diag *d;
        cfg_default(&cfg);
        cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
        cfg.max_deliveries = 200u;
        sched_reset(0xFFu);
        mock_vstate(&m, bits, 1u, 50u);
        m.irq_force_value_from_write = 40u;
        m.irq_forced_value = 0x0100u;
        m.irq_last_replica_xor = 0x0400u;
        m.irq_last_replica_from_write = 40u;
        m.irq_write_fail_at = at;                  /* one IRQ write reports a timeout */
        run_cfg(&m, &rl, &res, &cfg);
        if (vstate.diags_n == 0u) continue;
        d = &vstate.diags[vstate.diags_n - 1u];
        if (res.status == GBP_VSTATE_ACK_WRITE_FAILED) {
            saw_ack_fail++;
            CHECK((d->record_flags & GBP_VSTATE_DF_ACK_WRITTEN) == 0u);
            CHECK((d->record_flags & GBP_VSTATE_DF_REARM_WRITTEN) == 0u);
            CHECK(d->ack_value == 0u && d->t_ack == 0u && d->t_rearm == 0u);
        } else if (res.status == GBP_VSTATE_REARM_WRITE_FAILED) {
            saw_rearm_fail++;
            CHECK((d->record_flags & GBP_VSTATE_DF_ACK_WRITTEN) != 0u);
            CHECK((d->record_flags & GBP_VSTATE_DF_REARM_WRITTEN) == 0u);
            CHECK(d->t_rearm == 0u);
        }
        if (res.status == GBP_VSTATE_ACK_WRITE_FAILED || res.status == GBP_VSTATE_REARM_WRITE_FAILED) {
            /* no re-arm was written, so no next cause was ever invited: the
             * record is closed by the teardown, never left pending, and never
             * given a follow-up verdict it could not have observed */
            CHECK(vstate.diag_wait == -1);
            CHECK(d->followup_state == GBP_VSTATE_FU_UNKNOWN);
            CHECK(d->followup_reason == GBP_VSTATE_FUR_RUN_ABORTED);
            CHECK(d->t_next_cause == 0u && d->next_pending_gbi == 0u);
            CHECK((d->record_flags & GBP_VSTATE_DF_FOLLOWUP_FILLED) == 0u);
        }
        {   /* and no record anywhere in the store stayed pending */
            uint32_t i, pending = 0;
            for (i = 0; i < vstate.diags_n; i++)
                if (vstate.diags[i].followup_state == GBP_VSTATE_FU_PENDING) pending++;
            CHECK(pending == 0u);
        }
    }
    CHECK(saw_ack_fail > 0u);
    CHECK(saw_rearm_fail > 0u);
    printf("   %u ACK failures and %u re-arm failures, every record honest about its own writes\n",
           saw_ack_fail, saw_rearm_fail);
}

/*
 * §10 / §R4.4: TWO DIAGNOSTICS IN ONE TRANSACTION. A verify cycle reads the
 * window three times - PRESVC, POSTDRAIN and POSTACK - and all three can
 * disagree. Only the PRESVC record selected the service, so only it may carry
 * the ACK, the re-arm and the follow-up; the other two are complete when they are
 * opened and claim nothing about service.
 */
static void test_same_cycle_multiple_diagnostics(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    uint32_t i, presvc = 0, postdrain = 0, postack = 0, same_cycle = 0;
    printf("-- PRESVC + POSTDRAIN + POSTACK in one transaction: one owner, two witnesses\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 8u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    /* Early enough to fall inside the VERIFY cycles, which are the only ones that
     * take the POSTDRAIN and POSTACK snapshots. The register value itself is NOT
     * forced here: only the last replica is XORed, so the POSTACK window keeps
     * its bit 15 and the read is a genuine disagreement rather than a broken
     * shape. The majority carries AUDIO, the Disc reading does not. */
    m.irq_last_replica_xor = 0x0400u;
    m.irq_last_replica_from_write = 4u;
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);
    for (i = 0; i < vstate.diags_n; i++) {
        const struct gbp_vstate_diag *d = &vstate.diags[i];
        if (d->read_kind == GBP_VSTATE_DIAG_READ_PRESVC) presvc++;
        if (d->read_kind == GBP_VSTATE_DIAG_READ_POSTDRAIN) postdrain++;
        if (d->read_kind == GBP_VSTATE_DIAG_READ_POSTACK) postack++;
        if (d->read_kind == GBP_VSTATE_DIAG_READ_POSTDRAIN || d->read_kind == GBP_VSTATE_DIAG_READ_POSTACK) {
            /* the observational contract, exactly (§R4.5) */
            CHECK(d->service_selected == 0u);
            CHECK(d->ack_value == 0u && d->t_ack == 0u && d->t_rearm == 0u);
            CHECK((d->record_flags & (GBP_VSTATE_DF_SERVICE_WRITTEN | GBP_VSTATE_DF_ACK_WRITTEN |
                                      GBP_VSTATE_DF_REARM_WRITTEN | GBP_VSTATE_DF_PAYLOAD_VALID |
                                      GBP_VSTATE_DF_FRAME_QUARANTINED | GBP_VSTATE_DF_SOURCE_DEFERRED |
                                      GBP_VSTATE_DF_SERVICE_INCOMPLETE)) == 0u);
            CHECK(d->followup_state == GBP_VSTATE_FU_UNKNOWN);
            CHECK(d->followup_reason == GBP_VSTATE_FUR_OBSERVATIONAL);
            CHECK(d->t_next_cause == 0u);
        } else {
            /* the owner of the transaction kept its own narrative */
            CHECK((d->record_flags & GBP_VSTATE_DF_SERVICE_WRITTEN) != 0u);
            CHECK((d->record_flags & GBP_VSTATE_DF_ACK_WRITTEN) != 0u);
            CHECK(d->ack_value == (uint16_t)(d->authoritative_value | GBP_VSTATE_BIT15_MASK));
        }
        if (i > 0u && d->cycle == vstate.diags[i - 1u].cycle) same_cycle++;
    }
    /* all three combinations §10 asks for, several times over */
    CHECK(presvc >= 3u);
    CHECK(postdrain >= 3u);
    CHECK(postack >= 3u);
    CHECK(same_cycle >= 6u);            /* records really did share a transaction */
    CHECK(vstate.sem.observational_disagreements == postdrain + postack);
    CHECK(vstate.sem.service_selecting_disagreements == presvc + (vstate.diags_n - presvc - postdrain - postack));
    /* and the observational reads added NO device operation: the drains, the ACK
     * and the re-arm are the ones the cycle would have done anyway - exactly one
     * of each per delivery, with the disagreements changing none of the counts */
    CHECK(res.acks == res.deliveries);
    CHECK(res.rearms == res.deliveries || !res.service_ok);
    CHECK(res.isr_w1c == res.deliveries);
    CHECK(res.main_w1c == 0u);
    check_invariants(&m, &res, &rl);
    printf("   %lu PRESVC, %lu POSTDRAIN, %lu POSTACK, %lu sharing a cycle\n",
           (unsigned long)presvc, (unsigned long)postdrain, (unsigned long)postack,
           (unsigned long)same_cycle);
}

/* §49: a long run whose disagreements outnumber the store. The run must not stop,
 * the store must cap without overwriting, and nothing may grow with deliveries. */
static void test_more_disagreements_than_the_store(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- more disagreements than the store holds: capped, counted, and still running\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 700u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    m.irq_force_value_from_write = 40u;
    m.irq_forced_value = 0x0100u;
    m.irq_last_replica_from_write = 40u;
    m.irq_last_replica_xor = 0x0400u;       /* every cycle past the stage disagrees */
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.service_ok == 1);                              /* never a service failure */
    CHECK(res.stop == GBP_VSTATE_STOP_DELIVERY_CAP);
    CHECK(vstate.sem.disagreements_total > GBP_VSTATE_MAX_DISAGREEMENTS);
    CHECK(vstate.diags_n == GBP_VSTATE_MAX_DISAGREEMENTS);   /* exactly the cap */
    CHECK(vstate.sem.store_capped == 1u);
    CHECK(vstate.sem.diagnostics_preserved == GBP_VSTATE_MAX_DISAGREEMENTS);
    CHECK(vstate.sem.diagnostics_not_preserved ==
          vstate.sem.disagreements_total - GBP_VSTATE_MAX_DISAGREEMENTS);
    /* nothing was overwritten: the first record is still the first event */
    CHECK(vstate.diags[0].cycle < vstate.diags[GBP_VSTATE_MAX_DISAGREEMENTS - 1u].cycle);
    /* every preserved record is resolved; FU_PENDING may never survive */
    {
        uint32_t i, pending = 0;
        for (i = 0; i < vstate.diags_n; i++)
            if (vstate.diags[i].followup_state == GBP_VSTATE_FU_PENDING) pending++;
        CHECK(pending == 0u);
    }
    CHECK(vstate.sem.delta_hist[gbp_vstate_hist_index(0x0400u)] == vstate.sem.disagreements_total);
    /* §R3.15b: a disagreement emits NO event. 681 of them must not be able to
     * fill a 4096-entry store and turn a nonfatal condition into an
     * event_store_cap stop. */
    CHECK(vstate.events_n < 64u);
    CHECK(vstate.event_store_full == 0u);
    CHECK(res.stop != GBP_VSTATE_STOP_EVENT_STORE_CAP);
    /* and the report stays bounded: 8 records in full, whatever the total */
    {
        int shown = 0, i;
        for (i = 0; i < 12; i++) {
            char tag[32];
            snprintf(tag, sizeof tag, "READDISAGREE i=%d ", i);
            if (line_index(&rl, tag) >= 0) shown++;
        }
        CHECK(shown == (int)GBP_VSTATE_DIAG_LOG_MAX);
        CHECK(line_index(&rl, "READDISAGREEMORE ") >= 0);
    }
    check_invariants(&m, &res, &rl);
    {   /* §40: a FULL store serializes and parses - 256 records is a valid v5
         * file, and every one of them passes the cross-field invariants */
        static uint8_t file[1u << 22];
        struct gbp_vstatedump_info info, parsed;
        struct memsink sink;
        long n;
        memset(&info, 0, sizeof info);
        CHECK(gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0004",
                                          "gbp-video-state-probe", "synthetic") == 0);
        sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
        n = gbp_vstatedump_stream(&info, &vstate, &res, &cfg, chunk, sizeof chunk, sink_mem, &sink, 0);
        CHECK(n > 0);
        CHECK(info.diag_count == GBP_VSTATEDUMP_MAX_DIAGS);
        CHECK(gbp_vstatedump_parse_v5(file, (size_t)n, &parsed, 0, 0, 0, 0, 0, 0, 0, 0) == 0);
        CHECK(parsed.version == 5u);
        CHECK(parsed.diag_count == 256u);
        CHECK(parsed.diag_flags == GBP_VSTATEDUMP_DIAGF_CAPPED);
        {   /* and 257 declared is refused, with both CRCs made valid again */
            static uint8_t bad[1u << 22];
            memcpy(bad, file, (size_t)n);
            put32(bad + 0x1E4, 257u);
            put32(bad + 0x1FC, gbp_crc32(bad, 0x1FCu));
            put32(bad + info.off_footer + 8u, gbp_crc32(bad, info.off_footer));
            CHECK(gbp_vstatedump_parse_v5(bad, (size_t)n, 0, 0, 0, 0, 0, 0, 0, 0, 0) == -9);
        }
        printf("   256-record v5 file: %ld bytes, strict-parsed, capped flag set\n", n);
    }
    printf("   %lu disagreements, %lu preserved, %lu not preserved, run stopped at %s\n",
           (unsigned long)vstate.sem.disagreements_total, (unsigned long)vstate.diags_n,
           (unsigned long)vstate.sem.diagnostics_not_preserved, res.stop_name);
}

static void test_long_scan(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[2] = { 0x0500u, 0x0400u };
    printf("-- the full nominal scan: ~639 000 deliveries, no overflow, the stores stay bounded\n");
    cfg_default(&cfg);
    /* This scenario runs at the REAL time base and the REAL measured cadence, because its whole
     * point is the scale: 40.5 MHz, 120 s of valid observation, and the physical inter-block gap
     * GBP-VIDEO-001 measured (11 891 ticks median). VIDEO and AUDIO alternate, as the physical
     * source pattern did, so the delivery count lands in the design's estimated range. */
    cfg.a.tb_hz = GBP_TIME64_NOMINAL_HZ;
    cfg.min_valid_observation_s = 120u;
    cfg.min_valid_observation_ticks = gbp_time64_from_seconds(GBP_TIME64_NOMINAL_HZ, 120u);
    cfg.hard_wallclock_ticks = gbp_time64_from_seconds(GBP_TIME64_NOMINAL_HZ, 400u);
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 2u, 50u);
    m.bulk_tick_advance[1] = 11891u;           /* the physically measured inter-block gap */
    /* Start the 64-bit clock just below the 32-bit wrap so the run CROSSES it. On hardware the
     * elapsed time alone crosses (120 s at 40.5 MHz = 4.86e9 ticks > 2^32); at this synthetic
     * 1 MHz base it does not, so the origin is shifted to reproduce exactly the condition that
     * would corrupt a u32 timestamp: absolute values on both sides of 0x100000000. */
    m.tick64_origin = 0xFFFFFFFFull - 40000000ull;
    run_cfg(&m, &rl, &res, &cfg);
    printf("   deliveries=%lu video=%lu frames=%lu events=%lu valid=%llu capture=%llu\n",
           (unsigned long)res.deliveries, (unsigned long)res.video_completed, (unsigned long)vstate.frames_n,
           (unsigned long)vstate.events_n, (unsigned long long)res.valid_observation_elapsed,
           (unsigned long long)res.capture_elapsed);
    CHECK(res.service_ok == 1);
    CHECK(res.stop == GBP_VSTATE_STOP_NOMINAL_NEGATIVE);
    CHECK(res.status == GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL);
    CHECK(res.deliveries > 500000u);                     /* the design's estimated order of magnitude */
    CHECK(res.video_completed > 250000u);
    CHECK(vstate.frames_n > 6000u);
    CHECK(res.deliveries > (uint32_t)0xFFFFu);           /* far past anything a u16 could hold */
    CHECK(vstate.frames_n < GBP_VSTATE_MAX_FRAMES);      /* the frame store was NOT the stop */
    CHECK(vstate.frame_store_full == 0);
    CHECK(vstate.event_store_full == 0);
    CHECK(vstate.events_n < GBP_VSTATE_MAX_EVENTS);
    CHECK(res.counter_overflow == 0u);                   /* no u32 counter wrapped */
    CHECK(res.valid_observation_elapsed >= cfg.min_valid_observation_ticks);
    /* the run really crossed the 32-bit boundary, which is what would break a truncated path */
    CHECK(res.t_capture_start < (uint64_t)0x100000000ull);
    CHECK(res.t_stop > (uint64_t)0x100000000ull);
    CHECK((uint32_t)res.t_stop < (uint32_t)res.t_capture_start);   /* a u32 view really does regress */
    CHECK(res.t_stop > res.t_capture_start);                      /* the u64 view does not */
    {   /* every stored frame timestamp is monotonic across the wrap */
        uint32_t i, back = 0;
        for (i = 1; i < vstate.frames_n; i++)
            if (frames[i].t_first_block < frames[i - 1u].t_first_block) back++;
        CHECK(back == 0u);
    }
    {   /* and so is every event, by sequence number and by timestamp */
        uint32_t i, back = 0, seq_bad = 0;
        for (i = 1; i < vstate.events_n; i++) {
            if (events[i].t < events[i - 1u].t) back++;
            if (events[i].seq != events[i - 1u].seq + 1u) seq_bad++;
        }
        CHECK(back == 0u);
        CHECK(seq_bad == 0u);
    }
    CHECK(res.bytes_video == (uint64_t)res.video_completed * GBP_VSTATE_VIDEO_BLOCK_SIZE);
    CHECK(vstate.cost.count == (uint64_t)res.video_completed);
    /* the bounded records really are bounded */
    CHECK(res.cyc_first_n == GBP_VSTATE_CYC_FIRST);
    CHECK(res.cyc_last_n == GBP_VSTATE_CYC_LAST);
    CHECK(cyc_last[0].index != 0u);      /* the rolling window really moved off the first cycles */
    check_invariants(&m, &res, &rl);
}

/* Writes one synthetic run's sidecar, so the host parser is checked against the REAL C writer
 * rather than against a Python re-implementation of it. */
static int dump_sidecar(const char *path)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vstatedump_info info;
    struct memsink sink;
    const uint16_t bits[2] = { 0x0500u, 0x0400u };
    FILE *f;
    long n;
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 4000u;
    sched_reset(0xFFu);
    sched_change(241u, 0xF0u);
    sched_change(1041u, 0xA0u);
    sched_change(1841u, 0x50u);
    mock_vstate(&m, bits, 2u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    memset(&info, 0, sizeof info);
    if (gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "host-synthetic") != 0)
        return 2;
    sink.buf = sidecar; sink.cap = sizeof sidecar; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    n = gbp_vstatedump_stream(&info, &vstate, &res, &cfg, chunk, sizeof chunk, sink_mem, &sink, 0);
    if (n <= 0) return 3;
    f = fopen(path, "wb");
    if (!f) return 4;
    if (fwrite(sidecar, 1, (size_t)n, f) != (size_t)n) { fclose(f); return 5; }
    fclose(f);
    printf("wrote %ld bytes: frames=%lu events=%lu episodes=%lu cycles=%lu raw=%lu audio=%lu\n",
           n, (unsigned long)info.frame_count, (unsigned long)info.event_count,
           (unsigned long)info.episode_count, (unsigned long)info.cycle_count,
           (unsigned long)info.video_raw_frames, (unsigned long)info.audio_raw_count);
    return 0;
}

/*
 * Section 8 of the design: the SAME synthetic scenario run WITH and WITHOUT the per-block
 * signature, comparing the service cadence, the VIDEO and AUDIO rates, the ACK-to-REARM interval
 * and the next-cause timing. There is NO threshold — the design withdrew the arbitrary 25 % gate
 * for having no physical basis — so this prints a complete report and asserts that it is complete,
 * not that a number is below a constant. A reviewer reads it before any physical candidate.
 *
 * These are MOCK ticks on the host. They are NOT a hardware measurement, and Dolphin's timing
 * would not be one either. The physical half needs the real 40.5 MHz base and a real run; the
 * probe already records sig_ticks per cycle and min/median/p95/max in the sidecar header, so it
 * needs no new code.
 */
struct cadence {
    uint32_t deliveries, video, audio, frames;
    uint64_t capture, ack_to_rearm, rearm_to_next, cause_to_ack;
    uint32_t samples;
};

static void measure(struct cadence *out, int skip_signature)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[2] = { 0x0500u, 0x0400u };
    uint32_t i;
    memset(out, 0, sizeof *out);
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 4000u;
    cfg.bench_skip_signature = skip_signature;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 2u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    out->deliveries = res.deliveries;
    out->video = res.video_completed;
    out->audio = res.audio_drains;
    out->frames = vstate.frames_n;
    out->capture = res.capture_elapsed;
    for (i = 0; i < res.cyc_first_n; i++) {
        const struct gbp_vstate_cycle *c = &cyc_first[i];
        if (c->t_rearm < c->t_ack || c->t_next < c->t_rearm) continue;
        out->ack_to_rearm += c->t_rearm - c->t_ack;
        out->rearm_to_next += c->t_next - c->t_rearm;
        out->cause_to_ack += (c->t_ack > c->t_cause) ? (c->t_ack - c->t_cause) : 0u;
        out->samples++;
    }
}

static void test_bench_with_without(void)
{
    struct cadence with, without;
    printf("-- benchmark: the same scenario WITH and WITHOUT the per-block signature (MOCK ticks)\n");
    measure(&with, 0);
    measure(&without, 1);
    printf("   %-22s %12s %12s %12s\n", "quantity", "with", "without", "delta");
    printf("   %-22s %12lu %12lu %12ld\n", "deliveries", (unsigned long)with.deliveries,
           (unsigned long)without.deliveries, (long)with.deliveries - (long)without.deliveries);
    printf("   %-22s %12lu %12lu %12ld\n", "VIDEO blocks", (unsigned long)with.video,
           (unsigned long)without.video, (long)with.video - (long)without.video);
    printf("   %-22s %12lu %12lu %12ld\n", "AUDIO drains", (unsigned long)with.audio,
           (unsigned long)without.audio, (long)with.audio - (long)without.audio);
    printf("   %-22s %12lu %12lu %12ld\n", "frames assembled", (unsigned long)with.frames,
           (unsigned long)without.frames, (long)with.frames - (long)without.frames);
    printf("   %-22s %12llu %12llu %12lld\n", "capture ticks", (unsigned long long)with.capture,
           (unsigned long long)without.capture, (long long)with.capture - (long long)without.capture);
    if (with.samples && without.samples) {
        printf("   %-22s %12llu %12llu %12lld\n", "ACK->REARM (mean)",
               (unsigned long long)(with.ack_to_rearm / with.samples),
               (unsigned long long)(without.ack_to_rearm / without.samples),
               (long long)(with.ack_to_rearm / with.samples) - (long long)(without.ack_to_rearm / without.samples));
        printf("   %-22s %12llu %12llu %12lld\n", "REARM->next (mean)",
               (unsigned long long)(with.rearm_to_next / with.samples),
               (unsigned long long)(without.rearm_to_next / without.samples),
               (long long)(with.rearm_to_next / with.samples) - (long long)(without.rearm_to_next / without.samples));
        printf("   %-22s %12llu %12llu %12lld\n", "cause->ACK (mean)",
               (unsigned long long)(with.cause_to_ack / with.samples),
               (unsigned long long)(without.cause_to_ack / without.samples),
               (long long)(with.cause_to_ack / with.samples) - (long long)(without.cause_to_ack / without.samples));
    }
    printf("   reference points from the PHYSICAL GBP-VIDEO-001 run, for the eventual hardware\n"
           "   comparison: 294 us median between VIDEO blocks, 77 us median lean cycle, 2 485 ticks\n"
           "   (61 us) of VIDEO DMA, 5 327 deliveries/s. NO THRESHOLD IS APPLIED HERE.\n");
    /* the gate is that the report is COMPLETE, not that a number is below a constant */
    CHECK(with.deliveries == without.deliveries);          /* the same scenario really ran twice */
    CHECK(with.audio == without.audio);
    CHECK(with.video == without.video);
    CHECK(with.samples > 0u && without.samples > 0u);
    CHECK(with.frames > 0u);
    CHECK(without.frames == 0u);                           /* without the signature there is no frame evidence at all */
    CHECK(with.capture > 0u && without.capture > 0u);
}

/* The epoch of the hard safety budget: reconstructed from the stage's 32-bit timestamp and then
 * checked against a bracket of two real u64 reads. It must never be fabricated, never land in the
 * future, and never shorten the safety budget. */
static void test_epoch_never_fabricated(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    printf("-- the safety epoch: reconstructed, bracketed, and never invented\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 40u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.a.control_written == 1);
    CHECK(res.epoch_ok == 1);                               /* inside the bracket */
    CHECK(res.t_control_transform > 0u);
    CHECK(res.t_capture_start >= res.t_control_transform);  /* never in the future of the capture */
    CHECK(res.t_stop > res.t_control_transform);
    CHECK(res.safety_elapsed >= res.capture_elapsed);       /* the safety clock started earlier */
    CHECK(res.safety_elapsed == res.t_stop - res.t_control_transform);

    printf("-- the stage aborts before the CONTROL write: NO epoch is invented\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    mock_vstate(&m, bits, 1u, 50u);
    m.present = 0;                                          /* no GBP: the stage aborts early */
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.a.control_written == 0);
    CHECK(res.epoch_ok == -1);                              /* named, not guessed */
    CHECK(res.stop == GBP_VSTATE_STOP_FAILURE);
    CHECK(res.t_control_transform <= res.t_stop);           /* NOT a timestamp in the future */
    CHECK(res.safety_elapsed == res.t_stop - res.t_control_transform);
    CHECK(res.safety_elapsed < gbp_time64_from_seconds(TB_HZ, 60u));   /* a sane stage duration */
    CHECK(line_index(&rl, "epoch_ok=-1") >= 0);             /* and the log says so */
    /* the capture never started, so its clock reads 0 — NOT the absolute time base as a duration */
    CHECK(res.t_capture_start == 0u);
    CHECK(res.capture_elapsed == 0u);
    CHECK(res.baseline_elapsed == 0u);
    CHECK(res.valid_observation_elapsed == 0u);
    CHECK(res.valid_observation_at_target == 0u);
}

/* Section 13 of the audit: 16383, 16384 and the 16385th attempt. */
static void test_frame_store_cap_boundary(void)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    uint32_t i;
    printf("-- frame store cap at exactly 16384: no overwrite, no wrap, no write past the end\n");
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.hard_wallclock_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 40u * (GBP_VSTATE_MAX_FRAMES + 8u);
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    run_cfg(&m, &rl, &res, &cfg);
    CHECK(res.stop == GBP_VSTATE_STOP_FRAME_STORE_CAP);
    CHECK(vstate.frame_store_full == 1);
    CHECK(vstate.frames_n == GBP_VSTATE_MAX_FRAMES);
    CHECK(frames[0].index == 0u);
    CHECK(frames[GBP_VSTATE_MAX_FRAMES - 1u].index == GBP_VSTATE_MAX_FRAMES - 1u);
    CHECK(frames[GBP_VSTATE_MAX_FRAMES - 2u].index == GBP_VSTATE_MAX_FRAMES - 2u);
    /* every index is its own slot: nothing wrapped over anything */
    for (i = 0; i < GBP_VSTATE_MAX_FRAMES; i++) if (frames[i].index != i) break;
    CHECK(i == GBP_VSTATE_MAX_FRAMES);
    /* the scientific result of a run capped before its target is inconclusive, never negative */
    CHECK(res.status == GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE ||
          res.status == GBP_VSTATE_OK_STRUCTURED_CHANGE_OBSERVED);
    CHECK(res.status != GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL);
    CHECK(res.service_ok == 1);
    check_invariants(&m, &res, &rl);
    printf("   frames=%lu deliveries=%lu stop=%s\n", (unsigned long)vstate.frames_n,
           (unsigned long)res.deliveries, gbp_vstate_stop_name(res.stop));
}

/* A SYNTHETIC v3 sidecar carrying a disagreement, so the host tool can be tested against the
 * real C writer. Synthetic: the mock flips one bit of the last low replica. */
/* The same file the C round-trip test builds: a v3 sidecar whose diagnostic holds 32 DISTINCT
 * bytes, so tests/host/test_vstate.py can close the chain into the Python tool. */
static int dump_sidecar_diag_distinct(const char *path)
{
    static uint8_t file[1u << 20];
    struct gbp_vstatedump_info info;
    uint8_t pattern[GBP_BLOCK_SIZE];
    unsigned i;
    long n;
    FILE *f;
    for (i = 0; i < GBP_BLOCK_SIZE; i++) pattern[i] = (uint8_t)(0x11u + i * 7u);
    {   /* the same minimal file the round-trip test builds, through the real
         * capture entry point and the real serializer */
        struct gbp_vstate st2;
        static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
        static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
        static struct gbp_vstate_result r2;
        static struct gbp_vstate_diag store2[4];
        struct gbp_vstate_config c2;
        struct memsink sink;
        memset(&r2, 0, sizeof r2);
        cfg_default(&c2);
        gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                        raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
        gbp_vstate_diag_store(&st2, store2, 4u);
        if (gbp_vstate_diag_open(&st2, 4242u, 0x00000001FFFFFFFFULL, pattern,
                                 gbp_irq_value_disc(pattern), gbp_irq_value_gbi(pattern),
                                 GBP_VSTATE_DIAG_READ_POSTDRAIN,
                                 gbp_vstate_classify(gbp_irq_value_disc(pattern),
                                                     gbp_irq_value_gbi(pattern))) != 0) {
            /* index 0 is the only acceptable answer here */
        }
        gbp_vstate_diag_close(&st2, 0u);
        memset(&info, 0, sizeof info);
        if (gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0004",
                                        "gbp-video-state-probe", "synthetic") != 0) return 2;
        sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
        n = gbp_vstatedump_stream(&info, &st2, &r2, &c2, chunk, sizeof chunk, sink_mem, &sink, 0);
    }
    if (n <= 0) return 3;
    f = fopen(path, "wb");
    if (!f) return 4;
    if (fwrite(file, 1, (size_t)n, f) != (size_t)n) { fclose(f); return 5; }
    fclose(f);
    printf("wrote %ld bytes: v%u diag_count=%lu 32 distinct bytes, disc=%04x gbi=%04x\n", n,
           info.version, (unsigned long)info.diag_count,
           gbp_irq_value_disc(pattern), gbp_irq_value_gbi(pattern));
    return 0;
}

/*
 * A SYNTHETIC v5 sidecar with BOTH record shapes: a service-selecting record
 * carrying the whole narrative of one cycle (service, ACK, re-arm, follow-up)
 * and an observational one that claims none of it. The host battery tampers this
 * file into the shapes the physical v4 file has and requires both parsers to
 * refuse each of them (§31).
 */
static int dump_sidecar_v5(const char *path)
{
    static uint8_t file[1u << 20];
    struct gbp_vstate st2;
    static struct gbp_vstate_frame f2[GBP_VSTATE_MAX_FRAMES];
    static struct gbp_vstate_event e2[GBP_VSTATE_MAX_EVENTS];
    static struct gbp_vstate_result r2;
    static struct gbp_vstate_diag store2[4];
    struct gbp_vstate_config c2;
    struct gbp_vstatedump_info info;
    struct memsink sink;
    uint8_t w[GBP_BLOCK_SIZE];
    gbp_vstate_diag_handle h;
    long n;
    FILE *f;
    memset(&r2, 0, sizeof r2);
    cfg_default(&c2);
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 4u);
    gbp_vstate_gap_observe(&st2, 0x0400u, 100u);
    gbp_vstate_gap_observe(&st2, 0x0400u, 700u);
    window_split(w, 0x0100u, 0x0500u);            /* the physical shape */
    h = gbp_vstate_diag_open(&st2, 900u, 1000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                             GBP_VSTATE_DIS_SOURCE_SERVICED);
    if (h != 0) return 7;
    gbp_vstate_diag_service(&st2, h, 0x0100u, 0x0100u, 0u);
    gbp_vstate_diag_ack(&st2, h, 0x8100u, 1100u);
    gbp_vstate_diag_rearm(&st2, h, 1200u);
    if (gbp_vstate_diag_arm_followup(&st2, h) != 1) return 7;
    if (gbp_vstate_diag_followup(&st2, 1300u, 0x0400u, 0x0400u) != 1) return 7;
    if (gbp_vstate_diag_open(&st2, 901u, 1400u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_POSTACK,
                             GBP_VSTATE_DIS_SOURCE_SERVICED) != 1) return 7;
    gbp_vstate_diag_close(&st2, 0u);
    memset(&info, 0, sizeof info);
    if (gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0004",
                                    "gbp-video-state-probe", "synthetic") != 0) return 2;
    sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    n = gbp_vstatedump_stream(&info, &st2, &r2, &c2, chunk, sizeof chunk, sink_mem, &sink, 0);
    if (n <= 0) return 3;
    f = fopen(path, "wb");
    if (!f) return 4;
    if (fwrite(file, 1, (size_t)n, f) != (size_t)n) { fclose(f); return 5; }
    fclose(f);
    printf("wrote %ld bytes: v%u diag_count=%lu (one service-selecting, one observational)\n",
           n, info.version, (unsigned long)info.diag_count);
    return 0;
}

static int dump_sidecar_diag(const char *path)
{
    struct gbp_mock m;
    struct ringlog rl;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vstatedump_info info;
    struct memsink sink;
    const uint16_t bits[1] = { 0x0500u };
    FILE *f;
    long n;
    cfg_default(&cfg);
    cfg.min_valid_observation_ticks = (uint64_t)1 << 40;
    cfg.max_deliveries = 400u;
    sched_reset(0xFFu);
    mock_vstate(&m, bits, 1u, 50u);
    m.irq_disagree_from_write = 40u;
    run_cfg(&m, &rl, &res, &cfg);
    if (vstate.diags_n == 0u) return 6;
    memset(&info, 0, sizeof info);
    if (gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0004", "gbp-video-state-probe", "synthetic") != 0)
        return 2;
    sink.buf = sidecar; sink.cap = sizeof sidecar; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    n = gbp_vstatedump_stream(&info, &vstate, &res, &cfg, chunk, sizeof chunk, sink_mem, &sink, 0);
    if (n <= 0) return 3;
    f = fopen(path, "wb");
    if (!f) return 4;
    if (fwrite(sidecar, 1, (size_t)n, f) != (size_t)n) { fclose(f); return 5; }
    fclose(f);
    printf("wrote %ld bytes: v%u diag_count=%lu cycle=%lu disc=%04x gbi=%04x class=%s\n", n, info.version,
           (unsigned long)info.diag_count, (unsigned long)vstate.diags[0].cycle,
           vstate.diags[0].disc_value, vstate.diags[0].gbi_value,
           gbp_vstate_class_name(vstate.diags[0].classification));
    return 0;
}

/*
 * `--parse <file>`: the C parser's verdict on an arbitrary file, printed as a
 * number. It exists so the host suite can put the SAME bytes through both
 * implementations and require the same answer: two parsers that disagree about
 * what is a valid file are worse than one (§21, §31).
 */
static int parse_file(const char *path)
{
    static uint8_t buf[1u << 23];   /* larger than any sidecar this family has produced */
    size_t n;
    int rc;
    FILE *f = fopen(path, "rb");
    if (!f) { printf("rc=-99\n"); return 0; }
    n = fread(buf, 1, sizeof buf, f);
    fclose(f);
    rc = gbp_vstatedump_parse_v5(buf, n, 0, 0, 0, 0, 0, 0, 0, 0, 0);
    printf("rc=%d\n", rc);
    return 0;
}

int main(int argc, char **argv)
{
    int do_long = (argc > 1 && strcmp(argv[1], "--long") == 0);
    if (argc > 2 && strcmp(argv[1], "--parse") == 0) return parse_file(argv[2]);
    if (argc > 2 && strcmp(argv[1], "--dump") == 0) return dump_sidecar(argv[2]);
    if (argc > 2 && strcmp(argv[1], "--dump-diag") == 0) return dump_sidecar_diag(argv[2]);
    if (argc > 2 && strcmp(argv[1], "--dump-v5") == 0) return dump_sidecar_v5(argv[2]);
    if (argc > 2 && strcmp(argv[1], "--dump-diag-distinct") == 0) return dump_sidecar_diag_distinct(argv[2]);
    printf("== test_gbp_video_state (GBP-VIDEO-002 probe; every scenario SYNTHETIC)\n");
    {   /* the benchmark bypass is OFF by default, so no build can ever ship with it on */
        struct gbp_vstate_config defaults;
        gbp_vstate_config_default(&defaults);
        CHECK(defaults.bench_skip_signature == 0);
        CHECK(defaults.min_valid_observation_s == 120u);
        CHECK(defaults.hard_wallclock_s == 180u);
        CHECK(defaults.max_deliveries == 2000000u);
        CHECK(defaults.verify_cycles == 4u);
        gbp_vstate_config_timebase(&defaults, GBP_TIME64_NOMINAL_HZ);
        CHECK(defaults.hard_wallclock_ticks == GBP_VSTATE_HARD_WALLCLOCK_LIMIT_TICKS_U64);
        CHECK(defaults.hard_wallclock_ticks == 7290000000ull);
        CHECK(defaults.hard_wallclock_ticks > 0xFFFFFFFFull);
        CHECK(defaults.min_valid_observation_ticks == 4860000000ull);
    }
    test_nominal_negative();
    test_safety_budget_before_target();
    test_safety_wins_over_open_episode();
    test_episodes_and_no_early_stop();
    test_target_with_episode_open();
    test_no_next_cause();
    test_delivery_cap();
    test_audio_policy();
    test_disagreement_and_intervals();
    test_byte0_opens_no_episode();
    test_sidecar();
    test_read_semantics();
    test_historical_deviation_does_not_disagree();
    test_majority_is_exhaustively_the_rule();
    test_classification_is_the_normative_one();
    test_histogram_index_is_exhaustive();
    test_unexpected_source_guard_is_independent();
    test_fatal_classes();
    test_source_serviced_is_nonfatal();
    test_majority_extra_video_is_quarantined();
    test_disc_extra_video_fabricates_nothing();
    test_followup_lifecycle();
    test_followup_is_per_source_bit();
    test_prehandler_wait_default_changes_nothing();
    test_prehandler_wait_waits_then_serves_normally();
    test_prehandler_wait_cannot_be_reached_without_a_clock();
    test_prehandler_wait_records_fit_the_logger();
    test_colour_capture_starts_after_the_prehandler_wait();
    test_no_colour_state_exists_before_capture_start();
    test_colour_success_trace_and_raw_immutability();
    test_colour_capture_adds_no_operation();
    test_ownership_survives_a_store_that_runs_out();
    test_diag_close_touches_only_the_followup();
    test_majority_extra_only_never_waits();
    test_v5_rejects_the_v4_defect();
    test_quarantine_lands_on_the_consuming_frame();
    test_pending_record_survives_a_fatal_next_read();
    test_ack_and_rearm_flags_are_honest();
    test_store_is_bounded_and_the_last_record_still_closes();
    test_gap_statistics();
    test_v5_record_round_trip();
    test_v4_strictness();
    test_v4_count_zero_and_partial_saves();
    test_normal_path_is_untouched();
    test_disagreement_adds_no_operation();
    test_current_cycle_fields_survive_later_cycles();
    test_every_direction_costs_no_operation();
    test_markers_land_on_the_service_record_only();
    test_ack_and_rearm_failures_leave_no_false_claim();
    test_same_cycle_multiple_diagnostics();
    test_more_disagreements_than_the_store();
    test_epoch_never_fabricated();
    test_frame_store_cap_boundary();
    test_bench_with_without();
    if (do_long) test_long_scan();
    else printf("-- the full ~639 000-delivery scan is run by `--long` (slow); the mechanism is\n"
                "   exercised at a smaller scale by every scenario above\n");
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
