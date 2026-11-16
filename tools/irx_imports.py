#!/usr/bin/env python3
"""List the import stubs (and, with --exports, the export table) of a PS2 IRX module.

An IRX import table starts with the magic word 0x41E00000, then a zero word, a version
word, an 8-byte library name, and 8-byte stubs ("jr $ra" + "addiu $zero, $zero, ordinal")
until a pair of zero words.

    tools/irx_imports.py disc/IOP/SD_CALL.IRX [0x3934 ...]
    tools/irx_imports.py --exports disc/IOP/LIBSMF2.IRX     -> ordinal -> module-relative address

The export table starts with 0x41C00000, a zero word, a version word, the 8-byte library
name, then one function address per ordinal (ordinal 0 first) until a zero word after it.
"""
import struct
import sys
from pathlib import Path

IMPORT_MAGIC = 0x41E00000
EXPORT_MAGIC = 0x41C00000
JR_RA = 0x03E00008


def load_segment(path):
    data = Path(path).read_bytes()
    phoff, = struct.unpack_from("<I", data, 0x1C)
    phnum, = struct.unpack_from("<H", data, 0x2C)
    for i in range(phnum):
        p_type, p_offset, p_vaddr, _, p_filesz, *_ = struct.unpack_from("<8I", data, phoff + i * 32)
        if p_type == 1:  # PT_LOAD
            return data[p_offset:p_offset + p_filesz], p_vaddr
    sys.exit("no PT_LOAD segment")


def imports(segment, base):
    words = len(segment) // 4
    result = {}
    i = 0
    while i < words:
        if struct.unpack_from("<I", segment, i * 4)[0] != IMPORT_MAGIC:
            i += 1
            continue
        name = segment[i * 4 + 12:i * 4 + 20].split(b"\0")[0].decode("ascii", "replace")
        j = i + 5
        while j + 1 < words:
            first, second = struct.unpack_from("<II", segment, j * 4)
            if first == 0 and second == 0:
                break
            if first == JR_RA and (second >> 16) == 0x2400:
                result[base + j * 4] = (name, second & 0xFFFF)
            j += 2
        i = j
    return result


def exports(segment):
    words = len(segment) // 4
    for i in range(words):
        if struct.unpack_from("<I", segment, i * 4)[0] != EXPORT_MAGIC:
            continue
        name = segment[i * 4 + 12:i * 4 + 20].split(b"\0")[0].decode("ascii", "replace")
        # Addresses are unrelocated module offsets, so ordinal 0 may legitimately be 0.
        table = [struct.unpack_from("<I", segment, (i + 5) * 4)[0]]
        j = i + 6
        while j < words:
            address, = struct.unpack_from("<I", segment, j * 4)
            if address == 0:
                break
            table.append(address)
            j += 1
        return name, table
    return None, []


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--exports":
        segment, _ = load_segment(sys.argv[2])
        name, table = exports(segment)
        for ordinal, address in enumerate(table):
            print(f"{name}:{ordinal}  0x{address:05x}")
        return
    segment, base = load_segment(sys.argv[1])
    table = imports(segment, base)
    queries = [int(a, 0) for a in sys.argv[2:]]
    for address, (library, ordinal) in sorted(table.items()):
        if not queries or address in queries:
            print(f"0x{address:05x}  {library}:{ordinal}")


if __name__ == "__main__":
    main()
