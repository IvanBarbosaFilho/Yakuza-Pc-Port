#!/usr/bin/env python3
"""Minimal VU1 microcode disassembler (lower ops decoded, upper shown raw + flag bits).

usage: vudis.py <vu1.code> <start-hex> <end-hex>
Enough to follow integer-register dataflow (ILW/IADDIU/IADD/branches/XGKICK) in a dump made
with PS2X_DUMP_VU1.
"""
import struct
import sys

LOWEROP = {0x30: "iadd", 0x31: "isub", 0x32: "iaddi", 0x34: "iand", 0x35: "ior",
           0x38: "vcallms", 0x39: "vcallmsr"}
SPECIAL2 = {0x30: "move", 0x31: "mr32", 0x34: "lqi", 0x35: "sqi", 0x36: "lqd", 0x37: "sqd",
            0x38: "div", 0x39: "sqrt", 0x3A: "rsqrt", 0x3B: "waitq", 0x3C: "mtir", 0x3D: "mfir",
            0x3E: "ilwr", 0x3F: "iswr", 0x40: "rnext", 0x41: "rget", 0x42: "rinit", 0x43: "rxor",
            0x64: "mfp", 0x68: "xtop", 0x69: "xitop", 0x6C: "xgkick", 0x70: "esadd", 0x71: "ersadd",
            0x72: "eleng", 0x73: "erleng", 0x74: "eatanxy", 0x75: "eatanxz", 0x76: "esum",
            0x78: "esqrt", 0x79: "ersqrt", 0x7A: "ercpr", 0x7B: "waitp", 0x7C: "esin", 0x7D: "eatan",
            0x7E: "eexp"}
OPS = {0x00: "lq", 0x01: "sq", 0x04: "ilw", 0x05: "isw", 0x08: "iaddiu", 0x09: "isubiu",
       0x10: "fceq", 0x11: "fcset", 0x12: "fcand", 0x13: "fcor", 0x14: "fseq", 0x15: "fsset",
       0x16: "fsand", 0x17: "fsor", 0x18: "fmeq", 0x1A: "fmand", 0x1B: "fmor", 0x1C: "fcget",
       0x20: "b", 0x21: "bal", 0x24: "jr", 0x25: "jalr", 0x28: "ibeq", 0x29: "ibne",
       0x2C: "ibltz", 0x2D: "ibgtz", 0x2E: "iblez", 0x2F: "ibgez"}


def dest(bits):
    return "".join(c for i, c in enumerate("xyzw") if bits & (8 >> i)) or "-"


def sext(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def lower(word, pc):
    op = word >> 25
    it, is_, id_ = (word >> 16) & 31, (word >> 11) & 31, (word >> 6) & 31
    if op == 0x40:
        funct = word & 0x3F
        if funct >= 0x3C:
            sub = (((word >> 6) & 0x1F) << 2) | (funct & 3)
            name = SPECIAL2.get(sub, f"special2_{sub:#x}")
            return f"{name}.{dest((word >> 21) & 15)} it=vi{it} is=vi{is_} (ft=vf{it} fs=vf{is_})"
        if funct == 0x32:
            return f"iaddi vi{it}, vi{is_}, {sext(id_, 5)}"
        name = LOWEROP.get(funct, f"lowerop_{funct:#x}")
        return f"{name} vi{id_}, vi{is_}, vi{it}"
    name = OPS.get(op, f"op_{op:#x}")
    if op in (0x08, 0x09):
        imm = (((word >> 21) & 15) << 11) | (word & 0x7FF)
        return f"{name} vi{it}, vi{is_}, {imm:#x}"
    if op in (0x00, 0x01, 0x04, 0x05):
        return f"{name}.{dest((word >> 21) & 15)} vi/vf{it}, {sext(word & 0x7FF, 11):#x}(vi{is_})"
    if op >= 0x20 and op <= 0x2F:
        target = pc + 8 + sext(word & 0x7FF, 11) * 8
        return f"{name} vi{it}, vi{is_} -> {target:#x}"
    return f"{name} it={it} is={is_} imm={word & 0x7FF:#x}"


def main():
    code = open(sys.argv[1], "rb").read()
    start, end = int(sys.argv[2], 16), int(sys.argv[3], 16)
    for pc in range(start & ~7, end, 8):
        lo, up = struct.unpack_from("<II", code, pc)
        flags = "".join(f for f, bit in (("I", 31), ("E", 30), ("M", 29), ("D", 28), ("T", 27)) if up >> bit & 1)
        text = f"loi {lo:#x}" if up >> 31 & 1 else lower(lo, pc)
        print(f"{pc:04x}: {up:08x} {flags:3} | {lo:08x}  {text}")


if __name__ == "__main__":
    main()
