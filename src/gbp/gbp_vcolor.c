#include "gbp_vcolor.h"

#include <string.h>

void gbp_vcolor_init(struct gbp_vcolor *c, struct gbp_vcolor_frame *frames, uint32_t frames_cap)
{
    if (!c) return;
    memset(c, 0, sizeof *c);
    c->frames = frames;
    c->frames_cap = frames ? frames_cap : 0u;
}

unsigned gbp_vcolor_eligible(const struct gbp_vstate_frame *f)
{
    if (!f) return GBP_VCOLOR_NOT_COMPLETE;
    /* The order is the order of §V3.10 and it is not an accident: the cheapest
     * structural facts first, then the policy exclusions, so the recorded reason
     * is always the FIRST thing wrong with the frame rather than whichever test
     * happened to run last. */
    if (f->completeness != GBP_VSTATE_FRAME_COMPLETE_40) return GBP_VCOLOR_NOT_COMPLETE;
    if (f->blocks != GBP_VCOLOR_BLOCKS) return GBP_VCOLOR_WRONG_BLOCKS;
    if (!(f->flags & GBP_VSTATE_F_COMPLETE)) return GBP_VCOLOR_NOT_COMPLETE;
    if (f->flags & GBP_VSTATE_F_ANOMALY) return GBP_VCOLOR_ANOMALY;
    if (f->flags & GBP_VSTATE_F_RESYNC) return GBP_VCOLOR_RESYNC;
    /* The two R3 exclusions. A frame holding a block that was drained ONLY
     * because the majority carried a source the Disc reading did not is
     * quarantined from every scientific use (§R3.12); a frame in which a VIDEO
     * drain was deferred is contaminated for the same reason (§R3.13). Neither
     * may become colour evidence, and neither is repairable. */
    if (f->flags & GBP_VSTATE_F_MAJORITY_EXTRA) return GBP_VCOLOR_MAJORITY_EXTRA;
    if (f->flags & GBP_VSTATE_F_SOURCE_DEFERRED) return GBP_VCOLOR_SOURCE_DEFERRED;
    /* F_PRE_BASELINE is deliberately NOT tested here: see GBP_VCOLOR_RETIRED_PRE_BASELINE. */
    return GBP_VCOLOR_OK;
}

/* The whole comparison, and the whole cost: 40 words. */
static int sig_same(const uint32_t *a, const uint32_t *b)
{
    unsigned i;
    for (i = 0; i < GBP_VSTATE_FRAME_SIGS; i++) if (a[i] != b[i]) return 0;
    return 1;
}

static void sig_take(uint32_t *dst, const uint32_t *src)
{
    unsigned i;
    for (i = 0; i < GBP_VSTATE_FRAME_SIGS; i++) dst[i] = src[i];
}

static void record(struct gbp_vcolor *c, const struct gbp_vstate_frame *f, unsigned reason)
{
    struct gbp_vcolor_frame *r;
    c->frames_total++;
    if (reason == GBP_VCOLOR_OK) c->frames_eligible++;
    if (reason < GBP_VCOLOR_REASONS) c->frames_refused[reason]++;
    if (!c->frames || c->frames_n >= c->frames_cap) { c->frames_dropped++; return; }
    r = &c->frames[c->frames_n++];
    memset(r, 0, sizeof *r);
    r->t_first = f->t_first_block;
    r->t_last = f->t_last_block;
    r->index = f->index;
    r->blocks = f->blocks;
    r->flags = f->flags;
    r->reason = (uint16_t)reason;
    r->run_len_after = c->run_len;
    r->sig0 = f->sig[0];
    r->sig39 = f->sig[GBP_VSTATE_FRAME_SIGS - 1u];
}

static void cert_put(struct gbp_vcolor *c, const struct gbp_vstate_frame *f, uint32_t slot, uint32_t order)
{
    struct gbp_vcolor_cert *k;
    if (order >= GBP_VCOLOR_CERT_FRAMES) return;
    k = &c->cert[order];
    k->frame_index = f->index;
    k->blocks = f->blocks;
    k->t_first = f->t_first_block;
    k->t_last = f->t_last_block;
    k->raw_offset = order * GBP_VCOLOR_FRAME_BYTES;
    k->ring_slot = (uint16_t)slot;
    k->order = (uint16_t)order;
    k->sig0 = f->sig[0];
    k->sig39 = f->sig[GBP_VSTATE_FRAME_SIGS - 1u];
}

int gbp_vcolor_done(const struct gbp_vcolor *c)
{
    return (c && c->certified) ? 1 : 0;
}

int gbp_vcolor_frame(struct gbp_vcolor *c, const struct gbp_vstate_frame *f, int slot, uint64_t t)
{
    unsigned reason;
    if (!c || !f) return 0;
    /* Once certified nothing more is examined. The run stops at this frame, so
     * there is no hold window to serve and no reason to keep looking: every
     * further frame close would rotate the ring one slot nearer to the bytes
     * that were just certified. */
    if (c->certified) return 0;

    reason = gbp_vcolor_eligible(f);
    if (reason == GBP_VCOLOR_OK && slot < 0) reason = GBP_VCOLOR_NO_SLOT;

    if (reason != GBP_VCOLOR_OK) {
        /* Consecutiveness is part of the rule: an ineligible frame between two
         * identical ones breaks the run, because "three consecutive eligible
         * frames" is what the design asks for and a gap is not consecutive. */
        if (c->run_len) c->resets++;
        c->run_len = 0;
        record(c, f, reason);
        return 0;
    }

    if (c->run_len == 0u || !sig_same(f->sig, c->ref_sig)) {
        /* A new run starts at THIS frame: its signature vector becomes the
         * reference the next frames are compared against. 160 bytes copied,
         * once per run - and never a frame's bytes. */
        if (c->run_len) { c->resets++; c->sig_mismatches++; }
        sig_take(c->ref_sig, f->sig);
        c->run_len = 1u;
        c->run_first_index = f->index;
        c->cert_n = 1u;
        cert_put(c, f, (uint32_t)slot, 0u);
        record(c, f, reason);
        return 0;
    }

    /* Signature-identical to the frame that opened the run. */
    if (c->cert_n < GBP_VCOLOR_CERT_FRAMES) cert_put(c, f, (uint32_t)slot, c->cert_n++);
    c->run_len++;
    if (c->run_len >= GBP_VCOLOR_N_STABLE) {
        c->certified = 1;
        c->t_certified = t;
        record(c, f, reason);
        return 1;
    }
    record(c, f, reason);
    return 0;
}

int gbp_vcolor_slots_ok(const struct gbp_vcolor *c, const struct gbp_vstate *st)
{
    uint32_t i, j, slots, cur;
    if (!c || !st || !c->certified) return 0;
    if (c->cert_n != GBP_VCOLOR_CERT_FRAMES) return 0;
    slots = gbp_vstate_ring_slots(st);
    cur = gbp_vstate_current_slot(st);
    if (slots == 0u) return 0;
    for (i = 0; i < c->cert_n; i++) {
        uint32_t s = c->cert[i].ring_slot;
        if (s >= slots) return 0;
        /* The slot the assembler is filling is the one thing that can still be
         * written. A certified frame may never be it. */
        if (s == cur) return 0;
        if (c->cert[i].blocks != GBP_VCOLOR_BLOCKS) return 0;
        if (c->cert[i].raw_offset != i * GBP_VCOLOR_FRAME_BYTES) return 0;
        if (c->cert[i].order != i) return 0;
        for (j = 0; j < i; j++) if (c->cert[j].ring_slot == s) return 0;
    }
    return 1;
}

const char *gbp_vcolor_reason_name(unsigned reason)
{
    switch (reason) {
    case GBP_VCOLOR_OK: return "eligible";
    case GBP_VCOLOR_NOT_COMPLETE: return "not_complete";
    case GBP_VCOLOR_WRONG_BLOCKS: return "wrong_blocks";
    case GBP_VCOLOR_ANOMALY: return "anomaly";
    case GBP_VCOLOR_RESYNC: return "resync";
    case GBP_VCOLOR_MAJORITY_EXTRA: return "majority_extra_quarantine";
    case GBP_VCOLOR_SOURCE_DEFERRED: return "source_deferred";
    case GBP_VCOLOR_RETIRED_PRE_BASELINE: return "retired_pre_baseline";
    case GBP_VCOLOR_NO_SLOT: return "ring_slot_unavailable";
    default: return "?";
    }
}

uint64_t gbp_vcolor_static_bytes(void)
{
    /* The frame table, and nothing else: the certified bytes stay in the state
     * model's ring, which the ring's own budget already accounts for. */
    return (uint64_t)GBP_VCOLOR_MAX_FRAMES * sizeof(struct gbp_vcolor_frame);
}
