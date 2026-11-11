"""A procedural ocean and sky, rendered in numpy. No footage, no textures: sum-of-sines waves on a flat
sea seen from a camera a few metres up, Fresnel reflection of a gradient sky, one sun with a specular
glint, drifting noise clouds, bloom. Tunable from the config: horizon row and sun position."""
import math

import cv2
import numpy as np

from .media import smoothstep


class Ocean:
    def __init__(self, W, H, rng, horizon=600, sun=(520, 250), focal=1300.0, height_m=3.0):
        self.W, self.H = W, H
        self.yh, f, h = int(horizon), float(focal), float(height_m)
        self.f, self.h = f, h
        sx_, sy_ = sun
        ys, xs = np.mgrid[self.yh:H, 0:W].astype(np.float32)
        dy = ys - self.yh + 0.5
        self.z = h * f / dy; self.xw = (xs - W / 2) / f * self.z
        foot = self.z * self.z / (h * f)
        self.comps = []
        for i in range(13):
            lam = 0.7 * (1.42 ** i); ang = rng.uniform(-0.95, 0.95); k = 2 * math.pi / lam
            kx, kz = k * math.sin(ang), -k * math.cos(ang)
            amp = 0.011 * lam * rng.uniform(0.7, 1.2)
            att = np.clip(lam / (4 * foot), 0, 1).astype(np.float32)
            self.comps.append((kx, kz, math.sqrt(9.8 * k), amp * k * att, rng.uniform(0, 6.28)))
        vn = np.sqrt(self.xw ** 2 + h * h + self.z ** 2)
        self.V = (-self.xw / vn, h / vn, -self.z / vn)
        s = np.array([(sx_ - W / 2) / f, (self.yh - sy_) / f, 1.0]); self.S = s / np.linalg.norm(s)
        self.hor = np.array([0.80, 0.90, 0.96], np.float32); self.zen = np.array([0.20, 0.50, 0.88], np.float32)
        self.sunc = np.array([1.0, 0.93, 0.78], np.float32)
        # sky
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        elev = np.clip((self.yh - yy) / f, 0, None)
        g = np.clip(elev / 0.48, 0, 1) ** 0.6
        sky = self.hor * (1 - g[..., None]) + self.zen * g[..., None]
        d = np.hypot(xx - sx_, yy - sy_)
        self.glow = (np.exp(-(d / 46) ** 2) * 3.0 + np.exp(-d / 240) * 0.38)[..., None] * self.sunc
        self.sky = sky
        n = np.zeros((1024, 4096), np.float32)
        for o, a in ((6, 1.0), (12, 0.5), (24, 0.25), (48, 0.12), (96, 0.06)):
            n += a * cv2.resize(rng.random((o, o * 6), dtype=np.float32), (4096, 1024), interpolation=cv2.INTER_CUBIC)
        self.noise = n / n.max()
        self.haze = (1 - np.exp(-self.z / 500))[..., None]
        self.yy = yy
        self.cloud_row = sy_ + 180      # the cloud band sits a little under the sun

    def skycol(self, ry):
        g = np.clip(ry / 0.45, 0, 1) ** 0.6
        return self.hor * (1 - g[..., None]) + self.zen * g[..., None]

    def render(self, t):
        W, H = self.W, self.H
        out = self.sky.copy()
        off = int(t * 14) % 2000
        cl = cv2.resize(self.noise[:, off:off + 2048], (W, H), interpolation=cv2.INTER_LINEAR)
        band = np.clip(1.25 - np.abs(self.yy - self.cloud_row) / 300, 0, 1)
        ca = smoothstep(cl * (0.55 + 0.45 * band), 0.50, 0.78)[..., None] * 0.9
        out = out * (1 - ca) + np.array([1.0, 0.99, 0.97], np.float32) * ca
        out += self.glow * (1 - 0.6 * ca)
        sx = np.zeros_like(self.z); sz = np.zeros_like(self.z)
        for kx, kz, w, a, ph in self.comps:
            c = np.cos(kx * self.xw + kz * self.z - w * t + ph) * a
            sx += kx / math.hypot(kx, kz) * c; sz += kz / math.hypot(kx, kz) * c
        nn = np.sqrt(sx * sx + 1 + sz * sz); nx, ny, nz = -sx / nn, 1 / nn, -sz / nn
        vx, vy, vz = self.V
        ndv = np.clip(nx * vx + ny * vy + nz * vz, 0, 1)
        fres = (0.03 + 0.97 * (1 - ndv) ** 5)[..., None]
        rx, ry, rz = 2 * ndv * nx - vx, 2 * ndv * ny - vy, 2 * ndv * nz - vz
        rs = np.clip(rx * self.S[0] + ry * self.S[1] + rz * self.S[2], 0, 1)
        spec = (rs ** 380 * 7 + rs ** 28 * 0.30)[..., None]
        deep = np.array([0.015, 0.22, 0.36], np.float32) + np.array([0.02, 0.30, 0.30], np.float32) * np.clip(sx * 1.5 + 0.25, 0, 1)[..., None]
        wat = deep * (1 - fres) + self.skycol(np.abs(ry)) * fres + self.sunc * spec
        wat = wat * (1 - self.haze) + self.hor * 0.97 * self.haze
        out[self.yh:] = wat
        out = cv2.GaussianBlur(np.clip(out, 0, 1.6), (0, 0), 1.6)
        bloom = cv2.GaussianBlur(np.clip(out - 0.95, 0, None), (0, 0), 14)
        return np.clip(out + bloom * 0.8, 0, 1)
