/*
 * ringlog.h — preallocated, fixed-line RAM event log.
 *
 * Designed for the CLAUDE.md §13 flow:  event → RAM ring buffer → later
 * flush (SD2SP2 / USB Gecko / screen).  No allocation after init, no I/O,
 * safe to call from any context that may call vsnprintf (not from IRQ
 * handlers that must not touch the stack heavily — keep IRQ-side logging
 * to preformatted records if that ever becomes necessary).
 *
 * When the buffer is full, new lines are DROPPED and `dropped` is
 * incremented: the earliest records (identity, original hardware state)
 * are the ones worth keeping for a probe.
 */
#ifndef OPENGBP_RINGLOG_H
#define OPENGBP_RINGLOG_H

#include <stddef.h>
#include <stdint.h>
#include <stdarg.h>

#ifdef __cplusplus
extern "C" {
#endif

struct ringlog {
    char *storage;      /* capacity * line_len bytes, caller-provided */
    size_t line_len;    /* including the terminating NUL */
    size_t capacity;    /* number of lines */
    size_t count;       /* lines stored */
    uint32_t dropped;   /* lines refused because the buffer was full */
    uint32_t truncated; /* lines that did not fit line_len and were cut */
    uint32_t seq;       /* monotonically increasing record number */
};

/* storage must hold capacity * line_len bytes; line_len >= 8. */
void ringlog_init(struct ringlog *rl, char *storage, size_t line_len, size_t capacity);

/* Appends one formatted line, prefixed with "NNNNNN " (seq, 6 digits).
 * Returns 0 on success, 1 if truncated, -1 if dropped. */
int ringlog_printf(struct ringlog *rl, const char *fmt, ...)
#if defined(__GNUC__)
    __attribute__((format(printf, 2, 3)))
#endif
    ;
int ringlog_vprintf(struct ringlog *rl, const char *fmt, va_list ap);

/* Access stored lines in order (0 = oldest). NULL if out of range. */
const char *ringlog_line(const struct ringlog *rl, size_t index);

/* Formats 'n' bytes as lowercase hex into dst (needs 2n+1 bytes).
 * Returns dst. Shared helper so every log line encodes raw data the
 * same way. */
char *ringlog_hex(char *dst, size_t dst_cap, const uint8_t *src, size_t n);

#ifdef __cplusplus
}
#endif
#endif
