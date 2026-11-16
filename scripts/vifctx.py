"""Decode VIF codes around addresses in a RAM dump: vifctx.py <ram.bin> <code-hex> [count]"""
import struct, sys
d = open(sys.argv[1], "rb").read(); code = int(sys.argv[2], 16); count = int(sys.argv[3]) if len(sys.argv) > 3 else 2
pat = struct.pack("<I", code); i = d.find(pat); shown = 0
names = {0:"NOP",1:"STCYCL",2:"OFFSET",3:"BASE",4:"ITOP",5:"STMOD",6:"MSKPATH3",7:"MARK",0x10:"FLUSHE",0x11:"FLUSH",0x13:"FLUSHA",0x14:"MSCAL",0x15:"MSCALF",0x17:"MSCNT",0x20:"STMASK",0x30:"STROW",0x31:"STCOL",0x4a:"MPG",0x50:"DIRECT",0x51:"DIRECTHL"}
while i >= 0 and shown < count:
    # walk forward from 0x100 bytes before, aligned to the qword, decoding greedily
    print(f"--- hit at {i:#x}")
    o = max(0, i - 0x60) & ~3
    end = i + 0x80
    while o < end:
        v = struct.unpack_from("<I", d, o)[0]; cmd = (v >> 24) & 0x7f; num = (v >> 16) & 0xff; imm = v & 0xffff
        if cmd >= 0x60:
            vn = (cmd >> 2) & 3; vl = cmd & 3; m = (cmd >> 4) & 1
            print(f"  {o:#x}: {v:08x} UNPACK V{vn+1}-{32>>vl} m={m} num={num} addr={imm&0x3ff:#x}{' +TOPS' if imm&0x8000 else ''}{' usn' if imm&0x4000 else ''}")
        else:
            nm = names.get(cmd, f"?{cmd:#x}")
            extra = f" cl={imm&0xff} wl={imm>>8}" if cmd == 1 else ""
            print(f"  {o:#x}: {v:08x} {nm} num={num} imm={imm:#x}{extra}")
        o += 4
    shown += 1
    i = d.find(pat, i + 4)
