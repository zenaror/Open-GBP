/* F8 negative control 2: the equivalent forbidden CALL, which the text audit has
 * always caught (R_PPC_REL24 fopen inside gbp_vwitness_note_frame). It must stay
 * caught after the data-relocation model was added. */
#include <stdio.h>
unsigned gbp_vwitness_note_frame(unsigned streak, int complete)
{
    FILE *f = fopen("witness.bin", "wb");
    if (f)
        fclose(f);
    return complete ? streak + 1u : 0u;
}
