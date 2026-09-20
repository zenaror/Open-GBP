#!/bin/sh
# tools/audit_listings.sh <build/poc/NAME> <NAME>  -- runs INSIDE the project container.
#
# Produces, for every object the POC linked, the two listings tools/poc_audit.py
# audits: `<object>.objdump.txt` (objdump -dr: the code with its TEXT relocations
# interleaved) and `<object>.reloc.txt` (objdump -r: EVERY relocation section,
# which is where a forbidden symbol reached from a data initialiser becomes
# visible -- F8, HARDWARE_TESTS §V5.59), plus `elf.nm.txt`, the linked ELF's
# symbol table. The top-level Makefile runs this only when the ELF is newer than
# the listings (F3), so an audit never reads a stale disassembly.
set -eu
out="$1"; app="$2"
test -d "$out/obj" || { echo "audit_listings: no $out/obj -- the POC was not built" >&2; exit 1; }
test -f "$out/$app.elf" || { echo "audit_listings: no $out/$app.elf" >&2; exit 1; }
mkdir -p "$out/audit"
rm -f "$out"/audit/*.objdump.txt "$out"/audit/*.reloc.txt "$out/audit/elf.nm.txt"
for o in "$out"/obj/*.o; do
    b=$(basename "$o" .o)
    powerpc-eabi-objdump -dr "$o" > "$out/audit/$b.objdump.txt"
    powerpc-eabi-objdump -r "$o" > "$out/audit/$b.reloc.txt"
done
powerpc-eabi-nm "$out/$app.elf" > "$out/audit/elf.nm.txt"
