/*
 * gbp_rawlog.h — logged reads of GBP blocks and PI registers.
 *
 * Every read is logged with its raw bytes plus the two documented
 * interpretations (docs/protocol/REGISTERS.md §2.1): the Start-up Disc's
 * byte positions and GBI's majority vote. Raw data is never replaced by
 * an interpretation. Shared by probes; the executed GBP-INIT-001 code
 * (gbp_init_probe.c) keeps its own copy on purpose.
 */
#ifndef OPENGBP_GBP_RAWLOG_H
#define OPENGBP_GBP_RAWLOG_H

#include <stdint.h>
#include "gbp_transport.h"
#include "../log/ringlog.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_IDX_TEST 0u
#define GBP_IDX_CONTROL 4u
#define GBP_IDX_IRQ 0xDu

/* Reads block `idx` at `base` into out, logs "RAW <tag> idx=… data=…"
 * (CONTROL: sem_vote/sem_b1f; IRQ: sem_disc/sem_gbi). *errors is
 * incremented on failure when non-NULL. */
gbp_status gbp_rawlog_read_block(const struct gbp_transport *t, struct ringlog *log, const char *tag,
                                 uint32_t base, unsigned idx, uint8_t out[GBP_BLOCK_SIZE], unsigned *errors);

/* Reads INTSR/INTMR and logs "PI <tag> intsr= intmr= intsr13= intmr13=".
 * Returns 1 on success, 0 if the transport has no PI access or failed. */
int gbp_rawlog_read_pi(const struct gbp_transport *t, struct ringlog *log, const char *tag,
                       uint32_t *intsr, uint32_t *intmr);

/* Formatting only (same records as above), for code that must read
 * without formatting and log afterwards (GBP-INIT-003A's experimental
 * region): `rc_name` is "ok", "unavailable" or a gbp_status_name(). */
void gbp_rawlog_log_block(struct ringlog *log, const char *tag, uint32_t addr, unsigned idx, gbp_status rc,
                          const struct gbp_xfer_info *info, const uint8_t data[GBP_BLOCK_SIZE]);
void gbp_rawlog_log_pi(struct ringlog *log, const char *tag, const char *rc_name, uint32_t intsr, uint32_t intmr);

/* 16-bit IRQ value the Start-up Disc would read (bytes 0x1D, 0x1F). */
uint16_t gbp_irq_value_disc(const uint8_t block[GBP_BLOCK_SIZE]);
/* 16-bit IRQ value GBI would read (vote over bytes ≡1 / ≡3 mod 4). */
uint16_t gbp_irq_value_gbi(const uint8_t block[GBP_BLOCK_SIZE]);

#ifdef __cplusplus
}
#endif
#endif
