#!/usr/bin/env python3
"""Wrap a Metrowerks CodeWarrior "MWo3" overlay into a minimal MIPS ELF for ps2_recomp.

The whole overlay file (0x40-byte header included) is copied to its load address by the game;
.text follows the header, then .data, then .bss. The ELF has one PT_LOAD segment and sections
.ovlhdr / .text / .data / .bss so the recompiler sees code, data and the header bytes it uses as
the runtime signature of the overlay.

usage: mwo3_elf.py <overlay.bin> <out.elf>
"""
import struct
import sys
from pathlib import Path

HEADER_SIZE = 0x40
MWO3_MAGIC = 0x336F574D  # "MWo3"

SHT_PROGBITS, SHT_NOBITS, SHT_STRTAB = 1, 8, 3
SHF_WRITE, SHF_ALLOC, SHF_EXECINSTR = 1, 2, 4


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    blob = src.read_bytes()
    magic, _id, load, text_size, data_size, bss_size = struct.unpack_from("<6I", blob, 0)
    if magic != MWO3_MAGIC:
        sys.exit(f"{src}: not an MWo3 overlay")
    # MWO3_LOAD="name=0xADDR,...": the address the game's loader really uses when the header field is not it
    # (Yakuza's MAIN.BIN). The header bytes stay as on disc (they are the runtime signature).
    import os
    for item in os.environ.get("MWO3_LOAD", "").split(","):
        if "=" in item and item.split("=")[0].strip().lower() == src.name.lower():
            load = int(item.split("=")[1], 0)
    # MWO3_TEXT_ALL="name,...": the whole image (text + data) is code to recompile: Yakuza's MAIN.BIN has functions
    # (its C++ constructors, 0x570280...) in what the header counts as data.
    if src.name.lower() in [n.strip().lower() for n in os.environ.get("MWO3_TEXT_ALL", "").split(",")]:
        text_size, data_size = text_size + data_size, 0
    file_size = len(blob)

    names = b"\0.ovlhdr\0.text\0.data\0.bss\0.shstrtab\0"
    def name_offset(name):
        return names.index(name.encode() + b"\0")

    ehdr_size, phdr_size, shdr_size = 52, 32, 40
    payload_offset = 0x100  # file offset of the overlay image, aligned for readability
    shstr_offset = payload_offset + file_size
    shdr_offset = (shstr_offset + len(names) + 3) & ~3

    text_start = load + HEADER_SIZE
    data_start = text_start + text_size
    bss_start = data_start + data_size
    sections = [
        (0, 0, 0, 0, 0, 0),
        (name_offset(".ovlhdr"), SHT_PROGBITS, SHF_ALLOC, load, payload_offset, HEADER_SIZE),
        (name_offset(".text"), SHT_PROGBITS, SHF_ALLOC | SHF_EXECINSTR, text_start,
         payload_offset + HEADER_SIZE, text_size),
        (name_offset(".data"), SHT_PROGBITS, SHF_ALLOC | SHF_WRITE, data_start,
         payload_offset + HEADER_SIZE + text_size, data_size),
        (name_offset(".bss"), SHT_NOBITS, SHF_ALLOC | SHF_WRITE, bss_start, shstr_offset, bss_size),
        (name_offset(".shstrtab"), SHT_STRTAB, 0, 0, shstr_offset, len(names)),
    ]

    out = bytearray()
    ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + bytes(8)
    out += ident
    out += struct.pack("<HHIIIIIHHHHHH", 2, 8, 1, 0, ehdr_size, shdr_offset, 0x20924001,
                       ehdr_size, phdr_size, 1, shdr_size, len(sections), len(sections) - 1)
    out += struct.pack("<8I", 1, payload_offset, load, load, file_size, file_size + bss_size, 7, 0x10)
    out += bytes(payload_offset - len(out))
    out += blob
    out += names
    out += bytes(shdr_offset - len(out))
    for name, kind, flags, addr, offset, size in sections:
        out += struct.pack("<10I", name, kind, flags, addr, offset, size, 0, 0, 16 if kind else 0, 0)
    dst.write_bytes(out)


if __name__ == "__main__":
    main()
