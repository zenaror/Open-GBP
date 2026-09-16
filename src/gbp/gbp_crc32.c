#include "gbp_crc32.h"

uint32_t gbp_crc32_init(void)
{
    return 0xFFFFFFFFu;
}

uint32_t gbp_crc32_update(uint32_t state, const uint8_t *data, size_t n)
{
    size_t i;
    unsigned k;
    for (i = 0; i < n; i++) {
        state ^= data[i];
        for (k = 0; k < 8; k++) state = (state >> 1) ^ (0xEDB88320u & (0u - (state & 1u)));
    }
    return state;
}

uint32_t gbp_crc32_final(uint32_t state)
{
    return state ^ 0xFFFFFFFFu;
}

uint32_t gbp_crc32(const uint8_t *data, size_t n)
{
    return gbp_crc32_final(gbp_crc32_update(gbp_crc32_init(), data, n));
}
