/*
 * gbp_vwitness.c — see gbp_vwitness.h for what is retained and why the stop is
 * a count rather than a clock.
 */
#include "gbp_vwitness.h"

static void clear_scratch(struct gbp_vwitness *w)
{
    uint32_t i;
    for (i = 0; i < GBP_VWITNESS_FRAME_WORDS; i++) w->scratch[i] = 0u;
    w->scratch_present = 0u;
    w->scratch_blocks = 0u;
    w->staged_valid = 0u;
}

int gbp_vwitness_init(struct gbp_vwitness *w, uint16_t *store, struct gbp_vwitness_meta *meta,
                      uint32_t cap, uint32_t target)
{
    uint32_t i;
    uint8_t *b;
    if (!w) return -1;
    b = (uint8_t *)w;
    for (i = 0; i < sizeof *w; i++) b[i] = 0u;
    if (!store || !meta || cap == 0u) return -1;
    w->store = store;
    w->meta = meta;
    w->cap = cap;
    w->target = (target == 0u || target > cap) ? cap : target;
    w->copy_ticks_min = 0xFFFFFFFFu;
    w->qual_state = GBP_VWITNESS_QUAL_ARMED;   /* no qualification unless asked for */
    w->qual_frame_index = 0xFFFFFFFFu;
    return 0;
}

void gbp_vwitness_set_qualification(struct gbp_vwitness *w, uint32_t required)
{
    if (!w) return;
    w->qual_required = required;
    w->qual_state = required ? GBP_VWITNESS_QUAL_WARMUP : GBP_VWITNESS_QUAL_ARMED;
    w->qual_streak = 0u;
}

void gbp_vwitness_note_frame(struct gbp_vwitness *w, int qualifying)
{
    if (!w) return;
    /* ONE-WAY. Once the window is open the streak is history: a later resync
     * stays inside the scientific population, where it belongs. */
    if (w->qual_state == GBP_VWITNESS_QUAL_ARMED) return;
    w->warmup_frames++;
    if (w->elig_gated) {
        /* NOT ELIGIBLE YET (§V5.55). Seen and counted as startup evidence --
         * warmup_frames and warmup_disqualified keep their meaning, "before the
         * window opened" -- but the streak is neither built nor broken, so no
         * reset and no streak state can cross the eligibility boundary. */
        w->elig_frames_before++;
        if (!qualifying) { w->warmup_disqualified++; w->elig_disqualified_before++; }
        return;
    }
    if (!qualifying) {
        if (w->qual_streak) w->qual_resets++;
        w->qual_streak = 0u;
        w->warmup_disqualified++;
        return;
    }
    w->qual_streak++;
    if (w->qual_streak > w->qual_streak_max) w->qual_streak_max = w->qual_streak;
    if (w->qual_state == GBP_VWITNESS_QUAL_WARMUP && w->qual_streak >= w->qual_required) {
        /* The streak is complete, but THIS frame is already closed: retaining it
         * would mean starting mid-frame. The window opens at the next block 0. */
        w->qual_state = GBP_VWITNESS_QUAL_PENDING;
        w->qual_frame_index = w->warmup_frames - 1u;
    }
}

void gbp_vwitness_gate_streak(struct gbp_vwitness *w)
{
    if (!w) return;
    if (w->qual_state == GBP_VWITNESS_QUAL_ARMED) return;   /* nothing left to gate */
    w->elig_gated = 1u;
    w->qual_streak = 0u;
}

void gbp_vwitness_release_streak(struct gbp_vwitness *w, uint64_t t)
{
    if (!w || !w->elig_gated) return;                        /* one-way, idempotent */
    w->elig_gated = 0u;
    w->elig_released = 1u;
    w->t_eligible = t;
    w->qual_streak = 0u;                                     /* from ZERO, by contract */
}

int gbp_vwitness_streak_gated(const struct gbp_vwitness *w)
{
    return (w && w->elig_gated) ? 1 : 0;
}

int gbp_vwitness_qualified(const struct gbp_vwitness *w)
{
    return (w && w->qual_state != GBP_VWITNESS_QUAL_WARMUP) ? 1 : 0;
}

int gbp_vwitness_armed(const struct gbp_vwitness *w)
{
    return (w && w->qual_state == GBP_VWITNESS_QUAL_ARMED) ? 1 : 0;
}

void gbp_vwitness_arm(struct gbp_vwitness *w)
{
    if (!w || w->qual_state != GBP_VWITNESS_QUAL_PENDING) return;
    w->qual_state = GBP_VWITNESS_QUAL_ARMED;
    clear_scratch(w);            /* nothing from warm-up may leak into record 0 */
}

int gbp_vwitness_stage(struct gbp_vwitness *w, const uint8_t *block)
{
    const uint8_t *p;
    uint32_t i;
    if (!w || !w->store || !block) return -1;
    if (w->qual_state != GBP_VWITNESS_QUAL_ARMED) return -1;   /* warm-up: retain nothing */
    /* Local row 0, columns x = 1 .. 54. The word is bytes 1 and 3 of the pixel;
     * bytes 0 and 2 are not read (U-GBP-029) and bit 15 is not masked
     * (U-GBP-034). 54 iterations, two loads each, no branch, no call. */
    p = block + (size_t)GBP_VWITNESS_ROW * GBP_VWITNESS_LINE_STRIDE
              + (size_t)GBP_VWITNESS_STRIP_X0 * 4u;
    for (i = 0; i < GBP_VWITNESS_WORDS; i++) {
        w->staged[i] = (uint16_t)(((uint16_t)p[1] << 8) | (uint16_t)p[3]);
        p += 4u;
    }
    w->staged_valid = 1u;
    w->blocks_staged++;
    return 0;
}

int gbp_vwitness_place(struct gbp_vwitness *w, uint32_t index)
{
    uint16_t *dst;
    uint32_t i;
    if (!w || !w->store) return -1;
    if (!w->staged_valid) return -1;
    w->staged_valid = 0u;
    if (index >= GBP_VWITNESS_MAX_BLOCKS) {
        /* The assembler may accumulate up to 48 blocks before it gives up an
         * anchor; only the first 40 can be canonical. A block past the geometry
         * is COUNTED and dropped — never folded into a block it is not. */
        w->blocks_out_of_range++;
        return -1;
    }
    if (index >= GBP_VWITNESS_BLOCKS) {
        w->blocks_out_of_range++;
        return -1;
    }
    /* FIRST-RECORD INVARIANT. The window opens at a block-0 boundary, so the
     * very first scientific placement must be record 0, block 0 with an empty
     * scratch. A start anywhere else would make record 0 partial by
     * construction, which is exactly the defect this design exists to remove. */
    if (w->n == 0u && w->scratch_present == 0u && index != 0u) {
        w->blocks_out_of_range++;
        return -1;
    }
    dst = w->scratch + (size_t)index * GBP_VWITNESS_WORDS;
    for (i = 0; i < GBP_VWITNESS_WORDS; i++) dst[i] = w->staged[i];
    if (!(w->scratch_present & ((uint64_t)1u << index))) w->scratch_blocks++;
    w->scratch_present |= (uint64_t)1u << index;
    w->blocks_placed++;
    return 0;
}

int gbp_vwitness_commit(struct gbp_vwitness *w, const struct gbp_vwitness_meta *meta)
{
    struct gbp_vwitness_meta *m;
    uint16_t *dst;
    uint32_t i, pop = 0u;
    if (!w || !w->store || !meta) return -1;
    /* A warm-up frame consumes no record capacity and does not count toward the
     * target. `frames_seen` is the SCIENTIFIC population only; the warm-up has
     * its own counters so the transient stays visible (§V5.44.5). */
    if (w->qual_state != GBP_VWITNESS_QUAL_ARMED) { clear_scratch(w); return 0; }
    w->frames_seen++;
    if (w->n >= w->cap) {
        /* Nothing is overwritten and no record is rotated out: the oldest
         * witness is evidence too. This is the INCONCLUSIVE path by contract. */
        w->store_full = 1u;
        clear_scratch(w);
        return 0;
    }
    dst = w->store + (size_t)w->n * GBP_VWITNESS_FRAME_WORDS;
    for (i = 0; i < GBP_VWITNESS_FRAME_WORDS; i++) dst[i] = w->scratch[i];
    for (i = 0; i < GBP_VWITNESS_BLOCKS; i++)
        if (w->scratch_present & ((uint64_t)1u << i)) pop++;
    m = &w->meta[w->n];
    m->frame_index = meta->frame_index;
    m->t_first_block = meta->t_first_block;
    m->t_last_block = meta->t_last_block;
    m->blocks = meta->blocks;
    m->flags = meta->flags;
    m->completeness = meta->completeness;
    m->disagreements = meta->disagreements;
    m->present = w->scratch_present;
    m->blocks_captured = pop;
    if (w->n == 0u) w->t_first_record = meta->t_first_block;
    w->t_last_record = meta->t_last_block;
    w->n++;
    if (w->n >= w->target) w->target_reached = 1u;
    clear_scratch(w);
    return 1;
}

void gbp_vwitness_discard(struct gbp_vwitness *w)
{
    if (!w) return;
    if (w->scratch_blocks) w->frames_discarded++;
    clear_scratch(w);
}

void gbp_vwitness_note_ticks(struct gbp_vwitness *w, uint32_t ticks)
{
    if (!w || ticks == 0u) return;
    if (ticks < w->copy_ticks_min) w->copy_ticks_min = ticks;
    if (ticks > w->copy_ticks_max) w->copy_ticks_max = ticks;
    if (w->copy_ticks_sum <= 0xFFFFFFFFFFFFFFFFull - ticks) w->copy_ticks_sum += ticks;
    if (w->copy_ticks_n != 0xFFFFFFFFu) w->copy_ticks_n++;
}

uint32_t gbp_vwitness_copy_ticks_mean(const struct gbp_vwitness *w)
{
    if (!w || w->copy_ticks_n == 0u) return 0u;
    return (uint32_t)(w->copy_ticks_sum / w->copy_ticks_n);
}

int gbp_vwitness_target_reached(const struct gbp_vwitness *w)
{
    return (w && w->target_reached) ? 1 : 0;
}

int gbp_vwitness_store_full(const struct gbp_vwitness *w)
{
    return (w && w->store_full) ? 1 : 0;
}

const uint16_t *gbp_vwitness_record(const struct gbp_vwitness *w, uint32_t i)
{
    if (!w || !w->store || i >= w->n) return 0;
    return w->store + (size_t)i * GBP_VWITNESS_FRAME_WORDS;
}

const struct gbp_vwitness_meta *gbp_vwitness_meta_at(const struct gbp_vwitness *w, uint32_t i)
{
    if (!w || !w->meta || i >= w->n) return 0;
    return &w->meta[i];
}

uint16_t gbp_vwitness_word(const struct gbp_vwitness *w, uint32_t i, uint32_t block, uint32_t word)
{
    const uint16_t *r;
    if (block >= GBP_VWITNESS_BLOCKS || word >= GBP_VWITNESS_WORDS) return 0u;
    r = gbp_vwitness_record(w, i);
    if (!r) return 0u;
    return r[(size_t)block * GBP_VWITNESS_WORDS + word];
}
