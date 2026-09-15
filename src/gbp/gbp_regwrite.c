#include "gbp_regwrite.h"

#include <string.h>

#define IDX_CONTROL 4u
#define IDX_IRQ 0xDu

void gbp_regwrite_u16_layout(uint16_t value, uint8_t out[GBP_BLOCK_SIZE])
{
    unsigned i;
    for (i = 0; i < GBP_BLOCK_SIZE; i += 2u) {
        out[i] = (uint8_t)(value >> 8);
        out[i + 1u] = (uint8_t)(value & 0xFFu);
    }
}

void gbp_regwrite_byte_layout(uint8_t value, uint8_t out[GBP_BLOCK_SIZE])
{
    memset(out, value, GBP_BLOCK_SIZE);
}

static void do_write(const struct gbp_transport *t, uint32_t addr, struct gbp_regwrite_result *out, unsigned *errors)
{
    out->addr = addr;
    out->attempted = 1;
    memset(&out->info, 0, sizeof out->info);
    out->rc = t->write_block(t->ctx, addr, out->raw, &out->info);
    out->t_after = t->ticks ? t->ticks(t->ctx) : 0u;
    out->completed = (out->rc == GBP_OK) ? 1 : 0;
    if (out->rc != GBP_OK && errors) (*errors)++;
}

void gbp_regwrite_irq_u16(const struct gbp_transport *t, const char *tag, uint32_t base,
                          uint16_t before, uint16_t value, struct gbp_regwrite_result *out, unsigned *errors)
{
    memset(out, 0, sizeof *out);
    out->kind = GBP_REGWRITE_IRQ_U16;
    out->tag = tag;
    out->before = before;
    out->value = value;
    gbp_regwrite_u16_layout(value, out->raw);
    do_write(t, gbp_block_addr(base, IDX_IRQ, 0), out, errors);
}

void gbp_regwrite_control_byte(const struct gbp_transport *t, const char *tag, uint32_t base,
                               uint8_t value, struct gbp_regwrite_result *out, unsigned *errors)
{
    memset(out, 0, sizeof *out);
    out->kind = GBP_REGWRITE_CONTROL_BYTE;
    out->tag = tag;
    out->value = value;
    gbp_regwrite_byte_layout(value, out->raw);
    do_write(t, gbp_block_addr(base, IDX_CONTROL, 0), out, errors);
}

void gbp_regwrite_log(struct ringlog *log, const struct gbp_regwrite_result *r)
{
    char hex[GBP_BLOCK_SIZE * 2 + 1];
    if (!r->attempted) return;
    ringlog_hex(hex, sizeof hex, r->raw, GBP_BLOCK_SIZE);
    if (r->kind == GBP_REGWRITE_IRQ_U16) {
        ringlog_printf(log, "IRQW %s addr=%08lx before=%04x write=%04x layout=gbi-u16-replicated rc=%s ticks=%lu polls=%u dspcr=%04x t_after=%lu data=%s",
                       r->tag, (unsigned long)r->addr, (unsigned)r->before, (unsigned)r->value, gbp_status_name(r->rc),
                       (unsigned long)r->info.ticks, (unsigned)r->info.polls, (unsigned)r->info.dma_status,
                       (unsigned long)r->t_after, hex);
    } else {
        ringlog_printf(log, "CTLW %s addr=%08lx semantic=%02x rc=%s ticks=%lu polls=%u dspcr=%04x t_after=%lu layout=gbi-replicated data=%s",
                       r->tag, (unsigned long)r->addr, (unsigned)r->value, gbp_status_name(r->rc),
                       (unsigned long)r->info.ticks, (unsigned)r->info.polls, (unsigned)r->info.dma_status,
                       (unsigned long)r->t_after, hex);
    }
}
