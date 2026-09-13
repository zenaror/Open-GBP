/*
 * Host-side unit test for src/common/opengbp_ident.c
 *
 * Deliberately dependency-free: a tiny CHECK macro and a nonzero exit code
 * on failure so it can run under make on any host with a C compiler.
 */
#include <stdio.h>
#include <string.h>

#include "opengbp_ident.h"

static int failures = 0;
static int checks = 0;

#define CHECK(cond)                                                     \
    do {                                                                \
        ++checks;                                                       \
        if (!(cond)) {                                                  \
            ++failures;                                                 \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
        }                                                               \
    } while (0)

static void test_basic_format(void)
{
    const struct opengbp_ident id = { "smoke-test", "smoke-0001", "a982fb7" };
    char buf[OPENGBP_IDENT_MAX];
    const char *expect = "app=smoke-test build=smoke-0001 commit=a982fb7";
    size_t n = opengbp_ident_format(buf, sizeof buf, &id);

    CHECK(n == strlen(expect));
    CHECK(strcmp(buf, expect) == 0);
}

static void test_null_fields_become_unknown(void)
{
    const struct opengbp_ident id = { "x", 0, "" };
    char buf[OPENGBP_IDENT_MAX];
    const char *expect = "app=x build=unknown commit=unknown";

    opengbp_ident_format(buf, sizeof buf, &id);
    CHECK(strcmp(buf, expect) == 0);
}

static void test_null_ident(void)
{
    char buf[OPENGBP_IDENT_MAX];
    const char *expect = "app=unknown build=unknown commit=unknown";

    opengbp_ident_format(buf, sizeof buf, 0);
    CHECK(strcmp(buf, expect) == 0);
}

static void test_truncation_is_safe(void)
{
    const struct opengbp_ident id = { "smoke-test", "smoke-0001", "a982fb7" };
    char buf[12];
    size_t n;

    memset(buf, 'X', sizeof buf);
    n = opengbp_ident_format(buf, sizeof buf, &id);

    CHECK(n == strlen("app=smoke-test build=smoke-0001 commit=a982fb7"));
    CHECK(buf[sizeof buf - 1] == '\0');
    CHECK(strcmp(buf, "app=smoke-t") == 0);
}

static void test_zero_capacity(void)
{
    const struct opengbp_ident id = { "a", "b", "c" };
    size_t n = opengbp_ident_format(0, 0, &id);

    CHECK(n == strlen("app=a build=b commit=c"));
}

static void test_capacity_one(void)
{
    const struct opengbp_ident id = { "a", "b", "c" };
    char buf[1] = { 'X' };

    opengbp_ident_format(buf, sizeof buf, &id);
    CHECK(buf[0] == '\0');
}

int main(void)
{
    test_basic_format();
    test_null_fields_become_unknown();
    test_null_ident();
    test_truncation_is_safe();
    test_zero_capacity();
    test_capacity_one();

    printf("test_ident: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
