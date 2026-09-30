/*
 * test_gbp_control_policy.c -- Issue #145 (Phase 7's E2): the CONTROL comparison ignores bit 0x01 and is strict on the
 * other seven. THE REAL FUNCTIONS: gbp_control_agrees, gbp_initirqa_snapshot_control_agrees,
 * gbp_irq_service_preunmask_check and gbp_initirqa_note_control_tolerance -- nothing here re-implements them; the
 * expected values are written as literals or as the spec's own arithmetic (a mask of 0xFE), never as a call of the code
 * under test. SYNTHETIC: no physical evidence.
 *
 * Modes:  test_gbp_control_policy
 *         test_gbp_control_policy --verdicts   reads records on stdin, prints the verdicts of the real code (the host
 *                                              test tests/host/test_control_policy_replay.py feeds it the archive):
 *             snap EXP VOTE B1F                 -> "NEW OLD"      the snapshot check against the pre-policy expression
 *             pre  EXP VOTE B1F IRQD IRQG       -> "OK|FAIL why"  the real gbp_irq_service_preunmask_check (vstate masks)
 *             restore ORIG READBACK             -> "NEW OLD"      the restore read-back against the pre-policy expression
 *         every number is hexadecimal.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gbp_initirqa_probe.h"
#include "gbp_irq_service.h"
#include "gbp_control_policy.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

/* the pre-policy expressions, written out (the OLD code compared the two bytes for equality) */
static int old_snapshot_agrees(uint8_t vote, uint8_t b1f, uint8_t exp) { return !(vote != exp || vote != b1f); }

static void test_truth_table(void)
{
    unsigned r, e;
    printf("-- every (read, expected) pair against the spec: equal on all bits but 0x01\n");
    for (r = 0; r < 256u; r++) {
        for (e = 0; e < 256u; e++) {
            const int want_agree = ((r & 0xFEu) == (e & 0xFEu));
            const int want_exercised = want_agree && (r != e);
            CHECK(gbp_control_agrees((uint8_t)r, (uint8_t)e) == want_agree);
            CHECK(gbp_control_tolerance_exercised((uint8_t)r, (uint8_t)e) == want_exercised);
            CHECK(gbp_control_agrees((uint8_t)r, (uint8_t)e) == gbp_control_agrees((uint8_t)e, (uint8_t)r));
        }
    }
}

static void test_the_seven_strict_bits(void)
{
    unsigned e, b;
    printf("-- each of the seven other bits, from every expected byte, on its own and with 0x01\n");
    CHECK(GBP_CONTROL_TOLERATED_MASK == 0x01u);                       /* widening it is a decision: this line and the next fail */
    for (e = 0; e < 256u; e++) {
        CHECK(gbp_control_agrees((uint8_t)(e ^ 0x01u), (uint8_t)e));
        CHECK(gbp_control_tolerance_exercised((uint8_t)(e ^ 0x01u), (uint8_t)e));
        CHECK(!gbp_control_tolerance_exercised((uint8_t)e, (uint8_t)e));            /* equal is not "exercised" */
        for (b = 1; b < 8u; b++) {
            CHECK(!gbp_control_agrees((uint8_t)(e ^ (1u << b)), (uint8_t)e));
            CHECK(!gbp_control_agrees((uint8_t)(e ^ 0x01u ^ (1u << b)), (uint8_t)e));   /* the tolerance hides no second bit */
            CHECK(!gbp_control_tolerance_exercised((uint8_t)(e ^ (1u << b)), (uint8_t)e));
        }
    }
}

static void test_snapshot_level(void)
{
    struct gbp_initirqa_snapshot s;
    unsigned b;
    const uint8_t exp = 0x8e;
    printf("-- the snapshot check: the two READINGS must agree on every bit, the byte expected only up to 0x01\n");
    memset(&s, 0, sizeof s);
    s.control_vote = exp; s.control_b1f = exp;
    CHECK(gbp_initirqa_snapshot_control_agrees(&s, exp));
    s.control_vote = 0x8f; s.control_b1f = 0x8f;                      /* the GB/GBC case, both readings say 0x8f */
    CHECK(gbp_initirqa_snapshot_control_agrees(&s, exp));
    CHECK(!old_snapshot_agrees(s.control_vote, s.control_b1f, exp));   /* the old expression refused exactly this */
    s.control_vote = 0x8f; s.control_b1f = 0x8e;                      /* readings disagree, in the tolerated bit only */
    CHECK(!gbp_initirqa_snapshot_control_agrees(&s, exp));
    s.control_vote = 0x8e; s.control_b1f = 0x8f;
    CHECK(!gbp_initirqa_snapshot_control_agrees(&s, exp));
    for (b = 1; b < 8u; b++) {
        s.control_vote = (uint8_t)(exp ^ (1u << b)); s.control_b1f = s.control_vote;
        CHECK(!gbp_initirqa_snapshot_control_agrees(&s, exp));
    }
}

static struct gbp_initirqa_snapshot valid_preunmask(uint8_t vote)
{
    struct gbp_initirqa_snapshot s;
    memset(&s, 0, sizeof s);
    s.pi_ok = 1; s.pi2_ok = 1;
    s.control_rc = GBP_OK; s.irq_rc = GBP_OK;
    s.intsr = 0x2000u; s.intsr2 = 0x2000u;        /* cause latched: INTSR bit 13 */
    s.intmr = 0u; s.intmr2 = 0u;                  /* not unmasked */
    s.control_vote = vote; s.control_b1f = vote;
    s.irq_gbi = 0x0500u; s.irq_disc = 0x0500u;
    return s;
}

static void test_the_real_preunmask_check(void)
{
    const uint8_t exp = 0x8e;
    const char *why = 0;
    unsigned b;
    struct gbp_initirqa_snapshot s;
    printf("-- gbp_irq_service_preunmask_check, the real function, one bit at a time\n");
    s = valid_preunmask(exp);
    CHECK(gbp_irq_service_preunmask_check(&s, exp, 0x0555u, 0x0AAAu, 0x8000u, 0x7000u, 0u, 0u, &why) == 1);
    s = valid_preunmask(0x8f);
    CHECK(gbp_irq_service_preunmask_check(&s, exp, 0x0555u, 0x0AAAu, 0x8000u, 0x7000u, 0u, 0u, &why) == 1);
    for (b = 1; b < 8u; b++) {
        s = valid_preunmask((uint8_t)(exp ^ (1u << b)));
        why = 0;
        CHECK(gbp_irq_service_preunmask_check(&s, exp, 0x0555u, 0x0AAAu, 0x8000u, 0x7000u, 0u, 0u, &why) == 0);
        CHECK(why && strcmp(why, "control_changed") == 0);
        s = valid_preunmask((uint8_t)(exp ^ 0x01u ^ (1u << b)));
        why = 0;
        CHECK(gbp_irq_service_preunmask_check(&s, exp, 0x0555u, 0x0AAAu, 0x8000u, 0x7000u, 0u, 0u, &why) == 0);
        CHECK(why && strcmp(why, "control_changed") == 0);
    }
    /* the CONTROL clause is one clause of several: a good CONTROL byte does not rescue a bad IRQ state */
    s = valid_preunmask(0x8f); s.irq_gbi = 0x0400u; s.irq_disc = 0x0401u;
    why = 0;
    CHECK(gbp_irq_service_preunmask_check(&s, exp, 0x0555u, 0x0AAAu, 0x8000u, 0x7000u, 0u, 0u, &why) == 0);
    CHECK(why && strcmp(why, "semantic_disagree") == 0);
}

static void test_the_note(void)
{
    struct gbp_initirqa_result a;
    printf("-- gbp_initirqa_note_control_tolerance: counts only the tolerated case, keeps the first\n");
    memset(&a, 0, sizeof a);
    gbp_initirqa_note_control_tolerance(&a, "X", 0x8e, 0x8e);
    gbp_initirqa_note_control_tolerance(&a, "X", 0x8c, 0x8e);        /* a strict difference is not a tolerated comparison */
    CHECK(a.control_tol_n == 0u && a.control_tol_first_site[0] == '\0');
    gbp_initirqa_note_control_tolerance(&a, "PREUNMASK", 0x8f, 0x8e);
    gbp_initirqa_note_control_tolerance(&a, "POSTACK", 0x8f, 0x8e);
    CHECK(a.control_tol_n == 2u);
    CHECK(strcmp(a.control_tol_first_site, "PREUNMASK") == 0 && a.control_tol_first_vote == 0x8f && a.control_tol_first_exp == 0x8e);
    a.control_tol_n = 0xFFFFFFFFu;
    gbp_initirqa_note_control_tolerance(&a, "P", 0x8f, 0x8e);
    CHECK(a.control_tol_n == 0xFFFFFFFFu);                            /* saturates, never wraps to "never happened" */
}

static int verdicts(void)
{
    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        unsigned a, b, c, d, e;
        if (sscanf(line, "snap %x %x %x", &a, &b, &c) == 3) {
            struct gbp_initirqa_snapshot s;
            memset(&s, 0, sizeof s);
            s.control_vote = (uint8_t)b; s.control_b1f = (uint8_t)c;
            printf("%d %d\n", gbp_initirqa_snapshot_control_agrees(&s, (uint8_t)a), old_snapshot_agrees((uint8_t)b, (uint8_t)c, (uint8_t)a));
        } else if (sscanf(line, "pre %x %x %x %x %x", &a, &b, &c, &d, &e) == 5) {
            struct gbp_initirqa_snapshot s = valid_preunmask((uint8_t)b);
            const char *why = "-";
            int ok;
            s.control_b1f = (uint8_t)c; s.irq_disc = (uint16_t)d; s.irq_gbi = (uint16_t)e;
            ok = gbp_irq_service_preunmask_check(&s, (uint8_t)a, 0x0555u, 0x0AAAu, 0x8000u, 0x7000u, 0u, 0u, &why);
            printf("%s %s\n", ok ? "OK" : "FAIL", why);
        } else if (sscanf(line, "restore %x %x", &a, &b) == 2) {
            printf("%d %d\n", gbp_control_agrees((uint8_t)b, (uint8_t)a), (uint8_t)b == (uint8_t)a);
        } else {
            printf("?\n");
        }
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "--verdicts") == 0) return verdicts();
    test_truth_table();
    test_the_seven_strict_bits();
    test_snapshot_level();
    test_the_real_preunmask_check();
    test_the_note();
    printf("test_gbp_control_policy: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
