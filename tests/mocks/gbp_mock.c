#include "gbp_mock.h"

#include <string.h>

/* ---- one-shot handler body, run by the mock's delivery engine ---------
 * The very same statements the real backend executes (gbp_irq_oneshot.h);
 * the primitives act on the mock's PI model and record events so a test
 * can prove the order mask → W1C. A libogc2 handler gets no context, so
 * the delivery engine points `isr_mock` at the instance being served. */
static struct gbp_mock *isr_mock;
static uint32_t prim_ticks(void);
static uint32_t prim_read_intsr(void);
static uint32_t prim_read_intmr(void);
static void prim_mask(void);
static void prim_write_intsr(uint32_t v);
#define GBP_IRQ_PRIM_TICKS()        prim_ticks()
#define GBP_IRQ_PRIM_READ_INTSR()   prim_read_intsr()
#define GBP_IRQ_PRIM_READ_INTMR()   prim_read_intmr()
#define GBP_IRQ_PRIM_MASK()         prim_mask()
#define GBP_IRQ_PRIM_WRITE_INTSR(v) prim_write_intsr(v)
#include "../../src/gbp/gbp_irq_oneshot.h"

#define SOURCE_BITS 0x0555u
#define MASK_BITS   0x0AAAu
#define HIGH_BITS   0x7000u
#define BIT15       0x8000u

static void record_ev(struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t addr, uint16_t value,
                      const uint8_t *data, gbp_status rc);
static void violation(struct gbp_mock *m, unsigned bit);

void gbp_mock_init(struct gbp_mock *m)
{
    memset(m, 0, sizeof *m);
    m->present = 1;
    m->require_expansion = 0;
    m->byte_doubled = 1;
    m->arinfo = 0x0043;           /* size code 3 (16 MB), no expansion, bit 6 set (as GBI leaves it) */
    m->arinfo_initial = m->arinfo;
    m->irq_value = 0x0000;
    m->absent_fill = 0x00;
    m->control_byte = 0x90;       /* idle value observed on hardware 2026-09-14 (exp code 3) */
    m->intmr = 0x000000f0;        /* libogc2 __irq_init: HSP bit 13 masked */
    m->intsr = 0x00000000;
    m->control_writes_stick = 1;
    m->irq_ops_available = 1;
    m->irq_mode = MOCK_IRQ_NONE;
    m->max_deliveries = 8;
    m->irq_model = MOCK_IRQ_MODEL_STATIC;
    m->bit15_mode = MOCK_BIT15_LEVEL;
    m->irq_reg = 0x8AAE;          /* physical idle value (SOURCE_MASK model only) */
    memset(m->test_store, 0xFF, sizeof m->test_store); /* ~0x00 initial */
    m->bulk_ops_available = 1;
    m->bulk_ticks_per_line = 3;
}

uint8_t gbp_mock_bulk_byte(unsigned index, uint8_t seed, uint32_t k)
{
    /* deterministic, index-dependent, not a plausible device pattern: index 8 and index 1 never share a byte stream */
    return (uint8_t)(k * 7u + index * 0x35u + seed + ((k >> 5) & 0xFFu) * 3u);
}

static void record_ev(struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t addr, uint16_t value,
                      const uint8_t *data, gbp_status rc)
{
    struct gbp_mock_op *op;
    if (m->nops >= GBP_MOCK_MAX_OPS) { m->ops_dropped++; return; }
    op = &m->ops[m->nops++];
    op->kind = kind;
    op->addr = addr;
    op->len = 0;
    op->value = value;
    op->rc = rc;
    op->intsr = m->intsr;
    op->intmr = m->intmr;
    if (data) memcpy(op->data, data, GBP_BLOCK_SIZE); else memset(op->data, 0, GBP_BLOCK_SIZE);
}

static void violation(struct gbp_mock *m, unsigned bit)
{
    m->violations++;
    m->violation_mask |= bit;
}

/* ---- GBP IRQ register model (SOURCE_MASK) ---------------------------- */

/* Does the device line reach the PI cause bit under the synthetic model? */
static int device_line(const struct gbp_mock *m)
{
    unsigned i;
    if (m->bit15_mode == MOCK_BIT15_LEVEL && (m->irq_reg & BIT15)) return 0;   /* global hold */
    for (i = 0; i <= 10; i += 2) {
        if ((m->irq_reg & (1u << i)) && !(m->irq_reg & (1u << (i + 1)))) return 1;  /* source pending, mask open */
    }
    return 0;
}

static void reg_after_change(struct gbp_mock *m)
{
    if (m->bit15_mode == MOCK_BIT15_SUMMARY) {
        if (m->irq_reg & SOURCE_BITS) m->irq_reg |= BIT15; else m->irq_reg &= (uint16_t)~BIT15;
    }
    if (device_line(m)) {
        if (m->source_pi_delay && !(m->intsr & GBP_PI_HSP_BIT)) {      /* GBP-INIT-004 model: the PI latch lags the source */
            if (!m->pi_latch_pending) { m->pi_latch_pending = 1; m->pi_latch_at_tick = m->tick + m->source_pi_delay; }
        } else {
            m->intsr |= GBP_PI_HSP_BIT;                                /* visible whether or not INTMR enables it */
        }
    } else {
        m->pi_latch_pending = 0;                                       /* the line dropped before the latch */
        if (m->pi_cause_level) m->intsr &= ~GBP_PI_HSP_BIT;            /* level reading: follows the line */
    }
}

static void pi_latch_step(struct gbp_mock *m)
{
    if (m->pi_latch_pending && (int32_t)(m->tick - m->pi_latch_at_tick) >= 0) {
        m->pi_latch_pending = 0;
        if (device_line(m)) m->intsr |= GBP_PI_HSP_BIT;
    }
}

static void reg_write(struct gbp_mock *m, uint16_t v, int honor_w1c)
{
    m->last_irq_write_value = v;
    if (honor_w1c) m->irq_reg &= (uint16_t)~(v & SOURCE_BITS);         /* sources: write-1-to-clear */
    m->irq_reg = (uint16_t)((m->irq_reg & ~MASK_BITS) | (v & MASK_BITS)); /* masks: level */
    m->irq_reg = (uint16_t)((m->irq_reg & ~HIGH_BITS) | (v & HIGH_BITS)); /* bits 12-14: level (unused) */
    if (m->bit15_mode == MOCK_BIT15_LEVEL) m->irq_reg = (uint16_t)((m->irq_reg & ~BIT15) | (v & BIT15));
    else if (v & BIT15) m->irq_reg &= (uint16_t)~BIT15;                /* summary: W1C, recomputed below */
    reg_after_change(m);
}

static void phantom_step(struct gbp_mock *m)
{
    if (m->pi_phantom_pending && (int32_t)(m->tick - m->pi_phantom_at_tick) >= 0) {
        m->pi_phantom_pending = 0;
        m->intsr |= GBP_PI_HSP_BIT;          /* synthetic: a PI cause with no visible source */
    }
}

static void source_step(struct gbp_mock *m)
{
    unsigned i;
    phantom_step(m);
    if (m->irq_model != MOCK_IRQ_MODEL_SOURCE_MASK) return;
    if (m->source_assert_at_tick && !m->source_asserted_done && (int32_t)(m->tick - m->source_assert_at_tick) >= 0) {   /* wrap-safe */
        m->source_asserted_done = 1;
        m->irq_reg |= (uint16_t)(m->source_assert_bits & SOURCE_BITS);
        reg_after_change(m);
    }
    for (i = 0; i < m->n_src_sched && i < 8u; i++) {
        struct gbp_mock_src_sched *s = &m->src_sched[i];
        if (s->armed && !s->done && (int32_t)(m->tick - s->at_tick) >= 0) {
            s->done = 1;
            m->irq_reg |= (uint16_t)(s->bits & SOURCE_BITS);
            reg_after_change(m);
        }
    }
    pi_latch_step(m);
}

/* ---- PI HSP interrupt model (delivery) ------------------------------- */

static void mask_core(struct gbp_mock *m)
{
    m->mask_calls++;
    if (m->mask_ignored) return;
    if (m->mask_ignored_from_call && m->mask_calls >= m->mask_ignored_from_call) return;
    m->intmr &= ~GBP_PI_HSP_BIT;
}

static void w1c_core(struct gbp_mock *m, uint32_t v)
{
    uint32_t clear = v;
    /* Level model: while the device still asserts, bit 13 cannot be
     * cleared by the W1C (synthetic; U-GBP-022 is open). */
    if (m->intsr_sticky_after_w1c && m->cause_asserted) clear &= ~GBP_PI_HSP_BIT;
    if (m->irq_model == MOCK_IRQ_MODEL_SOURCE_MASK && m->pi_cause_level && device_line(m)) clear &= ~GBP_PI_HSP_BIT;
    if (m->intsr_w1c_ignored) clear &= ~GBP_PI_HSP_BIT;
    if ((clear & GBP_PI_HSP_BIT) && (m->intsr & GBP_PI_HSP_BIT) && m->pi_relatch_after_ticks &&
        m->irq_model == MOCK_IRQ_MODEL_SOURCE_MASK && device_line(m)) {
        m->relatch_pending = 1;
        m->relatch_at_tick = m->tick + m->pi_relatch_after_ticks;
    }
    m->intsr &= ~clear;
}

static void relatch_step(struct gbp_mock *m);
static uint32_t prim_ticks(void)
{
    struct gbp_mock *m = isr_mock;
    if (m->isr_ext || m->isr_multi) { m->tick += 1; relatch_step(m); pi_latch_step(m); }   /* the extended body's bounded wait needs a moving time base */
    return m->tick;
}
static uint32_t prim_read_intsr(void) { return isr_mock->intsr; }
static uint32_t prim_read_intmr(void) { return isr_mock->intmr; }
static void prim_mask(void)
{
    struct gbp_mock *m = isr_mock;
    mask_core(m);
    m->isr_masked_this_entry = 1;
    record_ev(m, MOCK_ISR_MASK, 0, 0, 0, GBP_OK);
}
static void prim_write_intsr(uint32_t v)
{
    struct gbp_mock *m = isr_mock;
    if (!m->isr_masked_this_entry) violation(m, GBP_MOCK_VIOL_ISR_W1C_BEFORE_MASK);
    m->isr_w1c_count++;
    w1c_core(m, v);
    record_ev(m, MOCK_ISR_W1C, 0, (uint16_t)v, 0, GBP_OK);
}

/* Re-latch model (synthetic): a W1C that cleared bit 13 while the device line
 * was still up re-sets it pi_relatch_after_ticks later. */
static void relatch_step(struct gbp_mock *m)
{
    if (m->relatch_pending && (int32_t)(m->tick - m->relatch_at_tick) >= 0) {
        m->relatch_pending = 0;
        if (device_line(m)) m->intsr |= GBP_PI_HSP_BIT;
    }
}

static void deliver(struct gbp_mock *m)
{
    struct gbp_mock *saved = isr_mock;
    m->in_isr = 1;
    m->isr_masked_this_entry = 0;
    m->deliveries++;
    record_ev(m, MOCK_ISR_ENTRY, 0, 0, 0, GBP_OK);
    isr_mock = m;
    if (m->isr_multi) { m->isr_entries_multi++; gbp_irq_multicycle_service(&m->multi); }
    else if (m->isr_ext) gbp_irq_oneshot_service_ext(&m->rec);
    else gbp_irq_oneshot_service(&m->rec);
    isr_mock = saved;
    record_ev(m, MOCK_ISR_EXIT, 0, 0, 0, GBP_OK);
    m->in_isr = 0;
    if (m->source_clear_at_delivery && m->deliveries == m->source_clear_at_delivery && m->irq_model == MOCK_IRQ_MODEL_SOURCE_MASK) {
        m->irq_reg &= (uint16_t)~SOURCE_BITS;                    /* synthetic: the source vanishes before the main loop looks */
        reg_after_change(m);
    }
}

/* Advances the synthetic device and delivers the interrupt whenever the
 * PI would raise the CPU exception: cause set AND mask enabled. Called
 * from every transport operation (the real interrupt is asynchronous;
 * the mock is synchronous at operation boundaries). */
static void irq_step(struct gbp_mock *m)
{
    unsigned guard = 0;
    if (m->in_isr) return;
    source_step(m);
    relatch_step(m);
    if (m->irq_mode == MOCK_IRQ_AFTER_TICKS && m->unmasked_once && !m->cause_asserted &&
        (uint32_t)(m->tick - m->unmask_tick) >= m->irq_after_ticks) {
        m->cause_asserted = 1;
        m->intsr |= GBP_PI_HSP_BIT;          /* visible whether or not it is masked */
    }
    while ((m->intsr & GBP_PI_HSP_BIT) && (m->intmr & GBP_PI_HSP_BIT)) {
        if (m->delivery_suppressed) break;                    /* synthetic: unmasked cause never reaches the CPU */
        if (m->suppress_delivery_at && m->deliveries + 1u == m->suppress_delivery_at) break;
        if (!m->handler_installed) {
            /* An unmasked cause with no handler: the real CPU would loop in
             * the exception forever (ENV-IRQ-001). Flag it and stop. */
            m->deliveries_without_handler++;
            violation(m, GBP_MOCK_VIOL_UNMASK_NO_HANDLER);
            break;
        }
        if (m->deliveries >= m->max_deliveries) { violation(m, GBP_MOCK_VIOL_STORM); break; }
        deliver(m);
        if (++guard > 64) break;
    }
    if (((m->second_delivery && m->deliveries == 1) || (m->second_delivery_at && m->deliveries == m->second_delivery_at)) &&
        !m->second_delivered && m->handler_installed) {
        /* gating-failure model: one more entry although the handler masked */
        m->second_delivered = 1;
        deliver(m);
    }
}

static gbp_status m_irq_install(void *ctx, int *old_was_null)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    m->installed_calls++;
    if (m->install_fails) { record_ev(m, MOCK_IRQ_INSTALL, 0, 0, 0, GBP_ERR_BACKEND); return GBP_ERR_BACKEND; }
    if (m->handler_installed) violation(m, GBP_MOCK_VIOL_INSTALL_TWICE);
    m->handler_installed = 1;
    memset((void *)&m->rec, 0, sizeof m->rec);
    memset((void *)&m->multi, 0, sizeof m->multi);
    m->multi.anomaly.count = 1;                     /* poisoned, as the real install does: never acknowledges */
    if (m->record_dirty_on_install) { m->rec.count = 1; m->multi.slots[0].count = 1; }
    if (m->clear_cause_on_install) m->intsr &= ~GBP_PI_HSP_BIT;               /* synthetic state changes at the install */
    if (m->intmr13_set_on_install) m->intmr |= GBP_PI_HSP_BIT;
    if (m->control_on_install) { m->control_byte = m->control_on_install; m->control_block = 0; }
    if (m->irq_reg_on_install) { m->irq_reg = m->irq_reg_on_install; reg_after_change(m); }
    if (old_was_null) *old_was_null = m->old_handler_nonnull ? 0 : 1;
    record_ev(m, MOCK_IRQ_INSTALL, 0, (uint16_t)(m->old_handler_nonnull ? 1 : 0), 0, GBP_OK);
    irq_step(m);
    return GBP_OK;
}

static gbp_status m_irq_restore(void *ctx)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    if (m->intmr & GBP_PI_HSP_BIT) violation(m, GBP_MOCK_VIOL_RESTORE_WHILE_UNMASKED);
    if (m->restore_fails) { record_ev(m, MOCK_IRQ_RESTORE, 0, 0, 0, GBP_ERR_BACKEND); return GBP_ERR_BACKEND; }
    m->handler_installed = 0;
    record_ev(m, MOCK_IRQ_RESTORE, 0, 0, 0, GBP_OK);
    return GBP_OK;
}

static gbp_status m_irq_mask(void *ctx)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    mask_core(m);
    record_ev(m, MOCK_IRQ_MASK, 0, 0, 0, GBP_OK);
    irq_step(m);
    return GBP_OK;
}

static gbp_status m_irq_unmask(void *ctx)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    if (!m->handler_installed) violation(m, GBP_MOCK_VIOL_UNMASK_NO_HANDLER);
    if (m->control_writes == 0) violation(m, GBP_MOCK_VIOL_UNMASK_BEFORE_CONTROL);
    if (!m->unmask_ignored) m->intmr |= GBP_PI_HSP_BIT;
    m->unmask_calls++;
    if (m->force_gen_valid && (m->force_gen_at_unmask == 0 || m->force_gen_at_unmask == m->unmask_calls)) {
        m->multi.expected_gen = m->force_expected_gen;          /* synthetic corruption of the published generation, once */
        m->force_gen_valid = 0;
    }
    m->unmasked_once = 1;
    m->unmask_tick = m->tick;
    if (m->irq_mode == MOCK_IRQ_ON_UNMASK && !m->cause_asserted) {
        m->cause_asserted = 1;
        m->intsr |= GBP_PI_HSP_BIT;
    }
    record_ev(m, MOCK_IRQ_UNMASK, 0, 0, 0, GBP_OK);
    irq_step(m);
    return GBP_OK;
}

static gbp_status m_irq_record(void *ctx, struct gbp_irq_record *out)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    irq_step(m);
    if (m->isr_multi) {
        uint32_t gen = m->multi.expected_gen;
        if (gen < GBP_IRQ_MAX_CYCLES) memcpy(out, (const void *)&m->multi.slots[gen], sizeof *out);
        else memcpy(out, (const void *)&m->multi.anomaly, sizeof *out);
        return GBP_OK;
    }
    memcpy(out, (const void *)&m->rec, sizeof *out);
    return GBP_OK;
}

/* ---- multi-cycle operations (GBP-INIT-004) ---- */
static gbp_status m_irq_prepare(void *ctx, uint32_t gen)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    m->prepare_calls++;
    m->last_prepare_gen = gen;
    if (m->intmr & GBP_PI_HSP_BIT) violation(m, GBP_MOCK_VIOL_PREPARE_WHILE_UNMASKED);
    record_ev(m, MOCK_IRQ_PREPARE, 0, (uint16_t)gen, 0, gen < GBP_IRQ_MAX_CYCLES ? GBP_OK : GBP_ERR_PARAM);
    if (gen >= GBP_IRQ_MAX_CYCLES) return GBP_ERR_PARAM;
    m->multi.expected_gen = gen;
    irq_step(m);
    return GBP_OK;
}

static gbp_status m_irq_record_slot(void *ctx, uint32_t slot, struct gbp_irq_record *out)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    irq_step(m);
    if (slot >= GBP_IRQ_MAX_CYCLES) return GBP_ERR_PARAM;
    memcpy(out, (const void *)&m->multi.slots[slot], sizeof *out);
    return GBP_OK;
}

static gbp_status m_irq_multi_status(void *ctx, struct gbp_irq_multi_status *out)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    irq_step(m);
    out->expected_gen = m->multi.expected_gen;
    out->entries_total = m->multi.entries_total;
    out->generation_errors = m->multi.generation_errors;
    memcpy(&out->anomaly, (const void *)&m->multi.anomaly, sizeof out->anomaly);
    return GBP_OK;
}

static gbp_status m_write_intsr(void *ctx, uint32_t v)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    m->intsr_writes++;
    m->last_intsr_write = v;
    w1c_core(m, v);
    record_ev(m, MOCK_INTSR_W, 0, (uint16_t)v, 0, GBP_OK);
    irq_step(m);
    return GBP_OK;
}

static gbp_status m_poll_intsr(void *ctx, uint32_t *intsr)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    if (m->pi_unavailable) return GBP_ERR_BACKEND;
    m->intsr_polls++;
    irq_step(m);
    *intsr = m->intsr;
    return GBP_OK;
}

/* ---- registers and blocks ------------------------------------------- */

static gbp_status m_read_arinfo(void *ctx, uint16_t *v)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    *v = m->arinfo;
    record_ev(m, MOCK_AR_R, 0, *v, 0, GBP_OK);
    return GBP_OK;
}

static gbp_status m_write_arinfo(void *ctx, uint16_t v)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    m->arinfo_writes++;
    if (m->arinfo_write_fail_at && m->arinfo_writes == m->arinfo_write_fail_at) {
        record_ev(m, MOCK_AR_W, 0, v, 0, GBP_ERR_BACKEND);
        return GBP_ERR_BACKEND;
    }
    if (v == m->arinfo_initial && v != m->arinfo && (m->handler_installed || (m->intmr & GBP_PI_HSP_BIT)))
        violation(m, GBP_MOCK_VIOL_ARINFO_BEFORE_IRQ_DOWN);
    m->arinfo = v;
    record_ev(m, MOCK_AR_W, 0, v, 0, GBP_OK);
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

/* Hardware-like presentation of a 16-bit register: hh hh ll ll per word. */
static void present_u16_doubled(uint16_t v, uint8_t out[GBP_BLOCK_SIZE])
{
    unsigned k;
    for (k = 0; k < GBP_BLOCK_SIZE; k += 4u) {
        out[k] = (uint8_t)(v >> 8);
        out[k + 1u] = (uint8_t)(v >> 8);
        out[k + 2u] = (uint8_t)(v & 0xFFu);
        out[k + 3u] = (uint8_t)(v & 0xFFu);
    }
}

static gbp_status m_read_block(void *ctx, uint32_t addr, uint8_t out[GBP_BLOCK_SIZE],
                               struct gbp_xfer_info *info)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    uint32_t base = gbp_internal_size_from_arinfo(m->arinfo);
    gbp_status rc;
    if (m->intmr & GBP_PI_HSP_BIT) violation(m, GBP_MOCK_VIOL_DMA_WHILE_UNMASKED);
    irq_step(m);
    rc = fault(m, info);
    if (rc != GBP_OK) { memset(out, 0, GBP_BLOCK_SIZE); record_ev(m, MOCK_RD, addr, 0, 0, rc); return rc; }
    if (m->silent_reads) {
        /* leave `out` exactly as the caller prepared it */
        record_ev(m, MOCK_RD, addr, 0, out, GBP_OK);
        return GBP_OK;
    }
    if (m->canned) {
        memcpy(out, m->canned, GBP_BLOCK_SIZE);
        record_ev(m, MOCK_RD, addr, 0, out, GBP_OK);
        return GBP_OK;
    }
    if (!answers(m)) {
        memset(out, m->absent_fill, GBP_BLOCK_SIZE);
    } else {
        switch (index_of(base, addr)) {
        case 0x0:
            memcpy(out, m->test_store, GBP_BLOCK_SIZE);
            if (m->test_byte0_anomaly) out[0] |= 0x40;
            break;
        case 0x4: {
            uint8_t v = m->control_byte;
            if (m->control_block) memcpy(out, m->control_block, GBP_BLOCK_SIZE);
            else if (m->byte_doubled) memset(out, v, GBP_BLOCK_SIZE);   /* hardware: uniform fill */
            else present_bytes(m, &v, 1, out);
            break;
        }
        case 0xD: {
            uint8_t v[2];
            if (m->irq_model == MOCK_IRQ_MODEL_SOURCE_MASK) {
                present_u16_doubled(m->irq_reg, out);
                if (m->irq_byte0_anomaly) out[0] |= 0x11;   /* byte 0 must never feed a decision */
                if (m->irq_disagree_on_install && m->installed_calls) out[0x1F] ^= 0x01;   /* Disc reading != GBI vote */
                if (m->irq_disagree_from_write && m->irq_writes >= m->irq_disagree_from_write) out[0x1F] ^= 0x01;
                break;
            }
            if (m->irq_block) { memcpy(out, m->irq_block, GBP_BLOCK_SIZE); break; }
            if (m->irq_present_u16) { present_u16_doubled(m->irq_value, out); break; }
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
    record_ev(m, MOCK_RD, addr, 0, out, GBP_OK);
    return GBP_OK;
}

static gbp_status m_write_block(void *ctx, uint32_t addr, const uint8_t in[GBP_BLOCK_SIZE],
                                struct gbp_xfer_info *info)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    uint32_t base = gbp_internal_size_from_arinfo(m->arinfo);
    gbp_status rc;
    if (m->write_hook) m->write_hook(m, addr, in, m->write_hook_user);
    if (m->intmr & GBP_PI_HSP_BIT) violation(m, GBP_MOCK_VIOL_DMA_WHILE_UNMASKED);
    irq_step(m);
    rc = fault(m, info);
    if (rc == GBP_OK && answers(m) && index_of(base, addr) == 0xD && m->irq_write_fail_at &&
        m->irq_writes + 1u == m->irq_write_fail_at) {
        rc = GBP_ERR_TIMEOUT;                    /* injected failure of the Nth IRQ-register write */
        if (info) info->dma_status = 0x0200;
    }
    record_ev(m, MOCK_WR, addr, 0, in, rc);
    if (answers(m) && index_of(base, addr) == 0xD) {
        m->irq_writes++;
        if (m->intmr13_set_after_irq_write && m->irq_writes == 1u) m->intmr |= GBP_PI_HSP_BIT;
        if (m->irq_model == MOCK_IRQ_MODEL_SOURCE_MASK && (rc == GBP_OK || m->irq_write_fail_applies)) {
            uint16_t v = (uint16_t)((in[0x1E] << 8) | in[0x1F]);
            unsigned i;
            reg_write(m, v, (m->ack_ignored_at_write && m->irq_writes == m->ack_ignored_at_write) ? 0 : 1);
            if (v == 0 && m->rearm_sticky_bits && m->irq_writes >= m->rearm_sticky_from_write) {   /* invalid re-arm read-back */
                m->irq_reg |= m->rearm_sticky_bits;
                reg_after_change(m);
            }
            if (m->bit15_drop_at_write && m->irq_writes == m->bit15_drop_at_write) {                 /* bit 15 not retained by the Nth write */
                m->irq_reg &= (uint16_t)~BIT15;
                reg_after_change(m);
            }
            if (m->source_assert_after_write && m->irq_writes == m->source_assert_after_write) {
                m->source_assert_at_tick = m->tick + m->source_assert_delay;
                if (m->source_assert_at_tick == 0) m->source_assert_at_tick = 1;
                m->source_asserted_done = 0;
            }
            if (m->pi_phantom_after_write && m->irq_writes == m->pi_phantom_after_write) {
                m->pi_phantom_pending = 1;
                m->pi_phantom_at_tick = m->tick + m->pi_phantom_delay;
            }
            for (i = 0; i < m->n_src_sched && i < 8u; i++) {
                struct gbp_mock_src_sched *s = &m->src_sched[i];
                if (s->after_write && s->after_write == m->irq_writes && !s->armed) {
                    s->at_tick = m->tick + s->delay;
                    if (s->at_tick == 0) s->at_tick = 1;
                    s->armed = 1;
                }
            }
            source_step(m);
        }
        if (m->control_change_after_irq_write && m->irq_writes == m->control_change_after_irq_write) {
            m->control_byte = m->control_change_value;                 /* CONTROL changes by itself (synthetic) */
            m->control_block = 0;
        }
    }
    if (rc != GBP_OK) return rc;
    if (answers(m) && index_of(base, addr) == 0x0) {
        size_t i;
        for (i = 0; i < GBP_BLOCK_SIZE; i++) m->test_store[i] = (uint8_t)~in[i];
    }
    if (answers(m) && index_of(base, addr) == 0x4) {
        m->control_writes++;
        if (m->intmr13_set_after_control_write && m->control_writes == 1u) m->intmr |= GBP_PI_HSP_BIT;
        if (m->control_writes_stick && m->control_writes != m->control_write_fail_at) {
            m->control_byte = in[GBP_BLOCK_SIZE - 1u];
            m->control_block = 0;
            if (m->irq_after_write) { m->irq_block = 0; m->irq_value = (uint16_t)((m->irq_after_write << 8) | m->irq_after_write); m->irq_present_u16 = 1; }
            if (m->intsr_bit13_follows_control) {
                if (m->control_byte & 0x10u) m->intsr &= ~GBP_PI_HSP_BIT; else m->intsr |= GBP_PI_HSP_BIT;
            }
            if (m->control_mask_clears_cause && (m->control_byte & 0x10u) && m->cause_asserted) {
                m->cause_asserted = 0;
                m->intsr &= ~GBP_PI_HSP_BIT;
            }
        }
    }
    irq_step(m);
    return GBP_OK;
}

/* ---- whole-block reads (SYNTHETIC; GBP-AV-SERVICE-001) ---- */
static void bulk_assert(struct gbp_mock *m)
{
    if (m->irq_model != MOCK_IRQ_MODEL_SOURCE_MASK) return;
    m->irq_reg |= (uint16_t)(m->bulk_assert_bits & SOURCE_BITS);
    reg_after_change(m);
}

static gbp_status m_read_bulk(void *ctx, uint32_t addr, uint8_t *out, uint32_t len, struct gbp_xfer_info *info)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    uint32_t base = gbp_internal_size_from_arinfo(m->arinfo);
    unsigned idx = index_of(base, addr);
    gbp_status rc;
    uint32_t k;
    if (info) memset(info, 0, sizeof *info);
    if (!gbp_bulk_args_ok(addr, out, len)) { record_ev(m, MOCK_RD_BULK, addr, 0, 0, GBP_ERR_PARAM); return GBP_ERR_PARAM; }
    if (!m->bulk_any_offset && addr != base + ((uint32_t)idx << 20)) {
        /* the exact block address, never an index inferred from a loose address */
        m->bulk_bad_addr++;
        record_ev(m, MOCK_RD_BULK, addr, 0, 0, GBP_ERR_PARAM);
        return GBP_ERR_PARAM;
    }
    if (m->intmr & GBP_PI_HSP_BIT) violation(m, GBP_MOCK_VIOL_DMA_WHILE_UNMASKED);
    m->bulk_reads++;
    if (m->bulk_assert_at_read && m->bulk_reads == m->bulk_assert_at_read && !m->bulk_assert_after) bulk_assert(m);
    irq_step(m);
    rc = fault(m, info);
    if (rc == GBP_OK) rc = m->bulk_rc[idx & 15u];
    if (info) {
        info->ticks = (len / GBP_BLOCK_SIZE) * m->bulk_ticks_per_line;
        info->polls = (uint16_t)(len / GBP_BLOCK_SIZE);
        info->dma_status_before = 0x0000;
        info->dma_status = (rc == GBP_OK) ? 0x0020 : (rc == GBP_ERR_TIMEOUT || rc == GBP_ERR_BUSY) ? 0x0200 : 0x0000;
    }
    if (rc != GBP_OK) {
        if (m->bulk_partial_on_fail && rc == GBP_ERR_TIMEOUT) for (k = 0; k < GBP_BLOCK_SIZE && k < len; k++) out[k] = gbp_mock_bulk_byte(idx, m->bulk_seed, k);
        if (rc == GBP_ERR_TIMEOUT && m->stuck_after_timeout) m->stuck = 1;
        record_ev(m, MOCK_RD_BULK, addr, 0, out, rc);
        m->ops[m->nops ? m->nops - 1u : 0].len = len;
        return rc;
    }
    if (!answers(m)) memset(out, m->absent_fill, len);
    else for (k = 0; k < len; k++) out[k] = gbp_mock_bulk_byte(idx, m->bulk_seed, k);
    m->bulk_bytes += len;
    record_ev(m, MOCK_RD_BULK, addr, 0, out, GBP_OK);
    m->ops[m->nops ? m->nops - 1u : 0].len = len;
    if (m->bulk_clears_source && m->irq_model == MOCK_IRQ_MODEL_SOURCE_MASK && answers(m)) {
        /* a status bit dropping because its block was consumed: no new PI evaluation (synthetic; nothing physical) */
        if (idx == 0x8u) m->irq_reg &= (uint16_t)~0x0400u;
        if (idx == 0x1u) m->irq_reg &= (uint16_t)~0x0100u;
        if (m->bit15_mode == MOCK_BIT15_SUMMARY && (m->irq_reg & SOURCE_BITS) == 0) m->irq_reg &= (uint16_t)~BIT15;
    }
    if (m->bulk_assert_at_read && m->bulk_reads == m->bulk_assert_at_read && m->bulk_assert_after) bulk_assert(m);
    irq_step(m);
    return GBP_OK;
}

static gbp_status m_read_pi(void *ctx, uint32_t *intsr, uint32_t *intmr)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    if (m->pi_unavailable) return GBP_ERR_BACKEND;
    irq_step(m);
    *intsr = m->intsr;
    *intmr = m->intmr;
    return GBP_OK;
}

static gbp_status m_write_intmr(void *ctx, uint32_t v)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    m->intmr_writes++;
    if (!m->intmr_write_ignored) m->intmr = v;
    irq_step(m);
    return GBP_OK;
}

static uint32_t m_ticks(void *ctx)
{
    struct gbp_mock *m = (struct gbp_mock *)ctx;
    m->tick += 10;
    irq_step(m);
    return m->tick;
}

void gbp_mock_transport(struct gbp_mock *m, struct gbp_transport *t)
{
    memset(t, 0, sizeof *t);
    t->read_arinfo = m_read_arinfo;
    t->write_arinfo = m_write_arinfo;
    t->read_block = m_read_block;
    t->write_block = m_write_block;
    t->read_bulk = m->bulk_ops_available ? m_read_bulk : 0;
    t->read_pi = m_read_pi;
    t->write_intmr = m_write_intmr;
    t->poll_intsr = m_poll_intsr;
    if (m->irq_ops_available) {
        t->write_intsr = m_write_intsr;
        t->irq_install = m_irq_install;
        t->irq_restore = m_irq_restore;
        t->irq_mask = m_irq_mask;
        t->irq_unmask = m_irq_unmask;
        t->irq_record = m_irq_record;
        t->irq_prepare = m_irq_prepare;
        t->irq_record_slot = m_irq_record_slot;
        t->irq_multi_status = m_irq_multi_status;
    } else {
        t->write_intsr = 0;
        t->irq_install = 0;
        t->irq_restore = 0;
        t->irq_mask = 0;
        t->irq_unmask = 0;
        t->irq_record = 0;
        t->irq_prepare = 0;
        t->irq_record_slot = 0;
        t->irq_multi_status = 0;
    }
    t->ticks = m_ticks;
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

static int op_matches(const struct gbp_mock_op *op, enum gbp_mock_op_kind kind, uint32_t base, unsigned block)
{
    if (op->kind != kind) return 0;
    if ((kind == MOCK_RD || kind == MOCK_WR || kind == MOCK_RD_BULK) && block < 16u && index_of(base, op->addr) != block) return 0;
    return 1;
}

int gbp_mock_first_op(const struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t base, unsigned block)
{
    unsigned i;
    for (i = 0; i < m->nops; i++) if (op_matches(&m->ops[i], kind, base, block)) return (int)i;
    return -1;
}

int gbp_mock_last_op(const struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t base, unsigned block)
{
    unsigned i;
    int found = -1;
    for (i = 0; i < m->nops; i++) if (op_matches(&m->ops[i], kind, base, block)) found = (int)i;
    return found;
}

int gbp_mock_nth_op(const struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t base, unsigned block, unsigned n)
{
    unsigned i, seen = 0;
    for (i = 0; i < m->nops; i++) {
        if (op_matches(&m->ops[i], kind, base, block) && ++seen == n) return (int)i;
    }
    return -1;
}

unsigned gbp_mock_count_block_ops(const struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t base, unsigned block)
{
    unsigned i, n = 0;
    for (i = 0; i < m->nops; i++) if (op_matches(&m->ops[i], kind, base, block)) n++;
    return n;
}
