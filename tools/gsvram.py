#!/usr/bin/env python3
"""Render a region of a GS local memory dump (PS2X_DUMP_VRAM) as PNG.

usage: gsvram.py <vram.bin> <out.png> --fbp N --fbw N [--psm 32|24|16] [--width W] [--height H]
                 [--x X] [--y Y] [--stats]

fbp/fbw are FRAME/DISPFB units (fbp: 2048 words, fbw: 64 pixels). PSMCT32/24 use the GS
block/column swizzle (same tables as ps2xRuntime's ps2_gs_psmct32.h); PSMCT16 uses its own.
--stats prints how many pixels are non-black and the colour range, to triage black screens.
"""

import argparse
import struct
import zlib

BLOCK32 = [[0, 1, 4, 5, 16, 17, 20, 21], [2, 3, 6, 7, 18, 19, 22, 23],
           [8, 9, 12, 13, 24, 25, 28, 29], [10, 11, 14, 15, 26, 27, 30, 31]]
COLUMN32 = [[0, 1, 4, 5, 8, 9, 12, 13], [2, 3, 6, 7, 10, 11, 14, 15],
            [16, 17, 20, 21, 24, 25, 28, 29], [18, 19, 22, 23, 26, 27, 30, 31],
            [32, 33, 36, 37, 40, 41, 44, 45], [34, 35, 38, 39, 42, 43, 46, 47],
            [48, 49, 52, 53, 56, 57, 60, 61], [50, 51, 54, 55, 58, 59, 62, 63]]
BLOCK16 = [[0, 2, 8, 10], [1, 3, 9, 11], [4, 6, 12, 14], [5, 7, 13, 15],
           [16, 18, 24, 26], [17, 19, 25, 27], [20, 22, 28, 30], [21, 23, 29, 31]]
COLUMN16 = [[0, 2, 8, 10, 16, 18, 24, 26, 1, 3, 9, 11, 17, 19, 25, 27],
            [4, 6, 12, 14, 20, 22, 28, 30, 5, 7, 13, 15, 21, 23, 29, 31],
            [32, 34, 40, 42, 48, 50, 56, 58, 33, 35, 41, 43, 49, 51, 57, 59],
            [36, 38, 44, 46, 52, 54, 60, 62, 37, 39, 45, 47, 53, 55, 61, 63],
            [64, 66, 72, 74, 80, 82, 88, 90, 65, 67, 73, 75, 81, 83, 89, 91],
            [68, 70, 76, 78, 84, 86, 92, 94, 69, 71, 77, 79, 85, 87, 93, 95],
            [96, 98, 104, 106, 112, 114, 120, 122, 97, 99, 105, 107, 113, 115, 121, 123],
            [100, 102, 108, 110, 116, 118, 124, 126, 101, 103, 109, 111, 117, 119, 125, 127]]
VRAM_SIZE = 4 << 20


def addr32(block, fbw, x, y):
    page = (block >> 5) + (y >> 5) * max(fbw, 1) + (x >> 6)
    block_id = (block & 31) + BLOCK32[(y >> 3) & 3][(x >> 3) & 7]
    return ((page << 13) + ((block_id >> 5) << 13) + (block_id & 31) * 256 + COLUMN32[y & 7][x & 7] * 4) % VRAM_SIZE


def addr16(block, fbw, x, y):
    page = (block >> 5) + (y >> 6) * max(fbw, 1) + (x >> 6)
    block_id = (block & 31) + BLOCK16[(y >> 3) & 7][(x >> 4) & 3]
    return ((page << 13) + ((block_id >> 5) << 13) + (block_id & 31) * 256 + COLUMN16[y & 7][x & 15] * 2) % VRAM_SIZE


def write_png(path, width, height, rows):
    raw = b"".join(b"\0" + bytes(row) for row in rows)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        f.write(chunk(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vram")
    ap.add_argument("out")
    ap.add_argument("--fbp", type=lambda v: int(v, 0), required=True)
    ap.add_argument("--fbw", type=lambda v: int(v, 0), required=True)
    ap.add_argument("--psm", type=int, default=32, choices=(32, 24, 16))
    ap.add_argument("--width", type=int, default=0)
    ap.add_argument("--height", type=int, default=448)
    ap.add_argument("--x", type=int, default=0)
    ap.add_argument("--y", type=int, default=0)
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    vram = open(args.vram, "rb").read()
    width = args.width or args.fbw * 64
    block = args.fbp * 32
    rows, lit, lo, hi = [], 0, [255] * 3, [0] * 3
    for y in range(args.y, args.y + args.height):
        row = bytearray()
        for x in range(args.x, args.x + width):
            if args.psm == 16:
                (v,) = struct.unpack_from("<H", vram, addr16(block, args.fbw, x, y))
                rgb = (((v & 31) << 3), ((v >> 5 & 31) << 3), ((v >> 10 & 31) << 3))
            else:
                a = addr32(block, args.fbw, x, y)
                rgb = (vram[a], vram[a + 1], vram[a + 2])
            row += bytes(rgb)
            if any(rgb):
                lit += 1
            for i in range(3):
                lo[i], hi[i] = min(lo[i], rgb[i]), max(hi[i], rgb[i])
        rows.append(row)
    write_png(args.out, width, args.height, rows)
    if args.stats:
        print(f"fbp={args.fbp} fbw={args.fbw} psm={args.psm}: {lit}/{width * args.height} non-black, "
              f"rgb min {lo} max {hi}")


if __name__ == "__main__":
    main()
