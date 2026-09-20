/*
 * gbp_vvidump.h — "OGBPVI1", the VI hand-over / latch sidecar of GBP-VIDEO-007
 * (HARDWARE_TESTS §V6.8; GitHub Issue #7). A NEW magic: OGBPDISP2 has no latch
 * instant and no register readback, and a frozen contract is never extended
 * in place. Family conventions: 8-byte magic, big-endian field by field, no
 * struct copy, identities that are an error when they do not fit, a footer
 * CRC-32 over everything before it. Written only after the teardown.
 *
 *   header   0x100 bytes
 *   records  records_n x 64 bytes
 *   footer   "OGBPVEND" + u32 CRC-32
 */
#ifndef OPENGBP_GBP_VVIDUMP_H
#define OPENGBP_GBP_VVIDUMP_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_vvi.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_VVIDUMP_MAGIC        "OGBPVI1\0"
#define GBP_VVIDUMP_END          "OGBPVEND"
#define GBP_VVIDUMP_VERSION      1u
#define GBP_VVIDUMP_HEADER_SIZE  0x100u
#define GBP_VVIDUMP_RECORD_SIZE  64u
#define GBP_VVIDUMP_FOOTER_SIZE  12u
#define GBP_VVIDUMP_ID_FIELD     32u
#define GBP_VVIDUMP_ID_MAX       31u
#define GBP_VVIDUMP_CHUNK        0x1000u

#define GBP_VVIDUMP_FLAG_TRUNCATED 0x0001u
#define GBP_VVIDUMP_FLAG_OVERFLOW  0x0002u   /* hand-overs beyond the capacity were dropped */
#define GBP_VVIDUMP_FLAG_ALL       0x0003u

struct gbp_vvidump_info {
    uint16_t version, header_size;
    uint32_t flags;
    uint32_t record_size, records_cap, records_n;
    uint32_t tb_hz, xfb_slots;
    uint32_t handed, latched, superseded, overflow, observe_calls;
    int32_t  awaiting_at_end;
    uint32_t off_records, off_footer;
    uint64_t total_size;
    char test_id[GBP_VVIDUMP_ID_FIELD];
    char build_id[GBP_VVIDUMP_ID_FIELD];
    char app[GBP_VVIDUMP_ID_FIELD];
    char commit[GBP_VVIDUMP_ID_FIELD];
    int identity_error;
    uint32_t header_crc32, total_crc32;
};

int gbp_vvidump_set_identity(struct gbp_vvidump_info *info, const char *test_id,
                             const char *build_id, const char *app, const char *commit);
int gbp_vvidump_layout(struct gbp_vvidump_info *info, const struct gbp_vvi *v);

typedef int (*gbp_vvidump_sink)(void *ctx, const uint8_t *data, uint32_t len);

long gbp_vvidump_stream(struct gbp_vvidump_info *info, const struct gbp_vvi *v,
                        uint8_t *chunk, uint32_t chunk_cap,
                        gbp_vvidump_sink sink, void *sink_ctx, uint64_t *written);

/* Strict parser: -1 short/magic, -2 version/sizes, -3 header CRC, -4 bounds,
 * -5 footer magic, -6 total CRC, -7 identity, -8 reserved/flags, -9 record. */
int gbp_vvidump_parse(const uint8_t *in, size_t n, struct gbp_vvidump_info *info,
                      const uint8_t **records);

#ifdef __cplusplus
}
#endif
#endif
