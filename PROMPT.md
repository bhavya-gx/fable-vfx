# The prompt

Paste this into Claude Code (or any coding agent) with this repo open and your clip in `footage/`. Replace the parts in square brackets. It is the same brief, tidied up, that produced the original video.

* * *

I recorded a talking-head clip at `footage/[my-clip].mov` and I want the fable-vfx pass on it. Read `README.md` and `configs/fable-5-2.json` first so you know the pipeline and the config format.

What I want in the video:

- Title behind my head for the opening line: "[YOUR TITLE]".
- When I snap my fingers the first time, the background turns into the ocean. When I snap again, it comes back.
- [A gold star] appears on my [left] hand when I say "[a star appears here]".
- [The letter B] appears on my [right] hand when I say "[the letter B appears here]".
- Both vanish when I say "[and now it's back]".
- Play the final at [1.25x].

Do it in this order and show me your work at each step:

1. Run `python3 render.py configs/mine.json prep` after writing `configs/mine.json` with just `source`, `prep` and `format`. Trim any dead air at the start with `prep.start`. Pull a contact sheet of `work/<name>/base.mp4` and look at it.
2. Transcribe `work/<name>/voice.wav` with word timestamps (use whatever Whisper you have, or `ffmpeg` + a local model). Give me the seconds for the title end, both snaps, each prop landing and the vanish. For the snaps, confirm the exact frame by extracting stills around the time the transcript says and looking for the hand closing.
3. Run `matte` and `plate`. Open `work/<name>/plate.jpg` and tell me if the room reconstruction looks clean.
4. Run `hands` at each prop second to confirm the right hand is detected. Fill in `title`, `ocean`, `props`, `vanish` and `mix.speed` in the config.
5. Run `stills` at: the middle of the title, one second into the ocean, just before the ocean comes back, a few frames after each prop lands, and mid vanish. Look at every still. Fix offsets, origins or timing in the config until the title is hidden by my head, the wipe starts from my hand, and the props sit just above my palms. Re-run stills until it is right.
6. Render a two second test around the first prop, then the whole thing: `render`, `sfx`, `mux`, `sheet`. Open the sheet and check every effect lands.
7. Give me the output path, the final config, and anything you were unsure about.

Rules: do not edit anything under `vfx/` or `render.py` unless the config cannot express what I asked for. If it cannot, tell me what you would add before you add it. Never commit footage or renders.
