/* F8 negative control 1 (HARDWARE_TESTS §V5.59): the forbidden filesystem symbol is
 * reached ONLY through a data initialiser -- a function pointer in a table. No
 * function calls it and no instruction takes its address, so the text disassembly
 * (objdump -dr) carries no relocation to fopen at all; only the .rodata/.data
 * relocation section does. Compiled as the stream probe's gbp_vwitness.o, an object
 * of the capture path that may reference memset and __udivdi3 and nothing else. */
#include <stdio.h>
typedef FILE *(*opener_fn)(const char *, const char *);
const opener_fn gbp_vwitness_openers[1] __attribute__((used)) = { fopen };
unsigned gbp_vwitness_note_frame(unsigned streak, int complete)
{
    return complete ? streak + 1u : 0u;
}
