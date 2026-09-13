#include <stdio.h>
#include <string.h>
#include "ringlog.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

int main(void)
{
    static char storage[4 * 32];
    struct ringlog rl;
    char hex[9];
    uint8_t b[4] = { 0xDE, 0xAD, 0xBE, 0xEF };
    int r;

    ringlog_init(&rl, storage, 32, 4);
    CHECK(ringlog_line(&rl, 0) == 0);
    r = ringlog_printf(&rl, "hello %d", 1);
    CHECK(r == 0);
    CHECK(strcmp(ringlog_line(&rl, 0), "000000 hello 1") == 0);
    /* truncation: line_len 32 incl. NUL, prefix 7 */
    r = ringlog_printf(&rl, "%s", "0123456789012345678901234567890123456789");
    CHECK(r == 1);
    CHECK(rl.truncated == 1);
    CHECK(strlen(ringlog_line(&rl, 1)) == 31);
    ringlog_printf(&rl, "c");
    ringlog_printf(&rl, "d");
    CHECK(rl.count == 4);
    /* full: dropped, seq keeps counting */
    r = ringlog_printf(&rl, "e");
    CHECK(r == -1);
    CHECK(rl.dropped == 1);
    CHECK(rl.count == 4);
    CHECK(rl.seq == 5);
    CHECK(strcmp(ringlog_line(&rl, 3), "000003 d") == 0);
    CHECK(ringlog_line(&rl, 4) == 0);

    CHECK(strcmp(ringlog_hex(hex, sizeof hex, b, 4), "deadbeef") == 0);
    CHECK(strcmp(ringlog_hex(hex, 5, b, 4), "dead") == 0);   /* capacity-limited */

    /* uninitialized storage is tolerated */
    ringlog_init(&rl, 0, 0, 0);
    CHECK(ringlog_printf(&rl, "x") == -1);
    CHECK(rl.dropped == 1);

    printf("test_ringlog: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
