"""Per-frame compositing: title behind the head, ocean swap on the snaps, props on the palms.

Everything timed or placed comes from the config. The scene works in output frames; the config is in seconds."""
import math
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import media as V
from .ocean import Ocean
from .sprites import blob, make_letter, make_sparkle, make_star, palette, place


def _track(hands, side, k0, k1, fallback):
    """Smoothed palm position for frames k0..k1. Missing frames are interpolated; no data at all -> fallback point."""
    ks = np.arange(k0, k1 + 1); pts = []
    for k in ks:
        p = V.palm_point(hands.get(int(k), {}).get(side, {})) if side in hands.get(int(k), {}) else None
        pts.append(p if p else (np.nan, np.nan))
    a = np.array(pts, np.float64)
    if np.isnan(a[:, 0]).all():
        if fallback is None:
            raise ValueError(f"no {side} hand was detected between frames {k0} and {k1}; give the prop a \"pos\": [x, y]")
        return {int(k): tuple(fallback) for k in ks}
    for c in range(2):
        ok = ~np.isnan(a[:, c]); a[:, c] = np.interp(ks, ks[ok], a[ok, c])
        ker = np.exp(-0.5 * (np.arange(-12, 13) / 5.0) ** 2); ker /= ker.sum()
        a[:, c] = np.convolve(np.pad(a[:, c], 12, mode="edge"), ker, mode="valid")
    return {int(k): (a[i, 0], a[i, 1]) for i, k in enumerate(ks)}


class Scene:
    def __init__(self, cfg):
        self.cfg = cfg
        W, H, FPS = cfg.width, cfg.height, cfg.fps
        self.W, self.H, self.FPS = W, H, FPS
        work, mdir = cfg.work, cfg.matte_dir
        self.mdir = mdir
        rng = np.random.default_rng(cfg["seed"])
        hands = V.load_hands(mdir)

        # == ocean (background swap between two snaps)
        oc = cfg["ocean"]
        self.ocean = None
        if oc:
            self.plate, self.ok = np.load(os.path.join(work, "plate.npy")), np.load(os.path.join(work, "plate_ok.npy"))
            self.ocean = Ocean(W, H, rng, horizon=oc["horizon"], sun=tuple(oc["sun"]))
            self.k_in, self.k_out, self.wipe = cfg.frames(oc["in"]), cfg.frames(oc["out"]), max(1, cfg.frames(oc["wipe"]))
            self.orig_in = self._origins(oc["in_origins"], hands, self.k_in)
            self.orig_out = self._origins(oc["out_origins"], hands, self.k_out)
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            self.d_in = np.minimum.reduce([np.hypot(xx - x, yy - y) for x, y in self.orig_in])
            self.d_out = np.minimum.reduce([np.hypot(xx - x, yy - y) for x, y in self.orig_out])
            self.daylight = np.array([1.0, 1.015, 1.05], np.float32) * 1.03      # a little daylight on the person

        # == title behind the head
        ti = cfg["title"]
        self.title = None
        if ti:
            font_path = cfg.font_of(ti["font"])
            im = Image.new("L", (W, H), 0); size = 40
            target = ti["width_frac"] * W
            while ImageDraw.Draw(im).textlength(ti["text"], font=ImageFont.truetype(font_path, size)) < target and size < H:
                size += 4
            ImageDraw.Draw(im).text((W // 2, ti["top"]), ti["text"], font=ImageFont.truetype(font_path, size), anchor="mt", fill=255)
            self.title = np.asarray(im, np.float32) / 255
            self.title_sh = cv2.GaussianBlur(self.title, (0, 0), 16) * 0.16
            self.title_end, self.title_fade = cfg.frames(ti["end"]), max(1, cfg.frames(ti["fade"]))

        # == props on the palms
        self.spk = make_sparkle()
        self.vanish = cfg.frames(cfg["vanish"]) if cfg["vanish"] is not None else None
        self.props = []
        for i, p in enumerate(cfg["props"]):
            colors = palette(p["colors"], "gold" if p["kind"] == "star" else "pink")
            sprite = make_star(colors) if p["kind"] == "star" else make_letter(p["text"], cfg.font_of(p["font"]), colors)
            land = cfg.frames(p["at"])
            fly = land - max(1, cfg.frames(p["fly_time"])) if p["enter"] == "fly" else None
            start = fly if fly is not None else land
            prop = dict(i=i, sprite=sprite, glow=tuple(colors["glow"]), hand=p["hand"], land=land, fly=fly, start=start,
                        enter=p["enter"], fly_from=tuple(p["fly_from"]), offset=tuple(p["offset"]), size=float(p["size"]),
                        seed=2 * i, pos=tuple(p["pos"]) if p.get("pos") else None)
            prop["anchor"] = _track(hands, p["hand"], start - 4, self.vanish + 12, prop["pos"])
            self.props.append(prop)
        # sparkle banks: one per prop entrance, one shared for the vanish (same rng order as the original edit)
        self.bursts = {f"p{p['i']}": [(rng.uniform(0, 6.28), rng.uniform(0.5, 1.0), rng.uniform(0.35, 1.0)) for _ in range(16)] for p in self.props}
        self.bursts["v"] = [(rng.uniform(0, 6.28), rng.uniform(0.5, 1.0), rng.uniform(0.35, 1.0)) for _ in range(16)]
        self.tw = [(rng.uniform(0, 6.28), rng.uniform(150, 215), rng.uniform(0.3, 0.7), int(rng.integers(0, 400))) for _ in range(60)]

    def _origins(self, spec, hands, k):
        """Where the wipe starts: explicit pixel points, or the palms of whichever hands are visible at the snap frame."""
        if spec != "hands":
            return [tuple(p) for p in spec]
        pts = [p for p in (V.hand_at(hands, k, "left"), V.hand_at(hands, k, "right")) if p]
        if not pts:
            print(f"  no hands found at frame {k}; wipe starts from the centre. Give ocean.in_origins / out_origins to place it.")
            pts = [(self.W / 2, self.H / 2)]
        return pts

    def needs_matte(self, k):
        t = self.title is not None and k < self.title_end + self.title_fade
        o = self.ocean is not None and self.k_in <= k < self.k_out + self.wipe + 1
        return t or o

    # == sparkle helpers
    def burst(self, f, name, cx, cy, a):
        if not 0 <= a < 0.8: return
        for ang, dist, sz in self.bursts[name]:
            r = 70 + 250 * dist * (1 - math.exp(-3.5 * a))
            s = sz * math.sin(math.pi * a / 0.8) ** 0.7
            place(f, self.spk, cx + r * math.cos(ang), cy + r * math.sin(ang) + 60 * a * a, s, 0, 1.0, add=True)

    def twinkle(self, f, k, cx, cy, seed):
        for ang, r, sz, ph in self.tw[seed::2]:
            a = ((k + ph) % 75) / 13.0
            if a < 1: place(f, self.spk, cx + r * math.cos(ang), cy + r * math.sin(ang) * 0.85, sz * math.sin(math.pi * a), 0, 0.95, add=True)

    def obj(self, f, k, prop, pos):
        """A landed prop: bouncy scale-in, gentle sway and bob, glow, sparkles, then the vanish poof."""
        FPS = self.FPS; seed = prop["seed"]; spr = prop["sprite"]; glowc = prop["glow"]
        t = k / FPS; a = (k - prop["land"]) / FPS; cx, cy = pos
        sc = prop["size"] * (1 + 0.30 * math.exp(-5.5 * a) * math.cos(11 * a)) * min(1.0, a / 0.10 + 0.25)
        rot = 6.5 * math.sin(2 * math.pi * 0.42 * t + seed); cy += 9 * math.sin(2 * math.pi * 0.55 * t + seed * 2)
        if k >= self.vanish + seed:
            v = (k - self.vanish - seed) / 8.0
            if v >= 1:
                self.burst(f, "v", cx, cy, (k - self.vanish - seed) / FPS - 0.1); return
            sc *= (1 + 0.25 * math.sin(math.pi * min(v * 2, 1))) * (1 - v * v); rot += 160 * v * v; cy -= 60 * v
            blob(f, cx, cy, 120, (1, 1, 1), 0.7 * math.sin(math.pi * v))
        blob(f, cx, cy, 150, glowc, 0.85 * math.exp(-4.0 * a) + 0.16)
        place(f, spr, cx, cy, sc, rot, 1.0)
        self.burst(f, f"p{prop['i']}", cx, cy, a)
        if a > 0.8 and k < self.vanish: self.twinkle(f, k, cx, cy, seed)

    # == the frame
    def frame(self, k, I):
        FPS = self.FPS
        A = V.load_matte(self.mdir, k) if self.needs_matte(k) else None
        out = I
        if self.ocean is not None and self.k_in <= k < self.k_out + self.wipe + 1:
            alpha, B = V.refine(I, A, self.plate, self.ok)
            sea = self.ocean.render((k - self.k_in) / FPS)
            lit = np.clip(I * self.daylight, 0, 1)
            comp = V.swap_background(lit, alpha, B * self.daylight, sea)
            wrap = cv2.GaussianBlur(sea, (0, 0), 20) * (cv2.GaussianBlur(1 - alpha, (0, 0), 5) * alpha)[..., None] * 0.35
            comp = np.clip(comp + wrap * (1 - comp), 0, 1)
            if k < self.k_in + self.wipe:
                p = (k - self.k_in + 1) / self.wipe; r = 2300 * (1 - (1 - p) ** 1.6); d = self.d_in; w = np.clip((r - d) / 70 + 0.5, 0, 1)
            elif k >= self.k_out:
                p = (k - self.k_out + 1) / self.wipe; r = 2300 * (1 - (1 - p) ** 1.6); d = self.d_out; w = 1 - np.clip((r - d) / 70 + 0.5, 0, 1)
            else:
                w = None
            if w is None:
                out = comp
            else:
                out = I * (1 - w[..., None]) + comp * w[..., None]
                ring = np.exp(-((r - d) / 38) ** 2)[..., None] * (1 - p) ** 0.6 * (1 - 0.75 * alpha[..., None])
                out = 1 - (1 - out) * (1 - ring * np.array([0.85, 0.97, 1.0], np.float32) * 0.9)
                for (x, y) in (self.orig_in if k < self.k_out else self.orig_out):
                    blob(out, x, y, 60 + 200 * p, (1, 1, 1), 0.8 * (1 - p) ** 2)
        out = np.ascontiguousarray(out, np.float32).copy()
        if self.title is not None and k < self.title_end + self.title_fade:
            op = min(1, (k + 2) / 6) * min(1, (self.title_end + self.title_fade - k) / self.title_fade)
            m = np.clip(cv2.GaussianBlur(cv2.dilate(A, np.ones((5, 5), np.uint8)), (0, 0), 1.2) * 1.15, 0, 1)
            tt = (self.title * op * (1 - m))[..., None]; ts = (self.title_sh * op * (1 - m))[..., None]
            out = out * (1 - ts); out = out * (1 - tt) + tt
        for prop in self.props:
            if not (prop["start"] <= k < self.vanish + 40):
                continue
            anc = prop["anchor"]; ax, ay = anc.get(k, anc[max(anc)])
            pos = (ax + prop["offset"][0], ay + prop["offset"][1])
            if prop["fly"] is not None and k < prop["land"]:
                p = (k - prop["fly"] + 1) / (prop["land"] - prop["fly"]); e = p ** 1.4
                sx, sy = prop["fly_from"]
                for j in range(7, 0, -1):                                   # comet tail
                    q = max(0, e - j * 0.035)
                    blob(out, sx + (pos[0] - sx) * q, sy + (pos[1] - sy) * q - 120 * math.sin(math.pi * q) * 0.5, 30 + 4 * j, (1, 0.93, 0.6), 0.5 * (1 - j / 8) * p)
                place(out, prop["sprite"], sx + (pos[0] - sx) * e, sy + (pos[1] - sy) * e - 60 * math.sin(math.pi * e), prop["size"] * (0.55 + 0.45 * e), -300 * (1 - e))
            else:
                if prop["enter"] == "pop":                                  # rises out of the palm
                    a = (k - prop["land"]) / FPS
                    pos = (pos[0], pos[1] + 170 * (1 - min(1, a / 0.22)) ** 2)
                self.obj(out, k, prop, pos)
        return out
