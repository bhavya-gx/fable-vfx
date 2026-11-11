# fable-vfx

A VFX pass for a talking-head clip, written by Claude (Fable 5.2) in one session and now driven by a small JSON config so it runs on your footage too.

What it does to a plain phone recording of someone talking to camera:

1. **Title behind the head.** Big text sits between the person and the wall, so their head covers it.
2. **Background swap on a snap.** The room becomes an ocean with a ring wipe out of the hand, and comes back on the second snap. Ocean, sky, sun, clouds and bloom are all computed, no stock footage.
3. **3D props on the palms.** A puffy gold star flies in and lands on one hand, a glossy letter pops out of the other. They follow the hands, bob, sparkle, then poof.
4. **Sound effects.** Whoosh, sea, chimes and the pop are synthesised in numpy and timed off the same config as the picture.
5. **Colour grade.** A "clean room" LUT that pulls the tungsten yellow out of the walls and leaves skin alone.

Everything runs locally: Python, ffmpeg, and Apple Vision for the person matte and hand tracking. No After Effects, no cloud, no API keys.

The config that produced the original video is in [`configs/fable-5-2.json`](configs/fable-5-2.json). Every number that was specific to that recording (where the snaps are, which hand gets which prop, the title text, the speed) lives there and nowhere else.

## Quick start (Mac)

You need ffmpeg, Python 3.10+, and Xcode command line tools (for the Swift matte tool).

```bash
brew install ffmpeg
xcode-select --install
git clone https://github.com/bhavya-gx/fable-vfx.git
cd fable-vfx
pip install -r requirements.txt
```

Put your clip in `footage/`, copy a config, edit the times, and run it:

```bash
cp configs/fable-5-2.json configs/mine.json
python3 render.py configs/mine.json all
```

That is six steps in a row: prep, matte, plate, render, sfx, mux, then a contact sheet in `work/<name>/sheet.jpg` so you can check the result before you post it. A 36 second 1080p clip takes about 15 minutes on an M-series Mac; the matte and the render are the slow parts.

## Make it work on your footage

**Record it so the effects have something to hold on to.** Phone on a stand, landscape, no camera movement. Hands fully in frame when you snap and when you "hold" a prop (palm up, a little away from the body). A plain wall behind you helps the matte. Say the moments out loud: "when I snap", "a star appears here". The pipeline does not listen, but you will use the transcript to find the seconds.

**Find the seconds.** Scrub the clip in QuickTime, or transcribe it (any Whisper build will do) and note:

- when the title should fade out (end of the opening line)
- the two snaps (ocean in, ocean out)
- the moment each prop should land
- the moment everything should vanish

**Fill the config.** Times are seconds in the *trimmed* clip, so if `prep.start` is 0.65, a snap at 10.05 in the raw file is `9.4` in the config.

```json
{
  "source": "footage/me.mov",
  "prep": {"start": 0.0, "duration": null, "grade": true},
  "title": {"text": "YOUR TITLE", "end": 2.8},
  "ocean": {"in": 9.4, "out": 15.2},
  "props": [
    {"kind": "star", "hand": "left", "enter": "fly", "at": 18.4},
    {"kind": "letter", "text": "B", "hand": "right", "enter": "pop", "at": 22.0}
  ],
  "vanish": 24.5,
  "mix": {"speed": 1.0}
}
```

Leave out `ocean`, `title` or `props` and that effect is simply skipped.

**Run it in pieces the first time.**

```bash
python3 render.py configs/mine.json prep      # trims, scales, grades -> work/<name>/base.mp4
python3 render.py configs/mine.json matte     # person matte + hand joints for every frame
python3 render.py configs/mine.json plate     # clean plate of the empty room
python3 render.py configs/mine.json hands 9.4,18.4   # where the palms are at those seconds
python3 render.py configs/mine.json stills 1.0,9.6,18.5,22.3   # test frames -> work/<name>/stills/
```

Open the stills. If the star sits in the wrong place, change the prop's `offset` (pixels from the palm centre, y goes down so `-310` is above the hand). If the wipe starts from the wrong spot, give `ocean.in_origins` explicit `[x, y]` points instead of `"hands"`. Then:

```bash
python3 render.py configs/mine.json render 17.5,19.5   # a two second test render
python3 render.py configs/mine.json render             # the whole thing -> work/<name>/vfx.mp4
python3 render.py configs/mine.json sfx
python3 render.py configs/mine.json mux                 # voice + sfx + speed -> out/<name>.mp4
python3 render.py configs/mine.json sheet
```

**Using Claude to do the above.** [`PROMPT.md`](PROMPT.md) is a prompt you can paste into Claude Code with this repo open and your clip in `footage/`. It walks the model through finding the moments, writing the config, checking stills and rendering.

## Config reference

| Key | What it is | Default |
|---|---|---|
| `source` | your recording | required |
| `name`, `work`, `output` | names the job, where temp files go, where the final lands | from the source filename, `work/<name>`, `out/<name>.mp4` |
| `format.width/height/fps` | output size and frame rate | 1920, 1080, 30 |
| `prep.start`, `prep.duration` | trim, in raw seconds | 0, whole clip |
| `prep.grade` | apply the clean-room LUT | true |
| `grade.yellow_desat`, `yellow_centre`, `mid_lift` | how hard the LUT pulls yellow, which hue, how much it lifts mids | 0.5, 44, 0.05 |
| `title.text` | the words behind the head | none (effect off) |
| `title.end`, `title.fade` | when it starts fading, how long the fade is, seconds | 2.8, 0.4 |
| `title.width_frac`, `title.top`, `title.font` | width as a fraction of the frame, top margin in px, .ttf path | 0.94, 36, Poppins Bold |
| `ocean.in`, `ocean.out` | the two snaps, seconds | required when `ocean` is present |
| `ocean.wipe` | length of the ring wipe, seconds | 0.5 |
| `ocean.in_origins`, `out_origins` | where the wipe starts: `"hands"` or a list of `[x, y]` | `"hands"` |
| `ocean.horizon`, `ocean.sun` | horizon row and sun position in px | 600, [520, 250] |
| `props[].kind` | `"star"` or `"letter"` | required |
| `props[].text` | the letter (or short word) for a letter prop | "B" |
| `props[].hand` | `"left"` or `"right"`, as seen on screen | required |
| `props[].enter` | `"fly"` (arcs in from `fly_from`) or `"pop"` (rises out of the palm) | "fly" |
| `props[].at` | second it lands on the palm | required |
| `props[].fly_time`, `fly_from` | how long the fly-in takes, where it starts in px (can be off screen) | 0.27, [-160, 40] |
| `props[].offset` | px from the palm centre | [0, -310] |
| `props[].size` | scale of the sprite | 0.78 |
| `props[].colors` | `"gold"`, `"pink"`, `"sky"`, `"mint"`, or `{"top","bottom","side","glow"}` RGB 0..1 | gold for stars, pink for letters |
| `props[].pos` | fixed `[x, y]` if there is no hand tracking | none |
| `vanish` | second the props disappear | required when there are props |
| `sfx.enabled`, `sfx.gain` | sound effects on, overall level | true, 1.0 |
| `mix.speed` | playback speed of the final (1.25 was used for the original) | 1.0 |
| `mix.voice_gain`, `mix.sfx_gain`, `mix.loudnorm` | voice level, effects level, normalise the voice to -16 LUFS | 1.0, 0.9, true |
| `encode.crf`, `encode.preset` | x264 quality | 15, slow |
| `matte.mode` | `"person"` (Vision person segmentation) or `"subject"` (foreground instance mask) | "person" |
| `seed` | random seed for waves, sparkles, clouds | 7 |

## What each step writes

| Step | Reads | Writes |
|---|---|---|
| `prep` | your source | `work/<name>/base.mp4` (video only, graded), `voice.wav`, `grade.cube` |
| `matte` | `base.mp4` | `work/<name>/matte/m_00001.png ...` and `hands.jsonl` |
| `plate` | `base.mp4`, mattes | `plate.npy`, `plate_ok.npy`, `plate.jpg` |
| `stills` | all of the above | `work/<name>/stills/t_NNNN.jpg` |
| `render` | all of the above | `work/<name>/vfx.mp4` (no sound) |
| `sfx` | the config | `work/<name>/sfx.wav` |
| `mux` | `vfx.mp4`, `voice.wav`, `sfx.wav` | your output file |
| `sheet` | the output | `work/<name>/sheet.jpg` |

## Not on a Mac?

Only the `matte` step is Apple-only. Everything else is Python and ffmpeg. To run elsewhere:

1. Make a greyscale person matte for every frame of `base.mp4` with any tool you like (Robust Video Matting, rembg, a Resolve magic mask export). Name them `work/<name>/matte/m_00001.png` for frame 0, `m_00002.png` for frame 1 and so on, or set `matte.offset` to 0 and start at `m_00000.png`.
2. There will be no `hands.jsonl`, so give each prop a `"pos": [x, y]` and the ocean explicit `in_origins` / `out_origins`.

## How it works

[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) explains each piece: why a clean plate makes the edges hold up, how the ocean is a sum of sines with Fresnel and a sun glint, how a flat mask becomes a puffy 3D sprite with a bevel and an extruded side, and how the sounds are built from noise and sine waves.

## What is not in here

The published version also had a captions pass and a few pause cuts, done in a separate editing session. This repo covers the effects, the grade, the sound and the speed change. Add captions with whatever you already use.

## Credits

Recorded, directed and published by [Bhavya Goel](https://github.com/bhavya-gx). Code written with Claude Fable 5.2 in Claude Code. Poppins by the Indian Type Foundry, SIL OFL. MIT licensed, see [LICENSE](LICENSE).
