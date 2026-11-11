"""Sound effects synthesised from scratch in numpy: whoosh on the snaps, a sea bed while the ocean is up,
a chime when a prop lands, a pop when one rises out of the palm, a descending chime on the vanish.
Timings follow the config, so the sound always lines up with the picture."""
import wave

import numpy as np

from .media import smoothstep

C = [2093.0, 2637.0, 3136.0, 3951.0, 4186.0, 5274.0]      # C7 E7 G7 B7 C8 E8


def render_sfx(cfg, path, dur, sr=48000):
    n = int(dur * sr); t = np.arange(n) / sr; out = np.zeros(n, np.float32); r = np.random.default_rng(3)

    def add(sig, at):
        i = int(at * sr); j = min(n, i + len(sig))
        if j > i: out[i:j] += sig[:j - i]

    def lp(x, fc):
        X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / sr); return np.fft.irfft(X / (1 + (f / fc) ** 4), len(x)).astype(np.float32)

    def bp(x, lo, hi):
        X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / sr)
        return np.fft.irfft(X * (1 / (1 + (lo / np.maximum(f, 1)) ** 4)) / (1 + (f / hi) ** 4), len(x)).astype(np.float32)

    def whoosh(d=0.55):
        m = int(d * sr); x = r.standard_normal(m).astype(np.float32); e = np.sin(np.pi * np.arange(m) / m) ** 2
        return (bp(x, 400, 2600) * e * 0.10 + bp(x, 1500, 7000) * e ** 3 * 0.05)

    def chime(notes, gap=0.045, dec=0.5, g=0.035):
        m = int((len(notes) * gap + dec * 3) * sr); x = np.zeros(m, np.float32); tt = np.arange(m) / sr
        for i, fq in enumerate(notes):
            d = np.clip(tt - i * gap, 0, None); on = tt >= i * gap
            x += on * np.exp(-d / dec * 3.2) * (np.sin(2 * np.pi * fq * d) + 0.35 * np.sin(2 * np.pi * fq * 2.01 * d)) * g * np.minimum(1, d / 0.004)
        return x

    def pop():
        m = int(0.12 * sr); tt = np.arange(m) / sr; fq = 520 * np.exp(-tt * 14) + 180
        return (np.sin(2 * np.pi * np.cumsum(fq) / sr) * np.exp(-tt * 32) * 0.16).astype(np.float32)

    oc = cfg["ocean"]
    if oc:
        s1, s2 = cfg.frames(oc["in"]) / cfg.fps, cfg.frames(oc["out"]) / cfg.fps
        add(whoosh(), s1 - 0.03); add(whoosh(), s2 - 0.03)
        sea = lp(r.standard_normal(n).astype(np.float32), 900) * (0.55 + 0.45 * np.sin(2 * np.pi * 0.21 * t + 1) ** 2) \
            + bp(r.standard_normal(n).astype(np.float32), 2500, 8000) * 0.12 * np.sin(2 * np.pi * 0.13 * t) ** 2
        env = smoothstep(t, s1, s1 + 0.5) * (1 - smoothstep(t, s2, s2 + 0.45))
        out += (sea / np.abs(sea).max() * 0.085 * env).astype(np.float32)
    for p in cfg["props"]:
        land = cfg.frames(p["at"]) / cfg.fps
        if p["enter"] == "fly":
            add(chime(C[:5]), land - 0.12)
        else:
            add(pop(), land); add(chime([C[1], C[3], C[5]], 0.05), land + 0.05)
    if cfg["props"] and cfg["vanish"] is not None:
        v = cfg.frames(cfg["vanish"]) / cfg.fps
        add(chime(C[4::-1], 0.035, 0.35), v); add(whoosh(0.3) * 0.6, v)
    out *= float(cfg["sfx"]["gain"])
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()
    print("sfx peak", round(float(np.abs(out).max()), 3))
