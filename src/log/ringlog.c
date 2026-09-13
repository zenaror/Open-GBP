#include "ringlog.h"

#include <stdio.h>
#include <string.h>

void ringlog_init(struct ringlog *rl, char *storage, size_t line_len, size_t capacity)
{
    rl->storage = storage;
    rl->line_len = line_len;
    rl->capacity = capacity;
    rl->count = 0;
    rl->dropped = 0;
    rl->truncated = 0;
    rl->seq = 0;
    if (storage != 0 && line_len > 0 && capacity > 0) {
        storage[0] = '\0';
    }
}

int ringlog_vprintf(struct ringlog *rl, const char *fmt, va_list ap)
{
    char *line;
    int n, m;

    if (rl->storage == 0 || rl->line_len < 8u) {
        rl->dropped++;
        return -1;
    }
    if (rl->count >= rl->capacity) {
        rl->dropped++;
        rl->seq++;
        return -1;
    }
    line = rl->storage + rl->count * rl->line_len;
    n = snprintf(line, rl->line_len, "%06u ", (unsigned)rl->seq);
    rl->seq++;
    if (n < 0 || (size_t)n >= rl->line_len) {
        line[rl->line_len - 1u] = '\0';
        rl->count++;
        rl->truncated++;
        return 1;
    }
    m = vsnprintf(line + n, rl->line_len - (size_t)n, fmt, ap);
    rl->count++;
    if (m < 0 || (size_t)m >= rl->line_len - (size_t)n) {
        rl->truncated++;
        return 1;
    }
    return 0;
}

int ringlog_printf(struct ringlog *rl, const char *fmt, ...)
{
    va_list ap;
    int r;
    va_start(ap, fmt);
    r = ringlog_vprintf(rl, fmt, ap);
    va_end(ap);
    return r;
}

const char *ringlog_line(const struct ringlog *rl, size_t index)
{
    if (rl->storage == 0 || index >= rl->count) {
        return 0;
    }
    return rl->storage + index * rl->line_len;
}

char *ringlog_hex(char *dst, size_t dst_cap, const uint8_t *src, size_t n)
{
    static const char digits[] = "0123456789abcdef";
    size_t i, o = 0;
    for (i = 0; i < n && o + 2u < dst_cap; i++) {
        dst[o++] = digits[src[i] >> 4];
        dst[o++] = digits[src[i] & 0xF];
    }
    if (dst_cap > 0) {
        dst[o < dst_cap ? o : dst_cap - 1u] = '\0';
    }
    return dst;
}
