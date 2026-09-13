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

#ifdef __cplusplus
}
#endif
#endif
