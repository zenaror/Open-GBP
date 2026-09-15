#include "gbp_replay.h"

#include <stdlib.h>
#include <string.h>

static int hexval(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

size_t gbp_hex_decode(const char *hex, uint8_t *out, size_t cap)
{
    size_t n = 0;
    while (n < cap) {
        int h = hexval(hex[0]), l;
        if (h < 0) break;
        l = hexval(hex[1]);
        if (l < 0) break;
        out[n++] = (uint8_t)((h << 4) | l);
        hex += 2;
    }
    return n;
}

static gbp_status status_from_name(const char *s)
{
    if (strncmp(s, "ok", 2) == 0) return GBP_OK;
    if (strncmp(s, "timeout", 7) == 0) return GBP_ERR_TIMEOUT;
    if (strncmp(s, "busy", 4) == 0) return GBP_ERR_BUSY;
    if (strncmp(s, "param", 5) == 0) return GBP_ERR_PARAM;
    return GBP_ERR_BACKEND;
}

/* Returns pointer to the next non-comment line and advances pos past it;
 * NULL when exhausted. Copies the line into buf (truncated). */
static const char *next_line(struct gbp_replay *r, char *buf, size_t cap)
{
    for (;;) {
        const char *s = r->script + r->pos;
        const char *e;
        size_t len;
        if (*s == '\0') return 0;
        e = strchr(s, '\n');
        len = e ? (size_t)(e - s) : strlen(s);
        r->pos += len + (e ? 1u : 0u);
        while (len > 0 && (s[0] == ' ' || s[0] == '\t')) { s++; len--; }
        if (len == 0 || s[0] == '#') continue;
        if (len >= cap) len = cap - 1u;
        memcpy(buf, s, len);
        buf[len] = '\0';
        return buf;
    }
}

/* Like next_line, but leaves pos untouched. */
static const char *peek_line(struct gbp_replay *r, char *buf, size_t cap)
{
    size_t saved = r->pos;
    const char *l = next_line(r, buf, cap);
    r->pos = saved;
    return l;
}

static gbp_status r_read_arinfo(void *ctx, uint16_t *value)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    if (!next_line(r, line, sizeof line)) { r->exhausted++; return GBP_ERR_BACKEND; }
    r->step++;
    if (line[0] != 'A' || line[2] != 'r') { r->mismatches++; return GBP_ERR_BACKEND; }
    *value = (uint16_t)strtoul(line + 4, 0, 16);
    r->arinfo = *value;
    return GBP_OK;
}

static gbp_status r_write_arinfo(void *ctx, uint16_t value)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    if (!next_line(r, line, sizeof line)) { r->exhausted++; return GBP_ERR_BACKEND; }
    r->step++;
    if (line[0] != 'A' || line[2] != 'w') { r->mismatches++; return GBP_ERR_BACKEND; }
    if ((uint16_t)strtoul(line + 4, 0, 16) != value) { r->mismatches++; return GBP_ERR_BACKEND; }
    r->arinfo = value;
    return GBP_OK;
}

static gbp_status r_read_block(void *ctx, uint32_t addr, uint8_t out[GBP_BLOCK_SIZE],
                               struct gbp_xfer_info *info)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    char *p, *end;
    gbp_status rc;
    if (info) memset(info, 0, sizeof *info);
    if (!next_line(r, line, sizeof line)) { r->exhausted++; return GBP_ERR_BACKEND; }
    r->step++;
    if (line[0] != 'R') { r->mismatches++; return GBP_ERR_BACKEND; }
    p = line + 2;
    if ((uint32_t)strtoul(p, &end, 16) != addr) { r->mismatches++; return GBP_ERR_BACKEND; }
    while (*end == ' ') end++;
    rc = status_from_name(end);
    p = strchr(end, ' ');
    memset(out, 0, GBP_BLOCK_SIZE);
    if (rc == GBP_OK && p) {
        while (*p == ' ') p++;
        gbp_hex_decode(p, out, GBP_BLOCK_SIZE);
    }
    return rc;
}

static gbp_status r_write_block(void *ctx, uint32_t addr, const uint8_t in[GBP_BLOCK_SIZE],
                                struct gbp_xfer_info *info)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    char *end;
    (void)in;
    if (info) memset(info, 0, sizeof *info);
    if (!next_line(r, line, sizeof line)) { r->exhausted++; return GBP_ERR_BACKEND; }
    r->step++;
    if (line[0] != 'W') { r->mismatches++; return GBP_ERR_BACKEND; }
    if ((uint32_t)strtoul(line + 2, &end, 16) != addr) { r->mismatches++; return GBP_ERR_BACKEND; }
    while (*end == ' ') end++;
    return status_from_name(end);
}

static gbp_status r_read_pi(void *ctx, uint32_t *intsr, uint32_t *intmr)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    char *end;
    if (!next_line(r, line, sizeof line)) { r->exhausted++; return GBP_ERR_BACKEND; }
    r->step++;
    if (line[0] != 'P' || line[2] != 'r') { r->mismatches++; return GBP_ERR_BACKEND; }
    *intsr = (uint32_t)strtoul(line + 4, &end, 16);
    *intmr = (uint32_t)strtoul(end, 0, 16);
    r->last_intsr = *intsr;
    return GBP_OK;
}

static gbp_status r_write_intmr(void *ctx, uint32_t v)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    if (!next_line(r, line, sizeof line)) { r->exhausted++; return GBP_ERR_BACKEND; }
    r->step++;
    if (line[0] != 'P' || line[2] != 'w') { r->mismatches++; return GBP_ERR_BACKEND; }
    if ((uint32_t)strtoul(line + 4, 0, 16) != v) { r->mismatches++; return GBP_ERR_BACKEND; }
    return GBP_OK;
}

static gbp_status r_write_intsr(void *ctx, uint32_t v)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    if (!next_line(r, line, sizeof line)) { r->exhausted++; return GBP_ERR_BACKEND; }
    r->step++;
    if (line[0] != 'P' || line[2] != 'a') { r->mismatches++; return GBP_ERR_BACKEND; }
    if ((uint32_t)strtoul(line + 4, 0, 16) != v) { r->mismatches++; return GBP_ERR_BACKEND; }
    return GBP_OK;
}

static uint32_t r_ticks(void *ctx)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    if (!r->timeline) return r->step * 10u;
    if (peek_line(r, line, sizeof line) && line[0] == 'T' && line[1] == ' ') {
        next_line(r, line, sizeof line);
        r->step++;
        r->last_ticks = (uint32_t)strtoul(line + 2, 0, 10);
        return r->last_ticks;
    }
    r->tick_polls++;
    r->last_ticks += r->poll_increment ? r->poll_increment : 1u;
    return r->last_ticks;
}

static gbp_status r_poll_intsr(void *ctx, uint32_t *intsr)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    if (peek_line(r, line, sizeof line) && line[0] == 'P' && line[2] == 'p') {
        next_line(r, line, sizeof line);
        r->step++;
        r->last_intsr = (uint32_t)strtoul(line + 4, 0, 16);
    }
    *intsr = r->last_intsr;
    return GBP_OK;
}

/* ---- interrupt path (only when the script carries "I " lines) ---- */

static int expect_irq_line(struct gbp_replay *r, char op, char *line, size_t cap)
{
    if (!next_line(r, line, cap)) { r->exhausted++; return 0; }
    r->step++;
    if (line[0] != 'I' || line[1] != ' ' || line[2] != op) { r->mismatches++; return 0; }
    return 1;
}

static gbp_status r_irq_install(void *ctx, int *old_was_null)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    if (!expect_irq_line(r, 'i', line, sizeof line)) return GBP_ERR_BACKEND;
    memset(&r->rec, 0, sizeof r->rec);
    r->handler_installed = 1;
    if (old_was_null) *old_was_null = (strncmp(line + 4, "null", 4) == 0) ? 1 : 0;
    return GBP_OK;
}

static gbp_status r_irq_restore(void *ctx)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    if (!expect_irq_line(r, 'r', line, sizeof line)) return GBP_ERR_BACKEND;
    r->handler_installed = 0;
    return GBP_OK;
}

static gbp_status r_irq_mask(void *ctx)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    if (!expect_irq_line(r, 'm', line, sizeof line)) return GBP_ERR_BACKEND;
    return GBP_OK;
}

static gbp_status r_irq_unmask(void *ctx)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    char line[160];
    char *p, *end;
    uint32_t v[14];
    unsigned k, n = 9;
    if (!expect_irq_line(r, 'u', line, sizeof line)) return GBP_ERR_BACKEND;
    p = line + 3;
    memset(v, 0, sizeof v);
    for (k = 0; k < 14; k++) {
        while (*p == ' ') p++;
        if (k >= 9 && *p == '\0') break;                      /* the extended fields are optional */
        v[k] = (uint32_t)strtoul(p, &end, (k < 3 || k == 10 || k == 13) ? 10 : 16);
        if (end == p) { r->mismatches++; return GBP_ERR_BACKEND; }
        p = end;
        n = k + 1u;
    }
    (void)n;
    r->rec.count = v[0];
    r->rec.fired = v[1];
    r->rec.t_entry = v[2];
    r->rec.intsr_before_ack = v[3];
    r->rec.intmr_at_entry = v[4];
    r->rec.intsr_after_ack = v[5];
    r->rec.intmr_after_mask = v[6];
    r->rec.reentry_intsr = v[7];
    r->rec.reentry_intmr = v[8];
    r->rec.intsr_before_w1c = v[9];                          /* extended handler (GBP-INIT-003B): */
    r->rec.t_second = v[10];                                 /*   intsr_before_w1c t_second intsr_second intmr_second reentry_t */
    r->rec.intsr_second = v[11];
    r->rec.intmr_second = v[12];
    r->rec.reentry_t = v[13];
    return GBP_OK;
}

static gbp_status r_irq_record(void *ctx, struct gbp_irq_record *out)
{
    struct gbp_replay *r = (struct gbp_replay *)ctx;
    *out = r->rec;
    return GBP_OK;
}

void gbp_replay_init(struct gbp_replay *r, const char *script)
{
    const char *s;
    memset(r, 0, sizeof *r);
    r->script = script ? script : "";
    /* Detect the optional sections once: "I " lines enable the interrupt
     * path, "T " lines enable the physical timeline for ticks(). */
    for (s = r->script; *s; ) {
        while (*s == ' ' || *s == '\t') s++;
        if (s[0] == 'I' && s[1] == ' ') r->has_irq_ops = 1;
        if (s[0] == 'T' && s[1] == ' ') r->timeline = 1;
        s = strchr(s, '\n');
        if (!s) break;
        s++;
    }
}

void gbp_replay_transport(struct gbp_replay *r, struct gbp_transport *t)
{
    t->read_arinfo = r_read_arinfo;
    t->write_arinfo = r_write_arinfo;
    t->read_block = r_read_block;
    t->write_block = r_write_block;
    t->read_pi = r_read_pi;
    t->write_intmr = r_write_intmr;
    /* No interrupt path in a replay: physical logs record no IRQ
     * operations, and none may be invented (docs/research/DEVLOG.md
     * 2026-09-15). A probe that needs it stops at its handler-install step. */
    t->write_intsr = r_write_intsr;
    t->poll_intsr = r_poll_intsr;
    if (r->has_irq_ops) {
        t->irq_install = r_irq_install;
        t->irq_restore = r_irq_restore;
        t->irq_mask = r_irq_mask;
        t->irq_unmask = r_irq_unmask;
        t->irq_record = r_irq_record;
    } else {
        t->irq_install = 0;
        t->irq_restore = 0;
        t->irq_mask = 0;
        t->irq_unmask = 0;
        t->irq_record = 0;
    }
    t->ticks = r_ticks;
    t->ctx = r;
}
