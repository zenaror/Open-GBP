/*
 * CRC-32 vectors, the raw AV block helpers (window offsets, summary, records)
 * and the block sidecar (serialize → parse round trips, every error code,
 * nothing uninitialized stored). Also: the mock's bulk read model and the
 * replay's "B" line with an attached block source. Host only, no hardware.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_crc32.h"
#include "gbp_avblock.h"
#include "gbp_avdump.h"
#include "gbp_replay.h"
#include "gbp_mock.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

#define LINES 64
#define LINE_LEN 256
static char storage[LINES * LINE_LEN];
static uint8_t audio_buf[0x1000] __attribute__((aligned(32)));
static uint8_t video_buf[0x0F00] __attribute__((aligned(32)));
static uint8_t dump_buf[GBP_AVDUMP_MAX_SIZE + 64];

static int count_lines_with(const struct ringlog *rl, const char *needle)
{
    size_t i; int n = 0;
    for (i = 0; i < rl->count; i++) if (strstr(ringlog_line(rl, i), needle)) n++;
    return n;
}

static void test_crc32_vectors(void)
{
    static const uint8_t check[] = "123456789";
    static const uint8_t a[] = "a";
    static const uint8_t abc[] = "abc";
    uint8_t z[32];
    uint32_t st;
    memset(z, 0, sizeof z);
    CHECK(gbp_crc32(check, 9) == 0xCBF43926u);           /* the standard check value */
    CHECK(gbp_crc32(a, 1) == 0xE8B7BE43u);
    CHECK(gbp_crc32(abc, 3) == 0x352441C2u);
    CHECK(gbp_crc32(z, 0) == 0u);
    CHECK(gbp_crc32(z, 32) == 0x190A55ADu);              /* 32 zero bytes */
    st = gbp_crc32_update(gbp_crc32_init(), check, 4);   /* incremental == one-shot */
    st = gbp_crc32_update(st, check + 4, 5);
    CHECK(gbp_crc32_final(st) == 0xCBF43926u);
}

static void test_window_offsets(void)
{
    uint32_t w[GBP_AVBLOCK_WINDOWS];
    gbp_avblock_window_offsets(0x1000, w);
    CHECK(w[0] == 0 && w[1] == 0x540 && w[2] == 0xAA0 && w[3] == 0xFE0);
    gbp_avblock_window_offsets(0x0F00, w);
    CHECK(w[0] == 0 && w[1] == 0x500 && w[2] == 0xA00 && w[3] == 0xEE0);
    gbp_avblock_window_offsets(32, w);
    CHECK(w[0] == 0 && w[1] == 0 && w[2] == 0 && w[3] == 0);
    CHECK((w[1] & 31u) == 0 && (w[2] & 31u) == 0);
}

static void test_avblock_summary_and_records(void)
{
    struct gbp_avblock b;
    struct ringlog rl;
    uint32_t k;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_avblock_init(&b, "video", 1, 0x0100, video_buf, sizeof video_buf, 0x0F00);
    for (k = 0; k < sizeof video_buf; k++) video_buf[k] = (uint8_t)(k & 0xFFu);
    video_buf[0] = 0x80; video_buf[1] = 0x92; video_buf[2] = 0x80; video_buf[3] = 0x34;   /* GBI's mask tests bit 7 of bytes 0 and 1 (hh hh ll ll) */
    /* not attempted: nothing about the buffer is reported */
    gbp_avblock_summarize(&b);
    CHECK(b.summarized == 0 && b.crc32 == 0);
    gbp_avblock_log_summary(&rl, &b);
    CHECK(count_lines_with(&rl, "BLOCK kind=video idx=1 len=0f00 present=0 valid=0") == 1 && count_lines_with(&rl, "BLOCKW") == 0);
    gbp_avblock_log_read(&rl, "VIDEOREAD", &b);
    CHECK(count_lines_with(&rl, "VIDEOREAD idx=1 addr=00000000 len=0f00 selected=0 attempted=0 rc=-") == 1);
    /* attempted but failed: present, not valid, no summary */
    b.selected = 1; b.attempted = 1; b.rc = GBP_ERR_TIMEOUT;
    gbp_avblock_summarize(&b);
    CHECK(b.summarized == 0);
    gbp_avblock_log_summary(&rl, &b);
    CHECK(count_lines_with(&rl, "BLOCK kind=video idx=1 len=0f00 present=1 valid=0 rc=timeout summary=-") == 1);
    /* completed: summary computed, the buffer untouched */
    b.completed = 1; b.rc = GBP_OK; b.t_start = 100; b.t_end = 160; b.info.ticks = 50; b.info.polls = 120; b.info.dma_status_before = 0x0804; b.info.dma_status = 0x0824;
    gbp_avblock_summarize(&b);
    CHECK(b.summarized == 1 && b.crc32 == gbp_crc32(video_buf, 0x0F00) && b.first_word == 0x80928034u && b.gbi_frame_start == 1);
    CHECK(b.w_off[0] == 0 && b.w_off[1] == 0x500 && b.w_off[2] == 0xA00 && b.w_off[3] == 0xEE0);
    CHECK(b.zeros == 14u && b.distinct == 256u);            /* 15 positions with k & 0xFF == 0, position 0 overwritten */
    for (k = 0; k < sizeof video_buf; k++) { uint8_t e = (uint8_t)(k & 0xFFu); if (k < 4) continue; CHECK(video_buf[k] == e); if (video_buf[k] != e) break; }
    gbp_avblock_log_read(&rl, "VIDEOREAD", &b);
    CHECK(count_lines_with(&rl, "VIDEOREAD idx=1 addr=00000000 len=0f00 selected=1 attempted=1 completed=1 rc=ok t_start=100 t_end=160 dt=60 wait_ticks=50 polls=120 csr_before=0804 csr_after=0824") == 1);
    gbp_avblock_log_summary(&rl, &b);
    CHECK(count_lines_with(&rl, "BLOCK kind=video idx=1 len=0f00 present=1 valid=1 crc32=") == 1);
    CHECK(count_lines_with(&rl, "w_off=0000,0500,0a00,0ee0 first_word=80928034 gbi_frame_start=1") == 1);
    CHECK(count_lines_with(&rl, "BLOCKW kind=video off=0000 data=80928034") == 1);
    CHECK(count_lines_with(&rl, "BLOCKW kind=video off=0ee0 data=") == 1 && count_lines_with(&rl, "BLOCKW kind=video") == 4);
    CHECK(rl.truncated == 0);
    /* an audio block whose first word does not pass GBI's test: flag 0, still raw */
    gbp_avblock_init(&b, "audio", 8, 0x0400, audio_buf, sizeof audio_buf, 0x1000);
    memset(audio_buf, 0x00, sizeof audio_buf);
    b.selected = 1; b.attempted = 1; b.completed = 1;
    gbp_avblock_summarize(&b);
    CHECK(b.zeros == 0x1000 && b.distinct == 1 && b.gbi_frame_start == 0 && b.first_word == 0);
}

/* the zeros count above: bytes (k & 0xFF) == 0 for k = 256j; 0x0F00 / 256 = 15 such positions; k = 0 was overwritten with 0x80 */
static void test_avblock_zero_count(void)
{
    struct gbp_avblock b;
    uint32_t k;
    gbp_avblock_init(&b, "video", 1, 0x0100, video_buf, sizeof video_buf, 0x0F00);
    for (k = 0; k < sizeof video_buf; k++) video_buf[k] = (uint8_t)(k & 0xFFu);
    b.attempted = 1; b.completed = 1;
    gbp_avblock_summarize(&b);
    CHECK(b.zeros == 15 && b.distinct == 256);
}

static void fill(uint8_t *p, size_t n, uint8_t seed)
{
    size_t i;
    for (i = 0; i < n; i++) p[i] = (uint8_t)(i * 3u + seed);
}

static void base_info(struct gbp_avdump_info *info)
{
    memset(info, 0, sizeof *info);
    info->pending_irq = 0x0500; info->drain_mask = 0x0500; info->tb_hz = 40500000u;
    CHECK(gbp_avdump_set_identity(info, "GBP-AV-SERVICE-001", "avsvc-0001", "gbp-av-service-probe", "5ed9d93-dirty") == 0);
    CHECK(info->identity_error == 0);
    info->audio_index = 8; info->video_index = 1;
}

/* recompute the header and total CRCs after a deliberate change to the header bytes */
static void reseal(uint8_t *buf, long n)
{
    uint32_t h = gbp_crc32(buf, 0xFC), t;
    buf[0xFC] = (uint8_t)(h >> 24); buf[0xFD] = (uint8_t)(h >> 16); buf[0xFE] = (uint8_t)(h >> 8); buf[0xFF] = (uint8_t)h;
    t = gbp_crc32(buf, (size_t)n - 12);
    buf[n - 4] = (uint8_t)(t >> 24); buf[n - 3] = (uint8_t)(t >> 16); buf[n - 2] = (uint8_t)(t >> 8); buf[n - 1] = (uint8_t)t;
}

/* the identity fields: exact official strings byte by byte, the 31/32 boundary, required/optional emptiness, the byte rule,
 * and every way a field in a file can break the rule */
static void test_sidecar_identities(void)
{
    struct gbp_avdump_info in, out;
    const uint8_t *a = 0, *v = 0;
    long n;
    char s31[32], s32[33];
    unsigned k;
    memset(s31, 'x', 31); s31[31] = '\0';
    memset(s32, 'y', 32); s32[32] = '\0';
    fill(audio_buf, sizeof audio_buf, 0x21);
    base_info(&in);
    in.flags = GBP_AVDUMP_FLAG_AUDIO_PRESENT | GBP_AVDUMP_FLAG_AUDIO_VALID; in.audio_len = 0x1000;
    n = gbp_avdump_serialize(&in, audio_buf, 0, dump_buf, sizeof dump_buf);
    CHECK(n == 0x100 + 0x1000 + 12);
    /* the fields as written: the characters, then zero bytes to the end of the 32-byte field */
    CHECK(memcmp(dump_buf + 0x40, "GBP-AV-SERVICE-001\0\0\0\0\0\0\0\0\0\0\0\0\0\0", 32) == 0);
    CHECK(memcmp(dump_buf + 0x60, "avsvc-0001\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0", 32) == 0);
    CHECK(memcmp(dump_buf + 0x80, "gbp-av-service-probe\0\0\0\0\0\0\0\0\0\0\0\0", 32) == 0);
    CHECK(memcmp(dump_buf + 0xA0, "5ed9d93-dirty\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0", 32) == 0);
    for (k = 0xC8; k < 0xFC; k++) CHECK(dump_buf[k] == 0);                                         /* reserved: zero */
    CHECK(dump_buf[0x08] == 0 && dump_buf[0x09] == 2 && dump_buf[0x0A] == 1 && dump_buf[0x0B] == 0);   /* version 2, header 0x100 */
    CHECK(dump_buf[0xC0 + 3] == 8 && dump_buf[0xC4 + 3] == 1);
    CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == 0);
    CHECK(strcmp(out.test_id, "GBP-AV-SERVICE-001") == 0 && strlen(out.test_id) == 18);              /* exact, not a prefix */
    CHECK(strcmp(out.build_id, "avsvc-0001") == 0 && strcmp(out.app, "gbp-av-service-probe") == 0 && strcmp(out.commit, "5ed9d93-dirty") == 0);
    CHECK(out.version == 2 && out.identity_error == 0 && a == dump_buf + 0x100);
    /* a 7-hex commit with -dirty and the longest realistic identities fit with room */
    CHECK(gbp_avdump_id_ok("GBP-AV-SERVICE-001", 0) && gbp_avdump_id_ok("gbp-av-service-probe", 1) && gbp_avdump_id_ok("avsvc-0001", 0));
    CHECK(gbp_avdump_id_ok("5ed9d93-dirty", 1) && gbp_avdump_id_ok("unknown", 1));
    /* boundary: 31 characters fit exactly; 32 never fit (an error, never a truncation) */
    CHECK(gbp_avdump_id_ok(s31, 0) == 1 && gbp_avdump_id_ok(s32, 0) == 0 && gbp_avdump_id_ok(s32, 1) == 0);
    base_info(&in);
    CHECK(gbp_avdump_set_identity(&in, s31, s31, s31, s31) == 0 && in.identity_error == 0 && strlen(in.test_id) == 31);
    n = gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf);
    CHECK(n == 0x100 + 12 && dump_buf[0x40 + 31] == 0 && dump_buf[0x40 + 30] == 'x');
    CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == 0 && strcmp(out.test_id, s31) == 0 && strcmp(out.commit, s31) == 0);
    base_info(&in);
    CHECK(gbp_avdump_set_identity(&in, s32, "avsvc-0001", "", "") == -1 && in.identity_error == 1 && in.test_id[0] == '\0');
    CHECK(gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf) == -2);
    base_info(&in);
    CHECK(gbp_avdump_set_identity(&in, "GBP-AV-SERVICE-001", "avsvc-0001", s32, "") == -1 && strcmp(in.test_id, "GBP-AV-SERVICE-001") == 0 && in.app[0] == '\0');
    CHECK(gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf) == -2);
    /* required / optional emptiness, the byte rule (printable ASCII without spaces) */
    base_info(&in);
    CHECK(gbp_avdump_set_identity(&in, "", "avsvc-0001", "", "") == -1 && gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf) == -2);
    base_info(&in);
    CHECK(gbp_avdump_set_identity(&in, "T", "B", "", "") == 0);
    n = gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf);
    CHECK(n > 0 && gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == 0 && out.app[0] == '\0' && out.commit[0] == '\0');
    CHECK(gbp_avdump_id_ok("with space", 0) == 0 && gbp_avdump_id_ok("tab\there", 0) == 0 && gbp_avdump_id_ok("caf\xc3\xa9", 0) == 0 && gbp_avdump_id_ok(0, 1) == 0);
    base_info(&in);
    strcpy(in.commit, "bad id");                                    /* bypassing set_identity: the serializer still refuses */
    CHECK(gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf) == -2);
    /* files that break the rule are rejected with -8 (CRCs resealed so only the identity rule fails) */
    base_info(&in);
    n = gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf);
    CHECK(n == 0x100 + 12);
    memset(dump_buf + 0x40, 'A', 32); reseal(dump_buf, n);                                           /* no NUL in the field */
    CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == -8);
    n = gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf);
    dump_buf[0x40 + 25] = 'Z'; reseal(dump_buf, n);                                                  /* a non-zero byte after the NUL */
    CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == -8);
    n = gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf);
    dump_buf[0x60 + 2] = ' '; reseal(dump_buf, n);                                                   /* a space inside build_id */
    CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == -8);
    n = gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf);
    memset(dump_buf + 0x60, 0, 32); reseal(dump_buf, n);                                             /* required field empty */
    CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == -8);
    n = gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf);
    memset(dump_buf + 0xA0, 0, 32); reseal(dump_buf, n);                                             /* optional field empty: fine */
    CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == 0 && out.commit[0] == '\0');
    n = gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf);
    dump_buf[0x09] = 1; reseal(dump_buf, n);                                                         /* the pre-release layout is refused */
    CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == -2);
}

static void test_sidecar_round_trips(void)
{
    struct gbp_avdump_info in, out;
    const uint8_t *a = 0, *v = 0;
    long n;
    int rc;
    size_t k;
    fill(audio_buf, sizeof audio_buf, 0x11);
    fill(video_buf, sizeof video_buf, 0x77);

    /* both blocks */
    base_info(&in);
    in.flags = GBP_AVDUMP_FLAG_AUDIO_PRESENT | GBP_AVDUMP_FLAG_AUDIO_VALID | GBP_AVDUMP_FLAG_VIDEO_PRESENT | GBP_AVDUMP_FLAG_VIDEO_VALID;
    in.audio_len = 0x1000; in.video_len = 0x0F00; in.audio_wait_ticks = 123; in.video_wait_ticks = 456; in.audio_dt_ticks = 130; in.video_dt_ticks = 470;
    CHECK(gbp_avdump_size(&in) == 0x100u + 0x1000u + 0x0F00u + 12u);
    n = gbp_avdump_serialize(&in, audio_buf, video_buf, dump_buf, sizeof dump_buf);
    CHECK(n == (long)gbp_avdump_size(&in) && n == 0x200C);
    CHECK(memcmp(dump_buf, "OGBPBLK1", 8) == 0 && memcmp(dump_buf + n - 12, "OGBPEND1", 8) == 0);
    CHECK(in.audio_crc32 == gbp_crc32(audio_buf, 0x1000) && in.video_crc32 == gbp_crc32(video_buf, 0x0F00));
    rc = gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v);
    CHECK(rc == 0 && a && v);
    CHECK(out.version == 2 && out.flags == in.flags && out.pending_irq == 0x0500 && out.drain_mask == 0x0500);
    CHECK(out.audio_len == 0x1000 && out.video_len == 0x0F00 && out.audio_crc32 == in.audio_crc32 && out.video_crc32 == in.video_crc32);
    CHECK(out.audio_wait_ticks == 123 && out.video_wait_ticks == 456 && out.audio_dt_ticks == 130 && out.video_dt_ticks == 470 && out.tb_hz == 40500000u);
    CHECK(strcmp(out.test_id, "GBP-AV-SERVICE-001") == 0 && strcmp(out.build_id, "avsvc-0001") == 0 && strcmp(out.commit, "5ed9d93-dirty") == 0);
    CHECK(strcmp(out.app, "gbp-av-service-probe") == 0);
    CHECK(out.audio_index == 8 && out.video_index == 1 && out.header_crc32 == in.header_crc32 && out.total_crc32 == in.total_crc32);
    CHECK(a && memcmp(a, audio_buf, 0x1000) == 0 && v && memcmp(v, video_buf, 0x0F00) == 0);
    CHECK(a == dump_buf + 0x100 && v == dump_buf + 0x100 + 0x1000);
    /* big-endian, fixed offsets */
    CHECK(dump_buf[0x08] == 0 && dump_buf[0x09] == 2 && dump_buf[0x0A] == 1 && dump_buf[0x0B] == 0x00);
    CHECK(dump_buf[0x10] == 0x05 && dump_buf[0x11] == 0x00 && dump_buf[0x14] == 0 && dump_buf[0x15] == 0 && dump_buf[0x16] == 0x10 && dump_buf[0x17] == 0);
    CHECK(dump_buf[0x18] == 0 && dump_buf[0x19] == 0 && dump_buf[0x1A] == 0x0F && dump_buf[0x1B] == 0);
    CHECK(dump_buf[0xC0 + 3] == 8 && dump_buf[0xC4 + 3] == 1);
    /* deterministic: serializing again gives the same bytes */
    {
        static uint8_t again[GBP_AVDUMP_MAX_SIZE + 64];
        struct gbp_avdump_info in2 = in;
        long n2 = gbp_avdump_serialize(&in2, audio_buf, video_buf, again, sizeof again);
        CHECK(n2 == n && memcmp(again, dump_buf, (size_t)n) == 0);
    }

    /* audio only */
    base_info(&in);
    in.flags = GBP_AVDUMP_FLAG_AUDIO_PRESENT | GBP_AVDUMP_FLAG_AUDIO_VALID;
    in.audio_len = 0x1000; in.video_len = 0; in.pending_irq = 0x0400; in.drain_mask = 0x0400;
    n = gbp_avdump_serialize(&in, audio_buf, 0, dump_buf, sizeof dump_buf);
    CHECK(n == 0x100 + 0x1000 + 12);
    rc = gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v);
    CHECK(rc == 0 && a && !v && out.video_len == 0 && out.video_crc32 == 0 && memcmp(a, audio_buf, 0x1000) == 0);
    /* video only */
    base_info(&in);
    in.flags = GBP_AVDUMP_FLAG_VIDEO_PRESENT | GBP_AVDUMP_FLAG_VIDEO_VALID;
    in.audio_len = 0; in.video_len = 0x0F00; in.pending_irq = 0x0100; in.drain_mask = 0x0100;
    n = gbp_avdump_serialize(&in, 0, video_buf, dump_buf, sizeof dump_buf);
    CHECK(n == 0x100 + 0x0F00 + 12);
    rc = gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v);
    CHECK(rc == 0 && !a && v && out.audio_len == 0 && memcmp(v, video_buf, 0x0F00) == 0 && v == dump_buf + 0x100);
    /* none (aborted before any DMA): header + footer only, nothing uninitialized */
    base_info(&in);
    in.audio_len = 0; in.video_len = 0; in.pending_irq = 0; in.drain_mask = 0;
    n = gbp_avdump_serialize(&in, 0, 0, dump_buf, sizeof dump_buf);
    CHECK(n == 0x100 + 12);
    rc = gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v);
    CHECK(rc == 0 && !a && !v && out.audio_len == 0 && out.video_len == 0);
    for (k = 0; k < 0x100; k++) if (k < 8 || (k >= 0x0C && k < 0x10) || (k >= 0x3C && k < 0xC8) || k >= 0xFC) continue; else CHECK(dump_buf[k] == 0 || k == 0x09 || k == 0x0A);
    /* present but not valid (failed read): stored as left in memory, flagged */
    base_info(&in);
    in.flags = GBP_AVDUMP_FLAG_AUDIO_PRESENT;
    in.audio_len = 0x1000; in.audio_rc = (uint32_t)GBP_ERR_TIMEOUT;
    n = gbp_avdump_serialize(&in, audio_buf, 0, dump_buf, sizeof dump_buf);
    rc = gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v);
    CHECK(rc == 0 && (out.flags & GBP_AVDUMP_FLAG_AUDIO_VALID) == 0 && out.audio_rc == (uint32_t)GBP_ERR_TIMEOUT && a);

    /* error handling: too small, inconsistent lengths, each parse code */
    base_info(&in); in.audio_len = 0x1000; in.video_len = 0x0F00;
    CHECK(gbp_avdump_serialize(&in, audio_buf, video_buf, dump_buf, 100) == -1);
    CHECK(gbp_avdump_serialize(&in, 0, video_buf, dump_buf, sizeof dump_buf) == -1);      /* audio_len without bytes */
    n = gbp_avdump_serialize(&in, audio_buf, video_buf, dump_buf, sizeof dump_buf);
    CHECK(gbp_avdump_parse(dump_buf, 10, &out, &a, &v) == -1);
    dump_buf[0] ^= 1; CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == -1); dump_buf[0] ^= 1;
    dump_buf[0x09] = 3; CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == -2); dump_buf[0x09] = 2;
    n = gbp_avdump_serialize(&in, audio_buf, video_buf, dump_buf, sizeof dump_buf);
    dump_buf[0x12] ^= 0x40; CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == -3); dump_buf[0x12] ^= 0x40;   /* header crc */
    CHECK(gbp_avdump_parse(dump_buf, (size_t)n - 1, &out, &a, &v) == -4);                                                /* truncated */
    dump_buf[n - 12] ^= 1; CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == -5); dump_buf[n - 12] ^= 1;      /* footer magic */
    dump_buf[n - 1] ^= 1; CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == -6); dump_buf[n - 1] ^= 1;        /* total crc */
    {
        /* a payload byte changed AND both CRCs recomputed: the stored per-block CRC no longer matches -> -7 */
        uint32_t total;
        dump_buf[0x100 + 5] ^= 0xFF;
        total = gbp_crc32(dump_buf, (size_t)n - 12);
        dump_buf[n - 4] = (uint8_t)(total >> 24); dump_buf[n - 3] = (uint8_t)(total >> 16); dump_buf[n - 2] = (uint8_t)(total >> 8); dump_buf[n - 1] = (uint8_t)total;
        CHECK(gbp_avdump_parse(dump_buf, (size_t)n, &out, &a, &v) == -7);
    }
    CHECK(gbp_avdump_parse(0, 0, &out, &a, &v) == -1 && a == 0 && v == 0);
    for (k = 0; k < 4; k++) (void)k;
}

/* the mock's bulk model: deterministic pattern per index, args rule, failure knobs, source clearing */
static void test_mock_bulk_model(void)
{
    struct gbp_mock m;
    struct gbp_transport t;
    struct gbp_xfer_info info;
    uint32_t k;
    uint16_t v;
    gbp_mock_init(&m);
    m.irq_model = MOCK_IRQ_MODEL_SOURCE_MASK;
    m.irq_reg = 0x0500;
    gbp_mock_transport(&m, &t);
    CHECK(gbp_transport_has_bulk_read(&t) == 1);
    CHECK(t.read_bulk(t.ctx, 0x01800000, audio_buf, 0x1000, &info) == GBP_OK);
    CHECK(info.ticks == 128u * 3u && info.polls == 128 && info.dma_status == 0x0020 && info.dma_status_before == 0);
    for (k = 0; k < 0x1000; k++) if (audio_buf[k] != gbp_mock_bulk_byte(8, 0, k)) break;
    CHECK(k == 0x1000);
    CHECK(t.read_bulk(t.ctx, 0x01100000, video_buf, 0x0F00, &info) == GBP_OK);
    CHECK(video_buf[0] == gbp_mock_bulk_byte(1, 0, 0) && video_buf[0] != audio_buf[0]);
    CHECK(m.bulk_reads == 2 && m.bulk_bytes == 0x1F00 && m.transfers == 2);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_RD_BULK, 0x01000000, 8) == 1 && gbp_mock_count_block_ops(&m, MOCK_RD_BULK, 0x01000000, 1) == 1);
    CHECK(m.ops[0].len == 0x1000 && m.ops[1].len == 0x0F00);
    CHECK(m.irq_reg == 0x0500);                                      /* the drain does not clear by default */
    /* argument rule */
    CHECK(t.read_bulk(t.ctx, 0x01800010, audio_buf, 0x1000, &info) == GBP_ERR_PARAM);
    CHECK(t.read_bulk(t.ctx, 0x01800000, audio_buf + 1, 0x1000, &info) == GBP_ERR_PARAM);
    CHECK(t.read_bulk(t.ctx, 0x01800000, audio_buf, 0x1010, &info) == GBP_ERR_PARAM);
    CHECK(t.read_bulk(t.ctx, 0x01800000, audio_buf, 0, &info) == GBP_ERR_PARAM);
    CHECK(gbp_bulk_args_ok(0x01800000, audio_buf, GBP_BULK_MAX_LEN) == 1 && gbp_bulk_args_ok(0x01800000, audio_buf, GBP_BULK_MAX_LEN + 32) == 0);
    /* the transfer never leaves its 1 MB register window and never wraps (source or destination) */
    CHECK(gbp_bulk_args_ok(0x01800000, audio_buf, 0x1000) == 1 && gbp_bulk_args_ok(0x01100000, video_buf, 0x0F00) == 1);
    CHECK(gbp_bulk_args_ok(0x018FF000, audio_buf, 0x1000) == 1 && gbp_bulk_args_ok(0x018FF020, audio_buf, 0x1000) == 0);
    CHECK(gbp_bulk_args_ok(0x018FFFE0, audio_buf, 0x40) == 0 && gbp_bulk_args_ok(0x01800020, audio_buf, GBP_BULK_MAX_LEN) == 0);
    CHECK(gbp_bulk_args_ok(0xFFFFFFE0, audio_buf, 0x40) == 0 && gbp_bulk_args_ok(0xFFF00000, audio_buf, GBP_BULK_MAX_LEN) == 0);   /* an end at 2^32 wraps */
    CHECK(gbp_bulk_args_ok(0xFFE00000, audio_buf, GBP_BULK_MAX_LEN) == 1);
    CHECK(gbp_bulk_args_ok(0x01800000, (const void *)((uintptr_t)0 - 32u), 0x1000) == 0);          /* destination wraps */
    CHECK(gbp_bulk_args_ok(0x01800000, 0, 0x1000) == 0);
    CHECK(t.read_bulk(t.ctx, 0x018FFFE0, audio_buf, 0x40, &info) == GBP_ERR_PARAM);
    /* the mock names the block by its exact address: an offset inside the window is refused and counted */
    CHECK(t.read_bulk(t.ctx, 0x01800020, audio_buf, 0x1000, &info) == GBP_ERR_PARAM && m.bulk_bad_addr == 1);
    CHECK(t.read_bulk(t.ctx, 0x01100040, video_buf, 0x0F00, &info) == GBP_ERR_PARAM && m.bulk_bad_addr == 2);
    CHECK(m.ops[m.nops - 2u].rc == GBP_ERR_PARAM && m.ops[m.nops - 2u].addr == 0x01800020 && m.ops[m.nops - 1u].rc == GBP_ERR_PARAM && m.ops[m.nops - 1u].addr == 0x01100040);
    m.bulk_any_offset = 1;
    CHECK(t.read_bulk(t.ctx, 0x01800020, audio_buf, 0x1000, &info) == GBP_OK && m.bulk_bad_addr == 2);
    m.bulk_any_offset = 0;
    /* drain-clears model */
    m.bulk_clears_source = 1;
    CHECK(t.read_bulk(t.ctx, 0x01800000, audio_buf, 0x1000, &info) == GBP_OK && m.irq_reg == 0x0100);
    CHECK(t.read_bulk(t.ctx, 0x01100000, video_buf, 0x0F00, &info) == GBP_OK && m.irq_reg == 0x0000);
    /* failure knobs */
    m.bulk_rc[8] = GBP_ERR_BUSY;
    CHECK(t.read_bulk(t.ctx, 0x01800000, audio_buf, 0x1000, &info) == GBP_ERR_BUSY && info.dma_status == 0x0200);
    m.bulk_rc[8] = GBP_ERR_TIMEOUT; m.bulk_partial_on_fail = 1; memset(audio_buf, 0xAA, 64);
    CHECK(t.read_bulk(t.ctx, 0x01800000, audio_buf, 0x1000, &info) == GBP_ERR_TIMEOUT);
    CHECK(audio_buf[0] == gbp_mock_bulk_byte(8, 0, 0) && audio_buf[32] == 0xAA);
    m.bulk_rc[8] = GBP_OK; m.bulk_seed = 0x5A;
    CHECK(t.read_bulk(t.ctx, 0x01800000, audio_buf, 0x1000, &info) == GBP_OK && audio_buf[0] == gbp_mock_bulk_byte(8, 0x5A, 0));
    /* a source that asserts during the read */
    m.irq_reg = 0x0400; m.bulk_assert_at_read = m.bulk_reads + 1; m.bulk_assert_bits = 0x0100;
    CHECK(t.read_bulk(t.ctx, 0x01800000, audio_buf, 0x1000, &info) == GBP_OK);
    v = m.irq_reg;
    CHECK((v & 0x0100) == 0x0100);
    /* no bulk ops */
    m.bulk_ops_available = 0;
    gbp_mock_transport(&m, &t);
    CHECK(gbp_transport_has_bulk_read(&t) == 0);
}

/* the replay's "B" line: exposed only with such a line; bytes from the attached source; crc check */
struct src_ctx { const uint8_t *audio; const uint8_t *video; unsigned calls; };
static uint32_t block_source(void *ctx, uint32_t base, uint32_t addr, uint32_t len, uint8_t *out)
{
    struct src_ctx *c = (struct src_ctx *)ctx;
    unsigned idx = (unsigned)((addr - base) >> 20) & 0xFu;
    c->calls++;
    if (idx == 8 && c->audio && len == 0x1000) { memcpy(out, c->audio, len); return len; }
    if (idx == 1 && c->video && len == 0x0F00) { memcpy(out, c->video, len); return len; }
    return 0;
}

static void test_replay_bulk_line(void)
{
    static uint8_t a[0x1000] __attribute__((aligned(32)));
    static uint8_t vv[0x0F00] __attribute__((aligned(32)));
    static uint8_t out[0x1000] __attribute__((aligned(32)));
    struct gbp_replay r;
    struct gbp_transport t;
    struct src_ctx sc;
    struct gbp_xfer_info info;
    char script[512];
    uint32_t ca, cv;
    fill(a, sizeof a, 1); fill(vv, sizeof vv, 2);
    ca = gbp_crc32(a, sizeof a); cv = gbp_crc32(vv, sizeof vv);
    snprintf(script, sizeof script, "A r 005b\nB 01800000 00001000 ok %08lx\nB 01100000 00000f00 ok %08lx\nB 01800000 00001000 timeout\nB 01100000 00000f00 ok deadbeef\n",
             (unsigned long)ca, (unsigned long)cv);
    gbp_replay_init(&r, script);
    CHECK(r.has_bulk_ops == 1);
    sc.audio = a; sc.video = vv; sc.calls = 0;
    r.block_source = block_source; r.block_ctx = &sc;
    gbp_replay_transport(&r, &t);
    CHECK(gbp_transport_has_bulk_read(&t) == 1);
    { uint16_t ar; CHECK(t.read_arinfo(t.ctx, &ar) == GBP_OK && ar == 0x005b); }
    CHECK(t.read_bulk(t.ctx, 0x01800000, out, 0x1000, &info) == GBP_OK && memcmp(out, a, 0x1000) == 0 && r.block_crc_mismatches == 0);
    CHECK(t.read_bulk(t.ctx, 0x01100000, out, 0x0F00, &info) == GBP_OK && memcmp(out, vv, 0x0F00) == 0 && r.blocks_missing == 0);
    CHECK(t.read_bulk(t.ctx, 0x01800000, out, 0x1000, &info) == GBP_ERR_TIMEOUT);
    CHECK(t.read_bulk(t.ctx, 0x01100000, out, 0x0F00, &info) == GBP_OK && r.block_crc_mismatches == 1);   /* wrong crc in the script */
    CHECK(r.bulk_reads == 4 && r.mismatches == 0 && r.exhausted == 0 && sc.calls == 3);
    /* a wrong address / length is a mismatch; exhausted afterwards */
    gbp_replay_init(&r, "B 01800000 00001000 ok\n");
    r.block_source = 0;
    gbp_replay_transport(&r, &t);
    CHECK(t.read_bulk(t.ctx, 0x01100000, out, 0x1000, &info) == GBP_ERR_BACKEND && r.mismatches == 1);
    gbp_replay_init(&r, "B 01800000 00001000 ok\n");
    gbp_replay_transport(&r, &t);
    CHECK(t.read_bulk(t.ctx, 0x01800000, out, 0x0F00, &info) == GBP_ERR_BACKEND && r.mismatches == 1);
    gbp_replay_init(&r, "B 01800000 00001000 ok\n");
    gbp_replay_transport(&r, &t);
    memset(out, 0xEE, sizeof out);
    CHECK(t.read_bulk(t.ctx, 0x01800000, out, 0x1000, &info) == GBP_OK && r.blocks_missing == 1 && out[0] == 0 && out[0xFFF] == 0);   /* no source: zeros, counted */
    CHECK(t.read_bulk(t.ctx, 0x01800000, out, 0x1000, &info) == GBP_ERR_BACKEND && r.exhausted == 1);
    /* scripts without a "B" line expose no bulk read (older fixtures unchanged) */
    gbp_replay_init(&r, "A r 005b\nR 01d00000 ok 00\n");
    gbp_replay_transport(&r, &t);
    CHECK(r.has_bulk_ops == 0 && gbp_transport_has_bulk_read(&t) == 0);
    /* bad arguments never consume a line */
    gbp_replay_init(&r, "B 01800000 00001000 ok\n");
    gbp_replay_transport(&r, &t);
    CHECK(t.read_bulk(t.ctx, 0x01800000, out + 1, 0x1000, &info) == GBP_ERR_PARAM && r.step == 0);
}

int main(void)
{
    test_crc32_vectors();
    test_window_offsets();
    test_avblock_summary_and_records();
    test_avblock_zero_count();
    test_sidecar_round_trips();
    test_sidecar_identities();
    test_mock_bulk_model();
    test_replay_bulk_line();
    printf("test_gbp_avdump: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
