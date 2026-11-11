#!/usr/bin/env python3
"""fable-vfx: config-driven VFX pass for a talking-head clip.

  python3 render.py CONFIG.json all                 # prep, matte, plate, render, sfx, mux
  python3 render.py CONFIG.json prep                # trim, scale, grade -> work/base.mp4 (+ voice.wav)
  python3 render.py CONFIG.json matte               # Apple Vision person matte + hand joints (macOS)
  python3 render.py CONFIG.json plate               # clean plate of the empty room
  python3 render.py CONFIG.json stills 2.5,9.6,18.4 # test frames at those seconds -> work/stills/
  python3 render.py CONFIG.json render            # the VFX video (no sound) -> work/vfx.mp4
  python3 render.py CONFIG.json render 17.5,19.5  # only those seconds, for a quick test
  python3 render.py CONFIG.json sfx                 # sound effects -> work/sfx.wav
  python3 render.py CONFIG.json mux                 # voice + sfx + speed -> the output file
  python3 render.py CONFIG.json sheet               # contact sheet of the output, to check it
  python3 render.py CONFIG.json hands 9.4           # where the hands are at that second (for origins / pos)
"""
import argparse
import os
import platform
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from vfx.config import Config          # noqa: E402
from vfx import media as V             # noqa: E402


def sh(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def step_prep(cfg):
    """Trim, scale to the output size, apply the grade LUT, drop audio -> base.mp4. Voice goes to voice.wav."""
    os.makedirs(cfg.work, exist_ok=True)
    pr, fmt = cfg["prep"], cfg["format"]
    vf = [f"scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=increase", f"crop={cfg.width}:{cfg.height}", f"fps={fmt['fps']}"]
    if pr["grade"]:
        from vfx.grade import write_cube
        cube = os.path.join(cfg.work, "grade.cube")
        write_cube(cube, **cfg["grade"])
        vf.append(f"lut3d={cube}")
    tr = ["-ss", pr["start"]] + (["-t", pr["duration"]] if pr["duration"] else [])
    sh(["ffmpeg", "-y", "-v", "error", *tr, "-i", cfg.source, "-vf", ",".join(vf), "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", pr["crf"], "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", cfg.base])
    sh(["ffmpeg", "-y", "-v", "error", *tr, "-i", cfg.source, "-vn", "-map", "0:a:0", "-ac", "1", "-ar", "48000",
        "-c:a", "pcm_s16le", os.path.join(cfg.work, "voice.wav")])
    print(f"  base: {V.duration(cfg.base):.2f}s, {V.count_frames(cfg.base)} frames")


def step_matte(cfg):
    """Person matte (m_NNNNN.png) and hand joints (hands.jsonl) for every frame, with Apple Vision."""
    if platform.system() != "Darwin":
        sys.exit("The matte step uses Apple Vision and only runs on macOS. On another OS, put your own mattes in "
                 f"{cfg.matte_dir} as m_00001.png, m_00002.png ... (8 bit grey, frame 0 = m_00001 with matte.offset 1) "
                 "and give every prop a \"pos\". See README, 'Not on a Mac?'.")
    binary = os.path.join(HERE, "tools", "matte")
    src = os.path.join(HERE, "tools", "matte.swift")
    if not os.path.exists(binary) or os.path.getmtime(binary) < os.path.getmtime(src):
        sh(["swiftc", "-O", src, "-o", binary])
    os.makedirs(cfg.matte_dir, exist_ok=True)
    sh([binary, cfg.base, cfg.matte_dir, cfg["matte"]["mode"]])


def step_plate(cfg):
    import cv2
    import numpy as np
    plate, ok = V.build_plate(cfg.base, cfg.matte_dir)
    np.save(os.path.join(cfg.work, "plate.npy"), plate); np.save(os.path.join(cfg.work, "plate_ok.npy"), ok)
    cv2.imwrite(os.path.join(cfg.work, "plate.jpg"), (plate[..., ::-1] * 255).astype(np.uint8))
    print(f"  plate seen for {ok.mean() * 100:.0f}% of pixels (the rest is filled in); preview at {cfg.work}/plate.jpg")


def step_stills(cfg, seconds):
    import cv2
    import numpy as np
    from vfx.scene import Scene
    out = os.path.join(cfg.work, "stills"); os.makedirs(out, exist_ok=True)
    sc = Scene(cfg)
    for s in seconds:
        k = cfg.frames(s)
        img = sc.frame(k, V.read_frame(cfg.base, k))
        path = os.path.join(out, f"t_{k:04d}.jpg")
        cv2.imwrite(path, (np.clip(img, 0, 1)[..., ::-1] * 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 92])
        print("  wrote", path)


def step_render(cfg, rng=None):
    from vfx.scene import Scene
    sc = Scene(cfg)
    total = V.count_frames(cfg.base)
    path = os.path.join(cfg.work, "vfx.mp4" if rng is None else f"vfx_{rng[0]:g}_{rng[1]:g}.mp4")
    wr = V.Writer(path, crf=cfg["encode"]["crf"], preset=cfg["encode"]["preset"])
    t0 = time.time()
    start, count = (0, None) if rng is None else (cfg.frames(rng[0]), cfg.frames(rng[1]) - cfg.frames(rng[0]))
    for k, I in V.read_frames(cfg.base, start, count):
        wr.write(sc.frame(k, I))
        if k % 100 == 0:
            el = time.time() - t0; done = k - start + 1
            print(f"  frame {k}/{total}  {el:.0f}s elapsed, ~{el / done * ((count or total - start) - done):.0f}s left", flush=True)
    wr.close()
    print("  wrote", path)


def step_sfx(cfg):
    from vfx.sfx import render_sfx
    render_sfx(cfg, os.path.join(cfg.work, "sfx.wav"), V.duration(cfg.base))


def step_mux(cfg):
    """Voice (cleaned and levelled) + sound effects under the VFX video, optional speed change -> output."""
    mix = cfg["mix"]; speed = float(mix.get("speed", 1.0))
    os.makedirs(os.path.dirname(cfg.output) or ".", exist_ok=True)
    vfx, voice, sfx = os.path.join(cfg.work, "vfx.mp4"), os.path.join(cfg.work, "voice.wav"), os.path.join(cfg.work, "sfx.wav")
    vchain = "highpass=f=80,afftdn=nf=-25" + (",loudnorm=I=-16:TP=-1.5:LRA=11" if mix["loudnorm"] else "") + f",volume={mix['voice_gain']}"
    inputs = ["-i", vfx, "-i", voice]
    fc = f"[1:a]{vchain}[v];"
    if cfg["sfx"]["enabled"] and os.path.exists(sfx):
        inputs += ["-i", sfx]
        fc += f"[2:a]volume={mix['sfx_gain']}[s];[v][s]amix=inputs=2:normalize=0:duration=first[a0];"
    else:
        fc += "[v]anull[a0];"
    if speed != 1.0:
        fc += f"[0:v]setpts=PTS/{speed}[vid];[a0]atempo={speed}[aud]"
    else:
        fc += "[0:v]null[vid];[a0]anull[aud]"
    sh(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[vid]", "-map", "[aud]",
        "-c:v", "libx264", "-preset", "slow", "-crf", cfg["encode"]["crf"], "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", cfg.output])
    print(f"  wrote {cfg.output}  ({V.duration(cfg.output):.2f}s)")


def step_sheet(cfg):
    dur = V.duration(cfg.output)
    path = os.path.join(cfg.work, "sheet.jpg")
    sh(["ffmpeg", "-y", "-v", "error", "-i", cfg.output, "-vf", f"fps=12/{dur:.3f},scale=480:-1,tile=4x3", "-frames:v", "1", path])
    print("  wrote", path, "(open it and check every effect lands where it should)")


def step_hands(cfg, seconds):
    hands = V.load_hands(cfg.matte_dir)
    for s in seconds:
        k = cfg.frames(s)
        for side in ("left", "right"):
            p = V.hand_at(hands, k, side)
            print(f"  {s}s (frame {k}) {side} palm:", f"[{p[0]:.0f}, {p[1]:.0f}]" if p else "not found")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config")
    ap.add_argument("step", choices=["all", "prep", "matte", "plate", "stills", "render", "sfx", "mux", "sheet", "hands"])
    ap.add_argument("seconds", nargs="?", help="stills/hands: comma separated seconds, e.g. 2.5,9.6,18.4. render: FROM,TO for a partial render")
    a = ap.parse_args()
    cfg = Config(a.config)
    V.configure(cfg.width, cfg.height, cfg.fps, cfg["matte"]["offset"])
    print(f"{cfg.name}: {cfg.width}x{cfg.height} @ {cfg.fps:g} fps, work in {cfg.work}")
    secs = [float(x) for x in a.seconds.split(",")] if a.seconds else []
    steps = ["prep", "matte", "plate", "render", "sfx", "mux", "sheet"] if a.step == "all" else [a.step]
    for s in steps:
        print(f"\n== {s}")
        if s == "prep": step_prep(cfg)
        elif s == "matte": step_matte(cfg)
        elif s == "plate": step_plate(cfg)
        elif s == "stills": step_stills(cfg, secs or [cfg["title"]["end"] / 2 if cfg["title"] else 1.0])
        elif s == "render": step_render(cfg, (secs[0], secs[1]) if len(secs) == 2 else None)
        elif s == "sfx": step_sfx(cfg)
        elif s == "mux": step_mux(cfg)
        elif s == "sheet": step_sheet(cfg)
        elif s == "hands": step_hands(cfg, secs)


if __name__ == "__main__":
    main()
