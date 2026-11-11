# The pipeline, step by step

Every step is `python3 render.py configs/<name>.json <step>`. `all` runs them in order. Each step only needs the ones above it, so you can re-run `stills` or `render` after a config change without redoing the matte.

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

## A quick test before the full render

```bash
python3 render.py configs/mine.json stills 1.0,9.6,18.5,22.3   # frames at those seconds -> work/<name>/stills/
python3 render.py configs/mine.json render 17.5,19.5           # just those two seconds -> work/<name>/vfx_17.5_19.5.mp4
```
