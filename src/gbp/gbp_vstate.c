#include "gbp_vstate.h"

#include <string.h>

/* The two record layouts are part of the sidecar contract, so a compiler that
 * padded them differently must fail the build, not produce a different file. */
typedef char gbp_vstate_frame_size_check[(sizeof(struct gbp_vstate_frame) == GBP_VSTATE_FRAME_REC) ? 1 : -1];
typedef char gbp_vstate_event_size_check[(sizeof(struct gbp_vstate_event) == GBP_VSTATE_EVENT_REC) ? 1 : -1];
typedef char gbp_vstate_diag_size_check[(sizeof(struct gbp_vstate_diag) == GBP_VSTATE_DIAG_REC_V4) ? 1 : -1];
/* the v4 record IS the v3 record plus 64 bytes, and the split is normative */
typedef char gbp_vstate_diag_split_check[(GBP_VSTATE_DIAG_REC_V4 - GBP_VSTATE_DIAG_REC == 64u) ? 1 : -1];
typedef char gbp_vstate_mask_check[((GBP_VSTATE_SRC_MASK | GBP_VSTATE_ODD_MASK | GBP_VSTATE_HIGH_MASK |
                                    GBP_VSTATE_BIT15_MASK) == 0xFFFFu) ? 1 : -1];
typedef char gbp_vstate_av_check[((GBP_VSTATE_AV_MASK & ~GBP_VSTATE_SRC_MASK) == 0u) ? 1 : -1];

#define ASM_SEEKING 0      /* no anchor: no Disc boundary has been observed yet */
#define ASM_IN_FRAME 1     /* anchored: a boundary told the assembler where this frame starts */

static int sig_equal(const uint32_t *a, const uint32_t *b)
{
    unsigned i;
    for (i = 0; i < GBP_VSTATE_FRAME_SIGS; i++) if (a[i] != b[i]) return 0;
    return 1;
}

static void sig_copy(uint32_t *dst, const uint32_t *src)
{
    memcpy(dst, src, GBP_VSTATE_FRAME_SIGS * sizeof(uint32_t));
}

void gbp_vstate_init(struct gbp_vstate *s,
                     struct gbp_vstate_frame *frames, uint32_t frames_cap,
                     struct gbp_vstate_event *events, uint32_t events_cap,
                     uint8_t *raw_ring, uint32_t raw_ring_cap,
                     uint8_t *episode_raw, uint32_t episode_raw_cap,
                     uint8_t *audio_raw, uint32_t audio_raw_cap)
{
    if (!s) return;
    memset(s, 0, sizeof *s);
    s->frames = frames; s->frames_cap = frames_cap;
    s->events = events; s->events_cap = events_cap;
    s->raw_ring = raw_ring; s->raw_ring_cap = raw_ring_cap;
    s->episode_raw = episode_raw; s->episode_raw_cap = episode_raw_cap;
    s->audio_raw = audio_raw; s->audio_raw_cap = audio_raw_cap;
    s->asm_state = ASM_SEEKING;
    s->prev_slot = -1;
    s->diag_wait = -1;
    {   unsigned k;
        for (k = 0u; k < GBP_VSTATE_GAP_SLOTS; k++) s->sem.gap[k].min_ticks = GBP_VSTATE_GAP_NONE;
    }
    s->audio.last_valid = -1;
    s->audio.last_next = 1u;
    gbp_vsig_cost_init(&s->cost);
}

int gbp_vstate_storage_ok(const struct gbp_vstate *s)
{
    if (!s || !s->frames || !s->events || !s->raw_ring || !s->episode_raw || !s->audio_raw) return 0;
    if (s->frames_cap < GBP_VSTATE_MAX_FRAMES || s->events_cap < GBP_VSTATE_MAX_EVENTS) return 0;
    if (s->raw_ring_cap < GBP_VSTATE_RAW_RING_BYTES) return 0;
    if (s->episode_raw_cap < GBP_VSTATE_EPISODE_RAW_BYTES) return 0;
    if (s->audio_raw_cap < GBP_VSTATE_AUDIO_RAW_BYTES) return 0;
    return 1;
}

uint64_t gbp_vstate_static_bytes(void)
{
    return (uint64_t)GBP_VSTATE_MAX_FRAMES * GBP_VSTATE_FRAME_REC
         + (uint64_t)GBP_VSTATE_MAX_EVENTS * GBP_VSTATE_EVENT_REC
         + (uint64_t)GBP_VSTATE_RAW_RING_BYTES
         + (uint64_t)GBP_VSTATE_EPISODE_RAW_BYTES
         + (uint64_t)GBP_VSTATE_AUDIO_RAW_BYTES;
}

/* ---- events ---------------------------------------------------------- */
uint32_t gbp_vstate_event(struct gbp_vstate *s, uint64_t t, enum gbp_vstate_event_type type,
                          uint32_t a, uint32_t b, uint32_t c, uint32_t d)
{
    struct gbp_vstate_event *e;
    if (!s || !s->events) return 0u;
    if (s->events_n >= s->events_cap) {
        s->event_store_full = 1;
        if (s->events_dropped != 0xFFFFFFFFu) s->events_dropped++;
        return 0u;
    }
    e = &s->events[s->events_n++];
    memset(e, 0, sizeof *e);
    s->event_seq++;                     /* 1-based: 0 means "not recorded" */
    e->seq = s->event_seq;
    e->t = t;
    e->type = (uint16_t)type;
    e->a = a; e->b = b; e->c = c; e->d = d;
    e->frame = s->frames_n;
    e->episode = s->episode_cur;
    if (s->events_n >= s->events_cap) s->event_store_full = 1;
    return e->seq;
}

const char *gbp_vstate_event_name(unsigned type)
{
    switch (type) {
    case GBP_VSTATE_EV_CAPTURE_START: return "capture_start";
    case GBP_VSTATE_EV_BASELINE_CANDIDATE: return "baseline_candidate";
    case GBP_VSTATE_EV_BASELINE_VALID: return "baseline_valid";
    case GBP_VSTATE_EV_EARLY_CANDIDATE: return "early_candidate";
    case GBP_VSTATE_EV_PREDICATE_DISAGREEMENT: return "predicate_disagreement";
    case GBP_VSTATE_EV_INCOMPLETE_INTERVAL: return "incomplete_interval";
    case GBP_VSTATE_EV_RESYNC: return "resync";
    case GBP_VSTATE_EV_EPISODE_OPEN: return "episode_open";
    case GBP_VSTATE_EV_EPISODE_STABILISING: return "episode_stabilising";
    case GBP_VSTATE_EV_EPISODE_STABLE: return "episode_stable";
    case GBP_VSTATE_EV_EPISODE_CLOSE: return "episode_close";
    case GBP_VSTATE_EV_EPISODE_STORE_FULL: return "episode_store_full";
    case GBP_VSTATE_EV_ANOMALY: return "anomaly";
    case GBP_VSTATE_EV_CAP_REACHED: return "cap_reached";
    case GBP_VSTATE_EV_SAFETY_BUDGET: return "safety_budget";
    case GBP_VSTATE_EV_SCIENTIFIC_TARGET: return "scientific_target";
    case GBP_VSTATE_EV_TAIL_BEGIN: return "tail_begin";
    case GBP_VSTATE_EV_STOP: return "stop";
    case GBP_VSTATE_EV_TEARDOWN_BEGIN: return "teardown_begin";
    case GBP_VSTATE_EV_TEARDOWN_END: return "teardown_end";
    default: return "none";
    }
}

/* ======================================================================
 * The semantic-disagreement policy (HARDWARE_TESTS GBP-VIDEO-002-R3).
 * Everything here is pure RAM: no I/O, no formatting, no second read, and no
 * value is ever re-derived from the device. The two readings arrive already
 * computed from the 32 bytes the transport delivered once.
 * ====================================================================== */

unsigned gbp_vstate_classify(uint16_t disc, uint16_t gbi)
{
    uint16_t delta = (uint16_t)(disc ^ gbi);
    if (delta == 0u) return GBP_VSTATE_DIS_NONE;
    /* Order matters and is normative (§R3.2): the bits with no contract come
     * first, because a difference there is never negotiable. */
    if ((delta & (uint16_t)~GBP_VSTATE_SRC_MASK) != 0u) return GBP_VSTATE_DIS_NON_SOURCE;
    if ((delta & (uint16_t)(GBP_VSTATE_SRC_MASK & ~GBP_VSTATE_AV_MASK)) != 0u)
        return GBP_VSTATE_DIS_SOURCE_OTHER;
    return GBP_VSTATE_DIS_SOURCE_SERVICED;
}

uint16_t gbp_vstate_authoritative(uint16_t disc, uint16_t gbi)
{
    /* Outside SRC_MASK nothing is chosen. By the time this is called the caller
     * has established that the two readings AGREE there - anything else is
     * NON_SOURCE and fatal - so `disc & ~SRC_MASK` and `gbi & ~SRC_MASK` are the
     * same bits and taking either is taking the agreed value, not a vote. Inside
     * SRC_MASK the bitwise majority wins. This is PROJECT POLICY, not a fact
     * about what the hardware intends (§R3.3). */
    uint16_t agreed_non_source = (uint16_t)(disc & (uint16_t)~GBP_VSTATE_SRC_MASK);
    uint16_t authoritative_sources = (uint16_t)(gbi & GBP_VSTATE_SRC_MASK);
    return (uint16_t)(agreed_non_source | authoritative_sources);
}

const char *gbp_vstate_class_name(unsigned c)
{
    switch (c) {
    case GBP_VSTATE_DIS_NONE: return "none";
    case GBP_VSTATE_DIS_SOURCE_SERVICED: return "source_serviced";
    case GBP_VSTATE_DIS_SOURCE_OTHER: return "source_other";
    case GBP_VSTATE_DIS_NON_SOURCE: return "non_source";
    default: return "?";
    }
}

const char *gbp_vstate_fu_name(unsigned st)
{
    switch (st) {
    case GBP_VSTATE_FU_PENDING: return "pending";
    case GBP_VSTATE_FU_SOURCE_PRESENT_NEXT: return "source_present_next";
    case GBP_VSTATE_FU_SOURCE_ABSENT_NEXT: return "source_absent_next";
    case GBP_VSTATE_FU_NO_NEXT_CAUSE: return "no_next_cause";
    case GBP_VSTATE_FU_UNKNOWN: return "unknown";
    default: return "?";
    }
}

const char *gbp_vstate_fur_name(unsigned r)
{
    switch (r) {
    case GBP_VSTATE_FUR_NONE: return "-";
    case GBP_VSTATE_FUR_OBSERVATIONAL: return "observational_site";
    case GBP_VSTATE_FUR_RUN_ABORTED: return "run_aborted";
    case GBP_VSTATE_FUR_NOT_APPLICABLE: return "not_applicable";
    case GBP_VSTATE_FUR_INTERNAL: return "internal_condition";
    default: return "?";
    }
}

unsigned gbp_vstate_hist_index(uint16_t v)
{
    /* source bit 2k -> index bit k, for k = 0..5 (§R3.28) */
    unsigned k, idx = 0u;
    for (k = 0u; k < GBP_VSTATE_GAP_SLOTS; k++)
        if (v & (uint16_t)(1u << (2u * k))) idx |= 1u << k;
    return idx;
}

uint16_t gbp_vstate_gap_slot_bit(unsigned slot)
{
    return (slot < GBP_VSTATE_GAP_SLOTS) ? (uint16_t)(1u << (2u * slot)) : 0u;
}

void gbp_vstate_diag_store(struct gbp_vstate *s, struct gbp_vstate_diag *store, uint32_t cap)
{
    unsigned k;
    if (!s) return;
    s->diags = store;
    s->diags_cap = store ? cap : 0u;
    s->diags_n = 0u;
    s->diag_wait = -1;
    if (store && cap) memset(store, 0, (size_t)cap * sizeof *store);
    for (k = 0u; k < GBP_VSTATE_GAP_SLOTS; k++) {
        s->sem.gap[k].count = 0u;
        s->sem.gap[k].min_ticks = GBP_VSTATE_GAP_NONE;
        s->sem.gap[k].max_ticks = 0u;
        s->sem.gap[k].last_ticks = 0u;
        s->sem.gap[k].last_cause_t = 0u;
    }
}

const struct gbp_vstate_diag *gbp_vstate_diag_first(const struct gbp_vstate *s)
{
    if (!s || !s->diags || s->diags_n == 0u) return 0;
    return &s->diags[0];
}

void gbp_vstate_block_majority_extra(struct gbp_vstate *s)
{
    if (s) s->next_block_majority_extra = GBP_VSTATE_B_MAJORITY_EXTRA;
}

int gbp_vstate_mark_source_deferred(struct gbp_vstate *s)
{
    /* No frame open means no frame is created: a marker never invents a frame
     * (§R3.29). The event still exists in the diagnostic record. */
    if (!s || s->cur_blocks == 0u) return 0;
    s->cur_flags |= GBP_VSTATE_F_SOURCE_DEFERRED;
    s->sem.frames_source_deferred++;
    return 1;
}

void gbp_vstate_gap_observe(struct gbp_vstate *s, uint16_t sources, uint64_t t_cause)
{
    unsigned k;
    if (!s) return;
    for (k = 0u; k < GBP_VSTATE_GAP_SLOTS; k++) {
        struct gbp_vstate_gap *g = &s->sem.gap[k];
        uint64_t d;
        if (!(sources & (uint16_t)(1u << (2u * k)))) continue;
        if (g->last_cause_t != 0u && t_cause > g->last_cause_t) {
            d = t_cause - g->last_cause_t;
            /* saturate rather than wrap: a gap this long cannot occur inside the
             * experiment's caps, and a silent wrap would be a lie (§R3.28) */
            g->last_ticks = (d >= (uint64_t)GBP_VSTATE_GAP_SAT) ? GBP_VSTATE_GAP_SAT : (uint32_t)d;
            if (g->count == 0u || g->last_ticks < g->min_ticks) g->min_ticks = g->last_ticks;
            if (g->last_ticks > g->max_ticks) g->max_ticks = g->last_ticks;
            if (g->count != 0xFFFFFFFFu) g->count++;
        }
        g->last_cause_t = t_cause;
    }
}

/* The gap statistic of the source a disagreement omitted, as it stood BEFORE the
 * event. When several bits were omitted the lowest one is described, and the
 * choice is documented rather than arbitrary. */
static void gap_snapshot(const struct gbp_vstate *s, uint16_t omitted, uint32_t *min, uint16_t *count)
{
    unsigned k;
    *min = GBP_VSTATE_GAP_NONE;
    *count = 0u;
    for (k = 0u; k < GBP_VSTATE_GAP_SLOTS; k++) {
        if (!(omitted & (uint16_t)(1u << (2u * k)))) continue;
        *min = s->sem.gap[k].min_ticks;
        *count = (s->sem.gap[k].count > 0xFFFFu) ? 0xFFFFu : (uint16_t)s->sem.gap[k].count;
        return;
    }
}

static int read_selects_service(uint16_t read_kind)
{
    return read_kind == GBP_VSTATE_DIAG_READ_LEAN || read_kind == GBP_VSTATE_DIAG_READ_PRESVC;
}

int gbp_vstate_diag_open(struct gbp_vstate *s, uint32_t cycle, uint64_t t, const uint8_t *raw,
                         uint16_t disc, uint16_t gbi, uint16_t read_kind, unsigned classification)
{
    struct gbp_vstate_diag *d;
    uint16_t delta, disc_extra, maj_extra;
    int idx;
    if (!s || !raw) return -1;

    delta = (uint16_t)(disc ^ gbi);
    disc_extra = (uint16_t)((disc & GBP_VSTATE_SRC_MASK) & ~(gbi & GBP_VSTATE_SRC_MASK));
    maj_extra = (uint16_t)((gbi & GBP_VSTATE_SRC_MASK) & ~(disc & GBP_VSTATE_SRC_MASK));

    /* Counters and histograms move for EVERY disagreement, preserved or not. */
    if (s->sem.disagreements_total != 0xFFFFFFFFu) s->sem.disagreements_total++;
    switch (classification) {
    case GBP_VSTATE_DIS_SOURCE_SERVICED: s->sem.source_serviced++; break;
    case GBP_VSTATE_DIS_SOURCE_OTHER: s->sem.source_other++; break;
    case GBP_VSTATE_DIS_NON_SOURCE: s->sem.non_source++; break;
    default: break;
    }
    if (disc_extra) s->sem.disc_extra_events++;
    if (maj_extra) s->sem.majority_extra_events++;
    if (disc_extra && maj_extra) s->sem.both_direction_events++;
    if (read_selects_service(read_kind)) s->sem.service_selecting_disagreements++;
    else s->sem.observational_disagreements++;
    s->sem.delta_hist[gbp_vstate_hist_index(delta)]++;
    s->sem.disc_extra_hist[gbp_vstate_hist_index(disc_extra)]++;
    s->sem.majority_extra_hist[gbp_vstate_hist_index(maj_extra)]++;

    if (!s->diags || s->diags_n >= s->diags_cap) {
        /* Store full or absent: nothing is overwritten, the flag is sticky, the
         * run does not stop, and a record already waiting can still be closed. */
        s->sem.diagnostics_not_preserved++;
        s->sem.store_capped = 1u;
        return -1;
    }
    idx = (int)s->diags_n;
    d = &s->diags[idx];
    memset(d, 0, sizeof *d);
    d->t = t;
    d->cycle = cycle;
    d->valid = 1u;
    d->disc_value = disc;
    d->gbi_value = gbi;
    d->read_kind = read_kind;
    d->attempts = 1u;
    memcpy(d->raw, raw, GBP_BLOCK_SIZE);          /* verbatim, before any reduction */
    d->frame_index = s->frames_n;
    d->block_in_frame = s->cur_blocks;
    d->delta = delta;
    d->disc_extra_sources = disc_extra;
    d->majority_extra_sources = maj_extra;
    d->classification = (uint16_t)classification;
    d->authoritative_value = gbp_vstate_authoritative(disc, gbi);
    gap_snapshot(s, disc_extra, &d->gap_min_before_ticks, &d->gap_count_before);
    if (!read_selects_service(read_kind)) {
        /* No service decision was taken here, so no follow-up chain exists and
         * the record must not be readable as though it had one (§R3.10). */
        d->followup_state = GBP_VSTATE_FU_UNKNOWN;
        d->followup_reason = GBP_VSTATE_FUR_OBSERVATIONAL;
        s->sem.followup_unknown++;
    } else if (disc_extra == 0u) {
        /* The majority omitted nothing: there is no omitted source to look for. */
        d->followup_state = GBP_VSTATE_FU_UNKNOWN;
        d->followup_reason = GBP_VSTATE_FUR_NOT_APPLICABLE;
        s->sem.followup_unknown++;
    } else {
        d->followup_state = GBP_VSTATE_FU_PENDING;
        d->followup_reason = GBP_VSTATE_FUR_NONE;
        s->diag_wait = idx;                        /* at most one at a time */
    }
    s->diags_n++;
    s->sem.diagnostics_preserved++;
    return idx;
}

void gbp_vstate_diag_service(struct gbp_vstate *s, uint16_t authoritative, uint16_t service_selected,
                             unsigned incomplete)
{
    struct gbp_vstate_diag *d;
    if (!s || !s->diags || s->diags_n == 0u) { if (s && incomplete) s->sem.service_incomplete_events++; return; }
    d = &s->diags[s->diags_n - 1u];
    d->authoritative_value = authoritative;
    d->service_selected = service_selected;
    if (incomplete) {
        d->record_flags |= GBP_VSTATE_DF_SERVICE_INCOMPLETE;
        s->sem.service_incomplete_events++;
    }
}

void gbp_vstate_diag_ack(struct gbp_vstate *s, uint16_t ack_value, uint64_t t_ack)
{
    struct gbp_vstate_diag *d;
    if (!s || !s->diags || s->diags_n == 0u) return;
    d = &s->diags[s->diags_n - 1u];
    d->ack_value = ack_value;
    d->t_ack = t_ack;
    d->record_flags |= GBP_VSTATE_DF_ACK_WRITTEN;
}

void gbp_vstate_diag_rearm(struct gbp_vstate *s, uint64_t t_rearm)
{
    struct gbp_vstate_diag *d;
    if (!s || !s->diags || s->diags_n == 0u) return;
    d = &s->diags[s->diags_n - 1u];
    d->t_rearm = t_rearm;
    d->record_flags |= GBP_VSTATE_DF_REARM_WRITTEN;
}

void gbp_vstate_diag_payload(struct gbp_vstate *s, uint16_t source, uint32_t crc32, uint32_t first_word)
{
    struct gbp_vstate_diag *d;
    if (!s) return;
    if (source == GBP_VSTATE_SRC_VIDEO) s->sem.majority_extra_video_services++;
    else if (source == GBP_VSTATE_SRC_AUDIO) s->sem.majority_extra_audio_services++;
    if (!s->diags || s->diags_n == 0u) return;
    d = &s->diags[s->diags_n - 1u];
    if (d->record_flags & GBP_VSTATE_DF_PAYLOAD_VALID) {
        /* The slot is taken. Priority is normative and fixed so it cannot drift
         * between runs (§R3.23): VIDEO keeps the slot, because it is the one the
         * scientific path has to reason about. */
        if (source == GBP_VSTATE_SRC_VIDEO && d->payload_source != GBP_VSTATE_SRC_VIDEO) {
            d->payload_source = source;
            d->payload_crc32 = crc32;
            d->payload_first_word = first_word;
        }
        d->record_flags |= GBP_VSTATE_DF_PAYLOAD_SECOND;
        return;
    }
    d->payload_source = source;
    d->payload_crc32 = crc32;
    d->payload_first_word = first_word;
    d->record_flags |= GBP_VSTATE_DF_PAYLOAD_VALID;
    s->sem.payload_diagnostics_captured++;
}

void gbp_vstate_diag_quarantined(struct gbp_vstate *s)
{
    if (!s || !s->diags || s->diags_n == 0u) return;
    s->diags[s->diags_n - 1u].record_flags |= GBP_VSTATE_DF_FRAME_QUARANTINED;
}

void gbp_vstate_diag_deferred(struct gbp_vstate *s)
{
    if (!s || !s->diags || s->diags_n == 0u) return;
    s->diags[s->diags_n - 1u].record_flags |= GBP_VSTATE_DF_SOURCE_DEFERRED;
}

int gbp_vstate_diag_followup(struct gbp_vstate *s, uint64_t t_cause, uint16_t next_gbi, uint16_t next_disc)
{
    struct gbp_vstate_diag *d;
    if (!s || s->diag_wait < 0) return 0;
    if (!s->diags || (uint32_t)s->diag_wait >= s->diags_n) { s->diag_wait = -1; return 0; }
    d = &s->diags[s->diag_wait];
    d->t_next_cause = t_cause;
    d->next_pending_gbi = next_gbi;
    d->next_pending_disc = next_disc;
    /*
     * Presence or absence, PER SOURCE BIT, against the AUTHORITATIVE source set of
     * the next read - `next_gbi & SRC_MASK`, the same reading the service loop
     * acts on. The Disc value of the next read is stored beside it but is NOT
     * consulted here: mixing the two authorities inside one series is exactly the
     * conflation this policy exists to avoid.
     *
     * The aggregate enum is defined narrowly so it can never be read as more than
     * it is (§R3.7):
     *   FU_SOURCE_PRESENT_NEXT  EVERY omitted source was present in that set
     *   FU_SOURCE_ABSENT_NEXT   at least one omitted source was NOT present -
     *                           which includes the partial case
     * The exact split is always derivable offline from two stored fields:
     *   present = disc_extra_sources &  (next_pending_gbi & SRC_MASK)
     *   absent  = disc_extra_sources & ~(next_pending_gbi & SRC_MASK)
     * and tools/vstate.py prints both. Nothing here says the source that came back
     * is the same assertion; it says it was observed after the re-arm.
     */
    {
        uint16_t next_sources = (uint16_t)(next_gbi & GBP_VSTATE_SRC_MASK);
        uint16_t present = (uint16_t)(d->disc_extra_sources & next_sources);
        if (present == d->disc_extra_sources) {
            d->followup_state = GBP_VSTATE_FU_SOURCE_PRESENT_NEXT;
            s->sem.followup_present++;
        } else {
            d->followup_state = GBP_VSTATE_FU_SOURCE_ABSENT_NEXT;
            s->sem.followup_absent++;
            if (present != 0u) s->sem.followup_partial++;   /* some came back, some did not */
        }
    }
    d->followup_reason = GBP_VSTATE_FUR_NONE;
    d->record_flags |= GBP_VSTATE_DF_FOLLOWUP_FILLED;
    s->diag_wait = -1;
    return 1;
}

void gbp_vstate_diag_close(struct gbp_vstate *s, unsigned aborted)
{
    struct gbp_vstate_diag *d;
    if (!s || s->diag_wait < 0) return;
    if (!s->diags || (uint32_t)s->diag_wait >= s->diags_n) { s->diag_wait = -1; return; }
    d = &s->diags[s->diag_wait];
    if (aborted) {
        d->followup_state = GBP_VSTATE_FU_UNKNOWN;
        d->followup_reason = GBP_VSTATE_FUR_RUN_ABORTED;
        s->sem.followup_unknown++;
    } else {
        d->followup_state = GBP_VSTATE_FU_NO_NEXT_CAUSE;
        d->followup_reason = GBP_VSTATE_FUR_NONE;
        s->sem.followup_no_next++;
    }
    s->diag_wait = -1;
}

const char *gbp_vstate_diag_read_name(unsigned kind)
{
    switch (kind) {
    case GBP_VSTATE_DIAG_READ_LEAN: return "READ";
    case GBP_VSTATE_DIAG_READ_PRESVC: return "PRESVC";
    case GBP_VSTATE_DIAG_READ_POSTDRAIN: return "POSTDRAIN";
    case GBP_VSTATE_DIAG_READ_POSTACK: return "POSTACK";
    default: return "OTHER";
    }
}

const char *gbp_vstate_completeness_name(unsigned c)
{
    switch (c) {
    case GBP_VSTATE_FRAME_COMPLETE_40: return "complete_40";
    case GBP_VSTATE_FRAME_INCOMPLETE_SHORT: return "incomplete_short";
    case GBP_VSTATE_FRAME_INCOMPLETE_LONG: return "incomplete_long";
    case GBP_VSTATE_FRAME_PREDICATE_ANOMALY: return "predicate_anomaly";
    case GBP_VSTATE_FRAME_RESYNC: return "resync";
    default: return "unknown";
    }
}

const char *gbp_vstate_episode_state_name(unsigned st)
{
    switch (st) {
    case GBP_VSTATE_EP_ARMED: return "armed";
    case GBP_VSTATE_EP_CHANGED: return "changed";
    case GBP_VSTATE_EP_STABILISING: return "stabilising";
    case GBP_VSTATE_EP_CLOSED: return "closed";
    default: return "?";
    }
}

/* ---- raw storage helpers -------------------------------------------- */
static uint8_t *ring_slot(struct gbp_vstate *s, uint32_t slot)
{
    return s->raw_ring + (size_t)slot * GBP_VSTATE_RAW_FRAME_BYTES;
}

const uint8_t *gbp_vstate_ring_block(const struct gbp_vstate *s, uint32_t slot, uint32_t block)
{
    if (!s || !s->raw_ring || slot >= GBP_VSTATE_RAW_RING_SLOTS || block >= GBP_VSTATE_FRAME_MAX_BLOCKS) return 0;
    return s->raw_ring + (size_t)slot * GBP_VSTATE_RAW_FRAME_BYTES + (size_t)block * GBP_VSTATE_VIDEO_BLOCK_SIZE;
}

const uint8_t *gbp_vstate_episode_block(const struct gbp_vstate *s, uint32_t raw_slot, uint32_t block)
{
    uint32_t slots = GBP_VSTATE_MAX_EPISODES * GBP_VSTATE_EPISODE_RAW_SLOTS;
    if (!s || !s->episode_raw || raw_slot >= slots || block >= GBP_VSTATE_FRAME_MAX_BLOCKS) return 0;
    return s->episode_raw + (size_t)raw_slot * GBP_VSTATE_RAW_FRAME_BYTES + (size_t)block * GBP_VSTATE_VIDEO_BLOCK_SIZE;
}

uint8_t *gbp_vstate_video_target(struct gbp_vstate *s)
{
    if (!s || !s->raw_ring) return 0;
    if (s->cur_blocks >= GBP_VSTATE_FRAME_MAX_BLOCKS) return 0;   /* the caller must close first; gbp_vstate_block() does */
    return ring_slot(s, s->cur_slot) + (size_t)s->cur_blocks * GBP_VSTATE_VIDEO_BLOCK_SIZE;
}

/* ---- episode bookkeeping -------------------------------------------- */
static struct gbp_vstate_episode *cur_episode(struct gbp_vstate *s)
{
    if (!s->episode_open || s->episode_cur == 0u) return 0;
    if (s->episode_shadow_active) return &s->shadow;
    if (s->episode_cur >= 1u && s->episode_cur <= s->episodes_n) return &s->episodes[s->episode_cur - 1u];
    return 0;
}

/* Copies one closed frame out of the ring into the episode's raw budget.
 * Returns 1 when a slot was used, 0 when the episode has no budget left (which is a bounded,
 * named condition, never an overwrite of an earlier episode). */
static int preserve_frame(struct gbp_vstate *s, struct gbp_vstate_episode *ep, uint32_t slot,
                          uint32_t frame_index, uint32_t blocks)
{
    uint32_t k, n;
    uint8_t *dst;
    const uint8_t *src;
    if (!ep || ep->raw_slot == 0xFFFFFFFFu) return 0;
    if (ep->raw_frames >= GBP_VSTATE_EPISODE_RAW_SLOTS) return 0;
    for (k = 0; k < ep->raw_frames; k++) if (ep->raw_frame_index[k] == frame_index) return 1;   /* already kept */
    n = blocks;
    if (n > GBP_VSTATE_FRAME_MAX_BLOCKS) n = GBP_VSTATE_FRAME_MAX_BLOCKS;
    dst = s->episode_raw + (size_t)(ep->raw_slot + ep->raw_frames) * GBP_VSTATE_RAW_FRAME_BYTES;
    src = ring_slot(s, slot);
    memcpy(dst, src, (size_t)n * GBP_VSTATE_VIDEO_BLOCK_SIZE);
    ep->raw_frame_index[ep->raw_frames] = frame_index;
    ep->raw_frame_blocks[ep->raw_frames] = n;
    ep->raw_frames++;
    ep->flags |= GBP_VSTATE_EPF_RAW_PRESERVED;
    s->episode_raw_used++;
    if (frame_index < s->frames_n) s->frames[frame_index].flags |= GBP_VSTATE_F_RAW_PRESERVED;
    return 1;
}

/* ---- the frame assembler -------------------------------------------- */
static void note_interval(struct gbp_vstate *s, uint32_t blocks, int had_boundary)
{
    uint32_t i = had_boundary ? blocks : (GBP_VSTATE_FRAME_MAX_BLOCKS + 1u);
    if (i > GBP_VSTATE_FRAME_MAX_BLOCKS + 1u) i = GBP_VSTATE_FRAME_MAX_BLOCKS + 1u;
    if (s->interval_hist[i] != 0xFFFFFFFFu) s->interval_hist[i]++;
}

static void run_baseline(struct gbp_vstate *s, struct gbp_vstate_frame *f, uint32_t slot,
                         struct gbp_vstate_step *step);
static void run_episodes(struct gbp_vstate *s, struct gbp_vstate_frame *f, uint32_t slot,
                         struct gbp_vstate_step *step);

/* Closes the frame being assembled. `had_boundary` says a Disc boundary ended it (the block that
 * carries the boundary belongs to the NEXT frame and has already been moved there by the caller).
 * Returns the ring slot the closed frame occupies. */
static uint32_t close_frame(struct gbp_vstate *s, int had_boundary, struct gbp_vstate_step *step)
{
    struct gbp_vstate_frame *f;
    uint32_t slot = s->cur_slot;
    uint32_t blocks = s->cur_blocks;
    uint16_t flags = s->cur_flags;
    unsigned completeness;
    int clean, complete, region_anomaly = 0;

    if (blocks == 40u && had_boundary) {
        completeness = GBP_VSTATE_FRAME_COMPLETE_40;
        flags |= GBP_VSTATE_F_COMPLETE;
    } else if (had_boundary && blocks < 40u) {
        completeness = (s->cur_disagreements ? (unsigned)GBP_VSTATE_FRAME_PREDICATE_ANOMALY
                                             : (unsigned)GBP_VSTATE_FRAME_INCOMPLETE_SHORT);
        region_anomaly = 1;                       /* class (b): a boundary at an unexpected position */
    } else if (had_boundary) {
        completeness = (s->cur_disagreements ? (unsigned)GBP_VSTATE_FRAME_PREDICATE_ANOMALY
                                             : (unsigned)GBP_VSTATE_FRAME_INCOMPLETE_LONG);
        flags |= GBP_VSTATE_F_OVERLONG | GBP_VSTATE_F_ANOMALY;
        region_anomaly = 1;
    } else {
        /* 48 blocks and no boundary at all. The design classifies this as frame-invalidating
         * (class a); it also leaves the assembler without an anchor, so the conservative rule the
         * design states — when in doubt the time does not count — additionally pauses the clock.
         * Both counters are incremented, so neither reading is hidden. */
        completeness = GBP_VSTATE_FRAME_INCOMPLETE_LONG;
        flags |= GBP_VSTATE_F_OVERLONG | GBP_VSTATE_F_ANOMALY;
        region_anomaly = 1;
    }
    if (s->cur_disagreements) flags |= GBP_VSTATE_F_DISAGREEMENT | GBP_VSTATE_F_ANOMALY;
    if (!s->baseline_valid) flags |= GBP_VSTATE_F_PRE_BASELINE;
    if (s->tail_active) flags |= GBP_VSTATE_F_TAIL;

    complete = (completeness == GBP_VSTATE_FRAME_COMPLETE_40) ? 1 : 0;
    clean = (complete && (flags & (GBP_VSTATE_F_ANOMALY | GBP_VSTATE_F_DISAGREEMENT | GBP_VSTATE_F_OVERLONG)) == 0u) ? 1 : 0;

    note_interval(s, blocks, had_boundary);
    if (complete) s->frames_complete++; else s->frames_incomplete++;
    if (flags & GBP_VSTATE_F_ANOMALY) s->anomalies_frame++;
    if (region_anomaly) {
        s->anomalies_region++;
        if (!s->resync_pending) gbp_vstate_event(s, s->cur_t_last, GBP_VSTATE_EV_RESYNC, s->frames_n, blocks,
                                                 had_boundary ? 1u : 0u, completeness);
        s->resync_pending = 1;
        s->resync_frames++;
        if (step) step->resync = 1;
    } else if (s->resync_pending) {
        /* A clean complete frame with an observed boundary re-establishes synchronisation. It ends
         * the pause but, conservatively, is NOT itself counted as negative evidence; the frames
         * after it are. Anything else keeps the pause. */
        s->resync_frames++;
        flags |= GBP_VSTATE_F_RESYNC;
        if (clean) s->resync_pending = 0;
        clean = 0;                                 /* not counted, not used for baseline or episodes */
    }

    if (s->frames_n >= s->frames_cap) {
        s->frame_store_full = 1;
        if (step) step->frame_store_full = 1;
        gbp_vstate_event(s, s->cur_t_last, GBP_VSTATE_EV_CAP_REACHED, 1u, s->frames_n, 0u, 0u);
        /* nothing is overwritten and nothing wraps: the frame is simply not stored and the run ends */
        s->cur_blocks = 0; s->cur_flags = 0; s->cur_disagreements = 0;
        return slot;
    }

    f = &s->frames[s->frames_n];
    memset(f, 0, sizeof *f);
    f->t_first_block = s->cur_t_first;
    f->t_last_block = s->cur_t_last;
    f->index = s->frames_n;
    f->blocks = (uint16_t)(blocks > 0xFFFFu ? 0xFFFFu : blocks);
    f->flags = flags;
    f->disagreements = s->cur_disagreements;
    f->completeness = (uint16_t)completeness;
    sig_copy(f->sig, s->cur_sig);
    s->frames_n++;

    if (completeness != GBP_VSTATE_FRAME_COMPLETE_40)
        gbp_vstate_event(s, s->cur_t_last, GBP_VSTATE_EV_INCOMPLETE_INTERVAL, f->index, blocks, completeness, had_boundary ? 1u : 0u);

    if (step) { step->frame_closed = 1; step->frame_index = f->index; step->frame_complete = complete; }

    /* the scientific clock: only a clean complete frame, only after baseline_valid, only while the
     * stream is interpretable. Its own span is used, which slightly understates the period — the
     * conservative direction. */
    if (clean && s->baseline_valid && !s->frame_store_full) {
        uint64_t dur = (f->t_last_block > f->t_first_block) ? (f->t_last_block - f->t_first_block) : 0u;
        s->valid_observation_elapsed += dur;
        s->frames_counted++;
        f->flags |= GBP_VSTATE_F_COUNTED;
        if (step) step->counted = 1;
    }

    if (s->tail_active) {
        s->tail_frames++;
        s->tail_ticks = (f->t_last_block > s->tail_t_begin) ? (f->t_last_block - s->tail_t_begin) : 0u;
    }

    if (clean) {
        if (!s->baseline_valid) run_baseline(s, f, slot, step);
        else run_episodes(s, f, slot, step);
    } else if (s->episode_open) {
        struct gbp_vstate_episode *ep = cur_episode(s);
        if (ep) {
            ep->frames++;
            f->episode = ep->index;
            if (ep->frames >= GBP_VSTATE_EPISODE_MAX_FRAMES) {
                /* an episode never runs unbounded, even through a stretch of unusable frames */
                ep->state = GBP_VSTATE_EP_CLOSED;
                ep->flags |= GBP_VSTATE_EPF_CAPPED;
                ep->close_frame = f->index;
                ep->t_close = f->t_last_block;
                s->unstable_episodes++;
                s->episode_open = 0;
                s->episode_cur = 0;
                s->episode_shadow_active = 0;
                gbp_vstate_event(s, f->t_last_block, GBP_VSTATE_EV_EPISODE_CLOSE, ep->index, f->index, ep->frames, 0u);
                if (step) step->episode_closed = 1;
            }
        }
    }

    s->prev_slot = (int)slot;
    s->prev_frame_index = f->index;
    s->prev_frame_blocks = blocks;
    s->prev_frame_clean = clean;
    s->cur_blocks = 0;
    s->cur_flags = 0;
    s->cur_disagreements = 0;
    return slot;
}

/* Baseline learning: three consecutive clean complete frames with identical signature vectors.
 * `current_reference_sig` doubles as the running candidate before baseline_valid, which is what
 * it becomes at baseline_valid — there is no second 160-byte buffer and no ambiguity. */
static void run_baseline(struct gbp_vstate *s, struct gbp_vstate_frame *f, uint32_t slot,
                         struct gbp_vstate_step *step)
{
    if (s->baseline_frames_seen == 0u) {
        sig_copy(s->current_reference_sig, f->sig);
        s->baseline_frames_seen = 1u;
        gbp_vstate_event(s, f->t_last_block, GBP_VSTATE_EV_BASELINE_CANDIDATE, f->index, 1u, 0u, 0u);
        f->flags |= GBP_VSTATE_F_BASELINE;
        return;
    }
    if (sig_equal(s->current_reference_sig, f->sig)) {
        s->baseline_frames_seen++;
        f->flags |= GBP_VSTATE_F_BASELINE;
        gbp_vstate_event(s, f->t_last_block, GBP_VSTATE_EV_BASELINE_CANDIDATE, f->index, s->baseline_frames_seen, 0u, 0u);
        if (s->baseline_frames_seen >= GBP_VSTATE_BASELINE_FRAMES) {
            s->baseline_valid = 1;
            s->baseline_frame_index = f->index;
            s->t_baseline_valid = f->t_last_block;
            sig_copy(s->original_baseline_sig, s->current_reference_sig);   /* fixed once, never overwritten */
            gbp_vstate_event(s, f->t_last_block, GBP_VSTATE_EV_BASELINE_VALID, f->index, s->baseline_frames_seen,
                             s->current_reference_sig[0], s->current_reference_sig[GBP_VSTATE_FRAME_SIGS - 1u]);
        }
        return;
    }
    /* A pre-baseline frame that differs from its neighbours is evidence, not noise: it is recorded
     * in full (it already is, in the frame store) and the FIRST one also keeps its raw, using one
     * episode descriptor. Later ones are counted only — otherwise a flickering start could consume
     * every descriptor before the baseline exists and leave nothing for a real episode. */
    s->early_candidates++;
    f->flags |= GBP_VSTATE_F_EARLY_CANDIDATE;
    if (s->episodes_n < GBP_VSTATE_MAX_EPISODES && s->early_candidates == 1u) {
        struct gbp_vstate_episode *ep = &s->episodes[s->episodes_n];
        memset(ep, 0, sizeof *ep);
        ep->index = s->episodes_n + 1u;
        ep->state = GBP_VSTATE_EP_CLOSED;
        ep->flags = GBP_VSTATE_EPF_EARLY;
        ep->open_frame = ep->close_frame = f->index;
        ep->t_open = ep->t_close = f->t_last_block;
        ep->raw_slot = s->episodes_n * GBP_VSTATE_EPISODE_RAW_SLOTS;
        ep->frames = 1u;
        sig_copy(ep->candidate, f->sig);
        s->episodes_n++;
        if (s->prev_slot >= 0) preserve_frame(s, ep, (uint32_t)s->prev_slot, s->prev_frame_index, s->prev_frame_blocks);
        preserve_frame(s, ep, slot, f->index, f->blocks);
        f->episode = ep->index;
    }
    gbp_vstate_event(s, f->t_last_block, GBP_VSTATE_EV_EARLY_CANDIDATE, f->index, s->early_candidates, f->sig[0], 0u);
    if (step) step->early_candidate = 1;
    sig_copy(s->current_reference_sig, f->sig);
    s->baseline_frames_seen = 1u;
}

static void open_episode(struct gbp_vstate *s, struct gbp_vstate_frame *f, uint32_t slot,
                         struct gbp_vstate_step *step)
{
    struct gbp_vstate_episode *ep;
    s->episode_count++;
    if (s->episodes_n < GBP_VSTATE_MAX_EPISODES) {
        ep = &s->episodes[s->episodes_n];
        memset(ep, 0, sizeof *ep);
        ep->index = s->episodes_n + 1u;
        ep->raw_slot = s->episodes_n * GBP_VSTATE_EPISODE_RAW_SLOTS;
        s->episodes_n++;
        s->episode_cur = ep->index;
        s->episode_shadow_active = 0;
    } else {
        /* The raw budget is exhausted. Monitoring does NOT stop: the episode is tracked in the
         * shadow descriptor so current_reference_signature keeps advancing, it is counted in
         * episodes_not_preserved, and NO earlier episode is touched. */
        ep = &s->shadow;
        memset(ep, 0, sizeof *ep);
        ep->index = GBP_VSTATE_EPISODE_SHADOW | s->episode_count;
        ep->raw_slot = 0xFFFFFFFFu;
        ep->flags |= GBP_VSTATE_EPF_NOT_PRESERVED;
        s->episode_cur = ep->index;
        s->episode_shadow_active = 1;
        s->episodes_not_preserved++;
        if (!s->episode_store_full) {
            s->episode_store_full = 1;
            gbp_vstate_event(s, f->t_last_block, GBP_VSTATE_EV_EPISODE_STORE_FULL, s->episode_count,
                             s->episodes_n, s->episode_raw_used, 0u);
            if (step) step->episode_store_full = 1;
        }
    }
    ep->state = GBP_VSTATE_EP_CHANGED;
    ep->open_frame = f->index;
    ep->t_open = f->t_last_block;
    ep->frames = 1u;
    ep->stable_count = 1u;
    sig_copy(ep->candidate, f->sig);
    s->episode_open = 1;
    f->episode = ep->index;
    f->flags |= GBP_VSTATE_F_EPISODE_CHANGE;
    /* the last reference frame before the change, then the first changed frame */
    if (s->prev_slot >= 0) preserve_frame(s, ep, (uint32_t)s->prev_slot, s->prev_frame_index, s->prev_frame_blocks);
    preserve_frame(s, ep, slot, f->index, f->blocks);
    gbp_vstate_event(s, f->t_last_block, GBP_VSTATE_EV_EPISODE_OPEN, ep->index, f->index,
                     s->current_reference_sig[0], f->sig[0]);
    if (step) step->episode_opened = 1;
}

static void close_episode(struct gbp_vstate *s, struct gbp_vstate_episode *ep, struct gbp_vstate_frame *f,
                          int stable, struct gbp_vstate_step *step)
{
    ep->state = GBP_VSTATE_EP_CLOSED;
    ep->close_frame = f->index;
    ep->t_close = f->t_last_block;
    if (stable) {
        ep->flags |= GBP_VSTATE_EPF_STABLE_FOUND;
        sig_copy(ep->final_sig, ep->candidate);
        s->stable_episodes++;
        /* the reference advances to the state the device actually settled into; the ORIGINAL
         * baseline is never touched, so every episode stays reportable against it too */
        sig_copy(s->current_reference_sig, ep->candidate);
        s->reference_updates++;
        f->flags |= GBP_VSTATE_F_EPISODE_STABLE;
    } else {
        ep->flags |= GBP_VSTATE_EPF_CAPPED;
        s->unstable_episodes++;
        /* no stable state was observed, so no new reference is invented */
    }
    s->episode_open = 0;
    s->episode_cur = 0;
    s->episode_shadow_active = 0;
    gbp_vstate_event(s, f->t_last_block, GBP_VSTATE_EV_EPISODE_CLOSE, ep->index, f->index, ep->frames,
                     stable ? 1u : 0u);
    if (step) { step->episode_closed = 1; step->episode_stable = stable; }
}

static void run_episodes(struct gbp_vstate *s, struct gbp_vstate_frame *f, uint32_t slot,
                         struct gbp_vstate_step *step)
{
    struct gbp_vstate_episode *ep = cur_episode(s);
    if (!s->episode_open) {
        if (sig_equal(s->current_reference_sig, f->sig)) return;            /* ARMED and matching */
        if (s->tail_active) return;                                          /* no new episode during the tail */
        open_episode(s, f, slot, step);
        return;
    }
    if (!ep) { s->episode_open = 0; s->episode_cur = 0; s->episode_shadow_active = 0; return; }
    ep->frames++;
    f->episode = ep->index;
    if (sig_equal(ep->candidate, f->sig)) {
        ep->stable_count++;
        ep->state = GBP_VSTATE_EP_STABILISING;
        gbp_vstate_event(s, f->t_last_block, GBP_VSTATE_EV_EPISODE_STABILISING, ep->index, f->index, ep->stable_count, 0u);
        if (ep->stable_count >= GBP_VSTATE_N_STABLE) {
            preserve_frame(s, ep, slot, f->index, f->blocks);               /* the stable state's raw */
            gbp_vstate_event(s, f->t_last_block, GBP_VSTATE_EV_EPISODE_STABLE, ep->index, f->index, ep->stable_count, f->sig[0]);
            close_episode(s, ep, f, 1, step);
            return;
        }
    } else {
        sig_copy(ep->candidate, f->sig);
        ep->stable_count = 1u;
        ep->state = GBP_VSTATE_EP_CHANGED;
        preserve_frame(s, ep, slot, f->index, f->blocks);                    /* context, while the budget allows */
        gbp_vstate_event(s, f->t_last_block, GBP_VSTATE_EV_EPISODE_STABILISING, ep->index, f->index, 1u, f->sig[0]);
    }
    if (ep->frames >= GBP_VSTATE_EPISODE_MAX_FRAMES) close_episode(s, ep, f, 0, step);
}

/* ---- feeding one block ---------------------------------------------- */
int gbp_vstate_block(struct gbp_vstate *s, const uint8_t *block, uint32_t len, const uint8_t first4[4],
                     uint64_t t, uint32_t sig, uint32_t sig_cost_ticks, struct gbp_vstate_step *step)
{
    int disc, gbi, disagree;
    if (step) memset(step, 0, sizeof *step);
    if (!s || !s->raw_ring || !first4) return -1;
    (void)block; (void)len;                       /* the bytes are already in the ring slot the caller was given */

    gbp_vsig_cost_add(&s->cost, sig_cost_ticks);
    s->blocks_total++;

    disc = gbp_vsig_flag_disc(first4);
    gbi = gbp_vsig_flag_gbi(first4);
    disagree = (disc && !gbi) ? 1 : 0;
    if (disc) s->boundaries_disc++;
    if (gbi) s->boundaries_gbi++;

    if (disc) {
        /* The Start-up Disc predicate is the segmentation signal: it reads byte 1 alone, and byte 1
         * is the stable byte (GBP-HW-070: byte 0 disagreed in 688 of 84 480 words, byte 2 never).
         * Neither predicate is ever fabricated or suppressed; both counts are reported. */
        if (s->cur_blocks > 0u) {
            uint32_t src_slot = s->cur_slot;
            uint32_t at = s->cur_blocks;
            uint32_t next_slot = (s->cur_slot + 1u) % GBP_VSTATE_RAW_RING_SLOTS;
            /* The boundary block was DMA'd at position `at` of the slot the previous interval was
             * filling; it is block 0 of the NEXT frame, so it moves once — one 0xF00 copy per
             * frame, about 60 per second, and never a copy per block. */
            memcpy(ring_slot(s, next_slot), ring_slot(s, src_slot) + (size_t)at * GBP_VSTATE_VIDEO_BLOCK_SIZE,
                   GBP_VSTATE_VIDEO_BLOCK_SIZE);
            if (s->asm_state == ASM_IN_FRAME) {
                close_frame(s, 1, step);
            } else {
                /* no anchor yet: the blocks before this boundary belong to no frame and are
                 * counted, never turned into one */
                s->blocks_before_first_boundary += at;
                s->cur_blocks = 0; s->cur_flags = 0; s->cur_disagreements = 0;
            }
            s->cur_slot = next_slot;
        }
        s->asm_state = ASM_IN_FRAME;
    }

    if (s->cur_blocks < GBP_VSTATE_FRAME_SIGS) s->cur_sig[s->cur_blocks] = sig;
    if (s->cur_blocks == 0u) {
        unsigned i;
        for (i = 1; i < GBP_VSTATE_FRAME_SIGS; i++) s->cur_sig[i] = 0u;
        s->cur_t_first = t;
    }
    /* §R3.11/§R3.12: provenance travels with the block, and the flag is applied
     * HERE - after any boundary has closed the previous frame - so it lands on
     * the frame that actually ACCUMULATES this block. Doing it earlier would put
     * it on the previous frame whenever the suspect block is itself a boundary,
     * invalidating the wrong frame and leaving the right one apparently clean.
     * F_MAJORITY_EXTRA plus F_ANOMALY: the existing machinery then keeps the
     * frame out of F_COUNTED, out of the baseline and out of every
     * structured-change decision, before any of those run for it. */
    if (s->next_block_majority_extra) {
        s->next_block_majority_extra = 0u;
        s->cur_flags |= (uint16_t)(GBP_VSTATE_F_MAJORITY_EXTRA | GBP_VSTATE_F_ANOMALY);
        s->sem.frames_quarantined++;
    }
    s->cur_blocks++;
    s->cur_t_last = t;
    if (disagree) {
        s->cur_disagreements++;
        s->disagreements_total++;
        if (!s->disagreement_seen) {
            s->disagreement_seen = 1;
            s->disagreement_first_frame = s->frames_n;
            s->disagreement_first_block = s->cur_blocks - 1u;
            s->disagreement_first4[0] = first4[0]; s->disagreement_first4[1] = first4[1];
            s->disagreement_first4[2] = first4[2]; s->disagreement_first4[3] = first4[3];
        }
        gbp_vstate_event(s, t, GBP_VSTATE_EV_PREDICATE_DISAGREEMENT, s->frames_n, s->cur_blocks - 1u,
                         ((uint32_t)first4[0] << 24) | ((uint32_t)first4[1] << 16) |
                         ((uint32_t)first4[2] << 8) | (uint32_t)first4[3], s->disagreements_total);
    }

    if (s->cur_blocks >= GBP_VSTATE_FRAME_MAX_BLOCKS) {
        /* 48 blocks and not one boundary. A boundary is NEVER synthesised from an assumed period:
         * the interval is closed as it was observed and the anchor is given up. */
        if (s->asm_state == ASM_IN_FRAME) {
            close_frame(s, 0, step);
        } else {
            s->blocks_before_first_boundary += s->cur_blocks;
            gbp_vstate_event(s, t, GBP_VSTATE_EV_INCOMPLETE_INTERVAL, s->frames_n, s->cur_blocks,
                             GBP_VSTATE_FRAME_UNKNOWN, 0u);
            s->cur_blocks = 0; s->cur_flags = 0; s->cur_disagreements = 0;
        }
        s->asm_state = ASM_SEEKING;
        s->cur_slot = (s->cur_slot + 1u) % GBP_VSTATE_RAW_RING_SLOTS;
    }
    if (step) {
        step->frame_store_full = s->frame_store_full ? 1 : step->frame_store_full;
        step->event_store_full = s->event_store_full ? 1 : step->event_store_full;
    }
    return 0;
}

/* ---- the scientific target, the safety cap and the tail -------------- */
int gbp_vstate_target_reached(struct gbp_vstate *s, uint64_t t)
{
    if (!s) return 0;
    gbp_vstate_event(s, t, GBP_VSTATE_EV_SCIENTIFIC_TARGET, s->frames_n, s->episode_count,
                     s->frames_counted, s->episode_open ? 1u : 0u);
    if (!s->episode_open) return 0;
    if (!s->tail_active) {
        struct gbp_vstate_episode *ep = cur_episode(s);
        s->tail_active = 1;
        s->tail_t_begin = t;
        if (ep) ep->flags |= GBP_VSTATE_EPF_TAIL;
        gbp_vstate_event(s, t, GBP_VSTATE_EV_TAIL_BEGIN, s->episode_cur, s->frames_n, 0u, 0u);
    }
    return 1;
}

void gbp_vstate_safety_stop(struct gbp_vstate *s, uint64_t t)
{
    struct gbp_vstate_episode *ep;
    if (!s) return;
    ep = cur_episode(s);
    if (ep && s->episode_open) {
        ep->state = GBP_VSTATE_EP_CLOSED;
        ep->flags |= GBP_VSTATE_EPF_TRUNCATED_BY_SAFETY;
        ep->close_frame = s->frames_n ? s->frames_n - 1u : 0u;
        ep->t_close = t;
        if (!(ep->flags & GBP_VSTATE_EPF_STABLE_FOUND)) s->unstable_episodes++;
        s->episode_open = 0;
        s->episode_cur = 0;
        s->episode_shadow_active = 0;
    }
    s->tail_active = 0;
    gbp_vstate_event(s, t, GBP_VSTATE_EV_SAFETY_BUDGET, s->frames_n, s->episode_count, ep ? ep->index : 0u, 0u);
}

void gbp_vstate_tail_truncate(struct gbp_vstate *s, uint64_t t)
{
    if (!s) return;
    if (s->tail_active) {
        s->tail_active = 0;
        s->tail_truncated_by_cap = 1;
        gbp_vstate_event(s, t, GBP_VSTATE_EV_CAP_REACHED, 2u, s->frames_n, s->tail_frames, 0u);
    }
}

/* ---- AUDIO ----------------------------------------------------------- */
uint8_t *gbp_vstate_audio_target(struct gbp_vstate *s, unsigned *slot)
{
    unsigned k;
    if (!s || !s->audio_raw) { if (slot) *slot = 0u; return 0; }
    if (!s->audio.first_valid) k = 0u;
    else k = s->audio.last_next;                  /* 1 or 2: never the slot holding the last valid capture */
    if (k >= GBP_VSTATE_AUDIO_RAW_SLOTS) k = 1u;
    if (slot) *slot = k;
    return s->audio_raw + (size_t)k * GBP_VSTATE_AUDIO_BLOCK_SIZE;
}

void gbp_vstate_audio_commit(struct gbp_vstate *s, unsigned slot, int completed, uint32_t bytes, uint64_t cycle)
{
    if (!s) return;
    s->audio.attempted++;
    if (!completed) { s->audio.failures++; return; }
    s->audio.completed++;
    s->audio.bytes += (uint64_t)bytes;
    if (slot == 0u && !s->audio.first_valid) {
        s->audio.first_valid = 1;
        s->audio.first_cycle = cycle;
        s->audio.last_next = 1u;
        return;
    }
    if (slot >= 1u && slot < GBP_VSTATE_AUDIO_RAW_SLOTS) {
        s->audio.last_valid = (int)slot;
        s->audio.last_cycle = cycle;
        s->audio.last_next = (slot == 1u) ? 2u : 1u;
    }
}

const uint8_t *gbp_vstate_audio_bytes(const struct gbp_vstate *s, unsigned slot)
{
    if (!s || !s->audio_raw || slot >= GBP_VSTATE_AUDIO_RAW_SLOTS) return 0;
    return s->audio_raw + (size_t)slot * GBP_VSTATE_AUDIO_BLOCK_SIZE;
}

unsigned gbp_vstate_audio_raw_count(const struct gbp_vstate *s)
{
    unsigned n = 0;
    if (!s) return 0u;
    if (s->audio.first_valid) n++;
    if (s->audio.last_valid >= 0) n++;
    return n;
}
