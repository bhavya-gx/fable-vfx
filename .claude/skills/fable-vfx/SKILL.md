---
name: fable-vfx
description: Add the fable-vfx effects to a talking-head clip (a title hidden behind the head, the room turning into an ocean on a finger snap, a 3D star and letter landing on the palms, synthesised sound effects, a clean colour grade) by writing a small JSON config and running render.py. Use when the user hands over a phone recording and asks for "the Fable 5.2 video treatment", the ocean snap, props on their hands, or effects on a talking-head clip.
---

Work from the repository root, the folder with `render.py`. Read `docs/config.md` before writing a config. Do not edit `vfx/` or `render.py` to get an effect; if the config cannot express what the user asked for, say what is missing and stop. Never commit footage, mattes or renders. Keep the raw clip unchanged.

## What you are making

A landscape 1080p video of the person talking to camera where, in this order and only the ones the user asked for: a title sits behind their head for the opening line; on the first finger snap the room wipes out from the hand into an ocean, on the second it wipes back; a prop (gold star, or a glossy letter or short word) arrives on a palm when they say so and follows the hand; everything vanishes on cue; sounds match each moment. The config that made the original is `configs/fable-5-2.json`. Copy it, do not edit it.

## Steps, in order, showing the user each result

1. **Look at the clip first.** `ffprobe` it. If it is portrait, rotated, or the hands are out of frame when they snap, tell the user before anything else. Write `configs/<name>.json` with `source`, `format` and `prep` only, then run `python3 render.py configs/<name>.json prep`. Trim dead air at the start with `prep.start`; every later time in the config is in this trimmed clip. Pull a contact sheet of `work/<name>/base.mp4` and look at it.
2. **Find the moments.** Transcribe `work/<name>/voice.wav` with word timestamps using whatever local Whisper is installed (`whisper`, `faster_whisper` or `mlx_whisper`). From the transcript, propose seconds for: the end of the opening line (title end), each snap, each prop landing, the vanish. A snap is a motion, not a word: extract stills around the transcript time and pick the frame where the fingers close. Show the user the list of moments before rendering.
3. **Matte and plate.** Run `matte`, then `plate`. Open `work/<name>/plate.jpg`. If the room reconstruction shows ghosting of the person, the camera moved; say so, the ocean edges will suffer.
4. **Hands.** Run `hands <s1>,<s2>,...` at each snap and prop moment. If a palm is "not found", widen the window by trying nearby seconds; if it is never found, set the prop's `pos` by hand from a still.
5. **Write the full config.** `title`, `ocean`, `props`, `vanish`, `mix.speed`. Leave out any effect the user did not ask for. Props: `hand` is as seen on screen. `enter` is `fly` for something arriving from off screen, `pop` for something rising out of the palm.
6. **Stills before video.** Run `stills` at: the middle of the title, one second into the ocean, just before it comes back, four frames after each prop lands, and halfway through the vanish. Look at every still. Check: the head covers part of the title; the wipe starts at the hand; props sit just above the palm, not on the fingers and not floating; nothing covers the face. Fix `offset`, `in_origins`, `out_origins` or timing in the config and re-run stills until right.
7. **Render.** A two second test (`render <from>,<to>`) around the first prop, then the full `render`, `sfx`, `mux`, `sheet`. Open the sheet and check every effect lands.
8. **Hand over** the output path, the final config, and anything you were unsure about, with the second where it happens.

## Judgement calls

- Timing beats transcript. If the person says "a star appears here" and opens the hand a beat later, land the prop on the hand, not on the word.
- A prop above a moving hand looks held; a prop on a still frame looks pasted. If the hand is not visibly presenting, suggest a different moment.
- Keep `mix.speed` at 1.0 unless asked; 1.25 was a choice for the original, not a rule.
- Do not add effects the user did not ask for. Do not invent a title.
- Captions are not part of this skill. If asked, add them with the tool the user already uses, after the mux.
