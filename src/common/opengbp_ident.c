/*
 * opengbp_ident.c — see opengbp_ident.h
 */
#include "opengbp_ident.h"

/* Appends src to dst[0..cap) starting at *pos. Advances *pos by the full
 * length of src regardless of truncation (snprintf semantics). */
static void ident_append(char *dst, size_t cap, size_t *pos, const char *src)
{
    if (src == 0 || src[0] == '\0') {
        src = OPENGBP_IDENT_UNKNOWN;
    }
    for (; *src != '\0'; ++src) {
        if (*pos + 1u < cap) {
            dst[*pos] = *src;
        }
        ++*pos;
    }
}

size_t opengbp_ident_format(char *dst, size_t cap, const struct opengbp_ident *id)
{
    size_t pos = 0u;
    const char *app = 0;
    const char *build_id = 0;
    const char *commit = 0;

    if (id != 0) {
        app = id->app;
        build_id = id->build_id;
        commit = id->commit;
    }

    ident_append(dst, cap, &pos, "app=");
    ident_append(dst, cap, &pos, app);
    ident_append(dst, cap, &pos, " build=");
    ident_append(dst, cap, &pos, build_id);
    ident_append(dst, cap, &pos, " commit=");
    ident_append(dst, cap, &pos, commit);

    if (cap > 0u) {
        dst[pos < cap ? pos : cap - 1u] = '\0';
    }
    return pos;
}
