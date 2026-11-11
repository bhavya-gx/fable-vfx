# Config reference

Times are seconds in the trimmed clip (after `prep.start`). Pixel positions are in the output frame, x to the right, y down. Leave out `title`, `ocean` or `props` and that effect is skipped. The config that made the original video is [`configs/fable-5-2.json`](../configs/fable-5-2.json).

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
