#include "sdlog.h"

#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <errno.h>
#include <fat.h>
#include <sdcard/gcsd.h>

int sdlog_save(const char *test_id, const char *build_id, const char *commit,
               const char *extra_header, const struct ringlog *rl,
               char *status, size_t status_cap, char *path_out, size_t path_cap)
{
    FILE *f;
    size_t i;
    char path[128];

    /* SD2SP2 sits on serial port 2 = EXI channel 2 (__io_gcsd2). */
    if (!fatMountSimple("sd", &__io_gcsd2)) {
        snprintf(status, status_cap, "SD mount failed (no SD2SP2 / no card / not FAT)");
        return -1;
    }
    mkdir("sd:/open-gbp", 0777);   /* ignore EEXIST */
    snprintf(path, sizeof path, "sd:/open-gbp/%s_%s.log", test_id, build_id);
    f = fopen(path, "w");
    if (!f) {
        snprintf(status, status_cap, "open %s failed errno=%d", path, errno);
        fatUnmount("sd");
        return -2;
    }
    fprintf(f, "# OPENGBP-LOG v1\n");
    fprintf(f, "test_id=%s\nbuild_id=%s\ncommit=%s\n", test_id, build_id, commit);
    if (extra_header && *extra_header) fprintf(f, "%s\n", extra_header);
    fprintf(f, "lines=%u dropped=%u truncated=%u\n", (unsigned)rl->count, (unsigned)rl->dropped,
            (unsigned)rl->truncated);
    fprintf(f, "# --- records ---\n");
    for (i = 0; i < rl->count; i++) {
        fprintf(f, "%s\n", ringlog_line(rl, i));
    }
    fprintf(f, "# --- end --- dropped=%u\n", (unsigned)rl->dropped);
    if (fclose(f) != 0) {
        snprintf(status, status_cap, "close failed errno=%d", errno);
        fatUnmount("sd");
        return -3;
    }
    fatUnmount("sd");
    snprintf(status, status_cap, "saved %u lines to %s", (unsigned)rl->count, path);
    if (path_out && path_cap) { strncpy(path_out, path, path_cap - 1); path_out[path_cap - 1] = '\0'; }
    return 0;
}

int sdlog_save_blob(const char *test_id, const char *build_id, const char *suffix,
                    const uint8_t *data, size_t len,
                    char *status, size_t status_cap, char *path_out, size_t path_cap)
{
    FILE *f;
    size_t n;
    char path[128];

    if (!fatMountSimple("sd", &__io_gcsd2)) {
        snprintf(status, status_cap, "SD mount failed (no SD2SP2 / no card / not FAT)");
        return -1;
    }
    mkdir("sd:/open-gbp", 0777);   /* ignore EEXIST */
    snprintf(path, sizeof path, "sd:/open-gbp/%s_%s%s", test_id, build_id, suffix);
    f = fopen(path, "wb");
    if (!f) {
        snprintf(status, status_cap, "open %s failed errno=%d", path, errno);
        fatUnmount("sd");
        return -2;
    }
    n = fwrite(data, 1, len, f);
    if (fclose(f) != 0) {
        snprintf(status, status_cap, "close failed errno=%d", errno);
        fatUnmount("sd");
        return -3;
    }
    fatUnmount("sd");
    if (n != len) {
        snprintf(status, status_cap, "short write %u/%u bytes to %s", (unsigned)n, (unsigned)len, path);
        return -4;
    }
    snprintf(status, status_cap, "saved %u bytes to %s", (unsigned)len, path);
    if (path_out && path_cap) { strncpy(path_out, path, path_cap - 1); path_out[path_cap - 1] = '\0'; }
    return 0;
}
