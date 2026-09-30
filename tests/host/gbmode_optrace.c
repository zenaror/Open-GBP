/*
 * tests/host/gbmode_optrace.c -- Issue #146 (Phase 7's E3): the device OPERATION STREAM of the vstate probe, dumped, so that two
 * source trees (stream-0015's commit and HEAD) can be compared op for op. It is compiled by tests/host/test_gbmode_image.py
 * against each tree's own src/ and tests/mocks/, and it uses only API that exists in both.
 *
 *   gbmode_optrace gba   the nominal GBA-mode scenario of tests/unit/test_gbp_video_state.c (CONTROL untouched by the device)
 *   gbmode_optrace gb    the same, but the device holds CONTROL bit 0x01 from the install on (the GB/GBC case)
 *
 * Output: one line per mock operation (kind, address, length, value, return code, a hash of the 32 data bytes), the whole ringlog,
 * and the result's status, stop and counters. SYNTHETIC: the mock's device, not the hardware's.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gbp_vstate_probe.h"
#include "gbp_rawlog.h"
#include "gbp_mock.h"

#define LINES 2048
#define LINE_LEN 256
#define TB_HZ 1000000u
#define BLOCK_TICKS 417u
#define T_DELIVERY 4000u
#define T_NEXT_CAUSE 4000u

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
static struct gbp_vstate_diag diag_store[GBP_VSTATE_MAX_DISAGREEMENTS];
static struct gbp_vstate_result res;
static struct gbp_mock m;
static struct ringlog rl;

static const uint32_t A1_DL[GBP_INITIRQA_MAX_A1_OBS] = { 50u, 100u };
static const uint32_t A2_DL[GBP_INITIRQA_MAX_A2_OBS] = { 50u, 100u, 200u, 400u, 800u, 1600u };

/* one VIDEO block: `7f 7f lo lo` per pixel, the frame-start bit on every 40th read; the screen changes once at read 1 (FF) */
static void fill_video(struct gbp_mock *mm, uint8_t *out, uint32_t len, unsigned read_n, void *user)
{
    uint32_t k;
    (void)mm; (void)user;
    for (k = 0; k + 3u < len; k += 4u) { out[k] = 0x7F; out[k + 1] = 0x7F; out[k + 2] = 0xFF; out[k + 3] = 0xFF; }
    if ((read_n - 1u) % 40u == 0u) { out[0] = 0xFF; out[1] = 0xFF; }
}

static uint32_t fnv(const uint8_t *d, size_t n)
{
    uint32_t h = 2166136261u;
    size_t i;
    for (i = 0; i < n; i++) { h ^= d[i]; h *= 16777619u; }
    return h;
}

int main(int argc, char **argv)
{
    struct gbp_transport t;
    struct gbp_vstate_config cfg;
    const uint16_t bits[1] = { 0x0500u };
    size_t i;
    int gb = (argc > 1 && strcmp(argv[1], "gb") == 0);

    gbp_mock_init(&m);
    m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK;
    m.isr_ext = 1;
    m.max_deliveries = 4000000u;
    m.source_assert_after_write = 2u;
    m.source_assert_delay = 300;
    m.source_assert_bits = bits[0];
    m.seq_steps[0].bits = bits[0]; m.seq_steps[0].delay = 50u; m.seq_len = 1u;
    m.bulk_clears_source = 1;
    m.video_fill = fill_video;
    m.bulk_tick_advance[1] = BLOCK_TICKS;
    if (gb) m.control_on_install = 0x8Du;      /* the mock's idle CONTROL is 0x90, so the expected byte is 0x8C: 0x8D is bit 0x01 alone */

    gbp_mock_transport(&m, &t);
    gbp_vstate_config_default(&cfg);
    gbp_vstate_config_timebase(&cfg, TB_HZ);
    memcpy(cfg.a.a1_obs_ticks, A1_DL, sizeof A1_DL);
    memcpy(cfg.a.a2_obs_ticks, A2_DL, sizeof A2_DL);
    cfg.a.tb_hz = TB_HZ;
    cfg.t_delivery_ticks = T_DELIVERY;
    cfg.t_next_cause_ticks = T_NEXT_CAUSE;
    cfg.min_valid_observation_s = 0u;
    cfg.min_valid_observation_ticks = (uint64_t)BLOCK_TICKS * 39u * 6u;
    gbp_vstate_init(&vstate, frames, GBP_VSTATE_MAX_FRAMES, events, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&vstate, diag_store, GBP_VSTATE_MAX_DISAGREEMENTS);
    cfg.st = &vstate;
    cfg.cyc_first = cyc_first; cfg.cyc_last = cyc_last; cfg.cyc_anomaly = cyc_anomaly; cfg.cyc_episode = cyc_episode;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_vstate_probe_run(&t, &rl, &cfg, &res);

    for (i = 0; i < m.nops; i++) {
        const struct gbp_mock_op *op = &m.ops[i];
        printf("OP %u %08lx %lu %04x %d %08lx\n", (unsigned)op->kind, (unsigned long)op->addr, (unsigned long)op->len,
               (unsigned)op->value, (int)op->rc, (unsigned long)fnv(op->data, sizeof op->data));
    }
    printf("OPS n=%lu dropped=%lu\n", (unsigned long)m.nops, (unsigned long)m.ops_dropped);
    for (i = 0; i < rl.count; i++) printf("LOG %s\n", ringlog_line(&rl, i));
    printf("RESULT status=%s stop=%s deliveries=%lu video=%lu\n", res.status_name, gbp_vstate_stop_name(res.stop),
           (unsigned long)res.deliveries, (unsigned long)res.video_completed);
    return 0;
}
