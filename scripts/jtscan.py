"""Find GCC switch tables (sltiu bound; sll; lui at; addu at; lw r,lo(at); jr r) in the ELF and report
which are missing from the recomp config and which case targets fall outside every exported function.
usage: jtscan.py <elf> <game.toml> <game.csv> [--toml out.toml]"""
import re, sys, struct
from rabbitizer import Instruction
from elftools.elf.elffile import ELFFile

elf, cfg, csv = sys.argv[1:4]
e = ELFFile(open(elf, "rb"))
text = e.get_section_by_name(".text")
if text is None:
    # Silent Hill 2's ELF has one unnamed section for code and data: take the executable section, cut at the
    # end of the last exported function so the data after the code is not scanned as instructions.
    text = next(s for s in e.iter_sections() if s["sh_flags"] & 0x4 and s["sh_size"])
    code_end = max(int(l.split(",")[2], 16) for l in open(csv).read().splitlines()[1:]
                   if l.count(",") >= 3 and l.split(",")[2].startswith("0x") and "ovl_" not in l.split(",")[0])
    tb, td = text["sh_addr"], text.data()[:max(0, code_end - text["sh_addr"])]
else:
    tb, td = text["sh_addr"], text.data()
segs = [(s["p_vaddr"], s.data()) for s in e.iter_segments() if s["p_type"] == "PT_LOAD"]
def rd(a):
    for v, d in segs:
        if v <= a < v + len(d) - 3:
            return struct.unpack_from("<I", d, a - v)[0]
    return None
known = set(int(m, 16) for m in re.findall(r'^address = "(0x[0-9a-fA-F]+)"', open(cfg).read(), re.M))
funcs = []
for line in open(csv):
    p = line.strip().split(",")
    if len(p) >= 3 and p[1].startswith("0x"):
        funcs.append((int(p[1], 16), int(p[2], 16)))
starts = set(s for s, _ in funcs)
def covered(a):
    return any(s <= a < e_ for s, e_ in funcs)

ins = [Instruction(struct.unpack_from("<I", td, i)[0], vram=tb + i) for i in range(0, len(td), 4)]
found = []
for i, x in enumerate(ins):
    if x.getOpcodeName() != "jr" or x.rs.name == "ra":
        continue
    r = x.rs
    # lw r, off(base) right before the jr (allowing one instruction between), and a sltiu bound before it
    lwi = next((j for j in range(i - 1, max(i - 3, -1), -1)
                if ins[j].getOpcodeName() == "lw" and ins[j].rt == r), None)
    if lwi is None:
        continue
    lw = ins[lwi]
    si = next((j for j in range(lwi - 1, max(lwi - 32, -1), -1) if ins[j].getOpcodeName() == "sltiu"), None)
    if si is None:
        continue
    bound = ins[si].getProcessedImmediate()
    const, tbase = {}, {}
    for j in range(si, lwi):
        y = ins[j]; n = y.getOpcodeName()
        if n == "lui":
            const[y.rt] = y.getProcessedImmediate() << 16; tbase.pop(y.rt, None)
        elif n in ("addiu", "ori"):
            v = None
            if y.rs in const:
                v = (const[y.rs] + y.getProcessedImmediate()) if n == "addiu" else (const[y.rs] | y.getProcessedImmediate())
            if v is None: const.pop(y.rt, None)
            else: const[y.rt] = v & 0xffffffff
            tbase.pop(y.rt, None)
        elif n in ("addu", "daddu"):
            a, b = y.rs in const, y.rt in const
            tbase.pop(y.rd, None)
            if a != b: tbase[y.rd] = const[y.rs] if a else const[y.rt]
            const.pop(y.rd, None)
    if lw.rs not in tbase:
        continue
    addr = (tbase[lw.rs] + lw.getProcessedImmediate()) & 0xffffffff
    targets = [rd(addr + 4 * k) for k in range(bound)]
    if any(t is None or not (tb <= t < tb + len(td)) for t in targets):
        continue
    found.append((tb + 4 * i, addr, targets))

missing = [f for f in found if f[1] not in known]
def addr_not_in_config(table):
    return table not in known
def owner(a):
    for s_, e_ in funcs:
        if s_ <= a < e_:
            return s_
    return None
# A case target needs its own entry unless it lies in the same function as the jr (the recompiler
# resolves in-function table targets) or is already a function start.
uncov = sorted(set(t for jr, _, ts in found for t in ts
                   if t not in starts and (owner(t) is None or owner(t) != owner(jr)
                                           or addr_not_in_config(_))))
print(f"{len(found)} switch tables by pattern; {len(known)} in config; {len(missing)} missing from config;"
      f" {len(uncov)} case targets outside the jr's function and not a function start")
for jr, addr, t in missing[:15]:
    print(f"  jr@{jr:#x} table {addr:#x} n={len(t)}")
if "--toml" in sys.argv:
    with open(sys.argv[sys.argv.index("--toml") + 1], "w") as o:
        for jr, addr, t in missing:
            o.write(f'[[jump_tables.table]]\naddress = "{addr:#x}"\nentries = [\n')
            for k, v in enumerate(t):
                o.write(f'  {{ index = {k}, target = "{v:#x}" }},\n')
            o.write("]\n")
if "--entries" in sys.argv:
    for t in uncov:
        print(f'  "jt_{t:08x}@{t:#010x}",')
