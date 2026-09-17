/*
 * sdlog.h — flush a ringlog to the SD2SP2 card (libogc2 + libfat).
 *
 * Never call this from a timing-critical path. It mounts the card, writes
 * one text file, unmounts, and reports what happened in a status string
 * so the screen can show it even when the card is absent.
 */
#ifndef OPENGBP_SDLOG_H
#define OPENGBP_SDLOG_H

#include <stddef.h>
#include <stdint.h>
#include "../log/ringlog.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Writes /<mount>/open-gbp/<test_id>_<build_id>.log with a header
 * (test_id, build_id, commit, extra) followed by every ringlog line and a
 * footer with the dropped/truncated counters. Returns 0 on success,
 * negative on failure; status receives a short human-readable message. */
int sdlog_save(const char *test_id, const char *build_id, const char *commit,
               const char *extra_header, const struct ringlog *rl,
               char *status, size_t status_cap, char *path_out, size_t path_cap);

/* Writes /<mount>/open-gbp/<test_id>_<build_id><suffix> with `len` raw bytes
 * (GBP-AV-SERVICE-001: the block sidecar "-blocks.bin", src/gbp/gbp_avdump.h).
 * Same rules as sdlog_save: never from a timing-critical path, mounts and
 * unmounts the card, reports in `status`. Returns 0 on success, negative on
 * failure (-4: short write). */
int sdlog_save_blob(const char *test_id, const char *build_id, const char *suffix,
                    const uint8_t *data, size_t len,
                    char *status, size_t status_cap, char *path_out, size_t path_cap);

/*
 * Streaming variant (GBP-VIDEO-002): the sidecar is several megabytes and is
 * never staged in RAM. The caller opens the file, pushes chunks of about
 * 64 KiB as it serializes, and closes. Same rules as the two calls above:
 * never from a timing-critical path, and — for an experiment — only after
 * the hardware teardown has completed.
 */
struct sdlog_stream {
    void *fp;                 /* FILE *, opaque here so callers need no <stdio.h> */
    int mounted;
    int failed;               /* a write or the open failed: no further write is attempted */
    uint64_t written;
    char path[128];
};

/* Opens /<mount>/open-gbp/<test_id>_<build_id><suffix> for writing. Returns 0
 * on success, negative on failure (-1 mount, -2 open); `status` explains. */
int sdlog_stream_open(struct sdlog_stream *s, const char *test_id, const char *build_id, const char *suffix,
                      char *status, size_t status_cap);
/* Appends `len` bytes. Returns 0 on success, -1 once the stream has failed
 * (the first failure is remembered and `written` stops advancing). */
int sdlog_stream_write(struct sdlog_stream *s, const uint8_t *data, uint32_t len);
/* Closes and unmounts. Returns 0 when the whole stream was written, negative
 * otherwise; `status` reports the byte count and the path either way. */
int sdlog_stream_close(struct sdlog_stream *s, char *status, size_t status_cap);

#ifdef __cplusplus
}
#endif
#endif
