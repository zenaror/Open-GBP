/*
 * gbp_awr.h — "audio window, raw, one run": the raw-block ride-along of
 * GBP-AUDIO-012 (HARDWARE_TESTS §V27; GitHub Issue #117). ONE contiguous
 * capture of N whole 4 096-byte AUDIO blocks into a caller-provided store,
 * armed once at a given moment, filled one block per call from the POC's
 * audio tap, closed when the store is full or when the POC tears down.
 *
 * WHY NOT gbp_awin. OGBPAW1 (gbp_awindump.h) is a frozen contract with a
 * fixed geometry: five windows of 256 blocks, a KEY-write anchor per window,
 * a 5 242 880-byte store that the §V27 image cannot afford beside its frame
 * store (brief B6/B7). A frozen contract is never extended in place, so a
 * single window of caller-chosen length is a NEW module and a NEW magic,
 * OGBPAWR1, with its own reader (tools/awrparse.py). Nothing here includes
 * gbp_awin; the two share only the family's conventions: 8-byte magic,
 * big-endian field by field, a header CRC-32 and a footer CRC-32 over
 * everything before the footer, the runtime's own gbp_crc32.
 *
 * WHAT IT IS NOT. It has no anchor of its own: §V27.11 places the ride-along
 * "right after the A press and before the first switch", outside every
 * phase, so the only instants it can carry are t_arm (the timebase when the
 * POC armed it) and the completion ticks of the first and last stored block,
 * plus the caller's per-block sequence of those two blocks. It measures no
 * clock: the caller times the whole gbp_awr_block() call and reports the
 * ticks through gbp_awr_note_cost(), so the copy's cost is reported, never
 * asserted (§V27.1: any instrument runs with its cost logged).
 *
 * WHERE EACH HALF RUNS.
 *
 *   gbp_awr_arm()      THE PUMP SLOT, once. Sets t_arm and the state; never
 *                      touches the store.
 *   gbp_awr_block()    THE AUDIO TAP, once per received AUDIO block. One
 *                      memcpy of 4 096 bytes in RAM while armed; no device
 *                      access, no allocation, no filesystem, no clock read.
 *   gbp_awr_finish()   THE TEARDOWN. Closes a capture still filling so the
 *                      file never claims a store that was not filled: a DONE
 *                      header with blocks_stored < blocks_cap says so.
 *   gbp_awr_header()   AFTER THE TEARDOWN, when the POC writes the file
 *   gbp_awr_footer()   through the sdlog stream API: header, then the blocks
 *   gbp_awr_stream()   straight out of the store, then the footer.
 *
 * In the §V27 image the tap and the pump slot are sequential on the main
 * thread (brief §3), so no field here is volatile; the module is bounded,
 * allocates nothing and prints nothing, and builds on the host
 * (tests/unit/test_gbp_awr.c).
 *
 * THE FILE, "OGBPAWR1" (big-endian, offsets in bytes):
 *
 *   header   0x80 bytes
 *     0x00  magic        "OGBPAWR1"
 *     0x08  version      u32   1
 *     0x0C  block_size   u32   4096
 *     0x10  blocks_stored u32
 *     0x14  blocks_cap   u32   the store's capacity in blocks
 *     0x18  tb_hz        u32   the timebase every tick field counts in
 *     0x1C  state        u32   0 idle, 1 armed, 2 filling, 3 done
 *     0x20  t_arm        u64   timebase at gbp_awr_arm()
 *     0x28  t_first      u64   completion ticks of the first stored block
 *     0x30  t_last       u64   completion ticks of the last stored block
 *     0x38  copy_min     u32   gbp_awr_note_cost() statistics (ticks)
 *     0x3C  copy_max     u32
 *     0x40  copy_sum     u64
 *     0x48  copy_n       u32
 *     0x4C  faults       u32   blocks offered while armed with a wrong length or no bytes
 *     0x50  ignored      u32   blocks offered while not armed (idle, or done)
 *     0x54  seen         u32   gbp_awr_block() calls
 *     0x58  seq_first    u32   the caller's sequence of the first stored block
 *     0x5C  seq_last     u32   ... and of the last
 *     0x60  arm_refused  u32   arms refused because one had already happened
 *     0x64  reserved     24 bytes, zero
 *     0x7C  crc32        u32   CRC-32 over 0x00 .. 0x7B
 *   blocks   blocks_stored x 4096 bytes, in the order stored
 *   footer   12 bytes: "OGBPAWRE" + u32 CRC-32 over everything before it
 */
#ifndef OPENGBP_GBP_AWR_H
#define OPENGBP_GBP_AWR_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_AWR_BLOCK_SIZE    0x1000u
#define GBP_AWR_MAGIC         "OGBPAWR1"
#define GBP_AWR_END           "OGBPAWRE"
#define GBP_AWR_VERSION       1u
#define GBP_AWR_HEADER_SIZE   0x80u
#define GBP_AWR_FOOTER_SIZE   12u
#define GBP_AWR_CRC_OFFSET    (GBP_AWR_HEADER_SIZE - 4u)    /* 0x7C */

enum gbp_awr_state {
    GBP_AWR_IDLE    = 0,
    GBP_AWR_ARMED   = 1,
    GBP_AWR_FILLING = 2,
    GBP_AWR_DONE    = 3
};

struct gbp_awr {
    uint8_t *store;
    uint32_t blocks_cap;        /* the store holds blocks_cap x GBP_AWR_BLOCK_SIZE bytes */
    uint32_t tb_hz;
    uint32_t state;             /* enum gbp_awr_state */
    uint32_t blocks_stored;
    uint64_t t_arm, t_first, t_last;
    uint32_t seq_first, seq_last;
    /* the cost of the copy, MEASURED by the caller and reported, never asserted */
    uint32_t copy_min, copy_max, copy_n;
    uint64_t copy_sum;
    /* what the tap offered and what was not kept */
    uint32_t seen, ignored, faults, arm_refused;
    int fault;                  /* init: 0 ok, 1 store_null, 2 cap_zero */
};

/* 0 on success; -1 with `fault` set otherwise. `blocks_cap` >= 1; the store
 * is the caller's and must hold blocks_cap x 4096 bytes. `tb_hz` only travels
 * into the header. */
int gbp_awr_init(struct gbp_awr *w, uint8_t *store, uint32_t blocks_cap, uint32_t tb_hz);
const char *gbp_awr_fault(const struct gbp_awr *w);

/* THE PUMP SLOT. 0 when the capture is now ARMED; -1 (counted) when it had
 * already been armed, finished, or never initialised. Armed once, ever. */
int gbp_awr_arm(struct gbp_awr *w, uint64_t t_now);

/* THE AUDIO TAP. One call per received AUDIO block. Returns 1 when the block
 * was stored, 0 otherwise: not armed (`ignored`), or armed but `len` is not
 * 4096 or `block` is null (`faults`). `t_done` is the block's completion
 * ticks and `seq` any per-block counter the caller keeps (0 if none); both
 * are recorded for the first and the last stored block. The store's last
 * block moves the state to DONE. */
int gbp_awr_block(struct gbp_awr *w, const uint8_t *block, uint32_t len, uint64_t t_done, uint32_t seq);

/* The ticks the caller measured around ONE gbp_awr_block() call. */
void gbp_awr_note_cost(struct gbp_awr *w, uint32_t ticks);

/* THE TEARDOWN. ARMED or FILLING -> DONE; nothing else changes. */
void gbp_awr_finish(struct gbp_awr *w);

/* 1 when the state is DONE (the store is full, or finish() closed it). */
int gbp_awr_done(const struct gbp_awr *w);
unsigned gbp_awr_copy_mean(const struct gbp_awr *w);
const uint8_t *gbp_awr_block_bytes(const struct gbp_awr *w, uint32_t index);

/* THE SERIALIZER. Never from a timing-critical path.
 *
 * gbp_awr_header()  writes the 0x80-byte header (with its CRC) into `out`;
 *                   returns 0x80, or 0 when `cap` < 0x80 or `w` is null.
 * gbp_awr_footer()  writes the 12-byte footer into `out` from the RUNNING
 *                   CRC-32 state (gbp_crc32_init(), then gbp_crc32_update()
 *                   over the header and every stored block, in file order);
 *                   it finalises the state itself. Returns 12, or 0.
 * gbp_awr_total()   the file's size for the current blocks_stored.
 *
 * gbp_awr_stream()  the whole file through `sink`: header, the blocks straight
 *                   out of the store (moved once, never staged), footer.
 *                   Returns the bytes written, or -1 (bad argument), -2 (the
 *                   sink refused; `written` says how far it got). */
size_t gbp_awr_header(const struct gbp_awr *w, uint8_t *out, size_t cap);
size_t gbp_awr_footer(uint32_t crc_state, uint8_t *out, size_t cap);
uint64_t gbp_awr_total(const struct gbp_awr *w);

typedef int (*gbp_awr_sink)(void *ctx, const uint8_t *data, uint32_t len);
long gbp_awr_stream(const struct gbp_awr *w, gbp_awr_sink sink, void *sink_ctx, uint64_t *written);

#ifdef __cplusplus
}
#endif
#endif
