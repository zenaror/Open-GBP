/*
 * opengbp_ident.h — build identity formatting shared by GameCube targets
 * and host-side tests.
 *
 * This module is intentionally free of libogc/OS dependencies so the exact
 * same object code semantics can be verified on the development host.
 */
#ifndef OPENGBP_IDENT_H
#define OPENGBP_IDENT_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Maximum formatted length (including the terminating NUL) callers should
 * reserve. Longer inputs are truncated safely. */
#define OPENGBP_IDENT_MAX 128u

/* Text used in place of a NULL or empty field. */
#define OPENGBP_IDENT_UNKNOWN "unknown"

struct opengbp_ident {
    const char *app;      /* semantic application/POC name, e.g. "smoke-test" */
    const char *build_id; /* build identifier, e.g. "smoke-0001" */
    const char *commit;   /* short Git commit hash or "unknown" */
};

/*
 * Formats "app=<app> build=<build_id> commit=<commit>" into dst.
 *
 * Behaves like snprintf: returns the length of the complete string
 * (excluding NUL) even if it was truncated; always NUL-terminates when
 * cap > 0. dst may be NULL only when cap == 0.
 */
size_t opengbp_ident_format(char *dst, size_t cap, const struct opengbp_ident *id);

#ifdef __cplusplus
}
#endif

#endif /* OPENGBP_IDENT_H */
