/*
 * gbp_crc32.h — CRC-32 (IEEE 802.3 / zlib: reflected polynomial
 * 0xEDB88320, initial 0xFFFFFFFF, final complement), bit by bit, no table.
 *
 * Used to summarize raw AUDIO/VIDEO blocks after the timed region of an
 * experiment and to seal the block sidecar (gbp_avdump.h). Deterministic,
 * host-testable (known vectors in tests/unit/test_gbp_avdump.c); never
 * called inside a handler or a timed region. The CRC is a summary for the
 * log and for cross-checks, never a replacement for the raw bytes.
 */
#ifndef OPENGBP_GBP_CRC32_H
#define OPENGBP_GBP_CRC32_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* CRC-32 of n bytes (zlib-compatible: crc32("123456789") == 0xCBF43926). */
uint32_t gbp_crc32(const uint8_t *data, size_t n);
/* Incremental form: gbp_crc32_update(gbp_crc32_init(), …) then gbp_crc32_final(). */
uint32_t gbp_crc32_init(void);
uint32_t gbp_crc32_update(uint32_t state, const uint8_t *data, size_t n);
uint32_t gbp_crc32_final(uint32_t state);

#ifdef __cplusplus
}
#endif
#endif
