"""tests/host/test_e5_breadth002_prereg.py -- GitHub Issue #160: the pre-registration of the second GBA breadth session on vehicle-0002 (HARDWARE_TESTS.md V32, the PHASE7_ENTRY
amendment, the DEVLOG entry, the HANDOFF paragraphs). Records only: nothing is built, pinned, staged or run.

Durable, append-only forms (no whole-file equality):
  * every block of HARDWARE_TESTS.md, DEVLOG.md and PHASE7_ENTRY.md as they stood at BASE (e1c063e) is found now, under a heading that starts with its heading, its body
    starting with its body of then (both heading levels); the HANDOFF only gained text (no line of BASE lost or changed); EVIDENCE.md: the evidence ids of BASE are a prefix of the current list and its blocks are found as at BASE (a later ingestion appends; the file is never compared whole);
  * V32 exists once, follows V31.13 in HARDWARE_TESTS.md, carries the subsections V32.1 ... V32.11 in order (each heading starting with its title), the identity of
    V31.13 (the DOL hash is the one V31.13 records), the CARTDECL titles of src/gbp/gbp_cartdecl.c at idx 1 / 4 / 5, the reader's constants (read from tools/playread.py), the
    rule sentence about a NOT MET row (V32.6 and V32.7), and the Operator's text of V32.9 and the request of V32.10 EXACTLY as frozen (the literals below are the Issue's);
  * tools/playread.py is the reader of BASE, byte for byte; tools/swiss-layout.tsv has no row 29 (to be amended on top by the hardware Issue's pin);
  * the HANDOFF and the DEVLOG carry the state, once, without citing the test id (the BREADTH family is not in TEST_FAMILIES), in HANDOFF and ROADMAP.
"""
import difflib
import hashlib
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import guards  # noqa: E402
import playread  # noqa: E402

BASE = "e1c063e16ed2c7917a452009ecaa287d642e237d"   # origin/main when Issue #160's records were written
HT, EV, DEVLOG, HANDOFF, P7 = ("docs/research/HARDWARE_TESTS.md", "docs/research/EVIDENCE.md", "docs/research/DEVLOG.md", "docs/HANDOFF.md",
                               "docs/research/PHASE7_ENTRY.md")
V32_HEAD = "## V32 — PHASE 7's E5 second breadth session and E7's first cartridge-hardware observation on `vehicle-0002`: `GBP-BREADTH-002`, RUN 64-66 (provisional numbers)"
SUBS = ("### V32.1 The questions", "### V32.2 Identity", "### V32.3 Titles, order, reasons, and the Operator's declaration",
        "### V32.4 The rival readings, written before the data", "### V32.5 The reader", "### V32.6 The gates, decided before the run",
        "### V32.7 The fallback rule and what follows a NOT MET", "### V32.8 Recorded, not judged",
        "### V32.9 The Operator's procedure and questions — FROZEN, in Portuguese, before the run",
        "### V32.10 The hardware test request, in `AGENTS.md` §14's format", "### V32.11 What this pre-registration does not do")
DOL = "02f89ccd1b07b10165d6d7b4287bf1b056a2a673661c89ad8e5b506fe56c55d8"
DEVLOG_HEAD = "## 2026-10-05 — Issue #160: GBP-BREADTH-002 "
P7_HEAD = "## Amendment — 2026-10-05 (Issue #160): E7's first observation rides E5's second session on `vehicle-0002`"
HANDOFF_BLOCKER = "**2026-10-05 (Issue #160), on top: the next physical Phase 7 session on `vehicle-0002` is PRE-REGISTERED"
HANDOFF_NEXT = "**2026-10-05 (Issue #160), on top: Issue #160 is done"
NOT_MET_RULE = ("A NOT MET row does NOT fail the boot and does NOT by itself block vehicle-0002's use in E6 / E7; it requires, BEFORE the next physical session with "
                "vehicle-0002, a diagnosis on paper in a checkpoint of its own.")

FROZEN_PT = """GBP-BREADTH-002 — três títulos, um boot cada, NESTA ORDEM:
  1) Yoshi's Island (EZ-Flash Omega DE, NOR)   2) WarioWare: Twisted (US)   3) WarioWare: Twisted (JP)
Sem Gecko: não precisa avisar antes de ligar.

ANTES DE CADA TÍTULO
 1. Console DESLIGADO POR COMPLETO (ciclo de energia). Cartucho do título no Game Boy Player. Nada no Link Port. Controle GENÉRICO na porta 1.
 2. Cartão SD2SP2: na pasta Open-GBP do cartão NÃO pode existir o arquivo  GBP-PLAY-002_vehicle-0002.log  (sem número no fim).
    Se existir, ele é do título anterior: renomeie como no passo 9 ANTES de continuar. Cartão no console.
 3. Ligue e abra pelo Swiss:  Open-GBP / 29-vehicle2 / boot.dol    Confira na tela:  vehicle-0002   7d2f58f.   Se estiver diferente, PARE e avise.
DURANTE
 4. Espere o aviso  PRESS A within 45 s  (cerca de 5 segundos) e aperte  A  ×1.  O jogo aparece; jogue normalmente. O teste termina sozinho em até 6 minutos.
 5. Título 1 (Yoshi, na NOR): NÃO salve o jogo de propósito. Títulos 2 e 3 (WarioWare: Twisted): você aceitou que o jogo possa gravar sozinho no cartucho. Se o cartucho NÃO tiver nenhum save, você pode começar um jogo novo para poder jogar; se JÁ tiver um save, continue nele e NÃO apague nem sobrescreva um save existente de propósito. Em nenhum título use as opções de salvar ou de apagar dados por conta própria. Se o jogo gravar, deixe terminar: não desligue nem segure Z durante uma gravação.
 6. Só nos WarioWare: Twisted (títulos 2 e 3): este jogo se joga girando o aparelho. Se achar seguro, gire o conjunto GameCube + Game Boy Player devagar e com cuidado,
    sem puxar cabos nem mexer no cartão ou no cartucho. Se não achar seguro, NÃO gire: jogue só com os botões. As duas escolhas valem; depois só diga qual fez.
 7. Para terminar antes:  Z  (segure 1/4 de segundo).
DEPOIS
 8. Quando o jogo sair da tela, SOLTE todos os botões e espere (até 5 segundos; depois a tela ignora os botões por 1 segundo).
    Tela final: direcional  ESQUERDA / DIREITA  escolhe o título (o nome aparece na tela);  A  ×1  confirma.
    X  ×1  grava; espere a tela confirmar a gravação. Se a tela NÃO confirmar, NÃO aperte START/PAUSE: fotografe a tela e avise.
    Gravou: START/PAUSE  ×1.  DESLIGUE o console POR COMPLETO.
 9. Cartão no PC. Na pasta Open-GBP do cartão, renomeie  GBP-PLAY-002_vehicle-0002.log  para:
       título 1 ->  GBP-PLAY-002_vehicle-0002-1.log
       título 2 ->  GBP-PLAY-002_vehicle-0002-2.log
       título 3 ->  GBP-PLAY-002_vehicle-0002-3.log
    Só renomeie: não abra e não edite o arquivo.
NO FIM DOS TRÊS
10. Copie os três arquivos -1, -2 e -3, sem abrir, para a pasta  logs/run64/  do projeto. Deixe o cartão conectado ao PC.
11. Responda na Issue ANTES de qualquer pessoa abrir os logs. Responda por título; se a resposta for igual para mais de um, diga para quais.
    Ciclo de energia ANTES e DEPOIS de cada título: sim / não.
    B. (IMAGEM) O que você viu na TV?
    C. (SOM) O que você ouviu?
    D. (CONTROLES) Os controles responderam como você esperava?
    E. Aconteceu algo estranho (travou, cortou, estalou, ficou lento)? Quando?
    F. Qualquer outra coisa.
    Só nos títulos 2 e 3:
    G. Você girou o aparelho? (sim / não). Se girou: o jogo reagiu ao giro? (sim / não / não sei dizer)
    H. Você sentiu ou ouviu alguma vibração vinda do cartucho ou do Game Boy Player? (sim / não / não reparei). Se sim, quando?
"""
FROZEN_PT_SHA256 = "b5c1b7371a227d85bd350bdd66b5561259d91be80389b400662b9ade258ab100"
REQUEST = """Test ID:                  GBP-BREADTH-002 (RUN 64 / 65 / 66, provisional: confirmed as the next free numbers at ingestion), log test_id=GBP-PLAY-002
Build ID:                 vehicle-0002, commit 7d2f58f
DOL:                      build/swiss/29-vehicle2/boot.dol, sha256 02f89ccd1b07b10165d6d7b4287bf1b056a2a673661c89ad8e5b506fe56c55d8 (512 224 B); exported and staged by the hardware Issue, not here
Required cartridge:       1 Yoshi's Island on the EZ-Flash Omega DE NOR; 2 WarioWare: Twisted (US), original; 3 WarioWare: Twisted (JP), original
Physical Link Port state: nothing connected
BBA state:                the standing declaration (present, no cable)
Steps:                    V32.9, frozen (power cycle before and after each title; slot 29-vehicle2; A ×1; play up to 6 minutes or Z; the title choice; X; the log renamed on the card per title)
Expected result/log:      three SD logs GBP-PLAY-002_vehicle-0002-{1,2,3}.log (renamed by the Operator) carrying IDENT, PLAYCFG, ENVMEM, the V28 records, PLAYSTARTUP / PLAYUND / PLAYUNDER,
                          STARTUP / STARTUPT / STARTUPV / STREAMINV / STREAMSELFTEST and CARTDECL; no Gecko capture; the Operator's words. NO prediction of any value.
Question answered:        V32.1 QA-QD
"""
DECLARATION = "1 - sim\n2 - sim\n3 - sim\n"
GATES = """G1 identity — IDENT `test=GBP-PLAY-002 app=gbp-play-gba2 build=vehicle-0002 commit=7d2f58f`, no `-dirty`; the card's `29-vehicle2/boot.dol` equal to the pin (verified at staging).
G2 `SERVICE/TRANSPORT: PASS` (a store-cap stop is a ROW, as the reader prints).
G3 `CAPTURE: PASS` (the per-phase form, Issue #156).
G4 every phase's `LOSS` inside 0.10-0.40 % (a LOSS of `n/a` is not inside).
G5 the reader's line `THE FALLBACK RULE'S ONLY INPUT (Issue #142): after_startup=0` and no `PROBLEM: underrun record` or `PROBLEM: no PLAYUNDER record` line.
G6 the five records present exactly once (no `record: MISSING`, no `N <tag> records (one expected)`), header `dropped=0 truncated=0`, and the seven computed startup rows MET (the transport row refers to G2).
G7 one `CARTDECL` line with `entered=pad_selection_after_session` (an OPERATOR DECLARATION; a disagreement with the order is recorded, not resolved).
"""
CLASSIFICATION = """- **INVALID** (the boot is not counted) — G1 fails, a log was overwritten by the next boot (the constant name), or a log was lost by a procedural cause the Operator reports. A log missing because the image did not reach the final screen or the screen did not confirm the save is NOT INVALID: it is a ROW, recorded with the Operator's words and photograph; QA is INCONCLUSIVE on that boot, and vehicle-0002 is not used again before a diagnosis checkpoint (the teardown block has never run outside host tests, §V31.13).
- **QA** — a log is COMPLETE when its header reads `dropped=0 truncated=0`. FAIL if any complete log has a MISSING or duplicated record: an image defect, and vehicle-0002 is not used again before a diagnosis checkpoint. PASS if at least one log is complete and no complete log has a MISSING or duplicated record. INCONCLUSIVE on a boot whose log is incomplete or missing, and for the session if no log is complete. The five records are written unconditionally at teardown (`poc/gbp-play-gba2/source/main.c:1163-1184` at `7d2f58f`, before `if (sync_started)`), so `PLAYSTARTUP t_dma` does not condition QA.
- **QB** — a boot with every row MET: the startup gate PASSES on that boot and the readings are FACT for that boot. **A NOT MET row does NOT fail the boot and does NOT by itself block vehicle-0002's use in E6 / E7; it requires, BEFORE the next physical session with vehicle-0002, a diagnosis on paper in a checkpoint of its own.** Policy A's drops / supersessions / reorder / depth / latency: NO RECORD (no `OGBPDISP2`; not built), never "passed".
- **QC** — each title is a ROW; a failing G2-G5 is a row that says so, not a failed run. The control boot is compared with RUN 61 on G2-G5 only, RUN 61 as read by this same reader (`CAPTURE: PASS` per §V31.11), not the frozen reader's `CAPTURE: FAIL` of §V31.10; a difference is recorded, and since the hot-path identity is code identity and timing identity is NOT established (§V31.13), with one boot of each it is at most a HYPOTHESIS (image or day); boots 2-3's rows then carry that caveat.
- **QD** — a positive is an OPERATOR OBSERVATION that the line worked in that boot; it is never FACT or CORROBORATED from this run (no machine record carries it). A negative or "não reparei" is UNKNOWN for the slot question (V32.4's rivals).
- **G7 outcome** — a missing line, `entered=none`, or a title other than the frozen order's is recorded; that boot's title is settled by asking the Operator which cartridge was in the slot (AGENTS.md §7.2), never inferred; it does not by itself make the boot INVALID.
"""
STEP5 = (" 5. Título 1 (Yoshi, na NOR): NÃO salve o jogo de propósito. Títulos 2 e 3 (WarioWare: Twisted): você aceitou que o jogo possa gravar sozinho no cartucho. "
         "Se o cartucho NÃO tiver nenhum save, você pode começar um jogo novo para poder jogar; se JÁ tiver um save, continue nele e NÃO apague nem sobrescreva um save existente de propósito. "
         "Em nenhum título use as opções de salvar ou de apagar dados por conta própria. Se o jogo gravar, deixe terminar: não desligue nem segure Z durante uma gravação.")


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def base(rel):
    b = guards.show(BASE, rel)
    return b.decode("utf-8") if isinstance(b, bytes) else b


def flat(s):
    return " ".join(s.replace("`", "").replace("**", "").split())


def v32():
    t = read(HT)
    i = t.index(V32_HEAD)
    j = t.find("\n## ", i + 1)
    return t[i:j if j > 0 else len(t)]


def sub(title):
    s = v32()
    i = s.index("\n" + title) + 1
    j = s.find("\n### ", i + 1)
    return s[i:j if j > 0 else len(s)]


def fenced(s):
    return re.search(r"```text\n(.*?)```", s, re.S).group(1)


def blocks(text):
    heads = list(re.finditer(r"^#{1,4} .*$", text, re.M))
    out = [("", text[:heads[0].start()] if heads else text)]
    for i, m in enumerate(heads):
        out.append((m.group(0), text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]))
    return out


def body(b):
    b = b.rstrip("\n")
    if b.endswith("\n---"):
        b = b[:-4].rstrip("\n")
    return b


class TheEarlierRecordsAreOnTopUnchanged(unittest.TestCase):
    def setUp(self):
        if not guards.base_available(BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)

    def walk(self, old, new):
        o, n = blocks(old), blocks(new)
        j = 0
        for h0, b0 in o:
            while j < len(n) and not n[j][0].startswith(h0):
                j += 1
            self.assertLess(j, len(n), "the block %r is gone or its heading changed" % h0[:70])
            self.assertTrue(n[j][1].startswith(body(b0)), "the text under %r changed above its end" % h0[:70])
            j += 1
        return len(o)

    def test_the_records_only_gained_text(self):
        for rel, minimum in ((HT, 1300), (DEVLOG, 380), (P7, 25)):
            self.assertGreater(self.walk(base(rel), read(rel)), minimum, rel)
        self.assertNotIn("## V32", base(HT))

    def test_the_handoff_only_gained_text(self):
        removed = [x for x in difflib.unified_diff(base(HANDOFF).splitlines(), read(HANDOFF).splitlines(), lineterm="", n=0)
                   if x.startswith("-") and not x.startswith("---")]
        self.assertEqual(removed, [])

    def test_evidence_only_ever_appended(self):
        ids_then = re.findall(r"^#{2,3} ((?:GBP|ENV)-[A-Z]+-\d{3}) ", base(EV), re.M)
        ids_now = re.findall(r"^#{2,3} ((?:GBP|ENV)-[A-Z]+-\d{3}) ", read(EV), re.M)
        self.assertEqual(ids_then[-1], "GBP-HW-384")
        self.assertEqual(ids_now[:len(ids_then)], ids_then, "the evidence ids of BASE are a prefix of the current list")
        self.assertGreater(self.walk(base(EV), read(EV)), 100)

    def test_the_reader_is_the_reader_of_base_and_the_slot_is_not_pinned(self):
        self.assertEqual(read("tools/playread.py"), base("tools/playread.py"))
        # AMENDED ON TOP (Hardware Issue #161, 2026-10-05): "no row 29" is a claim about BASE (the tree this pre-registration was written on); it is asserted THERE, and the
        # manifest now carries exactly the one row the hardware Issue pinned (the hash of V31.13 and of the DOL line of V32.10)
        then = base("tools/swiss-layout.tsv")
        self.assertFalse([l for l in then.splitlines() if l.startswith("29")], "a row 29 in tools/swiss-layout.tsv at BASE")
        self.assertNotIn("vehicle2", then)
        rows = [l.split("\t") for l in read("tools/swiss-layout.tsv").split("\n") if l and not l.startswith("#")]
        self.assertEqual([r for r in rows if r[0] == "29"],
                         [["29", "vehicle2", "gbp-play-gba2", "gbp-play-gba2.dol", "gbp-play-gba2", "vehicle2", "1", "02f89ccd1b07b10165d6d7b4287bf1b056a2a673661c89ad8e5b506fe56c55d8"]])


class TheSection(unittest.TestCase):
    def test_v32_exists_once_and_follows_v31(self):
        t = read(HT)
        self.assertEqual(t.count(V32_HEAD), 1)
        self.assertEqual(len(re.findall(r"^## V32 ", t, re.M)), 1)
        self.assertEqual(t[t.index(V32_HEAD) - 2:t.index(V32_HEAD)], "\n\n")
        self.assertLess(t.index("### V31.13 "), t.index(V32_HEAD))
        for head in ("NOT RUN, NOT STAGED, NOT PINNED", "GitHub Issue #160"):
            self.assertIn(head, t[t.index(V32_HEAD):t.index("\n", t.index(V32_HEAD))])

    def test_the_subsections_exist_once_in_order(self):
        s = v32()
        pos = []
        for title in SUBS:
            self.assertEqual(s.count("\n" + title), 1, title)
            self.assertEqual(len(re.findall(r"^### " + re.escape(title.split(" ")[1]) + " ", s, re.M)), 1, title)
            pos.append(s.index("\n" + title))
        self.assertEqual(pos, sorted(pos))

    def test_the_questions(self):
        s = sub(SUBS[0])
        for q in ("QA  Do the five teardown records of vehicle-0002 (STARTUP, STARTUPT, STARTUPV, STREAMINV, STREAMSELFTEST) reach the SD log of a physical session?",
                  "QB  Does the startup profile hold on the V28 chassis", "QC  The E5 rows of two new ORIGINAL titles", "QD  (E7) Does the Game Boy Player's slot pass WarioWare: Twisted's cartridge hardware"):
            self.assertIn(q, s, q)

    def test_the_identity_is_v31_13s(self):
        t = read(HT)
        v3113 = t[t.index("### V31.13 "):t.index(V32_HEAD)]
        self.assertIn(DOL, v3113)
        s = sub(SUBS[1])
        self.assertEqual(re.findall(r"[0-9a-f]{64}", s), [DOL])
        for tok in ("vehicle-0002", "GBP-PLAY-002", "7d2f58f", "512 224 B", "29-vehicle2: still RESERVED in the record only", "GBP-PLAY-002_vehicle-0002.log", "fopen(path, \"w\")",
                    "src/platform/sdlog.c:24-25"):
            self.assertIn(tok, s, tok)
        self.assertIn("the image is NOT physically validated by this pre-registration (AGENTS.md §5)", s)
        c = read("src/platform/sdlog.c")
        self.assertIn('snprintf(path, sizeof path, "sd:/open-gbp/%s_%s.log", test_id, build_id);', c)
        self.assertIn('f = fopen(path, "w");', c)
        self.assertIn('#define TEST_ID "GBP-PLAY-002"', read("poc/gbp-play-gba2/source/main.c"))

    def test_the_cartdecl_titles_match_the_source(self):
        rows = re.findall(r'^\s*\{ "(.*?)",\s+"([A-Z_]+)" \},', read("src/gbp/gbp_cartdecl.c"), re.M)
        self.assertEqual(rows[1], ("Yoshi's Island (SMA3) on the EZ-Flash Omega DE NOR", "FLASHCART_DELIVERED"))
        self.assertEqual(rows[4], ("WarioWare: Twisted (JP)", "ORIGINAL"))
        self.assertEqual(rows[5], ("WarioWare: Twisted (US)", "ORIGINAL"))
        s = sub(SUBS[2])
        self.assertIn("1  Yoshi's Island on the EZ-Flash Omega DE NOR", s)
        self.assertIn("FLASHCART_DELIVERED (CARTDECL idx 1", s)
        self.assertIn("2  WarioWare: Twisted (US)", s)
        self.assertIn("ORIGINAL (CARTDECL idx 5", s)
        self.assertIn("3  WarioWare: Twisted (JP)", s)
        self.assertIn("ORIGINAL (CARTDECL idx 4", s)
        self.assertLess(s.index("2  WarioWare: Twisted (US)"), s.index("3  WarioWare: Twisted (JP)"))

    def test_the_declaration_is_verbatim_and_variant_r_is_not_used(self):
        s = sub(SUBS[2])
        self.assertIn("```text\n" + DECLARATION + "```", s)
        self.assertIn("These are OPERATOR DECLARATIONS; they are cited, not interpreted. They select variant T.", s)
        self.assertIn("Variant R, recorded as an alternative NOT USED", flat(s).replace("**", ""))
        self.assertIn("the dedicated replication round the `vehicle-0002` decision declined", s)

    def test_the_reader_constants_match_the_reader(self):
        s = sub(SUBS[4])
        self.assertEqual(playread.LOSS_BAND, (0.0010, 0.0040))
        self.assertEqual(playread.FIRST_HANDOFF_BOUND_MS, 400)
        self.assertEqual(playread.STARTUP_K_DEFAULT, 64)
        self.assertEqual(playread.IMAGES["vehicle-0002"], "gbp-play-gba2")
        for tok in ("0.10-0.40 % per phase", "`FIRST_HANDOFF_BOUND_MS` 400", "`STARTUP_K_DEFAULT` 64", "ticks * 1000 < 400 * tb_hz", "have_first == 1",
                    "git diff --quiet <this Issue's commit> -- tools/playread.py", "git diff --quiet origin/main -- tools/playread.py",
                    "whether a NOT MET row fails a session is that session's hardware Issue's pre-registration, never this tool's"):
            self.assertIn(tok, s, tok)
        self.assertIn("whether a NOT MET row fails a session is that session's hardware Issue's pre-registration, never this tool's", " ".join(read("tools/playread.py").split()).replace("# ", ""))
        self.assertIn("0.10-0.40", sub(SUBS[5]))

    def test_the_gates_and_the_classification_are_pinned_literally(self):
        s = sub(SUBS[5])
        self.assertEqual(fenced(s), GATES)
        self.assertEqual(s.count("```"), 2)
        self.assertEqual(len(GATES.splitlines()), 7)
        self.assertEqual([l.split(" ")[0] for l in GATES.splitlines()], ["G1", "G2", "G3", "G4", "G5", "G6", "G7"])
        i = s.index("**Classification.**\n\n") + len("**Classification.**\n\n")
        self.assertEqual(s[i:].rstrip("\n") + "\n", CLASSIFICATION)
        self.assertEqual([l.split("**")[1] for l in CLASSIFICATION.splitlines()], ["INVALID", "QA", "QB", "QC", "QD", "G7 outcome"])
        flat_s = flat(s)
        # the clauses that carried a rule and escaped a mutation: each is also asserted on its own
        for tok in ("header `dropped=0 truncated=0`", "a log is COMPLETE when its header reads `dropped=0 truncated=0`",
                    "FAIL if any complete log has a MISSING or duplicated record: an image defect, and vehicle-0002 is not used again before a diagnosis checkpoint",
                    "PASS if at least one log is complete and no complete log has a MISSING or duplicated record",
                    "INCONCLUSIVE on a boot whose log is incomplete or missing, and for the session if no log is complete",
                    "so `PLAYSTARTUP t_dma` does not condition QA",
                    "A log missing because the image did not reach the final screen or the screen did not confirm the save is NOT INVALID",
                    "(a LOSS of `n/a` is not inside)", "THE FALLBACK RULE'S ONLY INPUT (Issue #142): after_startup=0", "`PROBLEM: no PLAYUNDER record`",
                    "with one boot of each it is at most a HYPOTHESIS (image or day)", "RUN 61 as read by this same reader (`CAPTURE: PASS` per §V31.11), not the frozen reader's `CAPTURE: FAIL` of §V31.10",
                    "it is never FACT or CORROBORATED from this run", "that boot's title is settled by asking the Operator which cartridge was in the slot (AGENTS.md §7.2), never inferred",
                    "it does not by itself make the boot INVALID", NOT_MET_RULE):
            self.assertIn(flat(tok), flat_s, tok)
        self.assertNotIn("PLAYSTARTUP t_dma` not `none`", s)
        self.assertIn("a diagnosis on paper (the logs and the code) in its own checkpoint", sub(SUBS[6]))
        self.assertIn("Any startup row NOT MET in any boot: before the next physical session with `vehicle-0002`", sub(SUBS[6]))
        self.assertIn("T256 A2", sub(SUBS[6]))
        self.assertIn("`after_startup` only", sub(SUBS[6]))

    def test_the_reader_notes_and_the_recorded_instant(self):
        self.assertIn("The header line `lines= dropped= truncated=` (`src/platform/sdlog.c:34-35` at `7d2f58f`) is read raw: the reader does not print it.", sub(SUBS[4]))
        c = read("src/platform/sdlog.c")
        self.assertIn('fprintf(f, "lines=%u dropped=%u truncated=%u\\n"', c)
        self.assertIn("THE FALLBACK RULE'S ONLY INPUT (Issue #142): after_startup=", read("tools/playread.py"))
        s = flat(sub(SUBS[3]))
        for tok in ("the recorded instant (STARTUPV t_decision, gbp_startrec.c:31) is t_dec = gettime() at main.c:842, at the start of the submit that hands over the first real frame, not gbp_vpresent_xfb_handed (:866) itself",):
            self.assertIn(flat(tok), s, tok)
        m = read("poc/gbp-play-gba2/source/main.c").splitlines()
        self.assertEqual(m[841].strip(), "t_dec = gettime();")
        self.assertIn("t_ho = have ? t_decision : 0u;", read("src/gbp/gbp_startrec.c"))
        s8 = flat(sub(SUBS[7]))
        self.assertIn(flat("every `PROBLEM:`, `note:` or `UNEXPECTED` line that no gate names is recorded verbatim and explained; none is read as passed"), s8)

    def test_step_5_of_the_frozen_text_is_the_amended_one(self):
        block = fenced(sub(SUBS[8]))
        self.assertEqual(sum(1 for l in block.splitlines() if l.startswith(" 5. ")), 1)
        self.assertIn(STEP5 + "\n", block)
        self.assertNotIn("NÃO salve o jogo de propósito (não use opção de salvar, não comece jogo novo que grave)", block)
        self.assertIn("NÃO apague nem sobrescreva um save existente de propósito", block)

    def test_the_qd_negative_does_not_discriminate(self):
        s = flat(sub(SUBS[3]))
        for tok in ("QD A POSITIVE", "NEGATIVE or \"não reparei\" has rivals this instrument cannot separate", "the slot does not pass the line", "rotation was too small",
                    "It is therefore NOT evidence that the slot does not pass it", "The video is content-blind and decides nothing about QD",
                    "never the time until the picture is on the television"):
            self.assertIn(flat(tok), s, tok)

    def test_the_operators_text_is_frozen_verbatim(self):
        s = sub(SUBS[8])
        block = fenced(s)
        self.assertEqual(block, FROZEN_PT)
        self.assertEqual(hashlib.sha256(block.encode("utf-8")).hexdigest(), FROZEN_PT_SHA256)
        self.assertEqual(s.count("```"), 2)
        self.assertEqual(block.splitlines()[0], "GBP-BREADTH-002 — três títulos, um boot cada, NESTA ORDEM:")

    def test_the_request_is_verbatim(self):
        s = sub(SUBS[9])
        self.assertEqual(fenced(s), REQUEST)
        self.assertEqual(s.count("```"), 2)
        self.assertIn(DOL, REQUEST)

    def test_what_it_does_not_do(self):
        s = flat(sub(SUBS[10]))
        for tok in ("No pin, export or card write; no run; no evidence id; no reader or image change; T256 A1 unchanged; §V31 and every earlier record untouched",):
            self.assertIn(flat(tok), s)


class TheStateFiles(unittest.TestCase):
    def test_the_devlog_entry(self):
        d = read(DEVLOG)
        self.assertEqual(d.count(DEVLOG_HEAD), 1)
        self.assertLess(d.index("## 2026-10-05 — Issue #158: "), d.index(DEVLOG_HEAD))
        e = d[d.index(DEVLOG_HEAD):]
        for tok in ("e1c063e", "1 - sim / 2 - sim / 3 - sim", "variant R", "Amendment 1", "The hardware Issue #161 (staging, pin and slot, then the run)", "src/platform/sdlog.c:24-25", "Premises re-verified at BASE", "no pin, no stage, no run", "T256 A1 is unchanged"):
            self.assertIn(tok, e, tok)

    def test_the_phase7_amendment_is_last_and_says_the_negative_does_not_discriminate(self):
        t = read(P7)
        self.assertEqual(t.count(P7_HEAD), 1)
        heads = re.findall(r"^## .*$", t, re.M)
        self.assertTrue(heads[-1].startswith(P7_HEAD))
        e = flat(t[t.index(P7_HEAD):])
        for tok in ("E7 begins BEFORE E6", "OPERATOR OBSERVATION", "does NOT discriminate", "never FACT or CORROBORATED from this run", "HARDWARE_TESTS.md §V32"):
            self.assertIn(flat(tok), e, tok)

    def test_the_handoff_paragraphs_come_before_the_previous_ones(self):
        h = read(HANDOFF)
        for heading, para in (("## Current blocker / current question\n\n", HANDOFF_BLOCKER), ("## Next safe action\n\n", HANDOFF_NEXT)):
            self.assertEqual(h.count(heading), 1)
            sec = h.split(heading)[1].split("\n## ")[0]
            self.assertEqual(sec.count(para), 1, heading)
            self.assertLess(sec.index(para), sec.index("Issue #158), on top:"), heading)
        self.assertIn("the next safe action is the hardware Issue for that session (Hardware Issue #161)", h)
        self.assertIn(DOL, h)

    def test_the_test_id_is_not_cited_where_the_family_is_not_registered(self):
        for rel in (HANDOFF, "docs/ROADMAP.md"):
            self.assertNotIn("GBP-BREADTH-002", read(rel), rel)


if __name__ == "__main__":
    unittest.main()
