// OpenGbpFunc.java — decompile selected functions and list constant call
// arguments at call sites of selected targets. Headless, reproducible.
//
//   -postScript OpenGbpFunc.java <outdir> decomp   <addr> [<addr>...]
//   -postScript OpenGbpFunc.java <outdir> callsites <addr> [<addr>...]
//   -postScript OpenGbpFunc.java <outdir> refs      <addr> [<addr>...]
//
// refs:      for each address (code or data), appends one TSV line per
//            incoming reference: target  from  function  reftype
//            to <outdir>/<program>/refs.tsv.
//
// decomp:    writes <outdir>/<program>/decomp/<addr>_<name>.c with the
//            decompiled C plus a header listing callers and callees.
// callsites: for every call to each target, writes one TSV line:
//            target  caller  callsite  arg0 arg1 ... (constants as 0x..,
//            other operands as a short varnode description)
//            to <outdir>/<program>/callsites.tsv (appends).
//
// Decompiled output derived from proprietary binaries must stay in an
// ignored/private directory (build/ or input/).
//@category OpenGBP
import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.pcode.*;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.*;

public class OpenGbpFunc extends GhidraScript {

    private DecompInterface decomp;

    private DecompileResults decompile(Function f) {
        return decomp.decompileFunction(f, 120, new ConsoleTaskMonitor());
    }

    private String vn(Varnode v, HighFunction hf) {
        if (v == null) return "?";
        if (v.isConstant()) return String.format("0x%X", v.getOffset());
        if (v.isAddress()) return "mem:" + v.getAddress();
        HighVariable hv = v.getHigh();
        if (hv != null && hv.getName() != null) return hv.getName();
        if (v.isRegister()) {
            var reg = currentProgram.getRegister(v.getAddress(), v.getSize());
            return reg != null ? reg.getName() : "reg";
        }
        return "var";
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 3) {
            printerr("usage: OpenGbpFunc.java <outdir> decomp|callsites <addr>...");
            return;
        }
        File out = new File(args[0], currentProgram.getName());
        out.mkdirs();
        decomp = new DecompInterface();
        decomp.toggleCCode(true);
        decomp.toggleSyntaxTree(true);
        decomp.setSimplificationStyle("decompile");
        decomp.openProgram(currentProgram);

        String mode = args[1];
        for (int i = 2; i < args.length; i++) {
            Address a = toAddr(Long.parseLong(args[i].replace("0x", ""), 16));
            if (mode.equals("refs")) {
                try (PrintWriter w = new PrintWriter(new FileWriter(new File(out, "refs.tsv"), true))) {
                    for (ghidra.program.model.symbol.Reference r : getReferencesTo(a)) {
                        Function ff = getFunctionContaining(r.getFromAddress());
                        w.printf("%s\t%s\t%s\t%s%n", a, r.getFromAddress(),
                                ff == null ? "-" : ff.getName() + "@" + ff.getEntryPoint(), r.getReferenceType());
                    }
                }
                println("refs " + a);
                continue;
            }
            Function f = getFunctionContaining(a);
            if (f == null && mode.equals("decomp")) {
                // e.g. an interrupt handler only reached through a function
                // pointer: define it on the fly (analysis is not re-run).
                f = createFunction(a, null);
                if (f != null) println("created function at " + a);
            }
            if (f == null) {
                printerr("no function at " + a);
                continue;
            }
            if (mode.equals("decomp")) {
                File dir = new File(out, "decomp");
                dir.mkdirs();
                DecompileResults res = decompile(f);
                try (PrintWriter w = new PrintWriter(new File(dir, f.getEntryPoint() + "_" + f.getName() + ".c"))) {
                    w.println("// " + currentProgram.getName() + " " + f.getName() + " @ " + f.getEntryPoint()
                            + " size=" + f.getBody().getNumAddresses());
                    w.print("// callers:");
                    for (Function c : f.getCallingFunctions(monitor)) w.print(" " + c.getName() + "@" + c.getEntryPoint());
                    w.println();
                    w.print("// callees:");
                    for (Function c : f.getCalledFunctions(monitor)) w.print(" " + c.getName() + "@" + c.getEntryPoint());
                    w.println();
                    if (res.decompileCompleted()) {
                        w.println(res.getDecompiledFunction().getC());
                    } else {
                        w.println("// DECOMPILE FAILED: " + res.getErrorMessage());
                    }
                }
                println("decomp " + f.getName());
            } else if (mode.equals("callsites")) {
                try (PrintWriter w = new PrintWriter(new FileWriter(new File(out, "callsites.tsv"), true))) {
                    for (Function caller : f.getCallingFunctions(monitor)) {
                        DecompileResults res = decompile(caller);
                        if (!res.decompileCompleted()) {
                            w.printf("%s@%s\t%s@%s\t?\tDECOMPILE_FAILED%n", f.getName(), f.getEntryPoint(),
                                    caller.getName(), caller.getEntryPoint());
                            continue;
                        }
                        HighFunction hf = res.getHighFunction();
                        Iterator<PcodeOpAST> ops = hf.getPcodeOps();
                        while (ops.hasNext()) {
                            PcodeOpAST op = ops.next();
                            if (op.getOpcode() != PcodeOp.CALL) continue;
                            Varnode tgt = op.getInput(0);
                            if (tgt == null || !tgt.isAddress() || !tgt.getAddress().equals(f.getEntryPoint())) continue;
                            StringBuilder sb = new StringBuilder();
                            for (int k = 1; k < op.getNumInputs(); k++) {
                                sb.append('\t').append(vn(op.getInput(k), hf));
                            }
                            w.printf("%s@%s\t%s@%s\t%s%s%n", f.getName(), f.getEntryPoint(), caller.getName(),
                                    caller.getEntryPoint(), op.getSeqnum().getTarget(), sb);
                        }
                    }
                }
                println("callsites " + f.getName());
            }
        }
        decomp.dispose();
    }
}
