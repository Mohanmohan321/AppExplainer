"""Generate per-scene narration from plan.json with a configurable engine, cached by content hash.

  python tts.py --plan PLAN [--force]
  python tts.py --list-voices [--lang en-IN]        # edge-tts voices

Engines (plan.tts.engine):
  edge-tts  Python package `edge-tts` (free, needs internet). Gives word timings.
  command   Any CLI: plan.tts.command with {text_file} and {out} placeholders; output ext = plan.tts.ext.
  silent    Silence sized to the script - for dry runs / tests (no network, no cost).
Writes <work>/tts.json (durations + caption tokens aligned to the ORIGINAL text, so pronunciation
respellings never leak into captions).
"""
import argparse, asyncio, hashlib, json, re, sys
from _common import Workspace, find_tool, run


def decoded_duration(ff, path):
    r = run([ff, "-hide_banner", "-i", str(path), "-f", "null", "-"])
    times = re.findall(r"time=(\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not times:
        raise RuntimeError(f"cannot read duration of {path}: {r.stderr[-300:]}")
    h, m, s = times[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


def spoken_text(text, prons):
    for k, v in (prons or {}).items():
        text = re.sub(re.escape(k), v, text)
    return text


def align_tokens(text, words, duration):
    """Caption tokens (original whitespace-split text) with timings from the engine's words."""
    toks = text.split()
    if words and len(words) == len(toks):
        return [{"text": t, "start": w["start"], "end": w["end"]} for t, w in zip(toks, words)]
    t0, t1 = (words[0]["start"], words[-1]["end"]) if words else (0.0, duration)
    total, acc, out = sum(len(t) for t in toks) or 1, 0, []
    for t in toks:
        s = t0 + (t1 - t0) * acc / total; acc += len(t)
        out.append({"text": t, "start": s, "end": t0 + (t1 - t0) * acc / total})
    return out


async def synth_edge(text, cfg, out):
    import edge_tts
    kw = dict(rate=cfg["rate"], pitch=cfg["pitch"], volume=cfg["volume"])
    try:
        com = edge_tts.Communicate(text, cfg["voice"], boundary="WordBoundary", **kw)
    except TypeError:                      # older edge-tts without the boundary argument
        com = edge_tts.Communicate(text, cfg["voice"], **kw)
    words = []
    with open(out, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"start": ch["offset"] / 1e7, "end": (ch["offset"] + ch["duration"]) / 1e7})
    return words


def synth_silent(ff, text, out):
    dur = max(1.5, len(text.split()) / 2.6)
    r = run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", f"{dur:.2f}", str(out)])
    if r.returncode: raise RuntimeError(r.stderr[-400:])
    return []


def synth_command(cfg, text, out, text_file):
    if not cfg.get("command"): raise SystemExit("tts.engine=command needs tts.command")
    text_file.write_text(text, encoding="utf-8")
    cmd = cfg["command"].format(text_file=str(text_file), out=str(out))
    r = run(cmd, shell=True)
    if r.returncode or not out.exists(): raise RuntimeError(f"tts command failed: {r.stderr[-400:]}")
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--list-voices", action="store_true"); ap.add_argument("--lang", default="")
    a = ap.parse_args()
    if a.list_voices:
        import edge_tts
        for v in asyncio.run(edge_tts.list_voices()):
            if v["Locale"].lower().startswith(a.lang.lower()):
                print(f"{v['ShortName']:<34}{v['Gender']:<8}{v['Locale']}")
        return
    if not a.plan: ap.error("--plan is required")
    ws = Workspace(a.plan); cfg = ws.plan["tts"]; ff = find_tool("ffmpeg")
    if not ff: raise SystemExit("ffmpeg not found (run preflight.py)")
    ws.audio.mkdir(parents=True, exist_ok=True)
    prev_path = ws.work / "tts.json"
    prev = {e["id"]: e for e in json.loads(prev_path.read_text(encoding="utf-8"))} if prev_path.exists() else {}
    ext = {"edge-tts": "mp3", "silent": "wav"}.get(cfg["engine"], cfg.get("ext", "wav"))
    out, reused = [], 0
    for s in ws.scenes:
        text = (s.get("narration") or "").strip()
        if not text:
            out.append({"id": s["id"], "file": None, "duration": 0.0, "hash": None, "tokens": []}); continue
        spoken = spoken_text(text, cfg.get("pronunciations"))
        key = hashlib.sha256(json.dumps([cfg["engine"], cfg["voice"], cfg["rate"], cfg["pitch"], cfg["volume"],
                                         cfg.get("command"), spoken], sort_keys=True).encode()).hexdigest()
        path = ws.audio / f"{s['id']}.{key[:8]}.{ext}"
        old = prev.get(s["id"])
        if not a.force and old and old.get("hash") == key and path.exists():
            out.append({**old, "file": str(path), "tokens": align_tokens(text, old.get("words", []), old["duration"]), "cached": True})
            reused += 1; continue
        if cfg["engine"] == "edge-tts": words = asyncio.run(synth_edge(spoken, cfg, path))
        elif cfg["engine"] == "silent": words = synth_silent(ff, spoken, path)
        elif cfg["engine"] == "command": words = synth_command(cfg, spoken, path, ws.audio / f"{s['id']}.txt")
        else: raise SystemExit(f"unknown tts.engine: {cfg['engine']}")
        dur = decoded_duration(ff, path)
        out.append({"id": s["id"], "file": str(path), "duration": dur, "hash": key, "words": words,
                    "tokens": align_tokens(text, words, dur), "cached": False})
    ws.work.mkdir(parents=True, exist_ok=True)
    prev_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for o in out:
        print(f"{o['id']:<16}{o['duration']:6.2f}s  {'cached' if o.get('cached') else ('-' if not o['file'] else 'new')}")
    print(f"total narration {sum(o['duration'] for o in out):.1f}s  ({reused} reused from cache)")


if __name__ == "__main__":
    main()
