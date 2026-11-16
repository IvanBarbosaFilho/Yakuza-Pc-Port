"""Sample Rule of Rose's movie pacing in PCSX2 over PINE: vblank counter (0x2dc290) and pictures allowed
(0x298f1c), twice a second for N seconds, then print the rate of each per second and per vblank.
usage: movierate.py <tools dir with pine.py> [seconds]"""
import sys
import time

sys.path.insert(0, sys.argv[1])
from pine import Pine  # noqa: E402

seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
pine = Pine()
samples = []
end = time.time() + seconds
while time.time() < end:
    samples.append((time.time(), pine.read(0x2dc290), pine.read(0x298f1c), pine.read(0x298f38)))
    time.sleep(0.5)
t0, v0, p0, _ = samples[0]
t1, v1, p1, _ = samples[-1]
for t, v, p, state in samples[::4]:
    print(f"t={t - t0:5.1f}s vblank={v} pictures={p} movie_state={state}")
dv, dp, dt = v1 - v0, (p1 - p0) & 0xFFFFFFFF, t1 - t0
print(f"over {dt:.1f}s: vblank {dv / dt:.1f}/s, pictures {dp / dt:.1f}/s, pictures per vblank {dp / dv if dv else 0:.3f}")
