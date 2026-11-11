"""Frame IO through ffmpeg, mattes and hand joints from tools/matte.swift, clean plate, edge refinement."""
import json
import os
import subprocess

import cv2
import numpy as np

# Set once from the config by configure(); every helper below reads them at call time.
W, H, FPS = 1920, 1080, 30.0
MATTE_OFFSET = 1          # matte.swift (AVFoundation) hands back one extra leading frame vs ffmpeg


def configure(width, height, fps, matte_offset=1):
    global W, H, FPS, MATTE_OFFSET
    W, H, FPS, MATTE_OFFSET = int(width), int(height), float(fps), int(matte_offset)


def read_frames(path, start=0, count=None):
    """Yield (index, float32 RGB 0..1) frames of a bt709 video at the configured size."""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vf",
           f"scale={W}:{H}:in_color_matrix=bt709:in_range=tv:out_range=full,format=rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=W * H * 3 * 4)
    n = W * H * 3
    i = 0
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            if i >= start:
                yield i, np.frombuffer(buf, np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0
            i += 1
            if count is not None and i >= start + count:
                break
    finally:
        p.kill(); p.stdout.close(); p.wait()     # kill first, so a partial read does not make ffmpeg complain about a broken pipe


def read_frame(path, k):
    for _, f in read_frames(path, k, 1):
        return f
    raise IndexError(f"frame {k} is past the end of {path}")


def count_frames(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                          "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return int(out or 0)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out)


class Writer:
    """Encode float RGB frames to a high quality bt709 h264 file."""
    def __init__(self, path, crf=14, preset="medium"):
        self.p = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
             "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", path],
            stdin=subprocess.PIPE)

    def write(self, rgb):
        self.p.stdin.write((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())

    def close(self):
        self.p.stdin.close(); self.p.wait()


def load_matte(mdir, k):
    path = os.path.join(mdir, f"m_{k + MATTE_OFFSET:05d}.png")
    m = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if m is None:
        raise FileNotFoundError(f"no matte for frame {k}: {path}. Run the matte step first.")
    return cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.0


def load_hands(mdir):
    """frame -> {'left': screen-left hand, 'right': screen-right hand}; each a dict of joint -> (x, y, conf) in pixels."""
    out = {}
    path = os.path.join(mdir, "hands.jsonl")
    if not os.path.exists(path):
        return out
    for line in open(path):
        d = json.loads(line)
        hs = []
        for h in d["hands"]:
            pts = {k: (v[0] * W, v[1] * H, v[2]) for k, v in h["pts"].items()}
            good = [p for p in pts.values() if p[2] > 0.3]
            if len(good) >= 5:
                hs.append((float(np.mean([p[0] for p in good])), pts))
        e = {}
        for cx, pts in hs:
            e["left" if cx < W / 2 else "right"] = pts
        out[d["f"] - MATTE_OFFSET] = e
    return out


def palm_point(pts):
    """Centre of the palm: wrist plus the four finger knuckles."""
    ks = ["VNHLKWRI", "VNHLKIMCP", "VNHLKMMCP", "VNHLKRMCP", "VNHLKPMCP"]
    g = [pts[k] for k in ks if k in pts and pts[k][2] > 0.3]
    if len(g) < 3:
        return None
    return float(np.mean([p[0] for p in g])), float(np.mean([p[1] for p in g]))


def hand_at(hands, k, side, window=6):
    """Palm point of `side` ('left'/'right') at frame k, looking a few frames either way if that frame has no hand."""
    for dk in range(window + 1):
        for kk in (k - dk, k + dk):
            p = palm_point(hands.get(kk, {}).get(side, {})) if side in hands.get(kk, {}) else None
            if p:
                return p
    return None


def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _disk(r):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def build_plate(video, mdir, step=4, grow=22):
    """Clean plate of the empty room: mean of every pixel over the frames where the person is not covering it."""
    acc = np.zeros((H, W, 3), np.float64); cnt = np.zeros((H, W), np.float64)
    ker = _disk(grow)
    for k, I in read_frames(video):
        if k % step:
            continue
        a = load_matte(mdir, k)
        bg = (cv2.dilate((a > 0.02).astype(np.uint8), ker) == 0)
        acc[bg] += I[bg]; cnt[bg] += 1
    ok = cnt >= 3
    plate = np.zeros((H, W, 3), np.float32)
    plate[ok] = (acc[ok] / cnt[ok][:, None]).astype(np.float32)
    # fill the never-seen area (behind the person) by pushing known colours inward, so lookups never hit black
    filled = plate.copy(); known = ok.astype(np.float32)
    for s in (9, 25, 61, 151, 301):
        num = cv2.GaussianBlur(filled * known[..., None], (0, 0), s)
        den = cv2.GaussianBlur(known, (0, 0), s)
        est = num / np.maximum(den, 1e-4)[..., None]
        take = (known < 0.5) & (den > 0.02)
        filled[take] = est[take]; known[take] = 1.0
    return filled, ok


def refine(I, A, plate, plate_ok, r_in=5, r_out=14):
    """Vision matte -> detailed alpha. Inside a band around the silhouette, alpha comes from where the pixel sits
    between the room colour behind it (clean plate) and the person's colour next to it. Returns (alpha, B) where B is
    the room colour estimate used, so the caller can swap the background with I + (1 - alpha) * (new - B)."""
    fg_core = cv2.erode((A > 0.9).astype(np.uint8), _disk(r_in)).astype(bool)
    near = cv2.dilate((A > 0.1).astype(np.uint8), _disk(r_out)).astype(bool)
    band = near & ~fg_core
    # foreground colour estimate: the person's own pixels spread outward into the band
    m = fg_core.astype(np.float32)
    F = np.zeros_like(I); have = np.zeros((H, W), bool)
    for s in (6, 16, 40):
        den = cv2.GaussianBlur(m, (0, 0), s)
        num = cv2.GaussianBlur(I * m[..., None], (0, 0), s)
        take = ~have & (den > 0.03)
        F[take] = (num / np.maximum(den, 1e-4)[..., None])[take]; have |= take
    # background: clean plate, exposure matched to this frame; where the plate never saw the pixel, use this frame's nearby background
    bg_core = ~near
    sel = bg_core & plate_ok
    ys, xs = np.nonzero(sel[::8, ::8])
    gain = np.median(I[::8, ::8][ys, xs] / np.maximum(plate[::8, ::8][ys, xs], 0.02), axis=0) if len(ys) > 500 else np.ones(3)
    B = plate * np.clip(gain, 0.9, 1.1).astype(np.float32)
    mb = bg_core.astype(np.float32)
    den = cv2.GaussianBlur(mb, (0, 0), 14); num = cv2.GaussianBlur(I * mb[..., None], (0, 0), 14)
    local = num / np.maximum(den, 1e-4)[..., None]
    use_local = ~plate_ok & (den > 0.05)
    B = np.where(use_local[..., None], local, B)
    d = F - B
    dd = (d * d).sum(-1)
    ac = np.clip(((I - B) * d).sum(-1) / (dd + 1e-4), 0, 1)
    conf = smoothstep(np.sqrt(dd), 0.07, 0.20) * have
    a = A * (1 - conf) + ac * conf
    # bounds: clearly-inside stays solid, far outside stays empty
    lower = smoothstep(cv2.erode(A, _disk(3)), 0.6, 0.97)
    upper = smoothstep(cv2.GaussianBlur(cv2.dilate(A, _disk(r_out - 4)), (0, 0), 3), 0.02, 0.35)
    a = np.clip(np.maximum(a, lower), 0, upper)
    alpha = np.where(fg_core, 1.0, np.where(band, a, 0.0)).astype(np.float32)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.6)
    return alpha, B


def swap_background(I, alpha, B, new):
    """Replace the room with `new` behind the person. Semi-transparent edge pixels lose the room colour instead of carrying it."""
    a = alpha[..., None]
    out = I + (1 - a) * (new - B)
    solid = alpha > 0.995
    empty = alpha < 0.005
    out = np.where(solid[..., None], I, np.where(empty[..., None], new, out))
    return np.clip(out, 0, 1)
