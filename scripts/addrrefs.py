"""Functions that build a given absolute address (lui hi + addiu/ori/load/store lo within 8 insns).
usage: addrrefs.py <elf> <csv> <addr> [<addr>...]   (range match: addr..addr+0x100)"""
import sys, struct
from rabbitizer import Instruction
from elftools.elf.elffile import ELFFile
elf, csv, *addrs = sys.argv[1:]
addrs = [int(a, 16) for a in addrs]
e = ELFFile(open(elf, "rb")); t = e.get_section_by_name(".text"); tb, td = t["sh_addr"], t.data()
funcs = []
for l in open(csv):
    p = l.strip().split(",")
    if len(p) >= 3 and p[1].startswith("0x"): funcs.append((int(p[1], 16), int(p[2], 16), p[0]))
def owner(a):
    best = None
    for s, e_, n in funcs:
        if s <= a < e_ and (best is None or s > best[0]): best = (s, n)
    return best[1] if best else "?"
ins = [Instruction(struct.unpack_from("<I", td, i)[0], vram=tb + i) for i in range(0, len(td), 4)]
for i, x in enumerate(ins):
    if x.getOpcodeName() != "lui": continue
    hi = x.getProcessedImmediate() << 16; r = x.rt
    for j in range(i + 1, min(i + 9, len(ins))):
        y = ins[j]
        if y.isJump() and not y.isBranch(): break
        if y.hasOperandAlias if False else False: pass
        try: rs = y.rs
        except Exception: continue
        if rs != r or y.getOpcodeName() == "lui": continue
        if not y.canBeLo(): continue
        v = (hi + y.getProcessedImmediate()) & 0xffffffff
        for a in addrs:
            if a <= v < a + 0x100:
                print(f"{tb+4*j:#x} {owner(tb+4*j):24s} {y.disassemble()}  -> {v:#x}")
