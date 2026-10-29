"""Shared helpers for the DemoFlow scripts: tool discovery, plan loading, workspace paths."""
import copy, json, pathlib, shutil, subprocess

DEFAULTS = {
    "title": "Demo video",
    "language": "en-US",
    "basename": "demo",
    "output_dir": "output",
    "work_dir": "work",
    "tts": {"engine": "edge-tts", "voice": "en-US-AriaNeural", "rate": "+0%", "pitch": "+0Hz",
            "volume": "+0%", "pronunciations": {}, "command": None, "ext": "wav"},
    "video": {"width": 1920, "height": 1080, "fps": 30, "crf": 18, "preset": "medium"},
    "captions": {"burn_in": True, "formats": ["srt", "vtt"], "font": None, "font_file": None,
                 "size": 46, "max_words": 8},
    "timing": {"lead": 0.15, "tail": 0.5, "fade_in": 0.6, "fade_out": 0.9},
    "music": None,   # {"file": "...", "volume": 0.08} - only when the user asks for it
    "scenes": [],
}


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


class Workspace:
    """Resolves every path relative to the directory that holds plan.json."""
    def __init__(self, plan_path):
        self.plan_path = pathlib.Path(plan_path).resolve()
        self.root = self.plan_path.parent
        self.plan = deep_merge(DEFAULTS, json.loads(self.plan_path.read_text(encoding="utf-8")))
        self.work = self.root / self.plan["work_dir"]
        self.out = self.root / self.plan["output_dir"]
        self.audio = self.work / "audio"
        self.scenes = self.plan["scenes"]
        ids = [s["id"] for s in self.scenes]
        if len(ids) != len(set(ids)):
            raise SystemExit("plan.json: scene ids must be unique")
        if not self.scenes:
            raise SystemExit("plan.json has no scenes")

    def resolve(self, p):
        p = pathlib.Path(p)
        return p if p.is_absolute() else (self.root / p)


def find_tool(name):
    """PATH first; for ffmpeg fall back to the imageio-ffmpeg bundled binary. ffprobe may be None."""
    p = shutil.which(name)
    if p:
        return p
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None
    return None


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ff_filters(ffmpeg):
    return run([ffmpeg, "-hide_banner", "-filters"]).stdout
