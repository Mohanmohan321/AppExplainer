"""Assemble the final video from plan.json + <work>/timeline.json + <work>/tts.json.

  python assemble.py --plan PLAN

Per scene: cut the recording (input seeking, accurate on Playwright's variable-frame-rate WebM),
speed up scenes that set "speed_up_to" (long waits), then concatenate; final pass lays narration on
the final timeline, burns captions (if ffmpeg has libass), mixes optional music, adds fades.
Outputs <output_dir>/<basename>.mp4 + .srt/.vtt + .script.md, and <work>/assemble_report.json
(consumed by validate.py). Written for ffmpeg >= 4.2 (avoids newer-only options).
"""
import argparse, json, re, shutil, subprocess, sys
from pathlib import Path
from _common import Workspace, find_tool, ff_filters, run


def ts_srt(t, sep=","):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02}{sep}{ms:03}"


def ts_ass(t):
    cs = int(round(t * 100)); h, cs = divmod(cs, 360000); m, cs = divmod(cs, 6000); s, cs = divmod(cs, 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


def chunk_tokens(tokens, max_words):
    """Caption lines: break at punctuation or max length; merge tiny tails."""
    out, cur = [], []
    for w in tokens:
        cur.append(w)
        if len(cur) >= max_words or re.search(r"[.,!?;:]$", w["text"]):
            out.append(cur); cur = []
    if cur: out.append(cur)
    merged = []
    for c in out:
        if merged and len(c) <= 2 and len(merged[-1]) + len(c) <= max_words + 2: merged[-1] += c
        else: merged.append(c)
    return merged


def find_sync(ff, video, seconds=40, rate=50):
    """Time (s) in the raw video where the magenta sync flash first appears."""
    r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-t", str(seconds), "-i", str(video), "-an",
                        "-vf", f"fps={rate},scale=16:9,format=rgb24", "-f", "rawvideo", "-"], capture_output=True)
    n = 16 * 9 * 3
    for i in range(len(r.stdout) // n):
        f = r.stdout[i * n:(i + 1) * n]
        R, G, B = (sum(f[c::3]) / (16 * 9) for c in range(3))
        if R > 200 and G < 80 and B > 200:
            return i / rate
    return None


FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\segoeuib.ttf", "Segoe UI"), (r"C:\Windows\Fonts\arialbd.ttf", "Arial"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVu Sans"),
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "Arial"),
]


def pick_font(ws):
    cap = ws.plan["captions"]
    if cap.get("font_file"):
        return ws.resolve(cap["font_file"]), cap.get("font") or Path(cap["font_file"]).stem
    for path, fam in FONT_CANDIDATES:
        if Path(path).exists():
            return Path(path), cap.get("font") or fam
    return None, cap.get("font") or "Arial"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--plan", required=True)
    ws = Workspace(ap.parse_args().plan)
    p = ws.plan; v, cap, tm = p["video"], p["captions"], p["timing"]
    ff = find_tool("ffmpeg")
    if not ff: raise SystemExit("ffmpeg not found (run preflight.py)")
    tl_path = ws.work / "timeline.json"
    if not tl_path.exists(): raise SystemExit("timeline.json missing - record first (a failed recording writes none)")
    tl = json.loads(tl_path.read_text(encoding="utf-8"))
    tts = {e["id"]: e for e in json.loads((ws.work / "tts.json").read_text(encoding="utf-8"))}
    video = tl["video"]; segs = {s["id"]: s for s in tl["timeline"]}
    missing = [s["id"] for s in ws.scenes if s["id"] not in segs and not s.get("optional")]
    if missing: raise SystemExit(f"scenes not recorded: {missing}")

    sync = find_sync(ff, video) if tl.get("sync_t") is not None else None
    delta = (sync - tl["sync_t"]) if sync is not None else 0.0
    print("video/clock offset: %+.2fs%s" % (delta, "" if sync is not None else "  (no sync marker found - assuming 0)"))
    if abs(delta) > 1.5: print("warning: large offset; check that the recording and timeline.json belong together")

    plan, cursor = [], 0.0
    for sc in ws.scenes:
        if sc["id"] not in segs: continue
        s = segs[sc["id"]]; raw = s["t1"] - s["t0"]; D = tts.get(sc["id"], {}).get("duration", 0.0)
        speed = 1.0
        if sc.get("speed_up_to"):
            target = max(float(sc["speed_up_to"]), D + tm["lead"] + tm["tail"] if D else 0)
            if raw > target: speed = raw / target
        out_len = raw / speed
        plan.append({"id": sc["id"], "t0": s["t0"], "raw": raw, "speed": speed, "out_start": cursor, "out_len": out_len, "narration": D})
        cursor += out_len
    total = cursor
    print("output length: %.1fs" % total, "; sped up:", {q["id"]: round(q["speed"], 1) for q in plan if q["speed"] > 1} or "none")

    # captions on the final timeline
    cues = []
    for q in plan:
        toks = tts.get(q["id"], {}).get("tokens") or []
        for c in chunk_tokens(toks, cap["max_words"]):
            cues.append([q["out_start"] + tm["lead"] + c[0]["start"], q["out_start"] + tm["lead"] + c[-1]["end"] + 0.12,
                         " ".join(w["text"] for w in c)])
    for i in range(len(cues) - 1):
        cues[i][1] = min(cues[i][1], cues[i + 1][0] - 0.02)
    ws.out.mkdir(parents=True, exist_ok=True)
    base = ws.out / p["basename"]
    if "srt" in cap["formats"]:
        base.with_suffix(".srt").write_text("\n".join(f"{i}\n{ts_srt(a)} --> {ts_srt(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1)), encoding="utf-8")
    if "vtt" in cap["formats"]:
        base.with_suffix(".vtt").write_text("WEBVTT\n\n" + "\n".join(f"{ts_srt(a, '.')} --> {ts_srt(b, '.')}\n{t}\n" for a, b, t in cues), encoding="utf-8")

    font_file, family = pick_font(ws)
    burn = cap["burn_in"] and cues
    if burn and " subtitles " not in ff_filters(ff):
        print("warning: this ffmpeg lacks libass 'subtitles' - captions NOT burned in (SRT/VTT still written)")
        burn = False
    if burn:
        ws.work.mkdir(exist_ok=True); fonts = ws.work / "fonts"; fonts.mkdir(exist_ok=True)
        if font_file: shutil.copy(font_file, fonts / Path(font_file).name)
        sz = int(cap["size"] * v["height"] / 1080)
        ass = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {v['width']}", f"PlayResY: {v['height']}", "WrapStyle: 2", "",
               "[V4+ Styles]",
               "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
               f"Style: Cap,{family},{sz},&H00FFFFFF,&H00FFFFFF,&H00241B18,&HB0241B18,-1,0,0,0,100,100,0,0,3,16,0,2,{int(v['width']*0.0625)},{int(v['width']*0.0625)},{int(v['height']*0.06)},1", "",
               "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
        ass += [f"Dialogue: 0,{ts_ass(a)},{ts_ass(b)},Cap,,0,0,0,,{t}" for a, b, t in cues]
        (ws.work / "captions.ass").write_text("\n".join(ass), encoding="utf-8")

    # 1) cut scenes
    segdir = ws.work / "segments"; shutil.rmtree(segdir, ignore_errors=True); segdir.mkdir(parents=True)
    lst = []
    for k, q in enumerate(plan):
        seg = segdir / f"s{k:02}.mp4"
        vf = (f"fps={v['fps']},setpts={1/q['speed']:.6f}*(PTS-STARTPTS),scale={v['width']}:{v['height']}:force_original_aspect_ratio=decrease,"
              f"pad={v['width']}:{v['height']}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")
        r = run([ff, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, q['t0'] + delta):.3f}", "-t", f"{q['raw']:.3f}",
                 "-i", str(video), "-an", "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-r", str(v["fps"]), str(seg)])
        if r.returncode: print(r.stderr[-1500:]); raise SystemExit(f"cutting scene {q['id']} failed")
        lst.append(f"file 'segments/{seg.name}'")
    (ws.work / "segments.txt").write_text("\n".join(lst), encoding="utf-8")
    r = run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "segments.txt", "-c", "copy", "video_all.mp4"], cwd=ws.work)
    if r.returncode: print(r.stderr[-1500:]); raise SystemExit("concat failed")

    # 2) final pass
    inputs, parts, labels = ["-i", str(ws.work / "video_all.mp4")], [], []
    idx = 1
    for k, q in enumerate(plan):
        f = tts.get(q["id"], {}).get("file")
        if f:
            inputs += ["-i", str(f)]
            parts.append(f"[{idx}:a]aresample=48000,adelay={int(tm['lead']*1000)},apad=whole_dur={q['out_len']:.3f},atrim=0:{q['out_len']:.3f},asetpts=PTS-STARTPTS[a{k}]")
            idx += 1
        else:
            parts.append(f"anullsrc=r=48000:cl=mono,atrim=0:{q['out_len']:.3f},asetpts=PTS-STARTPTS[a{k}]")
        labels.append(f"[a{k}]")
    parts.append("".join(labels) + f"concat=n={len(plan)}:v=0:a=1[ac]")
    music = p.get("music")
    if music:
        mf = ws.resolve(music["file"])
        if not mf.exists(): raise SystemExit(f"music file not found: {mf}")
        inputs += ["-stream_loop", "-1", "-i", str(mf)]
        parts.append(f"[{idx}:a]aresample=48000,volume={music.get('volume', 0.08)},atrim=0:{total:.3f},asetpts=PTS-STARTPTS[mu]")
        parts.append("[ac][mu]amix=inputs=2:duration=first:dropout_transition=0,volume=2[am]")
        amain = "[am]"
    else:
        amain = "[ac]"
    vf = "subtitles=captions.ass:fontsdir=fonts," if burn else ""
    parts.append(f"[0:v]{vf}fade=t=in:st=0:d={tm['fade_in']},fade=t=out:st={max(0, total-tm['fade_out']):.2f}:d={tm['fade_out']}[vout]")
    parts.append(f"{amain}afade=t=in:st=0:d=0.3,afade=t=out:st={max(0, total-0.8):.2f}:d=0.8[aout]")
    (ws.work / "filter.txt").write_text(";\n".join(parts), encoding="utf-8")
    final = base.with_suffix(".mp4")
    r = run([ff, "-y", "-hide_banner", *inputs, "-filter_complex_script", "filter.txt", "-map", "[vout]", "-map", "[aout]",
             "-c:v", "libx264", "-preset", v["preset"], "-crf", str(v["crf"]), "-pix_fmt", "yuv420p", "-r", str(v["fps"]),
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)], cwd=ws.work)
    if r.returncode: print(r.stderr[-3000:]); raise SystemExit("final encode failed")

    # script + report
    md = [f"# {p['title']}", "", f"Language: {p['language']}  |  Voice: {p['tts']['voice']}  |  Length: {total:.1f}s", ""]
    for i, (sc, q) in enumerate(((s, q) for s in ws.scenes for q in plan if q['id'] == s['id']), 1):
        md += [f"## {i}. {sc.get('title', sc['id'])}  ({q['out_start']:.1f}s - {q['out_start']+q['out_len']:.1f}s)"]
        for key in ("purpose", "actions", "expected_state"):
            if sc.get(key): md.append(f"- **{key.replace('_', ' ').title()}:** {sc[key]}")
        if sc.get("narration"): md.append(f"- **Narration:** {sc['narration']}")
        md.append("")
    base.with_suffix(".script.md").write_text("\n".join(md), encoding="utf-8")
    (ws.work / "assemble_report.json").write_text(json.dumps(
        {"final": str(final), "total": total, "burned_captions": bool(burn), "offset": delta,
         "scenes": plan, "cues": [{"start": a, "end": b, "text": t} for a, b, t in cues]}, indent=1), encoding="utf-8")
    print("wrote", final)


if __name__ == "__main__":
    main()
