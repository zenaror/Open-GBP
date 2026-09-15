/*
 * gbp_detect.h — TEST-handshake interpretation and presence policy.
 *
 * Derived from the official Nintendo Start-up Disc and from GBI, an
 * independent mature implementation (docs/protocol/INITIALIZATION.md §1):
 *
 *   Start-up Disc (0x8008ae3c): after writing 32×p and reading 32 bytes,
 *       require  block[1] == ~p                      (one byte, offset 1)
 *   GBI (0x80011c94 / 0x80015b08): require vote(block) == ~p, where vote()
 *       sets bit k iff more than 16 of the 32 bytes have bit k set.
 *
 * Both were validated against the physical captures of 2026-09-14
 * (captures/fixtures/hw-gamecube-*.gbpreplay): with the GBP attached both
 * pass 8/8 handshakes although byte 0 carried extra bits in 3 of them;
 * without the GBP (every block 0xC0) both fail 8/8. A whole-block
 * comparison (probe-0001) failed 3/8 with the GBP attached.
 *
 * Transport success (rc == GBP_OK) is NOT presence: without the GBP every
 * DMA still completed. Presence comes only from the handshake content.
 */
#ifndef OPENGBP_GBP_DETECT_H
#define OPENGBP_GBP_DETECT_H

#include <stdint.h>
#include "gbp_transport.h"
#include "../log/ringlog.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Byte obtained by GBI's per-bit majority vote over the 32 bytes. */
uint8_t gbp_majority_vote_byte(const uint8_t block[GBP_BLOCK_SIZE]);
/* Same vote over n bytes (GBI's 16-bit reads vote over 8 bytes each). */
uint8_t gbp_majority_vote_byte_n(const uint8_t *bytes, unsigned n);

/* 1 if the response satisfies the Start-up Disc criterion for `pattern`. */
int gbp_test_startup_disc_style(const uint8_t resp[GBP_BLOCK_SIZE], uint8_t pattern);

/* 1 if the response satisfies the GBI criterion for `pattern`. */
int gbp_test_majority_vote(const uint8_t resp[GBP_BLOCK_SIZE], uint8_t pattern);

/* 1 if all 32 bytes equal ~pattern (probe-0001's heuristic, kept for reporting). */
int gbp_test_whole_block(const uint8_t resp[GBP_BLOCK_SIZE], uint8_t pattern);

typedef enum {
    GBP_VERDICT_ABSENT = 0,        /* handshake content never matched */
    GBP_VERDICT_PRESENT = 1,       /* every handshake matched by the vote criterion */
    GBP_VERDICT_INCONSISTENT = 2,  /* criteria disagree or some transfers failed: do not trust */
    GBP_VERDICT_NO_DATA = 3        /* no handshake was completed */
} gbp_verdict;

/*
 * Open-GBP presence policy:
 *   PRESENT      iff n_handshakes > 0, every transfer completed, and the
 *                vote criterion passed for every pattern;
 *   ABSENT       iff transfers completed and the vote criterion passed for none;
 *   INCONSISTENT otherwise (partial matches, disc/vote disagreement,
 *                transport failures) — the caller must not proceed as if
 *                a GBP were present, and should log everything.
 * The disc criterion is computed and reported alongside as a cross-check.
 */
gbp_verdict gbp_presence_verdict(unsigned n_handshakes, unsigned n_transport_ok,
                                 unsigned n_vote_ok, unsigned n_disc_ok);

const char *gbp_verdict_name(gbp_verdict v);

/* Result of one TEST handshake sequence (write 32×p, read, judge). */
struct gbp_handshake_result {
    unsigned run, transport_ok, vote_ok, b1_ok, all32_ok, b1f_ok, failed;
    uint8_t last_resp[GBP_BLOCK_SIZE];
    gbp_verdict verdict;
};

/* Performs the handshake for every pattern against block `index` (0 =
 * TEST) at `base`, logging one "TESTW <tag> ..." and one "TESTR <tag> ..."
 * record per pattern (tag e.g. "mode=A" or "tag=DET"), and fills `out`
 * including the presence verdict. Only the TEST block is written. */
void gbp_detect_handshake(const struct gbp_transport *t, struct ringlog *log, const char *tag,
                          uint32_t base, unsigned index, const uint8_t *patterns, unsigned npatterns,
                          struct gbp_handshake_result *out);

#ifdef __cplusplus
}
#endif
#endif
