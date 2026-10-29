"""Inspect the environment (never installs anything) and optionally scaffold a workspace.

  python preflight.py                      # report tools + install hints
  python preflight.py --init DIR           # also create DIR/plan.json, DIR/record.py, DIR/.gitignore
                                           # (existing files are never overwritten)
"""
import argparse, importlib.util, pathlib, shutil, sys
from _common import find_tool, run, ff_filters

TEMPLATES = pathlib.Path(__file__).resolve().parents[1] / "templates"


def check():
    rep, ok = [], True
    def line(name, good, detail, hint=""):
        nonlocal ok
        rep.append(f"[{'ok' if good else 'MISSING'}] {name}: {detail}" + (f"\n        -> {hint}" if not good and hint else ""))
        return good
    line("python", sys.version_info >= (3, 9), sys.version.split()[0], "Python 3.9+ required")
    pw = importlib.util.find_spec("playwright") is not None
    ok &= line("playwright (python)", pw, "installed" if pw else "not installed", "pip install playwright && playwright install chromium")
    if pw:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                path = p.chromium.executable_path
            have = pathlib.Path(path).exists()
            ok &= line("chromium for playwright", have, path if have else "browser binary not found", "playwright install chromium")
        except Exception as e:
            ok &= line("chromium for playwright", False, str(e)[:120], "playwright install chromium")
    ff = find_tool("ffmpeg")
    ok &= line("ffmpeg", bool(ff), ff or "not found", "install ffmpeg, or: pip install imageio-ffmpeg")
    if ff:
        filt = ff_filters(ff)
        for f, why in (("subtitles", "burned-in captions (libass)"), ("overlay", "overlays"), ("concat", "joining scenes")):
            line(f"  ffmpeg filter '{f}'", f" {f} " in filt, why, "use a full ffmpeg build (e.g. gyan.dev / BtbN) for burn-in captions; SRT/VTT still work")
        ver = (run([ff, "-version"]).stdout.splitlines() or ["?"])[0]
        rep.append(f"        {ver}")
    fp = find_tool("ffprobe")
    line("ffprobe", bool(fp), fp or "not found - validate.py falls back to parsing `ffmpeg -i`", "optional: install a full ffmpeg build")
    et = importlib.util.find_spec("edge_tts") is not None
    line("edge-tts (optional TTS engine)", et, "installed" if et else "not installed", "pip install edge-tts   (needs internet; free). Alternatives: tts.engine = 'command' or 'silent'")
    print("\n".join(rep))
    return ok


def init(dest):
    dest = pathlib.Path(dest).resolve(); dest.mkdir(parents=True, exist_ok=True)
    for src, name in (("plan.example.json", "plan.json"), ("record_template.py", "record.py")):
        t = dest / name
        if t.exists():
            print(f"kept existing {t}")
        else:
            shutil.copy(TEMPLATES / src, t); print(f"created {t}")
    gi = dest / ".gitignore"
    wanted = ["work/", "*.state.json", ".env", "__pycache__/"]
    cur = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    add = [w for w in wanted if w not in cur]
    if add:
        gi.write_text("\n".join(cur + add) + "\n", encoding="utf-8"); print(f"updated {gi} (+{', '.join(add)})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--init", metavar="DIR")
    a = ap.parse_args()
    good = check()
    if a.init: init(a.init)
    sys.exit(0 if good else 1)
