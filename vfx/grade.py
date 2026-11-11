"""Colour grade as a 3D LUT (.cube), so ffmpeg (lut3d) and numpy apply the exact same look.

Look: "clean room". Phone footage lit by daylight from the front (skin is fine) and a tungsten ceiling lamp
behind (walls go mustard). So: pull saturation out of the yellow hue band only, leave skin hues alone,
lift the mids a little, keep blacks and whites pinned. The three numbers are in the config under "grade".
"""
import numpy as np


def _hue_deg(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn + 1e-6
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4))
    return h * 60.0, d / (mx + 1e-6)


def _smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def grade(rgb, yellow_desat=0.50, yellow_centre=44.0, mid_lift=0.05):
    """rgb: float array [..., 3] in 0..1 (display referred). Returns same shape."""
    rgb = np.asarray(rgb, np.float32)
    hue, sat = _hue_deg(rgb)
    dist = np.abs(((hue - yellow_centre + 180) % 360) - 180)
    w = 1 - _smooth(dist, 13.0, 27.0)            # full effect within 13 deg, gone by 27 deg (skin sits ~30 deg away)
    w = w * _smooth(sat, 0.04, 0.16)             # ignore near-neutral pixels (unstable hue)
    y = (rgb * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    out = y + (rgb - y) * (1 - yellow_desat * w[..., None])
    out = out + 0.012 * w[..., None]             # the de-yellowed wall reads a touch brighter
    out = np.clip(out, 0, 1)
    out = out + mid_lift * 4 * out * (1 - out) * (0.55 + 0.45 * (1 - out))
    s = out * out * (3 - 2 * out)
    out = out * 0.90 + s * 0.10
    y2 = (out * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    out = y2 + (out - y2) * 0.97                 # calm overall saturation a hair so skin does not run hot
    return np.clip(out, 0, 1)


def write_cube(path, size=33, **params):
    ax = np.linspace(0, 1, size, dtype=np.float32)
    b, g, r = np.meshgrid(ax, ax, ax, indexing="ij")     # .cube: red changes fastest
    lut = grade(np.stack([r, g, b], -1).reshape(-1, 3), **params)
    with open(path, "w") as f:
        f.write(f"TITLE \"clean room\"\nLUT_3D_SIZE {size}\n")
        for v in lut:
            f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
