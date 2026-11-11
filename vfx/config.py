"""Load and validate a project config. Times in the config are seconds; the code works in frames."""
import copy
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "format": {"width": 1920, "height": 1080, "fps": 30},
    "prep": {"start": 0.0, "duration": None, "grade": True, "crf": 12},
    "grade": {"yellow_desat": 0.50, "yellow_centre": 44.0, "mid_lift": 0.05},
    "matte": {"mode": "person", "offset": 1},
    "title": None,
    "ocean": None,
    "props": [],
    "vanish": None,
    "sfx": {"enabled": True, "gain": 1.0},
    "mix": {"voice_gain": 1.0, "sfx_gain": 0.9, "loudnorm": True},
    "encode": {"crf": 15, "preset": "slow"},
    "seed": 7,
}

TITLE_DEFAULTS = {"end": 2.8, "fade": 0.4, "width_frac": 0.94, "top": 36, "font": "fonts/Poppins-Bold.ttf"}
OCEAN_DEFAULTS = {"wipe": 0.5, "horizon": 600, "sun": [520, 250], "in_origins": "hands", "out_origins": "hands"}
PROP_DEFAULTS = {"kind": "star", "text": "B", "hand": "left", "enter": "fly", "fly_time": 0.27,
                 "fly_from": [-160, 40], "offset": [0, -310], "size": 0.78, "colors": None,
                 "font": "fonts/Poppins-Bold.ttf"}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class Config:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.root = os.path.dirname(self.path)
        raw = json.load(open(self.path, encoding="utf-8"))
        d = _merge(DEFAULTS, raw)
        if raw.get("title"):
            d["title"] = _merge(TITLE_DEFAULTS, raw["title"])
        if raw.get("ocean"):
            d["ocean"] = _merge(OCEAN_DEFAULTS, raw["ocean"])
        d["props"] = [_merge(PROP_DEFAULTS, p) for p in raw.get("props", [])]
        self.d = d
        self._check()

    # paths in the config are relative to where you run render.py (normally the repo folder)
    def path_of(self, p):
        return os.path.abspath(p)

    # fonts: your own path, or one that ships in the repo's fonts/ folder
    def font_of(self, p):
        if os.path.exists(p):
            return os.path.abspath(p)
        here = os.path.join(REPO, p)
        if os.path.exists(here):
            return here
        raise FileNotFoundError(f"font not found: {p}")

    @property
    def source(self): return self.path_of(self.d["source"])
    @property
    def work(self): return self.path_of(self.d.get("work", "work/" + self.name))
    @property
    def output(self): return self.path_of(self.d.get("output", f"out/{self.name}.mp4"))
    @property
    def name(self): return self.d.get("name") or os.path.splitext(os.path.basename(self.d["source"]))[0]
    @property
    def base(self): return os.path.join(self.work, "base.mp4")
    @property
    def matte_dir(self): return os.path.join(self.work, "matte")
    @property
    def width(self): return int(self.d["format"]["width"])
    @property
    def height(self): return int(self.d["format"]["height"])
    @property
    def fps(self): return float(self.d["format"]["fps"])

    def frames(self, seconds):
        return int(round(float(seconds) * self.fps))

    def __getitem__(self, k): return self.d[k]
    def get(self, k, default=None): return self.d.get(k, default)

    def _check(self):
        d = self.d
        if "source" not in d:
            raise ValueError("config needs \"source\": the path of your recording")
        for p in d["props"]:
            if p["kind"] not in ("star", "letter"):
                raise ValueError(f"prop kind must be 'star' or 'letter', got {p['kind']!r}")
            if p["hand"] not in ("left", "right"):
                raise ValueError("prop hand must be 'left' or 'right' (as seen on screen)")
            if p["enter"] not in ("fly", "pop"):
                raise ValueError("prop enter must be 'fly' or 'pop'")
            if "at" not in p:
                raise ValueError("every prop needs \"at\": the second it lands on the palm")
        if d["props"] and d["vanish"] is None:
            raise ValueError("\"vanish\": the second the props disappear, is needed when there are props")
        if d["ocean"]:
            for k in ("in", "out"):
                if k not in d["ocean"]:
                    raise ValueError(f"ocean needs \"{k}\": the second of the snap")
            if d["ocean"]["out"] <= d["ocean"]["in"]:
                raise ValueError("ocean.out must come after ocean.in")
