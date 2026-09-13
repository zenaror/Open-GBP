// OpenGbpScan.java — Open-GBP headless Ghidra scan for a GameCube DOL.
//
// Produces a structured, reproducible report used for Phase 2 reference
// analysis. It does NOT dump code; it lists addresses, constants and
// cross-references so conclusions can be traced back to the binary.
//
// Usage (headless, after import+analysis):
//   analyzeHeadless <projdir> <proj> -process main.dol -noanalysis \
//       -scriptPath <repo>/tools/ghidra -postScript OpenGbpScan.java <outdir>
//
// Output files in <outdir>/<program-name>/:
//   functions.tsv     address  size  name
//   mmio_refs.tsv     references whose target is a hardware register
//                     (0x0C000000-0x0CFFFFFF phys / 0xCC000000-0xCCFFFFFF)
//   lis_consts.tsv    every `lis`/`addis` immediate in "interesting" ranges:
//                     0x0100-0x03FF (ARAM addresses 16MB-64MB = HSP window
//                     in Dolphin's model) with the following instructions of
//                     the same function that consume the register, so the
//                     full 32-bit constant and its use (call argument /
//                     load / store) can be judged.
//   strings.tsv       defined strings (address, value) — useful to spot
//                     debug messages naming subsystems.
//   summary.txt       counts.
//
//@category OpenGBP
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.StringDataInstance;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.*;

import java.io.File;
import java.io.PrintWriter;
import java.util.*;

public class OpenGbpScan extends GhidraScript {

    private static boolean isHwReg(long a) {
        long p = a & 0x0FFFFFFFL;
        return (a >= 0xCC000000L && a <= 0xCCFFFFFFL) || (p >= 0x0C000000L && p <= 0x0CFFFFFFL);
    }

    private String funcName(Address a) {
        Function f = getFunctionContaining(a);
        return f == null ? "-" : f.getName() + "@" + f.getEntryPoint();
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            printerr("usage: OpenGbpScan.java <outdir>");
            return;
        }
        File out = new File(args[0], currentProgram.getName());
        out.mkdirs();
        Listing listing = currentProgram.getListing();

        // --- functions ---------------------------------------------------
        int nfunc = 0;
        try (PrintWriter w = new PrintWriter(new File(out, "functions.tsv"))) {
            w.println("address\tsize\tname\tcalls_out\tcalled_by");
            FunctionIterator it = listing.getFunctions(true);
            while (it.hasNext()) {
                Function f = it.next();
                w.printf("%s\t%d\t%s\t%d\t%d%n", f.getEntryPoint(), f.getBody().getNumAddresses(),
                        f.getName(), f.getCalledFunctions(monitor).size(),
                        f.getCallingFunctions(monitor).size());
                nfunc++;
            }
        }

        // --- MMIO references --------------------------------------------
        int nmmio = 0;
        try (PrintWriter w = new PrintWriter(new File(out, "mmio_refs.tsv"))) {
            w.println("from\tfunction\tto\ttype\tmnemonic");
            ReferenceManager rm = currentProgram.getReferenceManager();
            ReferenceIterator ri = rm.getReferenceIterator(currentProgram.getMinAddress());
            while (ri.hasNext()) {
                Reference r = ri.next();
                long to = r.getToAddress().getOffset();
                if (!isHwReg(to)) continue;
                Instruction ins = listing.getInstructionAt(r.getFromAddress());
                w.printf("%s\t%s\t%08X\t%s\t%s%n", r.getFromAddress(), funcName(r.getFromAddress()),
                        to, r.getReferenceType(), ins == null ? "-" : ins.getMnemonicString());
                nmmio++;
            }
        }

        // --- lis constants ----------------------------------------------
        int nlis = 0;
        try (PrintWriter w = new PrintWriter(new File(out, "lis_consts.tsv"))) {
            w.println("address\tfunction\tmnemonic\treg\timm16\tfollowing");
            InstructionIterator ii = listing.getInstructions(true);
            while (ii.hasNext()) {
                Instruction ins = ii.next();
                String m = ins.getMnemonicString();
                if (!(m.equals("lis") || m.equals("addis"))) continue;
                if (ins.getNumOperands() < 2) continue;
                Object[] ops = ins.getOpObjects(ins.getNumOperands() - 1);
                Scalar sc = null;
                for (Object o : ops) if (o instanceof Scalar) sc = (Scalar) o;
                if (sc == null) continue;
                long imm = sc.getUnsignedValue() & 0xFFFF;
                boolean interesting = (imm >= 0x0100 && imm <= 0x03FF) || imm == 0xCC00 || imm == 0x0C00;
                if (!interesting) continue;
                String reg = ins.getDefaultOperandRepresentation(0);
                // Collect up to 6 following instructions in the same function that mention the reg.
                StringBuilder sb = new StringBuilder();
                Function f = getFunctionContaining(ins.getAddress());
                Instruction n = ins.getNext();
                for (int k = 0; k < 8 && n != null; k++, n = n.getNext()) {
                    if (f != null && !f.getBody().contains(n.getAddress())) break;
                    String txt = n.toString();
                    if (txt.contains(reg) || n.getFlowType().isCall()) {
                        if (sb.length() > 0) sb.append(" | ");
                        sb.append(n.getAddress()).append(": ").append(txt);
                        if (n.getFlowType().isCall()) break;
                    }
                }
                w.printf("%s\t%s\t%s\t%s\t%04X\t%s%n", ins.getAddress(), funcName(ins.getAddress()),
                        m, reg, imm, sb);
                nlis++;
            }
        }

        // --- strings ----------------------------------------------------
        int nstr = 0;
        try (PrintWriter w = new PrintWriter(new File(out, "strings.tsv"))) {
            w.println("address\tvalue");
            DataIterator di = listing.getDefinedData(true);
            while (di.hasNext()) {
                Data d = di.next();
                if (!(d.getDataType() instanceof ghidra.program.model.data.AbstractStringDataType)) continue;
                Object v = d.getValue();
                if (v == null) continue;
                String s = v.toString().replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r");
                if (s.length() < 4) continue;
                w.printf("%s\t%s%n", d.getAddress(), s);
                nstr++;
            }
        }

        try (PrintWriter w = new PrintWriter(new File(out, "summary.txt"))) {
            w.printf("program=%s%nimage_base=%s%nfunctions=%d%nmmio_refs=%d%nlis_consts=%d%nstrings=%d%n",
                    currentProgram.getName(), currentProgram.getImageBase(), nfunc, nmmio, nlis, nstr);
            for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
                w.printf("block\t%s\t%s\t%s\t%d%n", b.getName(), b.getStart(), b.getEnd(), b.getSize());
            }
        }
        println("OpenGbpScan: " + currentProgram.getName() + " functions=" + nfunc + " mmio_refs=" + nmmio
                + " lis=" + nlis + " strings=" + nstr + " -> " + out);
    }
}
