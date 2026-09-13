#include "gbp_mock.h"

#include <string.h>

void gbp_mock_init(struct gbp_mock *m)
{
    memset(m, 0, sizeof *m);
    m->present = 1;
    m->require_expansion = 0;
    m->byte_doubled = 1;
    m->arinfo = 0x0043;           /* size code 3 (16 MB), no expansion, bit 6 set (as GBI leaves it) */
    m->control_byte = 0x02;       /* "cartridge inserted" per Phase 2 usage */
    m->irq_value = 0x0000;
    m->absent_fill = 0x00;
    memset(m->test_store, 0xFF, sizeof m->test_store); /* ~0x00 initial */
}

static void record(struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t addr, uint16_t value,
                   const uint8_t *data, gbp_status rc)
{
    struct gbp_mock_op *op;
    if (m->nops >= GBP_MOCK_MAX_OPS) { m->ops_dropped++; return; }
    op = &m->ops[m->nops++];
    op->kind = kind;
    op->addr = addr;
    op->value = value;
    op->rc = rc;
    if (data) memcpy(op->data, data, GBP_BLOCK_SIZE); else memset(op->data, 0, GBP_BLOCK_SIZE);
}

static gbp_status m_read_arinfo(void *ctx, uint16_t *v)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    *v = m->arinfo;
    record(m, MOCK_AR_R, 0, *v, 0, GBP_OK);
    return GBP_OK;
}

static gbp_status m_write_arinfo(void *ctx, uint16_t v)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    m->arinfo = v;
    record(m, MOCK_AR_W, 0, v, 0, GBP_OK);
    return GBP_OK;
}

static int answers(const struct gbp_mock *m)
{
    if (!m->present) return 0;
    if (m->require_expansion && ((m->arinfo >> 3) & 7u) == 0) return 0;
    return 1;
}

static gbp_status fault(struct gbp_mock *m, struct gbp_xfer_info *info)
{
    m->transfers++;
    if (info) {
        memset(info, 0, sizeof *info);
        info->ticks = 100 + m->transfers;
        info->polls = 1;
        info->dma_status = 0x0020;
    }
    if (m->stuck) {
        if (info) info->dma_status = 0x0200;
        return GBP_ERR_BUSY;
    }
    if (m->fail_at_op && m->transfers == m->fail_at_op) {
        if (m->fail_rc == GBP_ERR_TIMEOUT && m->stuck_after_timeout) m->stuck = 1;
        if (info) info->dma_status = (m->fail_rc == GBP_ERR_TIMEOUT) ? 0x0200 : 0x0000;
        return m->fail_rc;
    }
    return GBP_OK;
}

static unsigned index_of(uint32_t base, uint32_t addr)
{
    return (unsigned)((addr - base) >> 20) & 0xFu;
}

static void present_bytes(const struct gbp_mock *m, const uint8_t *logical, size_t n, uint8_t out[GBP_BLOCK_SIZE])
{
    /* logical = n bytes of register content, right-aligned in the block */
    size_t i;
    memset(out, 0, GBP_BLOCK_SIZE);
    if (m->byte_doubled) {
        /* each logical byte occupies two block bytes, value right-aligned */
        for (i = 0; i < n && 2 * i + 1 < GBP_BLOCK_SIZE; i++) {
            size_t k = GBP_BLOCK_SIZE - 2u - 2u * (n - 1u - i);
            out[k] = logical[i];
            out[k + 1] = logical[i];
        }
    } else {
        for (i = 0; i < n; i++) out[GBP_BLOCK_SIZE - n + i] = logical[i];
    }
}

static gbp_status m_read_block(void *ctx, uint32_t addr, uint8_t out[GBP_BLOCK_SIZE],
                               struct gbp_xfer_info *info)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    uint32_t base = gbp_internal_size_from_arinfo(m->arinfo);
    gbp_status rc = fault(m, info);
    if (rc != GBP_OK) { memset(out, 0, GBP_BLOCK_SIZE); record(m, MOCK_RD, addr, 0, 0, rc); return rc; }
    if (!answers(m)) {
        memset(out, m->absent_fill, GBP_BLOCK_SIZE);
    } else {
        switch (index_of(base, addr)) {
        case 0x0:
            memcpy(out, m->test_store, GBP_BLOCK_SIZE);
            break;
        case 0x4: {
            uint8_t v = m->control_byte;
            present_bytes(m, &v, 1, out);
            break;
        }
        case 0xD: {
            uint8_t v[2];
            v[0] = (uint8_t)(m->irq_value >> 8);
            v[1] = (uint8_t)m->irq_value;
            present_bytes(m, v, 2, out);
            break;
        }
        default:
            memset(out, 0xEE, GBP_BLOCK_SIZE);   /* "unexpected block" marker */
            break;
        }
    }
    record(m, MOCK_RD, addr, 0, out, GBP_OK);
    return GBP_OK;
}

static gbp_status m_write_block(void *ctx, uint32_t addr, const uint8_t in[GBP_BLOCK_SIZE],
                                struct gbp_xfer_info *info)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    uint32_t base = gbp_internal_size_from_arinfo(m->arinfo);
    gbp_status rc = fault(m, info);
    record(m, MOCK_WR, addr, 0, in, rc);
    if (rc != GBP_OK) return rc;
    if (answers(m) && index_of(base, addr) == 0x0) {
        size_t i;
        for (i = 0; i < GBP_BLOCK_SIZE; i++) m->test_store[i] = (uint8_t)~in[i];
    }
    return GBP_OK;
}

void gbp_mock_transport(struct gbp_mock *m, struct gbp_transport *t)
{
    t->read_arinfo = m_read_arinfo;
    t->write_arinfo = m_write_arinfo;
    t->read_block = m_read_block;
    t->write_block = m_write_block;
    t->ctx = m;
}

unsigned gbp_mock_writes_outside(const struct gbp_mock *m, uint32_t base, unsigned allowed_index)
{
    unsigned i, n = 0;
    for (i = 0; i < m->nops; i++) {
        if (m->ops[i].kind == MOCK_WR && index_of(base, m->ops[i].addr) != allowed_index) n++;
    }
    return n;
}
