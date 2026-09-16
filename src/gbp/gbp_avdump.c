#include "gbp_avdump.h"

#include <string.h>
#include "gbp_crc32.h"

#define OFF_FLAGS 0x0Cu
#define OFF_TEST_ID 0x40u
#define OFF_BUILD_ID 0x60u
#define OFF_APP 0x80u
#define OFF_COMMIT 0xA0u
#define OFF_AUDIO_INDEX 0xC0u
#define OFF_VIDEO_INDEX 0xC4u
#define OFF_HEADER_CRC 0xFCu

static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static void put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static uint16_t get16(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }
static uint32_t get32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3]; }

static int id_byte_ok(uint8_t c)
{
    return (c >= 0x21u && c <= 0x7Eu) ? 1 : 0;
}

int gbp_avdump_id_ok(const char *s, int may_be_empty)
{
    size_t i;
    if (!s) return 0;
    for (i = 0; s[i]; i++) {
        if (i >= GBP_AVDUMP_ID_MAX) return 0;                    /* does not fit: never truncated */
        if (!id_byte_ok((uint8_t)s[i])) return 0;
    }
    if (i == 0 && !may_be_empty) return 0;
    return 1;
}

static int set_one(char *dst, const char *src, int may_be_empty)
{
    memset(dst, 0, GBP_AVDUMP_ID_FIELD);
    if (!gbp_avdump_id_ok(src, may_be_empty)) return 0;
    memcpy(dst, src, strlen(src));                               /* < 32 bytes: the field keeps its NUL padding */
    return 1;
}

int gbp_avdump_set_identity(struct gbp_avdump_info *info, const char *test_id, const char *build_id,
                            const char *app, const char *commit)
{
    int ok = 1;
    if (!set_one(info->test_id, test_id, 0)) ok = 0;
    if (!set_one(info->build_id, build_id, 0)) ok = 0;
    if (!set_one(info->app, app, 1)) ok = 0;
    if (!set_one(info->commit, commit, 1)) ok = 0;
    info->identity_error = ok ? 0 : 1;
    return ok ? 0 : -1;
}

/* the field as written: the characters, then NUL bytes up to the field width */
static void put_id(uint8_t *p, const char *s)
{
    size_t n = strlen(s);
    memset(p, 0, GBP_AVDUMP_ID_FIELD);
    memcpy(p, s, n);
}

/* the field as read: a NUL within the field, only zero bytes after it, only identity bytes before it */
static int get_id(const uint8_t *p, char *dst, int may_be_empty)
{
    size_t i, n = 0;
    int seen_nul = 0;
    memset(dst, 0, GBP_AVDUMP_ID_FIELD);
    for (i = 0; i < GBP_AVDUMP_ID_FIELD; i++) {
        if (seen_nul) { if (p[i] != 0u) return 0; continue; }
        if (p[i] == 0u) { seen_nul = 1; continue; }
        if (!id_byte_ok(p[i])) return 0;
        n++;
    }
    if (!seen_nul || n > GBP_AVDUMP_ID_MAX) return 0;
    if (n == 0 && !may_be_empty) return 0;
    memcpy(dst, p, n);
    return 1;
}

size_t gbp_avdump_size(const struct gbp_avdump_info *info)
{
    return (size_t)GBP_AVDUMP_HEADER_SIZE + info->audio_len + info->video_len + GBP_AVDUMP_FOOTER_SIZE;
}

long gbp_avdump_serialize(struct gbp_avdump_info *info, const uint8_t *audio, const uint8_t *video,
                          uint8_t *out, size_t cap)
{
    size_t need = gbp_avdump_size(info);
    uint8_t *p = out;
    if (!out || cap < need) return -1;
    if ((info->audio_len && !audio) || (info->video_len && !video)) return -1;
    if (info->audio_len > 0x100000u || info->video_len > 0x100000u) return -1;
    if (info->identity_error || !gbp_avdump_id_ok(info->test_id, 0) || !gbp_avdump_id_ok(info->build_id, 0) ||
        !gbp_avdump_id_ok(info->app, 1) || !gbp_avdump_id_ok(info->commit, 1)) return -2;
    memset(p, 0, GBP_AVDUMP_HEADER_SIZE);                        /* every header byte, the reserved area included, starts as zero */
    memcpy(p + 0x00, GBP_AVDUMP_MAGIC, 8);
    put16(p + 0x08, (uint16_t)GBP_AVDUMP_VERSION);
    put16(p + 0x0A, (uint16_t)GBP_AVDUMP_HEADER_SIZE);
    put32(p + OFF_FLAGS, info->flags);
    put16(p + 0x10, info->pending_irq);
    put16(p + 0x12, info->drain_mask);
    put32(p + 0x14, info->audio_len);
    put32(p + 0x18, info->video_len);
    info->audio_crc32 = info->audio_len ? gbp_crc32(audio, info->audio_len) : 0u;
    info->video_crc32 = info->video_len ? gbp_crc32(video, info->video_len) : 0u;
    put32(p + 0x1C, info->audio_crc32);
    put32(p + 0x20, info->video_crc32);
    put32(p + 0x24, info->audio_rc);
    put32(p + 0x28, info->video_rc);
    put32(p + 0x2C, info->audio_wait_ticks);
    put32(p + 0x30, info->video_wait_ticks);
    put32(p + 0x34, info->audio_dt_ticks);
    put32(p + 0x38, info->video_dt_ticks);
    put32(p + 0x3C, info->tb_hz);
    put_id(p + OFF_TEST_ID, info->test_id);
    put_id(p + OFF_BUILD_ID, info->build_id);
    put_id(p + OFF_APP, info->app);
    put_id(p + OFF_COMMIT, info->commit);
    put32(p + OFF_AUDIO_INDEX, info->audio_index);
    put32(p + OFF_VIDEO_INDEX, info->video_index);
    info->header_crc32 = gbp_crc32(p, OFF_HEADER_CRC);
    put32(p + OFF_HEADER_CRC, info->header_crc32);
    p += GBP_AVDUMP_HEADER_SIZE;
    if (info->audio_len) { memcpy(p, audio, info->audio_len); p += info->audio_len; }
    if (info->video_len) { memcpy(p, video, info->video_len); p += info->video_len; }
    info->total_crc32 = gbp_crc32(out, (size_t)(p - out));
    memcpy(p, GBP_AVDUMP_END, 8);
    put32(p + 8, info->total_crc32);
    p += GBP_AVDUMP_FOOTER_SIZE;
    return (long)(p - out);
}

int gbp_avdump_parse(const uint8_t *in, size_t n, struct gbp_avdump_info *info,
                     const uint8_t **audio, const uint8_t **video)
{
    const uint8_t *p;
    size_t need;
    if (audio) *audio = 0;
    if (video) *video = 0;
    if (!in || n < GBP_AVDUMP_HEADER_SIZE + GBP_AVDUMP_FOOTER_SIZE || memcmp(in, GBP_AVDUMP_MAGIC, 8) != 0) return -1;
    memset(info, 0, sizeof *info);
    info->version = get16(in + 0x08);
    if (info->version != GBP_AVDUMP_VERSION || get16(in + 0x0A) != GBP_AVDUMP_HEADER_SIZE) return -2;
    info->header_crc32 = get32(in + OFF_HEADER_CRC);
    if (gbp_crc32(in, OFF_HEADER_CRC) != info->header_crc32) return -3;
    info->flags = get32(in + OFF_FLAGS);
    info->pending_irq = get16(in + 0x10);
    info->drain_mask = get16(in + 0x12);
    info->audio_len = get32(in + 0x14);
    info->video_len = get32(in + 0x18);
    info->audio_crc32 = get32(in + 0x1C);
    info->video_crc32 = get32(in + 0x20);
    info->audio_rc = get32(in + 0x24);
    info->video_rc = get32(in + 0x28);
    info->audio_wait_ticks = get32(in + 0x2C);
    info->video_wait_ticks = get32(in + 0x30);
    info->audio_dt_ticks = get32(in + 0x34);
    info->video_dt_ticks = get32(in + 0x38);
    info->tb_hz = get32(in + 0x3C);
    if (!get_id(in + OFF_TEST_ID, info->test_id, 0) || !get_id(in + OFF_BUILD_ID, info->build_id, 0) ||
        !get_id(in + OFF_APP, info->app, 1) || !get_id(in + OFF_COMMIT, info->commit, 1)) return -8;
    info->audio_index = get32(in + OFF_AUDIO_INDEX);
    info->video_index = get32(in + OFF_VIDEO_INDEX);
    if (info->audio_len > 0x100000u || info->video_len > 0x100000u) return -4;
    need = gbp_avdump_size(info);
    if (n < need) return -4;
    p = in + GBP_AVDUMP_HEADER_SIZE + info->audio_len + info->video_len;
    if (memcmp(p, GBP_AVDUMP_END, 8) != 0) return -5;
    info->total_crc32 = get32(p + 8);
    if (gbp_crc32(in, (size_t)(p - in)) != info->total_crc32) return -6;
    if (info->audio_len) {
        if (gbp_crc32(in + GBP_AVDUMP_HEADER_SIZE, info->audio_len) != info->audio_crc32) return -7;
        if (audio) *audio = in + GBP_AVDUMP_HEADER_SIZE;
    }
    if (info->video_len) {
        if (gbp_crc32(in + GBP_AVDUMP_HEADER_SIZE + info->audio_len, info->video_len) != info->video_crc32) return -7;
        if (video) *video = in + GBP_AVDUMP_HEADER_SIZE + info->audio_len;
    }
    return 0;
}
