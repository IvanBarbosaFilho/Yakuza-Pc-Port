#!/usr/bin/env python3
"""Extract Konami "mfar" archives (.MFA) from Silent Hill 3 (PS2).

Layout (reverse-engineered from B0.MFA):
  0x000  shell script stub left by the mfar tool, padded with spaces
  0x0D8  u32 file_count, u32 data_size
  0x0E0  file_count entries of 16 bytes:
           u32 name_offset  (absolute file offset of a NUL-terminated path)
           u32 data_offset  (relative to the data base, 0x800)
           u32 mode         (unix mode, e.g. 0x81B4 = -rw-rw-r--)
           u32 size
  0x800  file data
"""
import struct
import sys
from pathlib import Path

HEADER_OFFSET = 0xD8
DATA_BASE = 0x800


def read_cstr(buf, off):
    end = buf.index(b"\0", off)
    return buf[off:end].decode("ascii")


def parse(buf):
    count, data_size = struct.unpack_from("<II", buf, HEADER_OFFSET)
    entries = []
    for i in range(count):
        name_off, data_off, mode, size = struct.unpack_from("<IIII", buf, HEADER_OFFSET + 8 + i * 16)
        entries.append((read_cstr(buf, name_off), DATA_BASE + data_off, mode, size))
    return data_size, entries


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(f"usage: {sys.argv[0]} <archive.mfa> [out_dir]")
    buf = Path(sys.argv[1]).read_bytes()
    data_size, entries = parse(buf)
    out_dir = Path(sys.argv[2]) if len(sys.argv) == 3 else None

    print(f"{len(entries)} files, data size 0x{data_size:X}")
    for name, off, mode, size in entries:
        print(f"  0x{off:08X}  0x{size:06X}  {mode:o}  {name}")
        if out_dir:
            dest = out_dir / name
            if dest.resolve().is_relative_to(out_dir.resolve()) is False:
                sys.exit(f"refusing unsafe path: {name}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(buf[off:off + size])


if __name__ == "__main__":
    main()
