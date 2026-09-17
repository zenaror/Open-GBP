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

static void run_cfg(struct gbp_mock *m, struct ringlog *rl, struct gbp_vstate_result *res, struct gbp_vstate_config *cfg)
{
    struct gbp_transport t;
    gbp_mock_transport(m, &t);
    gbp_vstate_init(&vstate, frames, GBP_VSTATE_MAX_FRAMES, events, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
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
    CHECK(gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0001", "gbp-video-state-probe", "e581778-dirty") == 0);
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
        gbp_vstatedump_set_identity(&info2, "GBP-VIDEO-002", "vstate-0001", "gbp-video-state-probe", "e581778-dirty");
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
        gbp_vstatedump_set_identity(&info3, "GBP-VIDEO-002", "vstate-0001", "gbp-video-state-probe", "e581778-dirty");
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
        gbp_vstatedump_set_identity(&info4, "GBP-VIDEO-002", "vstate-0001", "gbp-video-state-probe", "e581778-dirty");
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

/* ---- the long scan ---------------------------------------------------- */
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
    if (gbp_vstatedump_set_identity(&info, "GBP-VIDEO-002", "vstate-0001", "gbp-video-state-probe", "host-synthetic") != 0)
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

int main(int argc, char **argv)
{
    int do_long = (argc > 1 && strcmp(argv[1], "--long") == 0);
    if (argc > 2 && strcmp(argv[1], "--dump") == 0) return dump_sidecar(argv[2]);
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
    test_epoch_never_fabricated();
    test_frame_store_cap_boundary();
    test_bench_with_without();
    if (do_long) test_long_scan();
    else printf("-- the full ~639 000-delivery scan is run by `--long` (slow); the mechanism is\n"
                "   exercised at a smaller scale by every scenario above\n");
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
