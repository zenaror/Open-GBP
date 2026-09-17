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
    CHECK(gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "e581778-dirty") == 0);
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
        gbp_vstatedump_set_identity(&info2, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "e581778-dirty");
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
        gbp_vstatedump_set_identity(&info3, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "e581778-dirty");
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
        gbp_vstatedump_set_identity(&info4, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "e581778-dirty");
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
    /* delta was zero, so nothing was classified as a disagreement at all */
    CHECK(vstate.sem.disagreements_total == 0u);
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
    CHECK(st2.diag_wait == 0);

    /* cycle 11 also disagrees: FIRST close 10, THEN open 11 */
    CHECK(gbp_vstate_diag_followup(&st2, 2000u, 0x0400u, 0x0400u) == 1);
    CHECK(st2.diags[0].followup_state == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT);
    CHECK(st2.diags[0].t_next_cause == 2000u);
    CHECK((st2.diags[0].record_flags & GBP_VSTATE_DF_FOLLOWUP_FILLED) != 0u);
    b = gbp_vstate_diag_open(&st2, 11u, 2000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                             GBP_VSTATE_DIS_SOURCE_SERVICED);
    CHECK(b == 1);
    CHECK(st2.diag_wait == 1);
    CHECK(st2.diags[0].followup_state == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT);  /* untouched */

    /* cycle 12: close 11 with the source ABSENT, then open 12 */
    CHECK(gbp_vstate_diag_followup(&st2, 3000u, 0x0100u, 0x0100u) == 1);
    CHECK(st2.diags[1].followup_state == GBP_VSTATE_FU_SOURCE_ABSENT_NEXT);
    c = gbp_vstate_diag_open(&st2, 12u, 3000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                             GBP_VSTATE_DIS_SOURCE_SERVICED);
    CHECK(c == 2);
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
    printf("-- a run that aborts closes the pending record as run_aborted\n");
    {
        int r = gbp_vstate_diag_open(&st2, 14u, 5000u, w, 0x0500u, 0x0100u,
                                     GBP_VSTATE_DIAG_READ_LEAN, GBP_VSTATE_DIS_SOURCE_SERVICED);
        CHECK(r == 4);
        gbp_vstate_diag_close(&st2, 1u);
        CHECK(st2.diags[4].followup_state == GBP_VSTATE_FU_UNKNOWN);
        CHECK(st2.diags[4].followup_reason == GBP_VSTATE_FUR_RUN_ABORTED);
    }
    printf("   5 records, states: %s %s %s %s %s\n",
           gbp_vstate_fu_name(st2.diags[0].followup_state), gbp_vstate_fu_name(st2.diags[1].followup_state),
           gbp_vstate_fu_name(st2.diags[2].followup_state), gbp_vstate_fu_name(st2.diags[3].followup_state),
           gbp_vstate_fu_name(st2.diags[4].followup_state));
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
        CHECK(gbp_vstate_diag_open(&st2, i, 100u + i, w, 0x0500u, 0x0100u,
                                   GBP_VSTATE_DIAG_READ_LEAN, GBP_VSTATE_DIS_SOURCE_SERVICED) == (int)i);
        if (i + 1u < 4u) CHECK(gbp_vstate_diag_followup(&st2, 200u + i, 0x0400u, 0x0400u) == 1);
    }
    CHECK(st2.diags_n == 4u);
    CHECK(st2.diag_wait == 3);                       /* the last one is still waiting */
    CHECK(st2.sem.store_capped == 0u);
    /* the fifth and sixth are counted, never stored, and never overwrite */
    for (i = 4u; i < 6u; i++)
        CHECK(gbp_vstate_diag_open(&st2, i, 100u + i, w, 0x0500u, 0x0100u,
                                   GBP_VSTATE_DIAG_READ_LEAN, GBP_VSTATE_DIS_SOURCE_SERVICED) == -1);
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

/* The 32 bytes, and the whole record, survive RAM -> serializer -> parser. */
static void test_v4_record_round_trip(void)
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
    CHECK(gbp_vstate_diag_open(&st2, 4242u, 0x00000001FFFFFFFFULL, pattern,
                               gbp_irq_value_disc(pattern), gbp_irq_value_gbi(pattern),
                               GBP_VSTATE_DIAG_READ_PRESVC, GBP_VSTATE_DIS_SOURCE_SERVICED) == 0);
    gbp_vstate_diag_service(&st2, 0x0100u, 0x0100u, 0u);
    gbp_vstate_diag_ack(&st2, 0x8100u, 0x1122334455667788ULL);
    gbp_vstate_diag_rearm(&st2, 0x1122334455667799ULL);
    gbp_vstate_diag_payload(&st2, GBP_VSTATE_SRC_AUDIO, 0xDEADBEEFu, 0xCAFEBABEu);
    gbp_vstate_diag_close(&st2, 0u);

    memset(&info, 0, sizeof info);
    CHECK(gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "synthetic") == 0);
    sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    n = gbp_vstatedump_stream(&info, &st2, &r2, &c2, chunk, sizeof chunk, sink_mem, &sink, 0);
    CHECK(n > 0);
    CHECK(info.version == 4u);
    CHECK(info.diag_rec_size == GBP_VSTATEDUMP_DIAG_REC_V4);
    CHECK(info.diag_count == 1u);
    CHECK(info.semantic_size == GBP_VSTATEDUMP_SEMANTIC_SIZE);
    CHECK(info.off_semantic == info.off_cycles + info.cycle_count * GBP_VSTATEDUMP_CYCLE_REC);
    CHECK(info.off_diag == info.off_semantic + GBP_VSTATEDUMP_SEMANTIC_SIZE);
    CHECK(info.off_video_raw == info.off_diag + GBP_VSTATEDUMP_DIAG_REC_V4);

    CHECK(gbp_vstatedump_parse_v4(file, (size_t)n, &parsed, 0, 0, 0, 0, &sb, &dg, 0, 0) == 0);
    CHECK(parsed.version == 4u);
    CHECK(dg != 0 && sb != 0);
    CHECK(gbp_vstatedump_decode_diag_v4(dg, &back) == 1);
    for (i = 0; i < GBP_BLOCK_SIZE; i++) CHECK(back.raw[i] == pattern[i]);
    CHECK(memcmp(dg + 0x18, pattern, GBP_BLOCK_SIZE) == 0);       /* verbatim ON THE WIRE */
    CHECK(back.t == 0x00000001FFFFFFFFULL);
    CHECK(back.cycle == 4242u);
    CHECK(back.read_kind == GBP_VSTATE_DIAG_READ_PRESVC);
    CHECK(back.classification == GBP_VSTATE_DIS_SOURCE_SERVICED);
    CHECK(back.delta == (uint16_t)(back.disc_value ^ back.gbi_value));
    CHECK(back.authoritative_value == 0x0100u);
    CHECK(back.ack_value == 0x8100u && back.t_ack == 0x1122334455667788ULL);
    CHECK(back.t_rearm == 0x1122334455667799ULL);
    CHECK(back.service_selected == 0x0100u);
    CHECK(back.payload_source == GBP_VSTATE_SRC_AUDIO);
    CHECK(back.payload_crc32 == 0xDEADBEEFu && back.payload_first_word == 0xCAFEBABEu);
    CHECK((back.record_flags & GBP_VSTATE_DF_PAYLOAD_VALID) != 0u);
    CHECK((back.record_flags & GBP_VSTATE_DF_ACK_WRITTEN) != 0u);
    CHECK(back.followup_state == GBP_VSTATE_FU_NO_NEXT_CAUSE);
    CHECK(back.gap_count_before == 1u && back.gap_min_before_ticks == 600u);
    CHECK(back.reserved1 == 0u);
    CHECK(gbp_vstatedump_decode_semantic(sb, &sem) == 0);
    CHECK(sem.disagreements_total == 1u);
    CHECK(sem.source_serviced == 1u);
    CHECK(sem.diagnostics_preserved == 1u);
    CHECK(sem.gap[5].count == 1u && sem.gap[5].min_ticks == 600u);
    CHECK(sem.delta_hist[gbp_vstate_hist_index(back.delta)] == 1u);

    printf("-- every one of the 160 bytes is covered by the CRC\n");
    {
        static uint8_t bad[1u << 20];
        unsigned k, undetected = 0;
        for (k = 0; k < GBP_VSTATEDUMP_DIAG_REC_V4; k++) {
            memcpy(bad, file, (size_t)n);
            bad[info.off_diag + k] ^= 0x01u;
            if (gbp_vstatedump_parse(bad, (size_t)n, 0, 0, 0, 0, 0, 0, 0) == 0) undetected++;
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
    printf("-- the strict v4 parser, with both CRCs recomputed after every tamper\n");
    memset(&r2, 0, sizeof r2);
    cfg_default(&c2);
    gbp_vstate_init(&st2, f2, GBP_VSTATE_MAX_FRAMES, e2, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&st2, store2, 4u);
    window_split(w, 0x0100u, 0x0500u);
    CHECK(gbp_vstate_diag_open(&st2, 7u, 7000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                               GBP_VSTATE_DIS_SOURCE_SERVICED) == 0);
    gbp_vstate_diag_close(&st2, 0u);
    memset(&info, 0, sizeof info);
    gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "synthetic");
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

    TAMPER(put16(bad + 0x008, 5u), -2, "unknown version 5");
    /* a v4 file relabelled as v3 is refused by v3's own reserved-area rule:
     * 0x1EA..0x1FB carry diag_flags, off_semantic and semantic_size, which v3
     * requires to be zero. The versions cannot read each other by accident. */
    TAMPER(put16(bad + 0x008, 3u), -8, "v4 claiming to be v3");
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
    TAMPER(put16(bad + info.off_diag + 0x6E, 0x0100u), -8, "unknown record flag");
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
    CHECK(gbp_vstate_diag_followup(&st2, 400u, 0x0500u, 0x0500u) == 1);
    CHECK(st2.diags[1].followup_state == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT);
    CHECK(st2.sem.followup_partial == 1u);              /* unchanged */
    printf("-- the DISC value of the next read is stored but never decides\n");
    CHECK(gbp_vstate_diag_open(&st2, 3u, 500u, w, 0x0500u, 0x0000u, GBP_VSTATE_DIAG_READ_LEAN,
                               GBP_VSTATE_DIS_SOURCE_SERVICED) == 2);
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
    gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "synthetic");
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
        gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "synthetic");
        sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.failed = 0; sink.fail_after = 0;
        full = gbp_vstatedump_stream(&info, &st2, &r2, &c2, small, sizeof small, sink_mem, &sink, 0);
        CHECK(full > 0);
    }
    {   /* the card refuses from the very first byte */
        struct gbp_vstate_diag before = st2.diags[0];
        struct gbp_vstatedump_info i2;
        memset(&i2, 0, sizeof i2);
        gbp_vstatedump_set_identity(&i2, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "synthetic");
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
            gbp_vstatedump_set_identity(&i2, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "synthetic");
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
    gbp_vstate_diag_ack(&st2, 0x8100u, 250u);
    CHECK((st2.diags[1].record_flags & GBP_VSTATE_DF_ACK_WRITTEN) != 0u);
    CHECK((st2.diags[1].record_flags & GBP_VSTATE_DF_REARM_WRITTEN) == 0u);
    CHECK(st2.diags[1].t_rearm == 0u);
    gbp_vstate_diag_rearm(&st2, 260u);
    CHECK((st2.diags[1].record_flags & GBP_VSTATE_DF_REARM_WRITTEN) != 0u);
    printf("   flags track the writes, never the intention\n");
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
    if (gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "host-synthetic") != 0)
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
        if (!gbp_vstate_diag_open(&st2, 4242u, 0x00000001FFFFFFFFULL, pattern,
                                  gbp_irq_value_disc(pattern), gbp_irq_value_gbi(pattern),
                                  GBP_VSTATE_DIAG_READ_POSTDRAIN, GBP_VSTATE_DIS_SOURCE_SERVICED) == 0) {
            /* index 0 is the only acceptable answer here */
        }
        gbp_vstate_diag_close(&st2, 0u);
        memset(&info, 0, sizeof info);
        if (gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0003",
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
    if (gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0003", "gbp-video-state-probe", "synthetic") != 0)
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

int main(int argc, char **argv)
{
    int do_long = (argc > 1 && strcmp(argv[1], "--long") == 0);
    if (argc > 2 && strcmp(argv[1], "--dump") == 0) return dump_sidecar(argv[2]);
    if (argc > 2 && strcmp(argv[1], "--dump-diag") == 0) return dump_sidecar_diag(argv[2]);
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
    test_quarantine_lands_on_the_consuming_frame();
    test_pending_record_survives_a_fatal_next_read();
    test_ack_and_rearm_flags_are_honest();
    test_store_is_bounded_and_the_last_record_still_closes();
    test_gap_statistics();
    test_v4_record_round_trip();
    test_v4_strictness();
    test_v4_count_zero_and_partial_saves();
    test_normal_path_is_untouched();
    test_disagreement_adds_no_operation();
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
