#!/usr/bin/env python3
"""Summarise periodic screenshots without opening them.

usage: frames_report.py <frames-dir> [--crop x,y,w,h]

For every frame_NNNNNN.png prints the mean brightness and the share of lit pixels (> 8/255) of
a crop of the picture (default: the 640x448 game area at the window centre), plus "=" when the
crop is identical to the previous frame, so black screens, frozen frames and new content stand
out in the pipeline log. Needs ffmpeg.
"""
import hashlib
import subprocess
import sys
from pathlib import Path


def gray_crop(path, crop):
    x, y, w, h = crop
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(path), "-vf", f"crop={w}:{h}:{x}:{y}",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True, capture_output=True).stdout
    return raw


def main():
    frames = Path(sys.argv[1])
    crop = (148, 200, 640, 448)
    if "--crop" in sys.argv:
        crop = tuple(int(v) for v in sys.argv[sys.argv.index("--crop") + 1].split(","))
    previous = None
    row = []
    for path in sorted(frames.glob("frame_*.png")):
        try:
            data = gray_crop(path, crop)
        except subprocess.CalledProcessError:
            continue
        if not data:
            continue
        digest = hashlib.md5(data).digest()
        mean = sum(data) / len(data)
        lit = 100.0 * sum(1 for b in data if b > 8) / len(data)
        frame = int(path.stem.split("_")[1])
        row.append(f"{frame}:{mean:.0f}/{lit:.0f}%{'=' if digest == previous else ''}")
        previous = digest
    print("frames (frame:mean/lit%, '=' same as previous):")
    for i in range(0, len(row), 10):
        print("  " + " ".join(row[i:i + 10]))


if __name__ == "__main__":
    main()
