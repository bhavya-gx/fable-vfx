"""Puffy 3D-looking sprites (a star, a letter) built from a flat mask, plus sparkles, glow blobs and compositing."""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .media import smoothstep

PALETTES = {
    "gold": {"top": (1.0, 0.90, 0.30), "bottom": (1.0, 0.66, 0.10), "side": (0.86, 0.45, 0.04), "glow": (1.0, 0.95, 0.70)},
    "pink": {"top": (1.0, 0.62, 0.78), "bottom": (0.96, 0.36, 0.60), "side": (0.72, 0.16, 0.40), "glow": (1.0, 0.80, 0.90)},
    "sky":  {"top": (0.70, 0.90, 1.0), "bottom": (0.30, 0.65, 1.0), "side": (0.10, 0.35, 0.80), "glow": (0.80, 0.92, 1.0)},
    "mint": {"top": (0.75, 1.0, 0.85), "bottom": (0.35, 0.88, 0.60), "side": (0.10, 0.55, 0.35), "glow": (0.85, 1.0, 0.92)},
}


def palette(spec, default):
    """spec: a palette name, or a dict with top/bottom/side (and optional glow) as 0..1 RGB triples."""
    if spec is None:
        return PALETTES[default]
    if isinstance(spec, str):
        if spec not in PALETTES:
            raise ValueError(f"unknown colour {spec!r}; choose from {', '.join(PALETTES)} or give top/bottom/side")
        return PALETTES[spec]
    p = dict(PALETTES[default]); p.update(spec)
    return p


def puffy(mask, top, bot, side, r=46, depth=16):
    """mask: float 0..1 (S x S). Returns straight-alpha RGBA float sprite with bevel shading + extruded side."""
    S = mask.shape[0]
    dt = cv2.distanceTransform((mask > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    u = np.clip(dt / r, 0, 1); hgt = np.sqrt(np.clip(1 - (1 - u) ** 2, 0, 1)) * r
    hgt = cv2.GaussianBlur(hgt, (0, 0), 3.5)
    gx = cv2.Sobel(hgt, cv2.CV_32F, 1, 0, ksize=3) / 8; gy = cv2.Sobel(hgt, cv2.CV_32F, 0, 1, ksize=3) / 8
    n = np.stack([-gx * 1.6, -gy * 1.6, np.ones_like(gx)], -1); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    L = np.array([-0.45, -0.62, 0.64]); L /= np.linalg.norm(L)
    Hv = L + np.array([0, 0, 1.0]); Hv /= np.linalg.norm(Hv)
    diff = np.clip(n @ L, 0, 1); spec = np.clip(n @ Hv, 0, 1) ** 46
    g = np.linspace(0, 1, S, dtype=np.float32)[:, None, None]
    alb = np.array(top, np.float32) * (1 - g) + np.array(bot, np.float32) * g
    face = alb * (0.50 + 0.66 * diff[..., None]) + spec[..., None] * 0.75
    face += (1 - n[..., 2:3]) * np.clip(-n[..., 1:2], 0, 1) * 0.25          # top rim light
    rgb = np.zeros((S, S, 3), np.float32); a = np.zeros((S, S), np.float32)
    for i in range(depth, 0, -1):                                           # extruded side, back to front
        M = np.float32([[1, 0, i * 0.45], [0, 1, i * 0.8]])
        m = cv2.warpAffine(mask, M, (S, S))
        sc = np.array(side, np.float32) * (0.72 + 0.28 * (1 - i / depth))
        rgb = rgb * (1 - m[..., None]) + sc * m[..., None]; a = np.maximum(a, m)
    rgb = rgb * (1 - mask[..., None]) + face * mask[..., None]; a = np.maximum(a, mask)
    return np.dstack([np.clip(rgb, 0, 1), a]).astype(np.float32)


def make_star(colors, S=420):
    im = Image.new("L", (S * 2, S * 2), 0); c = S
    pts = []
    for i in range(10):
        rr = (S * 0.84) if i % 2 == 0 else (S * 0.84 * 0.52)
        ang = -math.pi / 2 + i * math.pi / 5
        pts.append((c + rr * math.cos(ang), c + rr * math.sin(ang) + S * 0.04))
    ImageDraw.Draw(im).polygon(pts, fill=255)
    m = cv2.GaussianBlur(np.asarray(im, np.float32) / 255, (0, 0), 22)
    m = smoothstep(m, 0.44, 0.50)                                           # rounded tips
    m = cv2.resize(m, (S, S), interpolation=cv2.INTER_AREA)
    return puffy(m, colors["top"], colors["bottom"], colors["side"])


def make_letter(text, font_path, colors, S=420):
    im = Image.new("L", (S, S), 0)
    size = int(S * 0.98)
    f = ImageFont.truetype(font_path, size)
    d = ImageDraw.Draw(im)
    while d.textlength(text, font=f) > S * 0.92 and size > 40:          # longer text shrinks to fit the tile
        size -= 8; f = ImageFont.truetype(font_path, size)
    d.text((S // 2 - 6, S // 2 - 8), text, font=f, anchor="mm", fill=255)
    m = cv2.GaussianBlur(np.asarray(im, np.float32) / 255, (0, 0), 1.2)
    return puffy(m, colors["top"], colors["bottom"], colors["side"], r=34)


def make_sparkle(S=96):
    y, x = np.mgrid[-S // 2:S // 2, -S // 2:S // 2].astype(np.float32)
    ax, ay = np.abs(x), np.abs(y)
    v = np.maximum(np.exp(-ax / 1.6 - ay / 15), np.exp(-ay / 1.6 - ax / 15)) + np.exp(-(x * x + y * y) / 30) * 0.9
    return np.clip(v, 0, 1)


def blob(frame, cx, cy, rad, col, amt):
    """Soft glow, screen-blended."""
    if amt <= 0.003: return
    H, W = frame.shape[:2]
    x0, x1, y0, y1 = int(max(0, cx - 3 * rad)), int(min(W, cx + 3 * rad)), int(max(0, cy - 3 * rad)), int(min(H, cy + 3 * rad))
    if x1 <= x0 or y1 <= y0: return
    y, x = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    g = np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * rad * rad))[..., None] * amt
    roi = frame[y0:y1, x0:x1]; roi[:] = 1 - (1 - roi) * (1 - g * np.array(col, np.float32))


def place(frame, spr, cx, cy, scale, rot=0.0, op=1.0, add=False):
    """Composite a sprite (RGBA float, or a single-channel light map with add=True) at (cx, cy)."""
    if scale <= 0.01 or op <= 0.01: return
    H, W = frame.shape[:2]
    sh, sw = spr.shape[:2]; half = int(max(sw, sh) * scale * 0.75) + 2
    x0, y0 = int(round(cx)) - half, int(round(cy)) - half
    M = cv2.getRotationMatrix2D((sw / 2, sh / 2), rot, scale)
    M[0, 2] += cx - x0 - sw / 2; M[1, 2] += cy - y0 - sh / 2
    p = cv2.warpAffine(spr, M, (2 * half, 2 * half), flags=cv2.INTER_LINEAR if scale > 0.6 else cv2.INTER_AREA)
    X0, Y0, X1, Y1 = max(0, x0), max(0, y0), min(W, x0 + 2 * half), min(H, y0 + 2 * half)
    if X1 <= X0 or Y1 <= Y0: return
    p = p[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0]; roi = frame[Y0:Y1, X0:X1]
    if add:
        roi[:] = 1 - (1 - roi) * (1 - p[..., None] * op)
    else:
        a = p[..., 3:4] * op
        sh_ = cv2.GaussianBlur(p[..., 3], (0, 0), 9)[..., None] * 0.22 * op       # soft contact shadow / separation
        roi[:] = roi * (1 - sh_); roi[:] = roi * (1 - a) + p[..., :3] * a
