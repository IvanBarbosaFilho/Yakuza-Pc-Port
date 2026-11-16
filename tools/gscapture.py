#!/usr/bin/env python3
"""Summarise a GS frame capture (PS2X_GS_CAPTURE=<vsync>[+<frames>]:<path>) as render passes.

usage: gscapture.py <path>.prims [--pass N] [--render N --out DIR] [--track FBP[:FBW[:H]],...]

Consecutive primitives drawn with the same state (target, texture, blend, test, prim type,
scissor) form a pass. Each pass prints its target (fbp/psm/mask), texture (tbp0/psm/size),
ALPHA as a blend equation, TEST, the screen area covered and sample vertex colours/UVs.
Passes that sample from inside a render target written earlier in the capture are marked
"<- reads fbp N": that is how PS2 games do blur/glow/bloom (draw the frame back into itself
with sprites), the usual suspects when a post-processed picture looks wrong.
--pass N prints every primitive of pass N. With PS2X_GS_CAPTURE_VRAM=1 the capture also has
VRAM before every pass; --render N writes pass N's target before and after it as PNGs (and its
texture source when the texture is a render target). --track 256,128 follows CT32 buffers through
the frame: per pass, lit pixels, brightest channel, mean, and how many pixels the pass changed,
next to the pass's draw; the first pass that makes a buffer go wrong stands out.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from collections import OrderedDict

TOKEN = re.compile(r"(\w+)=\(([^)]*)\)|(\w+)=([^\s()]+)")
PRIM_TYPES = ["point", "line", "linestrip", "tri", "tristrip", "trifan", "sprite", "?"]
PSM = {0x00: "CT32", 0x01: "CT24", 0x02: "CT16", 0x0A: "CT16S", 0x13: "T8", 0x14: "T4", 0x1B: "T8H",
       0x24: "T4HL", 0x2C: "T4HH", 0x30: "Z32", 0x31: "Z24", 0x32: "Z16", 0x3A: "Z16S"}
ABCD = ["Cs", "Cd", "0", "?"]
ABC_C = ["As", "Ad", "FIX", "?"]
# Blocks (64 words = 256 bytes) per page (2048 words) is 32; fbp counts pages, tbp0 blocks.
BLOCKS_PER_PAGE = 32


def parse(line):
    out = {}
    for m in TOKEN.finditer(line):
        if m.group(1):
            inner = {k: v for k, v in (p.split("=", 1) for p in m.group(2).split() if "=" in p)}
            if inner:
                for k, v in inner.items():
                    out[f"{m.group(1)}.{k}"] = v
            else:
                out[m.group(1)] = m.group(2)
        else:
            out[m.group(3)] = m.group(4)
    return out


def num(v):
    return int(v, 0) if v.startswith("0x") else int(v)


def blend(alpha):
    a = num(alpha)
    A, B, C, D, fix = a & 3, (a >> 2) & 3, (a >> 4) & 3, (a >> 6) & 3, (a >> 32) & 0xFF
    c = ABC_C[C] + (f"({fix})" if C == 2 else "")
    return f"({ABCD[A]}-{ABCD[B]})*{c}+{ABCD[D]}"


def test_str(test):
    t = num(test)
    out = []
    if t & 1:
        out.append(f"ate{['NEVER','ALWAYS','<','<=','==','>=','>','!='][(t >> 1) & 7]}{(t >> 4) & 0xFF}"
                   f"/fail={['KEEP','FB','ZB','RGB'][(t >> 12) & 3]}")
    if t & (1 << 14):
        out.append(f"date{(t >> 15) & 1}")
    if t & (1 << 16):
        out.append(f"z{['NEVER','ALWAYS','>=','>'][(t >> 17) & 3]}")
    return ",".join(out) or "-"


def pair(v):
    x, y = v.split(",")
    return float(x), float(y)


def pass_key(p):
    keys = ("type", "tme", "abe", "fst", "ctxt", "fbp", "fbw", "fbmsk", "psm", "zbp", "zmsk", "tex0.tbp0",
            "tex0.tbw", "tex0.psm", "tex0.tw", "tex0.th", "tex0.tfx", "tex0.tcc", "test", "alpha", "scissor")
    return tuple(p.get(k) for k in keys)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prims")
    ap.add_argument("--pass", dest="show", type=int, default=None)
    ap.add_argument("--render", type=int, default=None)
    ap.add_argument("--out", default=".")
    ap.add_argument("--track", help="CT32 buffers to follow, e.g. 256,128 or 256:8:448")
    args = ap.parse_args()

    # With per-pass VRAM the capture marks pass starts itself ("pass=N vram=..."): use those.
    passes, vram = [], []
    marked = False
    for line in open(args.prims):
        if line.startswith("pass="):
            marked = True
            passes.append([])
            vram.append(line.split("vram=", 1)[1].strip())
        elif "idx=" in line:
            p = parse(line)
            if marked:
                passes[-1].append(p)
            elif passes and pass_key(passes[-1][0]) == pass_key(p):
                passes[-1].append(p)
            else:
                passes.append([p])
    passes = [g for g in passes if g] if not marked else passes
    print(f"{sum(len(g) for g in passes)} primitives in {len(passes)} passes"
          + (" (VRAM before each pass)" if marked else ""))
    if args.render is not None:
        render(args, passes, vram)
        return
    if args.track:
        track(args, passes, vram)
        return

    written = OrderedDict()  # fbp -> first pass that wrote it
    for i, group in enumerate(passes):
        p = group[0]
        xs, ys = [], []
        for q in group:
            for v in ("v0", "v1", "v2"):
                if v in q:
                    x, y = pair(q[v])
                    xs.append(x)
                    ys.append(y)
        fbp = num(p["fbp"])
        target = f"fbp={fbp} {PSM.get(num(p['psm']), p['psm'])} w={num(p['fbw']) * 64}"
        if p["fbmsk"] != "0x0":
            target += f" msk={p['fbmsk']}"
        tex = "-"
        note = ""
        if p["tme"] == "1":
            tbp = num(p["tex0.tbp0"])
            tex = (f"tbp={tbp} {PSM.get(num(p['tex0.psm']), p['tex0.psm'])} "
                   f"{1 << num(p['tex0.tw'])}x{1 << num(p['tex0.th'])} tfx={p['tex0.tfx']} tcc={p['tex0.tcc']}")
            for wfbp in written:
                if wfbp * BLOCKS_PER_PAGE <= tbp < (wfbp + 40) * BLOCKS_PER_PAGE:
                    note = f" <- reads fbp {wfbp} (+{tbp - wfbp * BLOCKS_PER_PAGE} blocks)"
                    break
        kind = PRIM_TYPES[num(p["type"]) & 7]
        bl = blend(p["alpha"]) if p["abe"] == "1" else "opaque"
        area = f"({min(xs):.0f},{min(ys):.0f})-({max(xs):.0f},{max(ys):.0f})" if xs else "?"
        rgba = p.get("rgba0", "?")
        uv = p.get("uv0") if p.get("fst") == "1" else p.get("stq0")
        print(f"#{i:<4} {len(group):5}x {kind:9} {target:24} tex[{tex}] {bl:22} {test_str(p['test']):18} "
              f"{area} rgba0={rgba} uv0={uv} z={'off' if p['zmsk'] == '1' else 'on'}{note}")
        written.setdefault(fbp, i)
        if args.show == i:
            for q in group:
                print("      ", " ".join(f"{k}={q[k]}" for k in ("idx", "v0", "v1", "v2", "uv0", "uv1", "rgba0", "rgba1")
                                         if k in q))


def buffer_stats(data, previous):
    """(lit pixels, max channel, mean channel, changed pixels) of a CT32 byte range; the GS
    swizzle only reorders pixels inside it, so totals need no unswizzling."""
    lit = changed = total = hi = 0
    for i in range(0, len(data), 4):
        r, g, b = data[i], data[i + 1], data[i + 2]
        if r or g or b:
            lit += 1
            hi = max(hi, r, g, b)
            total += r + g + b
        if previous is not None and previous[i:i + 3] != data[i:i + 3]:
            changed += 1
    return lit, hi, total / max(1, 3 * len(data) // 4), changed


def track(args, passes, vram):
    buffers = []
    for item in args.track.split(","):
        parts = [int(x, 0) for x in item.split(":")]
        buffers.append((parts[0], parts[1] if len(parts) > 1 else 8, parts[2] if len(parts) > 2 else 512))
    if not vram:
        print("--track needs a capture made with PS2X_GS_CAPTURE_VRAM=1")
        return
    snapshots = vram + [args.prims.replace(".prims", ".after.bin")]
    print("pass   " + "".join(f"fbp {b[0]}: lit max mean changed".ljust(38) for b in buffers) + "draw")
    previous = [None] * len(buffers)
    for n, path in enumerate(snapshots):
        try:
            data = open(path, "rb").read()
        except OSError:
            continue
        cells = []
        for k, (fbp, fbw, height) in enumerate(buffers):
            region = data[fbp * 8192: fbp * 8192 + fbw * 64 * height * 4]
            lit, hi, mean, changed = buffer_stats(region, previous[k])
            previous[k] = region
            cells.append(f"{lit:8} {hi:3} {mean:6.1f} {changed:8}".ljust(38))
        draw = ""
        if 0 < n <= len(passes) and passes[n - 1]:
            p = passes[n - 1][0]
            draw = (f"#{n - 1} {len(passes[n - 1])}x {PRIM_TYPES[num(p['type']) & 7]} -> fbp {p['fbp']}"
                    + (f" tex {p['tex0.tbp0']}" if p.get("tme") == "1" else "")
                    + (f" {blend(p['alpha'])}" if p.get("abe") == "1" else ""))
        label = "after" if n == len(vram) else f"<#{n}"
        print(f"{label:6} " + "".join(cells) + draw)


def render(args, passes, vram):
    """PNGs of pass N's target before/after it, and of its texture when that is a render target."""
    n = args.render
    p = passes[n][0]
    before = vram[n]
    after = vram[n + 1] if n + 1 < len(vram) else args.prims.replace(".prims", ".after.bin")
    gsvram = Path(__file__).resolve().parent / "gsvram.py"
    out = Path(args.out)
    psm = {0x00: "32", 0x01: "24", 0x02: "16", 0x0A: "16"}

    def png(dump, name, fbp, fbw, fpsm, height=512):
        target = out / f"pass{n}_{name}.png"
        subprocess.run([sys.executable, "-I", str(gsvram), dump, str(target), "--fbp", str(fbp), "--fbw", str(fbw),
                        "--psm", psm.get(fpsm, "32"), "--width", str(fbw * 64), "--height", str(height)], check=False)
        print(target)

    fbp, fbw, fpsm = num(p["fbp"]), num(p["fbw"]), num(p["psm"])
    png(before, "target_before", fbp, fbw, fpsm)
    png(after, "target_after", fbp, fbw, fpsm)
    if p["tme"] == "1" and num(p["tex0.tbp0"]) % BLOCKS_PER_PAGE == 0:
        png(before, "texture", num(p["tex0.tbp0"]) // BLOCKS_PER_PAGE, max(1, num(p["tex0.tbw"])),
            num(p["tex0.psm"]), 1 << num(p["tex0.th"]))


if __name__ == "__main__":
    main()
