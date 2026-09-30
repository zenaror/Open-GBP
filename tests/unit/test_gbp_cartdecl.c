/*
 * tests/unit/test_gbp_cartdecl.c -- GitHub Issue #153, HARDWARE_TESTS.md V31.4: the cartridge declaration's list, its step and its one log line.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_cartdecl.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) { failures++; printf("  FAIL: %s: got %lld, want %lld\n", what, got, want); }
}

static void eqs(const char *got, const char *want, const char *what)
{
    checks++;
    if (strcmp(got, want) != 0) { failures++; printf("  FAIL: %s:\n    got  %s\n    want %s\n", what, got, want); }
}

static void check(int cond, const char *what)
{
    checks++;
    if (!cond) { failures++; printf("  FAIL: %s\n", what); }
}

static void test_the_list(void)
{
    uint32_t i;
    eqi(gbp_cartdecl_count(), 8, "eight entries: UNDECLARED, the three titles of the first session, three more GBA titles, and 'other'");
    eqs(gbp_cartdecl_entry_at(0u)->form, "UNDECLARED", "the first entry is UNDECLARED (the default)");
    eqs(gbp_cartdecl_entry_at(1u)->title, "Yoshi's Island (SMA3) on the EZ-Flash Omega DE NOR", "entry 1: the known control");
    eqs(gbp_cartdecl_entry_at(1u)->form, "FLASHCART_DELIVERED", "a ROM on the flashcart's NOR");
    eqs(gbp_cartdecl_entry_at(2u)->title, "Kingdom Hearts: Chain of Memories (JP)", "entry 2");
    eqs(gbp_cartdecl_entry_at(2u)->form, "ORIGINAL", "his word: original");
    eqs(gbp_cartdecl_entry_at(3u)->form, "UNOFFICIAL", "Road Rage: his word 'paralelo'");
    check(gbp_cartdecl_entry_at(gbp_cartdecl_count()) == NULL, "out of range is NULL");
    for (i = 0u; i < gbp_cartdecl_count(); i++) {
        const struct gbp_cartdecl_entry *e = gbp_cartdecl_entry_at(i);
        check(strlen(e->title) <= 60u && strchr(e->title, '"') == NULL, "a title fits the log line and holds no double quote");
        check(!strcmp(e->form, "ORIGINAL") || !strcmp(e->form, "UNOFFICIAL") || !strcmp(e->form, "FLASHCART_DELIVERED") || !strcmp(e->form, "UNDECLARED"),
              "the form is one of the four values of V31.4");
    }
}

static void test_the_step_wraps(void)
{
    const uint32_t n = gbp_cartdecl_count();
    eqi(gbp_cartdecl_step(0u, 1), 1, "right from 0");
    eqi(gbp_cartdecl_step(n - 1u, 1), 0, "right wraps to 0");
    eqi(gbp_cartdecl_step(0u, -1), (long long)n - 1, "left wraps to the last");
    eqi(gbp_cartdecl_step(3u, 0), 3, "no direction: unchanged");
    eqi(gbp_cartdecl_step(n + 5u, 1), 1, "an out-of-range index is UNDECLARED first");
}

static void test_the_line(void)
{
    char b[256];
    gbp_cartdecl_fmt(b, sizeof b, 2u, 1);
    eqs(b, "CARTDECL idx=2 title=\"Kingdom Hearts: Chain of Memories (JP)\" form=ORIGINAL mode=GBA entered=pad_selection_after_session", "a confirmed selection");
    gbp_cartdecl_fmt(b, sizeof b, 2u, 0);
    eqs(b, "CARTDECL idx=0 title=\"UNDECLARED (nothing selected)\" form=UNDECLARED mode=GBA entered=none",
        "an unconfirmed selection saves as UNDECLARED whatever was stepped to");
    gbp_cartdecl_fmt(b, sizeof b, 99u, 1);
    eqs(b, "CARTDECL idx=0 title=\"UNDECLARED (nothing selected)\" form=UNDECLARED mode=GBA entered=pad_selection_after_session",
        "an out-of-range confirmed index is UNDECLARED, and the Operator did press A");
    check(strlen(b) < 248u, "fits the log line");
}

int main(void)
{
    test_the_list();
    test_the_step_wraps();
    test_the_line();
    printf("test_gbp_cartdecl: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
