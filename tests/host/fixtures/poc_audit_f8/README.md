# poc_audit F8 negative controls — real PowerPC listings

Three tiny objects compiled with the project's own cross compiler and the stream
probe's flags, whose `objdump -dr` (text, with its relocations interleaved) and
`objdump -r` (every relocation section) listings are what `tools/poc_audit.py`
actually reads. `tests/host/test_poc_audit_data_reloc.py` audits them; nothing in
those tests matches C source strings.

```text
compiler   powerpc-eabi-gcc (devkitPPC) 16.1.0   (ghcr.io/extremscorner/libogc2:20260805)
flags      -std=gnu11 -g -O2 -Wall -Wextra -Wshadow -DGEKKO -mogc -mcpu=750 -meabi -mhard-float
produced   docker compose run --rm -T dev sh -c 'cd tests/host/fixtures/poc_audit_f8; \
             powerpc-eabi-gcc $FLAGS -c src/data_ref_fopen.c -o data_ref/gbp_vwitness.o; \
             powerpc-eabi-gcc $FLAGS -c src/call_fopen.c     -o call/gbp_vwitness.o; \
             powerpc-eabi-gcc $FLAGS -c src/addr_taken.c     -o addr_taken/gbp_initirqa_probe.o; \
             for each: powerpc-eabi-objdump -dr X.o > X.objdump.txt; powerpc-eabi-objdump -r X.o > X.reloc.txt'
```

| directory | source | what it proves |
|---|---|---|
| `data_ref/` | `src/data_ref_fopen.c` → `gbp_vwitness.o` | `fopen` reached ONLY from a data initialiser: `-dr` has no relocation to it, `-r` has `.sdata… R_PPC_ADDR32 fopen`. The pre-§V5.59 auditor could not see it (finding F8). |
| `call/` | `src/call_fopen.c` → `gbp_vwitness.o` | the equivalent CALL (`R_PPC_REL24 fopen` in text): always caught, still caught. |
| `addr_taken/` | `src/addr_taken.c` → `gbp_initirqa_probe.o` | exactly 3 + 2 pinned calls, plus the address of `gbp_regwrite_irq_u16` taken in a data table AND in text; neither may inflate the exact call-site count. |

The `.o` files are not kept; regenerate with the command above if the compiler
changes and record the new version here.
