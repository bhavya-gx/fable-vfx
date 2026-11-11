# Contributing

Thanks for looking. The point of this repo is that someone can read it in ten minutes and run it on their own clip, so please keep it that way.

- `main` is protected. Nobody pushes to it directly, including the owner. Open a pull request from a branch or a fork.
- Pull requests should keep the one-command flow working: `python3 render.py configs/your.json all`.
- New effects go in `vfx/` as their own module and are switched on from the config, so a config without them renders exactly as before.
- Do not commit footage, mattes, renders or `.npy` files. `.gitignore` already blocks them.
- Keep the prose plain. No em dashes.

If you made something with it, open an issue with a link. That is the best kind of contribution.
