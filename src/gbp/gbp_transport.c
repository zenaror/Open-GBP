#include "gbp_transport.h"

uint32_t gbp_internal_size_from_arinfo(uint16_t arinfo)
{
    switch (arinfo & 7u) {
    case 0: return 0x00200000u;
    case 1: return 0x00400000u;
    case 2: return 0x00800000u;
    case 3: return 0x01000000u;
    case 4: return 0x02000000u;
    default: return 0u;
    }
}

uint16_t gbp_arinfo_with_expansion(uint16_t arinfo, unsigned code)
{
    return (uint16_t)((arinfo & (uint16_t)~0x0038u) | (uint16_t)((code & 7u) << 3));
}

uint32_t gbp_block_addr(uint32_t base, unsigned index, uint32_t offset)
{
    if (index > 15u || (offset & (GBP_BLOCK_SIZE - 1u)) != 0u || offset >= 0x100000u) {
        return 0u;
    }
    return base + ((uint32_t)index << 20) + offset;
}

const char *gbp_status_name(gbp_status s)
{
    switch (s) {
    case GBP_OK: return "ok";
    case GBP_ERR_TIMEOUT: return "timeout";
    case GBP_ERR_BUSY: return "busy";
    case GBP_ERR_PARAM: return "param";
    case GBP_ERR_BACKEND: return "backend";
    default: return "?";
    }
}
